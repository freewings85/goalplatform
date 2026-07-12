"""「用 Jira 账号登录」—— Atlassian OAuth 3LO 登录、会话、登出。"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from db import get_session
from deps import SESSION_COOKIE, current_user
from models import User
from oauth import (
    build_authorize_url,
    exchange_code,
    fetch_cloud,
    fetch_identity,
    get_config,
    store_tokens,
)
from security import decrypt, encrypt, make_session_token
from serializers import user_dict

router = APIRouter(prefix="/api/auth", tags=["auth"])

STATE_COOKIE = "gp_oauth_state"


@router.get("/status")
def auth_status(session: Session = Depends(get_session), user: User | None = Depends(current_user)):
    cfg = get_config(session)
    return {
        "configured": cfg.configured,
        "logged_in": user is not None,
        "user": user_dict(user) if user else None,
    }


@router.get("/me")
def me(user: User | None = Depends(current_user)):
    if not user:
        raise HTTPException(401, "未登录")
    return user_dict(user)


@router.get("/login")
def login(session: Session = Depends(get_session)):
    cfg = get_config(session)
    if not cfg.configured:
        raise HTTPException(400, "OAuth 未配置（去设置里填 client_id / secret / 站点）")
    state = secrets.token_urlsafe(16)
    resp = RedirectResponse(build_authorize_url(cfg, state), status_code=302)
    resp.set_cookie(STATE_COOKIE, encrypt(state), httponly=True, samesite="lax", max_age=600, path="/")
    return resp


@router.get("/callback")
def callback(
    code: str = "",
    state: str = "",
    gp_oauth_state: str | None = Cookie(default=None),
    session: Session = Depends(get_session),
):
    # 校验 state（防 CSRF）
    expected = None
    if gp_oauth_state:
        try:
            expected = decrypt(gp_oauth_state)
        except Exception:
            expected = None
    if not code or not state or state != expected:
        raise HTTPException(400, "OAuth 回调校验失败（state 不匹配或缺 code）")

    cfg = get_config(session)
    tokens = exchange_code(cfg, code)
    access = tokens["access_token"]
    ident = fetch_identity(cfg, access)          # {account_id, email, name}
    cloud = fetch_cloud(cfg, access)             # {id, url}

    account_id = ident.get("account_id") or ident.get("accountId") or ""
    email = ident.get("email", "")
    name = ident.get("name") or email or account_id

    # upsert：先按 account_id，再按 email（把已播种的同名用户接上），否则新建
    user = session.exec(select(User).where(User.atlassian_account_id == account_id)).first()
    if not user and email:
        user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        user = User(name=name)
        session.add(user)
    user.name = name or user.name
    user.email = email or user.email
    user.atlassian_account_id = account_id
    user.oauth_cloud_id = cloud.get("id", "")
    user.oauth_site_url = cloud.get("url", "")
    user.is_active = True
    store_tokens(user, tokens)
    session.add(user)
    session.commit()
    session.refresh(user)

    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(SESSION_COOKIE, make_session_token(user.id), httponly=True, samesite="lax", path="/")
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


@router.post("/logout")
def logout(resp: Response):
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
