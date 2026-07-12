"""Jira Server / Data Center REST API v2 客户端（Basic auth：用户名 + 密码）。

针对自建 Jira Server（如 8.1.0）：
- 鉴权：HTTP Basic（username:password）。Server 8.1 无 OAuth 3LO、无 PAT。
- 路径：{base}/rest/api/2/...（Server 是 v2；v3/ADF 是 Cloud 专属）。
- 描述字段：v2 用**纯文本字符串**（不是 ADF）。
- 指派：用 {"name": <username>}（Server 用用户名，不是 Cloud 的 accountId）。
切到别的 Jira 只改 base_url + 各用户登录名密码，代码不动。
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

TIMEOUT = 15.0


@dataclass
class JiraAuth:
    base_url: str          # 形如 http://192.168.100.130:18080
    username: str          # Jira 登录名
    password: str          # Jira 密码

    @property
    def ok(self) -> bool:
        return bool(self.base_url and self.username and self.password)


class JiraError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"[Jira {status}] {message}")


def _client(auth: JiraAuth) -> httpx.Client:
    return httpx.Client(
        base_url=auth.base_url.rstrip("/"),
        auth=(auth.username, auth.password),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
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
        raise JiraError(resp.status_code, (msg or resp.reason_phrase)[:500])


def _issue_url(auth: JiraAuth, key: str) -> str:
    return f"{auth.base_url.rstrip('/')}/browse/{key}"


def myself(auth: JiraAuth) -> dict:
    """校验凭据 + 取身份。返回 {name, key, displayName, email}。用于登录。"""
    with _client(auth) as c:
        r = c.get("/rest/api/2/myself")
        _raise(r)
        d = r.json()
    return {
        "name": d.get("name", ""),
        "key": d.get("key", d.get("name", "")),
        "displayName": d.get("displayName", ""),
        "email": d.get("emailAddress", ""),
    }


def create_issue(
    auth: JiraAuth,
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "任务",
) -> dict:
    fields: dict = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = description
    with _client(auth) as c:
        r = c.post("/rest/api/2/issue", json={"fields": fields})
        _raise(r)
        data = r.json()
    key = data["key"]
    return {"key": key, "id": data.get("id", ""), "url": _issue_url(auth, key)}


def get_issue(auth: JiraAuth, key: str) -> dict:
    with _client(auth) as c:
        r = c.get(f"/rest/api/2/issue/{key}", params={"fields": "summary"})
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
        r = c.post("/rest/api/2/issueLink", json=body)
        _raise(r)


def assign_issue(auth: JiraAuth, key: str, username: str) -> None:
    """把 issue 指派给某 Jira 用户（尽力而为，调用方吞异常）。"""
    with _client(auth) as c:
        r = c.put(f"/rest/api/2/issue/{key}/assignee", json={"name": username})
        _raise(r)


def get_attachments(auth: JiraAuth, key: str) -> list[dict]:
    """取 issue 上已上传的附件（产出物）。返回 [{filename, url, size}]。"""
    with _client(auth) as c:
        r = c.get(f"/rest/api/2/issue/{key}", params={"fields": "attachment"})
        _raise(r)
        data = r.json()
    out = []
    for a in (data.get("fields", {}).get("attachment") or []):
        out.append({"filename": a.get("filename", ""), "url": a.get("content", ""), "size": a.get("size", 0)})
    return out
