"""
SMS 代理服务 — 持有阿里云 AccessKey，为客户端提供短信发送/核验中转

部署位置：云端服务器（通过环境变量配置）
职责：
  1. 接收客户端 SMS 请求（POST /sms/send、/sms/verify）
  2. 校验 HMAC-SHA256 签名（防未授权调用 + 防重放）
  3. 调用阿里云 PNVS SDK 执行实际短信操作

安全机制：
  - 客户端请求须携带 X-SMS-Timestamp 和 X-SMS-Sign 头
  - 签名 = HMAC-SHA256(token, timestamp)，token 为共享密钥
  - timestamp 超过 TTL（默认 5 分钟）视为过期拒绝
"""

import hashlib
import hmac
import logging
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 加载 .env 配置
load_dotenv()

# ============================================================
# 日志
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
# 配置（从 .env 读取，密钥不落地客户端）
# ============================================================

# 共享密钥（与客户端 SMS_PROXY_TOKEN 一致）
SMS_PROXY_TOKEN = os.getenv("SMS_PROXY_TOKEN", "")

# 签名有效期（秒），防重放
SMS_SIGN_TTL = int(os.getenv("SMS_SIGN_TTL", "300"))

# 阿里云 PNVS 配置
ALI_ACCESS_KEY_ID = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
ALI_ACCESS_KEY_SECRET = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
SMS_SIGN_NAME = os.getenv("SMS_SIGN_NAME", "恒创联众")
SMS_TEMPLATE_CODE = os.getenv("SMS_TEMPLATE_CODE", "100001")
SMS_EXPIRE_MINUTES = int(os.getenv("SMS_EXPIRE_MINUTES", "5"))
SMS_TEMPLATE_PARAM = os.getenv(
    "SMS_TEMPLATE_PARAM",
    '{"code":"##code##","min":"%d"}' % SMS_EXPIRE_MINUTES,
)
SMS_CODE_TYPE = int(os.getenv("SMS_CODE_TYPE", "1"))
SMS_CODE_LENGTH = int(os.getenv("SMS_CODE_LENGTH", "6"))

# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(title="SMS Proxy", version="1.0.0")


# ============================================================
# 签名校验
# ============================================================

def verify_signature(timestamp: str, sign: str) -> bool:
    """
    校验请求签名。

    Args:
        timestamp: 请求时间戳（Unix 秒）
        sign: 客户端签名（HMAC-SHA256(token, timestamp)）

    Returns:
        校验通过返回 True，否则 False
    """
    if not SMS_PROXY_TOKEN:
        logger.error("SMS_PROXY_TOKEN 未配置")
        return False

    # 检查时间戳是否过期
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False

    now = int(time.time())
    if abs(now - ts) > SMS_SIGN_TTL:
        logger.warning(f"签名过期: timestamp={timestamp}, now={now}, ttl={SMS_SIGN_TTL}")
        return False

    # 计算期望签名
    expected = hmac.new(
        SMS_PROXY_TOKEN.encode(),
        timestamp.encode(),
        hashlib.sha256,
    ).hexdigest()

    # 常量时间比较，防时序攻击
    return hmac.compare_digest(sign, expected)


def check_auth(request: Request) -> None:
    """从请求头提取并校验签名，失败时抛出 HTTPException"""
    timestamp = request.headers.get("X-SMS-Timestamp", "")
    sign = request.headers.get("X-SMS-Sign", "")

    if not timestamp or not sign:
        raise HTTPException(401, "缺少签名头 X-SMS-Timestamp / X-SMS-Sign")

    if not verify_signature(timestamp, sign):
        raise HTTPException(401, "签名校验失败")


# ============================================================
# PNVS 客户端
# ============================================================

def get_pnvs_client():
    """懒加载 PNVS SDK 客户端"""
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


# ============================================================
# 请求模型
# ============================================================

class SmsSendRequest(BaseModel):
    phone: str = Field(..., description="国内 11 位手机号")


class SmsVerifyRequest(BaseModel):
    phone: str = Field(..., description="国内 11 位手机号")
    code: str = Field(..., description="用户输入的验证码")


# ============================================================
# 端点
# ============================================================

