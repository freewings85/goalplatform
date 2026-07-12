"""对称加密 Jira API Token（存储用）。

密钥来源：环境变量 GOALPLATFORM_SECRET_KEY；缺省则生成并持久化到 backend/.secret_key（已 gitignore）。
Token 永不明文出库，也永不出现在任何 GET 响应里。
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet

_KEY_FILE = Path(__file__).parent / ".secret_key"


def _load_key() -> bytes:
    env = os.environ.get("GOALPLATFORM_SECRET_KEY")
    if env:
        return env.encode()
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    return key


_fernet = Fernet(_load_key())


def encrypt(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()


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
