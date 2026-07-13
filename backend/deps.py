"""共享依赖：当前登录用户（来自签名会话 cookie）。"""
from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, HTTPException
from sqlmodel import Session

from db import get_session
from models import User, UserRole
from security import read_admin_token, read_session_token

SESSION_COOKIE = "gp_session"
ADMIN_COOKIE = "gp_admin"


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


def require_manager(user: Optional[User] = Depends(current_user)) -> User:
    """需要「管理用户」角色（审批相关操作）。"""
    if not user:
        raise HTTPException(401, "未登录")
    if user.role != UserRole.manager:
        raise HTTPException(403, "需要管理用户权限")
    return user


def require_admin(gp_admin: Optional[str] = Cookie(default=None)) -> bool:
    """需要管理控制台（/management）的 admin 登录态，与主应用登录无关。"""
    if not gp_admin or not read_admin_token(gp_admin):
        raise HTTPException(401, "管理员未登录")
    return True
