"""安全原语：口令哈希、邀请码/设备 token（服务端只存 hash，明文仅一次返回）。

裁决口径（cmsg_01m63fn448vz5fta7ahrggq9rk #1/插单③）：管理员建号只产生 pending 用户 +
邀请码，密码全程由用户凭邀请码自助设置——**无初始密码下发环节**。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 240_000  # OWASP 2024+ 量级，纯 stdlib（不新增依赖）


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2-sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2-sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
    return hmac.compare_digest(dk.hex(), hash_hex)


def generate_secret_code(nbytes: int = 16) -> str:
    """邀请码/配对码/设备 token 明文（一次性展示，服务端不落明文）。"""
    return secrets.token_urlsafe(nbytes)


def hash_secret(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
