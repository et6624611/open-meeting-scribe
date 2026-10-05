"""
core/sms.py — 短信认证服务（云端代理模式）

职责：
  1. 通过云端 SMS 代理发送验证码短信
  2. 通过云端 SMS 代理核验用户输入的验证码
  3. 本地频率限制（60 秒冷却 + 每天 10 次上限）

设计：
  - 阿里云 AccessKey 不落地客户端，由云端代理持有
  - 客户端通过 HTTP + 共享密钥（SMS_PROXY_TOKEN）调用代理端点
  - 代理负责调用阿里云 PNVS SDK（SendSmsVerifyCode / CheckSmsVerifyCode）
  - 验证码由阿里云 PNVS 全权托管（生成、发送、有效期、核验）
  - 频率限制用内存字典，与 _oauth_states 同一模式（单实例够用）
"""

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request

from core.i18n import _

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# 云端 SMS 代理地址（代理持有阿里云 AccessKey，密钥不落地）
# 必须通过 .env 或桌面端 desktop-secrets.env 配置；未配置时短信功能不可用
SMS_PROXY_URL = os.getenv("SMS_PROXY_URL", "").rstrip("/")

# 代理共享密钥（用于请求签名，防止未授权调用）
# 必须与 SMS 代理服务器持有相同密钥；未配置时短信功能不可用
SMS_PROXY_TOKEN = os.getenv("SMS_PROXY_TOKEN", "")

# 签名有效期（秒），防重放
SMS_SIGN_TTL = 300

# 验证码有效期（分钟）
SMS_EXPIRE_MINUTES = 5

# 手机号正则：国内 11 位，1[3-9] 开头
PHONE_REGEX = re.compile(r"^1[3-9]\d{9}$")

# ============================================================
# 频率限制（内存字典，单实例够用）
# ============================================================

# {phone: [timestamp1, timestamp2, ...]}
_sms_rate_limits: dict[str, list[float]] = {}

SMS_COOLDOWN_SECONDS = 60   # 同一号码两次发送最小间隔
SMS_DAILY_MAX = 10          # 同一号码每天最多发送次数


def validate_phone(phone: str) -> bool:
    """校验手机号格式（国内 11 位）"""
    return bool(PHONE_REGEX.match(phone))


def can_send(phone: str) -> tuple[bool, str]:
    """
    检查频率限制。

    Returns:
        (是否允许发送, 拒绝原因)
    """
    now = time.time()
    records = _sms_rate_limits.get(phone, [])

    # 清理 24 小时前的记录
    day_ago = now - 86400
    records = [t for t in records if t > day_ago]
    _sms_rate_limits[phone] = records

    if not records:
        return True, ""

    # 冷却时间检查
    last_send = records[-1]
    elapsed = now - last_send
    if elapsed < SMS_COOLDOWN_SECONDS:
        remaining = int(SMS_COOLDOWN_SECONDS - elapsed)
        return False, _("Please wait {seconds} seconds before trying again").format(seconds=remaining)

    # 每日上限检查
    if len(records) >= SMS_DAILY_MAX:
        return False, _("Daily send limit reached, please try again tomorrow")

    return True, ""


def _record_send(phone: str) -> None:
    """记录一次发送（更新频率限制字典）"""
    _sms_rate_limits.setdefault(phone, []).append(time.time())


# ============================================================
# 代理通信
# ============================================================

def _make_sign(timestamp: str) -> str:
    """
    生成请求签名：HMAC-SHA256(token, timestamp)。
    代理端用相同 token + timestamp 校验，timestamp 超过 TTL 视为过期。
    """
    if not SMS_PROXY_TOKEN:
        raise RuntimeError(
            "未配置 SMS_PROXY_TOKEN，无法调用短信代理。\n"
            "请在 .env 文件中配置以下两项：\n"
            "  1. SMS_PROXY_URL — 短信代理服务地址（如 https://sms.yourdomain.com）\n"
            "  2. SMS_PROXY_TOKEN — 共享密钥（与 sms-proxy 服务端配置相同）\n"
            "详见：sms-proxy/README.md"
        )
    return hmac.new(
        SMS_PROXY_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()


def _proxy_request(path: str, payload: dict) -> dict:
    """
    向 SMS 代理发送 POST 请求。

    Args:
        path: 代理端点路径（如 /sms/send）
        payload: 请求体（JSON）

    Returns:
        代理返回的 JSON dict
    """
    url = f"{SMS_PROXY_URL}{path}"
    timestamp = str(int(time.time()))
    sign = _make_sign(timestamp)

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-SMS-Timestamp": timestamp,
            "X-SMS-Sign": sign,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data
    except urllib.error.HTTPError as e:
        # 读取错误响应体
        try:
            err_body = json.loads(e.read().decode())
        except Exception:
            err_body = None
        msg = (err_body or {}).get("message", f"HTTP {e.code}")
        # 4xx 为业务失败（如验证码错误/已过期），透传响应体交由调用方判读；
        # 5xx 为服务异常，抛错以免被误判为核验不通过
        if 400 <= e.code < 500 and err_body is not None and "success" in err_body:
            logger.info(f"SMS 代理业务失败: {path} → {msg}")
            return err_body
        logger.error(f"SMS 代理请求失败: {path} → {msg}")
        raise RuntimeError(f"短信代理返回错误: {msg}")
    except urllib.error.URLError as e:
        logger.error(f"SMS 代理连接失败: {path} → {e.reason}")
        raise RuntimeError(f"短信代理连接失败: {e.reason}")
    except Exception as e:
        logger.error(f"SMS 代理请求异常: {path} → {e}")
        raise RuntimeError(f"短信服务异常: {e}")


def send_verify_code(phone: str) -> dict:
    """
    通过云端代理发送验证码短信。

    Args:
        phone: 国内 11 位手机号

    Returns:
        {"success": True, "expire_minutes": 5}
        或抛出 RuntimeError（发送失败时）
    """
    result = _proxy_request("/sms/send", {"phone": phone})

    if not result.get("success"):
        msg = result.get("message", "发送失败")
        logger.error(f"代理发送失败: phone={phone[:3]}****{phone[-4:]}, message={msg}")
        raise RuntimeError(f"短信发送失败: {msg}")

    _record_send(phone)
    logger.info(f"验证码已发送: phone={phone[:3]}****{phone[-4:]}")
    return {
        "success": True,
        "expire_minutes": result.get("expire_minutes", SMS_EXPIRE_MINUTES),
    }


def check_verify_code(phone: str, code: str) -> tuple[bool, str]:
    """
    通过云端代理核验验证码。

    Args:
        phone: 手机号
        code: 用户输入的验证码

    Returns:
        (是否通过, 原因说明)
    """
    try:
        result = _proxy_request("/sms/verify", {"phone": phone, "code": code})
    except RuntimeError:
        return False, "验证服务异常，请稍后重试"

    if result.get("success"):
        logger.info(f"验证码核验通过: phone={phone[:3]}****{phone[-4:]}")
        return True, ""
    else:
        msg = result.get("message", "验证码错误或已过期")
        logger.info(f"验证码核验失败: phone={phone[:3]}****{phone[-4:]}, message={msg}")
        return False, msg
