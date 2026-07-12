"""设置读写 + 用「当前登录用户的 OAuth 令牌」构造 Jira 调用所需的 JiraAuth。"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from models import AppSetting, User


def get_setting(session: Session, key: str, default: str = "") -> str:
    row = session.get(AppSetting, key)
    return row.value if row else default


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(AppSetting, key)
    if row:
        row.value = value
    else:
        row = AppSetting(key=key, value=value)
    session.add(row)
    session.commit()


def auth_for_user(session: Session, user: Optional[User]):
    """OAuth：Jira API 走 {api_base}/ex/jira/{cloudid}，Bearer=用户 access token（自动续期）。"""
    # 延迟导入避免循环
    from jira_client import JiraAuth
    from oauth import get_config, valid_access_token

    if not user or not user.oauth_cloud_id:
        return JiraAuth(base_url="", token="")
    token = valid_access_token(session, user)
    if not token:
        return JiraAuth(base_url="", token="")
    api_base = get_config(session).api_base.rstrip("/")
    base = f"{api_base}/ex/jira/{user.oauth_cloud_id}"
    return JiraAuth(base_url=base, token=token, site_url=user.oauth_site_url)
