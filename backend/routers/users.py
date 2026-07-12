"""用户：身份来自「用 Jira 登录」（OAuth），这里只做只读列表 + 停用/删除。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from db import get_session
from models import Goal, User
from serializers import user_dict

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
def list_users(session: Session = Depends(get_session)):
    users = session.exec(select(User).order_by(User.id)).all()
    return [user_dict(u) for u in users]


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, session: Session = Depends(get_session)):
    u = session.get(User, user_id)
    if not u:
        raise HTTPException(404, "用户不存在")
    for g in session.exec(select(Goal).where(Goal.owner_user_id == user_id)).all():
        g.owner_user_id = None
        session.add(g)
    session.delete(u)
    session.commit()
