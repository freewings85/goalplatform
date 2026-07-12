"""Jira Cloud REST API v3 客户端（OAuth Bearer）。

OAuth 3LO 下，Jira API 走 https://api.atlassian.com/ex/jira/{cloudid}/rest/api/3/...
鉴权用 Authorization: Bearer {access_token}。
描述字段用 ADF（v3 要求）。切换真/mock 只改 base_url（见 jira_config）。
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

TIMEOUT = 15.0


@dataclass
class JiraAuth:
    base_url: str          # 形如 https://api.atlassian.com/ex/jira/{cloudid}  或  mock 的等价地址
    token: str             # OAuth access token
    site_url: str = ""     # 站点浏览地址（拼 /browse/KEY 用），如 https://xxx.atlassian.net

    @property
    def ok(self) -> bool:
        return bool(self.base_url and self.token)


class JiraError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"[Jira {status}] {message}")


def _adf(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": ([{"type": "text", "text": text}] if text else [])}
        ],
    }


def _client(auth: JiraAuth) -> httpx.Client:
    return httpx.Client(
        base_url=auth.base_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {auth.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=TIMEOUT,
    )


def _raise(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        msg = resp.text
        try:
            data = resp.json()
            errs = data.get("errorMessages") or list((data.get("errors") or {}).values())
            if errs:
                msg = "；".join(str(e) for e in errs)
        except Exception:
            pass
        raise JiraError(resp.status_code, msg[:500])


def _issue_url(auth: JiraAuth, key: str) -> str:
    base = (auth.site_url or auth.base_url).rstrip("/")
    return f"{base}/browse/{key}"


def create_issue(
    auth: JiraAuth,
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    assignee_account_id: str | None = None,
) -> dict:
    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "description": _adf(description),
    }
    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}
    with _client(auth) as c:
        r = c.post("/rest/api/3/issue", json={"fields": fields})
        _raise(r)
        data = r.json()
    key = data["key"]
    return {"key": key, "id": data.get("id", ""), "url": _issue_url(auth, key)}


def get_issue(auth: JiraAuth, key: str) -> dict:
    with _client(auth) as c:
        r = c.get(f"/rest/api/3/issue/{key}")
        _raise(r)
        data = r.json()
    return {"key": data["key"], "id": data.get("id", ""), "url": _issue_url(auth, data["key"])}


def add_link(auth: JiraAuth, inward_key: str, outward_key: str, link_type: str = "Relates") -> None:
    body = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_key},
        "outwardIssue": {"key": outward_key},
    }
    with _client(auth) as c:
        r = c.post("/rest/api/3/issueLink", json=body)
        _raise(r)
