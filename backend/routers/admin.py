"""管理控制台（/management）：独立 admin 账号，只做用户白名单管理 + 改自己密码。

与主应用「用 Jira 登录」完全隔离：这里用单独的 admin 口令（哈希存 AppSetting）
和单独的 cookie gp_admin。admin 不是 Jira 用户，也不参与阶段审批（审批是主应用里
角色=管理用户的 Jira 用户做的）。
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlmodel import Session, select

from db import get_session
from deps import ADMIN_COOKIE, require_admin
from jira_config import get_setting, set_setting
from models import Goal, Stage, User
from schemas import AdminLoginIn, AdminPasswordIn, AdminUserIn, AdminUserUpdate
from security import hash_password, make_admin_token, read_admin_token, verify_password
from serializers import user_dict

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_PW_KEY = "admin_password_hash"


@router.get("/status")
def admin_status(gp_admin: str | None = Cookie(default=None)):
    return {"logged_in": bool(gp_admin and read_admin_token(gp_admin))}


@router.post("/login")
def admin_login(payload: AdminLoginIn, response: Response, session: Session = Depends(get_session)):
    stored = get_setting(session, ADMIN_PW_KEY, "")
    if not stored or not verify_password(payload.password, stored):
        raise HTTPException(401, "管理员密码不正确")
    response.set_cookie(ADMIN_COOKIE, make_admin_token(), httponly=True, samesite="lax", path="/")
    return {"ok": True}


@router.post("/logout")
def admin_logout(resp: Response):
    resp.delete_cookie(ADMIN_COOKIE, path="/")
    return {"ok": True}


@router.post("/password")
def admin_change_password(
    payload: AdminPasswordIn,
    session: Session = Depends(get_session),
    _: bool = Depends(require_admin),
):
    stored = get_setting(session, ADMIN_PW_KEY, "")
    if not verify_password(payload.old_password, stored):
        raise HTTPException(400, "原密码不正确")
    if len(payload.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    set_setting(session, ADMIN_PW_KEY, hash_password(payload.new_password))
    return {"ok": True}


# ---------- 用户白名单 ----------
@router.get("/users")
def admin_list_users(session: Session = Depends(get_session), _: bool = Depends(require_admin)):
    return [user_dict(u) for u in session.exec(select(User).order_by(User.id)).all()]


@router.post("/users", status_code=201)
def admin_add_user(payload: AdminUserIn, session: Session = Depends(get_session), _: bool = Depends(require_admin)):
    name = payload.name.strip()
    jira_username = payload.jira_username.strip()
    if not name or not jira_username:
        raise HTTPException(400, "显示名与 Jira 用户名都不能空")
    if session.exec(select(User).where(User.jira_username == jira_username)).first():
        raise HTTPException(400, f"用户 {jira_username} 已存在")
    u = User(name=name, jira_username=jira_username, role=payload.role, is_active=True)
    session.add(u)
    session.commit()
    session.refresh(u)
    return user_dict(u)


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: AdminUserUpdate,
    session: Session = Depends(get_session),
    _: bool = Depends(require_admin),
):
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    data = payload.model_dump(exclude_unset=True)
    if "jira_username" in data:
        newname = (data["jira_username"] or "").strip()
        if not newname:
            raise HTTPException(400, "Jira 用户名不能空")
        clash = session.exec(select(User).where(User.jira_username == newname)).first()
        if clash and clash.id != user_id:
            raise HTTPException(400, f"用户 {newname} 已存在")
        data["jira_username"] = newname
    for k, v in data.items():
        setattr(u, k, v)
    session.add(u)
    session.commit()
    session.refresh(u)
    return user_dict(u)


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(user_id: int, session: Session = Depends(get_session), _: bool = Depends(require_admin)):
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    for g in session.exec(select(Goal).where(Goal.owner_user_id == user_id)).all():
        g.owner_user_id = None
        session.add(g)
    for st in session.exec(select(Stage).where(Stage.approved_by_id == user_id)).all():
        st.approved_by_id = None  # 保留审批状态/意见，只断开外键
        session.add(st)
    session.delete(u)
    session.commit()
