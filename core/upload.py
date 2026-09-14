"""
core/upload.py — 本地文件 → DashScope 临时存储 → oss:// 临时 URL / Local file → DashScope temp storage → oss:// temporary URL

⚠️ 注意 / Note：主管线已改为通过 ASR 代理上传（core/transcribe.py 直接发送文件到代理） / Main pipeline now uploads via ASR proxy (core/transcribe.py sends file directly to proxy),
本模块仅保留给 CLI 测试命令使用 / This module retained only for CLI test commands. 正常转写流程不再调用此模块 / Normal transcription flow no longer calls this module.

职责 / Responsibilities:
  1. 获取上传凭证（getPolicy） / Get upload credential (getPolicy)
  2. POST 上传到 OSS / POST upload to OSS
  3. 返回 oss:// 临时 URL（≤1GB / 48h 有效） / Return oss:// temporary URL (≤1GB / 48h valid)

硬约束（详见 docs/API_CONTRACTS.md §1） / Hard constraints (see docs/API_CONTRACTS.md §1):
  - 转写 API 只认公网 URL，本地文件必须先上传 / Transcription API only accepts public URLs; local files must be uploaded first
  - 上传凭证接口限流 100 QPS / Upload credential API rate limited to 100 QPS
"""

import logging
from pathlib import Path
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com"


def _get_api_key() -> str:
    """从设置或环境变量读取 ASR API Key / Read ASR API Key from settings or environment."""
    from app.store import get_asr_config
    key = get_asr_config()["api_key"]
    if not key:
        raise RuntimeError("未设置 ASR API Key，请在设置页面配置语音转写服务或通过 .env 配置 DASHSCOPE_API_KEY")
    return key


def get_upload_policy(model: str = "paraformer-v2") -> dict:
    """
    获取上传凭证 / Get upload credential.

    Returns:
        dict: {
            upload_host, upload_dir, oss_access_key_id,
            policy, signature, x_oss_object_acl, x_oss_forbid_overwrite
        }
    """
    api_key = _get_api_key()
    url = f"{DASHSCOPE_BASE}/api/v1/uploads"
    params = {"action": "getPolicy", "model": model}
    headers = {"Authorization": f"Bearer {api_key}"}

    logger.debug(f"获取上传凭证: model={model}")
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    if "data" not in data:
        raise RuntimeError(f"获取上传凭证失败: {data}")

    return data["data"]


def upload_file(
    file_path: str | Path,
    model: str = "paraformer-v2",
) -> str:
    """
    上传本地文件到 DashScope 临时存储，返回 oss:// URL / Upload local file to DashScope temp storage; return oss:// URL.

    Args:
        file_path: 本地文件路径 / Local file path
        model: 模型名（凭证与模型绑定） / Model name (credential bound to model)

    Returns:
        oss:// 临时 URL（48h 有效） / oss:// temporary URL (48h valid)

    Raises:
        FileNotFoundError: 文件不存在 / File not found
        RuntimeError: 上传失败或文件超限（>1GB） / Upload failed or file exceeds limit (>1GB)
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    file_size = file_path.stat().st_size
    if file_size > 1024 * 1024 * 1024:  # 1GB
        raise RuntimeError(f"文件过大: {file_size / 1024 / 1024:.0f}MB > 1GB 上限")

    logger.info(f"上传文件: {file_path.name} ({file_size / 1024 / 1024:.1f} MB)")

    # 1. 获取上传凭证 / Get upload credential
    policy = get_upload_policy(model)
    upload_host = policy["upload_host"]
    upload_dir = policy["upload_dir"]

    # 2. 构造 OSS key（文件与模型名+主账号绑定） / Construct OSS key (file + model name + account binding)
    oss_key = f"{upload_dir}/{file_path.name}"

    # 3. POST 上传到 OSS（multipart） / POST upload to OSS (multipart)
    form_data = {
        "key": oss_key,
        "OSSAccessKeyId": policy["oss_access_key_id"],
        "policy": policy["policy"],
        "Signature": policy["signature"],
        "x-oss-object-acl": policy["x_oss_object_acl"],
        "x-oss-forbid-overwrite": policy["x_oss_forbid_overwrite"],
        "success_action_status": "200",
    }

    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f)}
        resp = requests.post(upload_host, data=form_data, files=files, timeout=600)

    if resp.status_code != 200:
        raise RuntimeError(f"上传失败: HTTP {resp.status_code} — {resp.text}")

    oss_url = f"oss://{oss_key}"
    logger.info(f"上传成功: {oss_url}")
    return oss_url


def encode_oss_url(oss_url: str) -> str:
    """
    对 oss:// URL 进行编码（含空格/中文时必须） / Encode oss:// URL (required for spaces/Chinese characters).

    DashScope 要求 URL 中的特殊字符必须 URL 编码 / DashScope requires URL encoding of special characters,
    否则报 InvalidFile.DownloadFailed / otherwise InvalidFile.DownloadFailed error.
    """
    # oss://bucket/path/filename → 只编码路径部分 / Only encode path portion
    prefix = "oss://"
    if oss_url.startswith(prefix):
        path = oss_url[len(prefix):]
        # 按 / 分割，逐段编码 / Split by / and encode each segment
        parts = path.split("/")
        encoded_parts = [quote(p, safe="") for p in parts]
        return prefix + "/".join(encoded_parts)
    return oss_url
