"""全局设置：OAuth 应用配置（client_id/secret + auth/api base + 回调）。

secret 只写不回显。本地默认已指向 jira_mock，开箱即可登录验证。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import SQLModel, Session

from db import get_session
from oauth import get_config, save_config

router = APIRouter(prefix="/api/settings", tags=["settings"])


class OAuthSettingIn(SQLModel):
    client_id: Optional[str] = None
    client_secret: Optional[str] = None       # 空/缺省 = 不改；填了才更新
    auth_base: Optional[str] = None
    api_base: Optional[str] = None
    redirect_uri: Optional[str] = None


@router.get("/oauth")
def get_oauth(session: Session = Depends(get_session)):
    cfg = get_config(session)
    return {
        "client_id": cfg.client_id,
        "auth_base": cfg.auth_base,
        "api_base": cfg.api_base,
        "redirect_uri": cfg.redirect_uri,
        "has_secret": bool(cfg.client_secret),
        "configured": cfg.configured,
    }


@router.put("/oauth")
def put_oauth(payload: OAuthSettingIn, session: Session = Depends(get_session)):
    data = payload.model_dump(exclude_unset=True)
    # 只有显式传了非空 secret 才更新，避免把已存的清掉
    if not data.get("client_secret"):
        data.pop("client_secret", None)
    save_config(session, **data)
    return get_oauth(session)
