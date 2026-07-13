"""对称加密 Jira 密码（存储用）+ 会话 cookie 签发。

密钥来源（依次）：
1. 环境变量 GOALPLATFORM_SECRET_KEY（设了就用它，多副本部署时建议固定一个）
2. 密钥文件（GOALPLATFORM_SECRET_KEY_FILE 或 backend/.secret_key，兼容老部署/本地）
3. 数据库 app_setting.secret_key —— 都没有就自动生成并落库，零配置、容器无状态

Jira 密码永不明文出库，也永不出现在任何 GET 响应里。
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from cryptography.fernet import Fernet

_KEY_FILE = Path(os.environ.get("GOALPLATFORM_SECRET_KEY_FILE") or (Path(__file__).parent / ".secret_key"))

_fernet: Fernet | None = None


def _resolve_key() -> bytes:
    env = os.environ.get("GOALPLATFORM_SECRET_KEY")
    if env:
        return env.encode()
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()
    # 落库：首次启动生成一个存 app_setting，之后一直用它（惰性导入避免循环依赖）
    from sqlmodel import Session

    from db import engine
    from models import AppSetting

    with Session(engine) as s:
        row = s.get(AppSetting, "secret_key")
        if row and row.value:
            return row.value.encode()
        key = Fernet.generate_key()
        s.add(AppSetting(key="secret_key", value=key.decode()))
        s.commit()
        return key


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_resolve_key())
    return _fernet


def encrypt(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()


# ---- 管理员口令哈希（只校验、不还原，所以用加盐 PBKDF2，而非可逆的 Fernet） ----
_PBKDF2_ROUNDS = 200_000


def hash_password(plain: str) -> str:
    """返回 "salt$hash"（都是 hex）。"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, _PBKDF2_ROUNDS)
    return salt.hex() + "$" + dk.hex()


def verify_password(plain: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), bytes.fromhex(salt_hex), _PBKDF2_ROUNDS)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---- 会话 cookie（登录态；不是密码，是 OAuth 登录结果的签名） ----
SESSION_TTL_SECONDS = 7 * 24 * 3600


def make_session_token(user_id: int) -> str:
    from datetime import datetime, timedelta
    exp = (datetime.utcnow() + timedelta(seconds=SESSION_TTL_SECONDS)).timestamp()
    return encrypt(f"{user_id}|{exp}")


def read_session_token(token: str) -> int | None:
    from datetime import datetime
    try:
        uid, exp = decrypt(token).split("|", 1)
        if float(exp) < datetime.utcnow().timestamp():
            return None
        return int(uid)
    except Exception:
        return None


# ---- 管理控制台会话 cookie（与主应用的 gp_session 完全隔离） ----
def make_admin_token() -> str:
    from datetime import datetime, timedelta
    exp = (datetime.utcnow() + timedelta(seconds=SESSION_TTL_SECONDS)).timestamp()
    return encrypt(f"admin|{exp}")


def read_admin_token(token: str) -> bool:
    from datetime import datetime
    try:
        marker, exp = decrypt(token).split("|", 1)
        return marker == "admin" and float(exp) >= datetime.utcnow().timestamp()
    except Exception:
        return False
