"""登录 = 用 Jira（Server）的用户名+密码。校验通过即建/认用户、下发会话 cookie。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session, select

from db import get_session
from deps import SESSION_COOKIE, current_user
from jira_client import JiraAuth, JiraError, myself
from jira_config import jira_base_url
from models import User
from schemas import LoginIn
from security import encrypt, make_session_token
from serializers import user_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(session: Session = Depends(get_session), user: User | None = Depends(current_user)):
    return {
        "configured": bool(jira_base_url(session)),
        "jira_base_url": jira_base_url(session),
        "logged_in": user is not None,
        "user": user_dict(user) if user else None,
    }


@router.get("/me")
def me(user: User | None = Depends(current_user)):
    if not user:
        raise HTTPException(401, "未登录")
    return user_dict(user)


@router.post("/login")
def login(payload: LoginIn, response: Response, session: Session = Depends(get_session)):
    base = jira_base_url(session)
    if not base:
        raise HTTPException(400, "尚未配置 Jira 站点地址")
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(400, "请输入 Jira 用户名和密码")

    auth = JiraAuth(base_url=base, username=username, password=payload.password)
    try:
        ident = myself(auth)                    # 校验凭据（401 = 账号或密码错）
    except JiraError as e:
        if e.status in (401, 403):
            raise HTTPException(401, "Jira 账号或密码不正确")
        raise HTTPException(502, f"连接 Jira 失败：{e.message}")
    except Exception as e:
        raise HTTPException(502, f"连接 Jira 失败：{e}")

    jira_name = ident["name"] or username
    # 白名单：只有管理员在「用户管理」中添加过的账号才能登录（先按 jira_username，再按 email 认领）
    user = session.exec(select(User).where(User.jira_username == jira_name)).first()
    if not user and ident.get("email"):
        user = session.exec(select(User).where(User.email == ident["email"])).first()
    if not user:
        raise HTTPException(403, "未授权：请联系管理员在用户管理中添加你的账号")
    if not user.is_active:
        raise HTTPException(403, "账号已停用：请联系管理员")
    # 认领 / 更新资料并存加密凭据（角色由管理员维护，登录不改）
    user.name = ident.get("displayName") or user.name or jira_name
    user.email = ident.get("email") or user.email
    user.jira_username = jira_name
    user.jira_password_enc = encrypt(payload.password)
    session.add(user)
    session.commit()
    session.refresh(user)

    response.set_cookie(SESSION_COOKIE, make_session_token(user.id), httponly=True, samesite="lax", path="/")
    return user_dict(user)


@router.post("/logout")
def logout(resp: Response):
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
