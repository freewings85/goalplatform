"""本地 Jira mock（仅供开发/验证）——现在也模拟「用 Jira 登录」(OAuth 3LO)。

实现（形状对齐真实 Atlassian）：
    OAuth:  GET /authorize（假登录/授权页） · POST /oauth/token · GET /oauth/token/accessible-resources · GET /me
    Jira:   POST /ex/jira/{cloud}/rest/api/3/issue · GET .../issue/{key} · POST .../issueLink
    浏览:   GET /browse/{key}（跳转链接落地页）

运行：.venv/bin/uvicorn jira_mock:app --host 127.0.0.1 --port 8099
把「用户 / 集成」里的 auth_base / api_base 指向 http://127.0.0.1:8099 即可端到端验证登录。
换真 Atlassian 时改成 auth.atlassian.com / api.atlassian.com + 真 client_id/secret，代码不动。
"""
from __future__ import annotations

import itertools
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

app = FastAPI(title="Jira + Atlassian OAuth Mock (dev only)")

# 与种子用户 email 一致，登录后按 email 接上已播种的中文名用户
IDENTITIES = {
    "liming@goalplatform.local": {"name": "李明", "account_id": "acct-liming"},
    "chenlei@goalplatform.local": {"name": "陈磊", "account_id": "acct-chenlei"},
    "wangfang@goalplatform.local": {"name": "王芳", "account_id": "acct-wangfang"},
    "zhangwei@goalplatform.local": {"name": "张伟", "account_id": "acct-zhangwei"},
    "zhoulin@goalplatform.local": {"name": "周琳", "account_id": "acct-zhoulin"},
    "wutao@goalplatform.local": {"name": "吴涛", "account_id": "acct-wutao"},
}
CLOUD_ID = "mock-cloud-1"
SITE_URL = "http://127.0.0.1:8099"

_ISSUES: dict[str, dict] = {}
_LINKS: list[dict] = []
_counter: dict[str, "itertools.count"] = {}


# ================= OAuth =================
@app.get("/authorize", response_class=HTMLResponse)
def authorize(redirect_uri: str, state: str = "", client_id: str = "", scope: str = ""):
    """假的登录/授权页：列出可选身份，点一个就带 code 回调。"""
    btns = "".join(
        f'<a class="b" href="{redirect_uri}?code={quote("code:"+email)}&state={quote(state)}">'
        f'以 <b>{ident["name"]}</b>（{email}）登录并授权</a>'
        for email, ident in IDENTITIES.items()
    )
    return f"""<!doctype html><meta charset=utf-8><title>Atlassian（mock）登录</title>
    <style>body{{font-family:sans-serif;background:#f4f5f7;margin:0;padding:48px;color:#172b4d}}
    .card{{max-width:520px;margin:auto;background:#fff;border-radius:10px;padding:28px;box-shadow:0 1px 4px rgba(0,0,0,.15)}}
    h1{{font-size:18px}} .b{{display:block;padding:11px 14px;margin:8px 0;border:1px solid #dfe1e6;border-radius:8px;
    text-decoration:none;color:#0052cc}} .b:hover{{background:#f4f5f7}} .m{{color:#6b778c;font-size:13px}}</style>
    <div class="card"><h1>🔓 Atlassian 账号登录（本地 mock）</h1>
    <p class="m">这是本地验证用的假授权页。选一个身份即完成「用 Jira 登录」。scope: {scope}</p>{btns}</div>"""


@app.post("/oauth/token")
async def token(request: Request):
    body = await request.json()
    grant = body.get("grant_type")
    if grant == "authorization_code":
        code = body.get("code", "")
        email = code[len("code:"):] if code.startswith("code:") else code
    elif grant == "refresh_token":
        rt = body.get("refresh_token", "")
        email = rt[len("mockrt:"):] if rt.startswith("mockrt:") else ""
    else:
        raise HTTPException(400, "unsupported grant_type")
    if email not in IDENTITIES:
        raise HTTPException(400, "invalid code/refresh_token")
    return {
        "access_token": "mockat:" + email,
        "refresh_token": "mockrt:" + email,
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "read:me read:jira-work write:jira-work offline_access",
    }


def _bearer_email(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    tok = authorization.split(" ", 1)[1]
    email = tok[len("mockat:"):] if tok.startswith("mockat:") else ""
    if email not in IDENTITIES:
        raise HTTPException(401, "invalid token")
    return email


@app.get("/me")
def me(authorization: str | None = Header(None)):
    email = _bearer_email(authorization)
    ident = IDENTITIES[email]
    return {"account_id": ident["account_id"], "email": email, "name": ident["name"]}


@app.get("/oauth/token/accessible-resources")
def resources(authorization: str | None = Header(None)):
    _bearer_email(authorization)
    return [{"id": CLOUD_ID, "url": SITE_URL, "name": "Mock Jira", "scopes": ["read:jira-work", "write:jira-work"]}]


# ================= Jira（OAuth ex 路径，Bearer） =================
@app.post("/ex/jira/{cloud}/rest/api/3/issue", status_code=201)
async def create_issue(cloud: str, request: Request, authorization: str | None = Header(None)):
    _bearer_email(authorization)
    body = await request.json()
    fields = (body or {}).get("fields", {})
    project = (fields.get("project") or {}).get("key")
    if not project:
        raise HTTPException(400, "project is required")
    if not fields.get("summary"):
        raise HTTPException(400, "summary is required")
    c = _counter.setdefault(project, itertools.count(1))
    n = next(c)
    key = f"{project}-{n}"
    issue = {"id": str(10000 + n), "key": key, "self": f"{SITE_URL}/rest/api/3/issue/{key}", "fields": fields}
    _ISSUES[key] = issue
    return {"id": issue["id"], "key": key, "self": issue["self"]}


@app.get("/ex/jira/{cloud}/rest/api/3/issue/{key}")
def get_issue(cloud: str, key: str, authorization: str | None = Header(None)):
    _bearer_email(authorization)
    issue = _ISSUES.get(key)
    if not issue:
        raise HTTPException(404, f"Issue does not exist: {key}")
    return issue


@app.post("/ex/jira/{cloud}/rest/api/3/issueLink", status_code=201)
async def create_link(cloud: str, request: Request, authorization: str | None = Header(None)):
    _bearer_email(authorization)
    body = await request.json()
    inward = (body.get("inwardIssue") or {}).get("key")
    outward = (body.get("outwardIssue") or {}).get("key")
    if not inward or not outward:
        raise HTTPException(400, "inwardIssue and outwardIssue required")
    _LINKS.append({"type": (body.get("type") or {}).get("name", "Relates"), "inward": inward, "outward": outward})
    return {}


@app.get("/browse/{key}", response_class=HTMLResponse)
def browse(key: str):
    exists = key in _ISSUES
    return f"""<!doctype html><meta charset=utf-8><title>{key} · Mock Jira</title>
    <body style="font-family:sans-serif;padding:40px;color:#172b4d">
    <h1>{'🟦 '+key if exists else '❓ '+key+'（未找到）'}</h1>
    <p style="color:#6b778c">Mock Jira 的 issue 落地页（真环境即 Jira 的 /browse/{key}）。</p></body>"""


@app.get("/_mock/state")
def state():
    return {"issues": list(_ISSUES.keys()), "links": _LINKS}
