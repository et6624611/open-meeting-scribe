"""
core/sms.py — 阿里云短信认证服务 (PNVS) 封装

职责：
  1. 调用 SendSmsVerifyCode 发送验证码短信
  2. 调用 CheckSmsVerifyCode 核验用户输入的验证码
  3. 本地频率限制（60 秒冷却 + 每天 10 次上限）

设计：
  - 验证码由阿里云 PNVS 全权托管（生成、发送、有效期、核验）
  - 频率限制用内存字典，与 _oauth_states 同一模式（单实例够用）
  - SDK 调用为同步阻塞，路由层用 def（FastAPI 自动线程池化）
"""

import os
import re
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

ALI_ACCESS_KEY_ID = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
ALI_ACCESS_KEY_SECRET = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
SMS_SIGN_NAME = os.getenv("SMS_SIGN_NAME", "恒创联众")
SMS_TEMPLATE_CODE = os.getenv("SMS_TEMPLATE_CODE", "100001")

# 验证码有效期（分钟）；注意 PNVS 的 ValidTime 单位是「秒」，下发时需 ×60
SMS_EXPIRE_MINUTES = 5

# 短信模板参数（JSON 字符串，TemplateParam 必填）：
#   - 缺失 → 报 MissingTemplateParam
#   - 变量名/个数须与赠送模板内容完全一致 → 否则报「请检查模板内容与模板参数是否匹配」
# 默认适配 PNVS 赠送模板 100001（内容形如「您的验证码是${code}，有效期${min}分钟，请勿告诉他人」）：
#   - code 用占位符 ##code##，由 PNVS 动态生成并托管，CheckSmsVerifyCode 方可核验
#   - min 与 SMS_EXPIRE_MINUTES 保持一致
# 若你的模板变量名不同（如 ${number}）或没有 ${min}，在 .env 覆盖 SMS_TEMPLATE_PARAM。
SMS_TEMPLATE_PARAM = os.getenv(
    "SMS_TEMPLATE_PARAM",
    '{"code":"##code##","min":"%d"}' % SMS_EXPIRE_MINUTES,
)

# 验证码生成规则（传入 ##code## 占位符时 CodeType 必填）：1=纯数字，详见 PNVS 文档
SMS_CODE_TYPE = int(os.getenv("SMS_CODE_TYPE", "1"))
# 验证码长度：4~8 位，默认 6 位（与前端输入框 maxlength 一致）
SMS_CODE_LENGTH = int(os.getenv("SMS_CODE_LENGTH", "6"))

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
        return False, f"请等待 {remaining} 秒后再试"

    # 每日上限检查
    if len(records) >= SMS_DAILY_MAX:
        return False, "今日发送次数已达上限，请明天再试"

    return True, ""


def _record_send(phone: str) -> None:
    """记录一次发送（更新频率限制字典）"""
    _sms_rate_limits.setdefault(phone, []).append(time.time())


def _get_pnvs_client():
    """懒加载 PNVS SDK 客户端（避免启动时 import 失败）"""
    from alibabacloud_dypnsapi20170525.client import Client as DypnsapiClient
    from alibabacloud_tea_openapi.models import Config

    if not ALI_ACCESS_KEY_ID or not ALI_ACCESS_KEY_SECRET:
        raise RuntimeError("未配置 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET")

    config = Config(
        access_key_id=ALI_ACCESS_KEY_ID,
        access_key_secret=ALI_ACCESS_KEY_SECRET,
        endpoint="dypnsapi.aliyuncs.com",
    )
    return DypnsapiClient(config)


def send_verify_code(phone: str) -> dict:
    """
    调用 PNVS SendSmsVerifyCode 发送验证码短信。

    Args:
        phone: 国内 11 位手机号

    Returns:
        {"success": True, "expire_minutes": 5}
        或抛出 RuntimeError（发送失败时）
    """
    from alibabacloud_dypnsapi20170525.models import SendSmsVerifyCodeRequest

    client = _get_pnvs_client()
    out_id = f"oms_{int(time.time())}"

    try:
        request = SendSmsVerifyCodeRequest(
            phone_number=phone,
            sign_name=SMS_SIGN_NAME,
            template_code=SMS_TEMPLATE_CODE,
            template_param=SMS_TEMPLATE_PARAM,   # 必填，否则报 MissingTemplateParam
            code_type=SMS_CODE_TYPE,             # 传 ##code## 占位符时必填（1=纯数字）
            code_length=SMS_CODE_LENGTH,
            valid_time=SMS_EXPIRE_MINUTES * 60,  # ValidTime 单位是秒（默认 300），不是分钟
            out_id=out_id,
        )
        response = client.send_sms_verify_code(request)
        body = response.body
        code = getattr(body, "code", "") or ""
        message = getattr(body, "message", "") or ""

        if code != "OK":
            logger.error(f"PNVS 发送失败: code={code}, message={message}, phone={phone[:3]}****{phone[-4:]}")
            # 模板参数不匹配时给出可操作提示：模板变量名/个数须与控制台赠送模板一致
            hint = ""
            if "模板" in message or "TEMPLATE" in code.upper():
                hint = (
                    f"（当前 TemplateParam={SMS_TEMPLATE_PARAM}；请核对控制台赠送模板 "
                    f"{SMS_TEMPLATE_CODE} 的变量名与个数，必要时在 .env 覆盖 SMS_TEMPLATE_PARAM）"
                )
            raise RuntimeError(f"短信发送失败: {message or code}{hint}")

        _record_send(phone)
        logger.info(f"验证码已发送: phone={phone[:3]}****{phone[-4:]}")
        return {"success": True, "expire_minutes": SMS_EXPIRE_MINUTES}

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"PNVS API 调用异常: {e}")
        raise RuntimeError(f"短信服务异常: {e}")


def check_verify_code(phone: str, code: str) -> tuple[bool, str]:
    """
    调用 PNVS CheckSmsVerifyCode 核验验证码。

    Args:
        phone: 手机号
        code: 用户输入的验证码

    Returns:
        (是否通过, 原因说明)
    """
    from alibabacloud_dypnsapi20170525.models import CheckSmsVerifyCodeRequest

    client = _get_pnvs_client()

    request = CheckSmsVerifyCodeRequest(
        phone_number=phone,
        verify_code=code,
    )

    try:
        response = client.check_sms_verify_code(request)
        body = response.body
        api_code = getattr(body, "code", "") or ""
        message = getattr(body, "message", "") or ""

        # 接口请求本身失败（非 OK）→ 视为服务异常
        if api_code != "OK":
            logger.warning(f"PNVS 核验接口错误: code={api_code}, message={message}")
            return False, "验证服务异常，请稍后重试"

        # 核验结果只以 Model.VerifyResult 为准：PASS=通过，UNKNOWN=失败。
        # 官方明确：Code=OK / Success=true 仅代表请求成功，不代表核验通过；
        # 旧代码误读 body.pass_/body.Pass（字段不存在）导致恒判失败。
        model = getattr(body, "model", None)
        verify_result = (getattr(model, "verify_result", "") or "") if model else ""

        if verify_result == "PASS":
            logger.info(f"验证码核验通过: phone={phone[:3]}****{phone[-4:]}")
            return True, ""
        else:
            logger.info(f"验证码核验失败: phone={phone[:3]}****{phone[-4:]}, verify_result={verify_result!r}")
            return False, "验证码错误或已过期"

    except Exception as e:
        logger.error(f"PNVS 核验 API 调用异常: {e}")
        return False, "验证服务异常，请稍后重试"
