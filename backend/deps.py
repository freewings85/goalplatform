"""共享依赖：当前登录用户（来自签名会话 cookie）。"""
from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, HTTPException
from sqlmodel import Session

from db import get_session
from models import User
from security import read_session_token

SESSION_COOKIE = "gp_session"


def current_user(
    gp_session: Optional[str] = Cookie(default=None),
    session: Session = Depends(get_session),
) -> Optional[User]:
    if not gp_session:
        return None
    uid = read_session_token(gp_session)
    if uid is None:
        return None
    return session.get(User, uid)


def require_user(user: Optional[User] = Depends(current_user)) -> User:
    if not user:
        raise HTTPException(401, "未登录")
    return user
