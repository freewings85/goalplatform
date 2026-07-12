"""Atlassian OAuth 2.0 (3LO) —— 「用 Jira 账号登录」。

真站点：授权/令牌走 auth.atlassian.com，资源走 api.atlassian.com。
本地：两者都指向 jira_mock（默认配置即如此），无需注册 app 即可端到端验证。
换真只改设置里的 client_id/secret + 两个 base，代码不动。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlmodel import Session

from jira_config import get_setting, set_setting
from models import User
from security import decrypt, encrypt

SCOPES = "read:me read:jira-work write:jira-work offline_access"

DEFAULTS = {
    "oauth_client_id": "localdev",
    "oauth_client_secret": "localsecret",
    "oauth_auth_base": "http://127.0.0.1:8099",   # 真：https://auth.atlassian.com
    "oauth_api_base": "http://127.0.0.1:8099",    # 真：https://api.atlassian.com
    "oauth_redirect_uri": "http://127.0.0.1:8000/api/auth/callback",
}


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    auth_base: str
    api_base: str
    redirect_uri: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.auth_base and self.api_base and self.redirect_uri)


def get_config(session: Session) -> OAuthConfig:
    g = lambda k: get_setting(session, k, DEFAULTS[k])
    return OAuthConfig(g("oauth_client_id"), g("oauth_client_secret"), g("oauth_auth_base"),
                       g("oauth_api_base"), g("oauth_redirect_uri"))


def save_config(session: Session, **kw) -> None:
    for k, v in kw.items():
        if k in DEFAULTS and v is not None:
            set_setting(session, k, v.strip())


def build_authorize_url(cfg: OAuthConfig, state: str) -> str:
    q = {
        "audience": "api.atlassian.com",
        "client_id": cfg.client_id,
        "scope": SCOPES,
        "redirect_uri": cfg.redirect_uri,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    return f"{cfg.auth_base.rstrip('/')}/authorize?{urlencode(q)}"


def exchange_code(cfg: OAuthConfig, code: str) -> dict:
    body = {
        "grant_type": "authorization_code",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "code": code,
        "redirect_uri": cfg.redirect_uri,
    }
    r = httpx.post(f"{cfg.auth_base.rstrip('/')}/oauth/token", json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def refresh_tokens(cfg: OAuthConfig, refresh_token: str) -> dict:
    body = {
        "grant_type": "refresh_token",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "refresh_token": refresh_token,
    }
    r = httpx.post(f"{cfg.auth_base.rstrip('/')}/oauth/token", json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_identity(cfg: OAuthConfig, access_token: str) -> dict:
    r = httpx.get(f"{cfg.api_base.rstrip('/')}/me",
                  headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    r.raise_for_status()
    return r.json()   # {account_id, email, name}


def fetch_cloud(cfg: OAuthConfig, access_token: str) -> dict:
    r = httpx.get(f"{cfg.api_base.rstrip('/')}/oauth/token/accessible-resources",
                  headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    r.raise_for_status()
    rows = r.json() or []
    if not rows:
        return {"id": "", "url": ""}
    return {"id": rows[0].get("id", ""), "url": rows[0].get("url", "")}


def store_tokens(user: User, tokens: dict) -> None:
    """把令牌加密写到 user（access + 过期时间 + refresh）。"""
    user.oauth_access_enc = encrypt(tokens["access_token"])
    user.oauth_access_expires = datetime.utcnow() + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    if tokens.get("refresh_token"):
        user.oauth_refresh_enc = encrypt(tokens["refresh_token"])


def valid_access_token(session: Session, user: User) -> str | None:
    """返回当前可用的 access token；过期则用 refresh 续期。都没有则 None。"""
    if not user.oauth_access_enc:
        return None
    exp = user.oauth_access_expires
    if exp and exp > datetime.utcnow() + timedelta(seconds=30):
        try:
            return decrypt(user.oauth_access_enc)
        except Exception:
            pass
    # 需要续期
    if not user.oauth_refresh_enc:
        try:
            return decrypt(user.oauth_access_enc)  # 兜底：还没过期太久就先用着
        except Exception:
            return None
    try:
        cfg = get_config(session)
        tokens = refresh_tokens(cfg, decrypt(user.oauth_refresh_enc))
        store_tokens(user, tokens)
        session.add(user)
        session.commit()
        session.refresh(user)
        return decrypt(user.oauth_access_enc)
    except Exception:
        return None