@app.post("/sms/send")
def sms_send(req: SmsSendRequest, request: Request):
    """
    发送验证码短信。

    流程：
    1. 校验签名
    2. 调用 PNVS SendSmsVerifyCode
    3. 返回 {"success": true, "expire_minutes": 5}
    """
    check_auth(request)

    from alibabacloud_dypnsapi20170525.models import SendSmsVerifyCodeRequest

    client = get_pnvs_client()
    out_id = f"oms_proxy_{int(time.time())}"

    try:
        sms_request = SendSmsVerifyCodeRequest(
            phone_number=req.phone,
            sign_name=SMS_SIGN_NAME,
            template_code=SMS_TEMPLATE_CODE,
            template_param=SMS_TEMPLATE_PARAM,
            code_type=SMS_CODE_TYPE,
            code_length=SMS_CODE_LENGTH,
            valid_time=SMS_EXPIRE_MINUTES * 60,
            out_id=out_id,
        )
        response = client.send_sms_verify_code(sms_request)
        body = response.body
        code = getattr(body, "code", "") or ""
        message = getattr(body, "message", "") or ""

        if code != "OK":
            logger.error(f"PNVS 发送失败: code={code}, message={message}, phone={req.phone[:3]}****{req.phone[-4:]}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": message or code},
            )

        logger.info(f"验证码已发送: phone={req.phone[:3]}****{req.phone[-4:]}")
        return {"success": True, "expire_minutes": SMS_EXPIRE_MINUTES}

    except Exception as e:
        logger.error(f"PNVS API 调用异常: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"短信服务异常: {e}"},
        )


@app.post("/sms/verify")
def sms_verify(req: SmsVerifyRequest, request: Request):
    """
    核验验证码。

    流程：
    1. 校验签名
    2. 调用 PNVS CheckSmsVerifyCode
    3. 返回 {"success": true/false, "message": "..."}
    """
    check_auth(request)

    from alibabacloud_dypnsapi20170525.models import CheckSmsVerifyCodeRequest

    client = get_pnvs_client()

    try:
        sms_request = CheckSmsVerifyCodeRequest(
            phone_number=req.phone,
            verify_code=req.code,
        )
        response = client.check_sms_verify_code(sms_request)
        body = response.body
        api_code = getattr(body, "code", "") or ""
        message = getattr(body, "message", "") or ""

        if api_code != "OK":
            logger.warning(f"PNVS 核验接口错误: code={api_code}, message={message}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "验证服务异常，请稍后重试"},
            )

        model = getattr(body, "model", None)
        verify_result = (getattr(model, "verify_result", "") or "") if model else ""

        if verify_result == "PASS":
            logger.info(f"验证码核验通过: phone={req.phone[:3]}****{req.phone[-4:]}")
            return {"success": True}
        else:
            logger.info(f"验证码核验失败: phone={req.phone[:3]}****{req.phone[-4:]}, verify_result={verify_result!r}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "验证码错误或已过期"},
            )

    except Exception as e:
        err = str(e)
        # 阿里云以异常形式抛出 isv.ValidateFail（HTTP 400）：表示验证码错误/已过期/已被使用，
        # 属于核验失败而非服务异常，需映射为 400，避免客户端误报"验证服务异常"
        if "isv.ValidateFail" in err:
            logger.info(f"验证码核验失败(ValidateFail): phone={req.phone[:3]}****{req.phone[-4:]}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "验证码错误或已过期"},
            )
        logger.error(f"PNVS 核验 API 调用异常: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"验证服务异常: {e}"},
        )


@app.get("/health")
def health():
    """健康检查端点"""
    return {"status": "ok", "service": "sms-proxy"}


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn

    # 检查必要配置
    if not SMS_PROXY_TOKEN:
        logger.error("SMS_PROXY_TOKEN 未配置，服务拒绝启动")
        exit(1)

    if not ALI_ACCESS_KEY_ID or not ALI_ACCESS_KEY_SECRET:
        logger.error("ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET 未配置")
        exit(1)

    logger.info("SMS 代理服务启动中...")
    uvicorn.run(app, host="0.0.0.0", port=8080)
