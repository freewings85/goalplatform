"""业务线看板:按角色出内容(管理用户看全部,普通用户看自己负责的)+ 按根条目分页。

范围规则(服务端强制,见 docs/superpowers/specs/2026-07-14-role-board-design.md):
- manager:该业务线 + 所选周期下全部顶层目标,各带完整子树
- normal:自己负责的目标 + 完整子树;祖先也是自己负责的只列祖先(不重复)
- 周期过滤只作用在根条目上,子树完整展示
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from db import get_session
from deps import require_user
from models import Goal, User, UserRole
from serializers import goal_dict

router = APIRouter(prefix="/api", tags=["board"])

PAGE_SIZE = 5  # 每页根条目数


@router.get("/board")
def board(
    business_line_id: int,
    cycle_id: Optional[int] = None,
    page: int = 1,
    session: Session = Depends(get_session),
    user: User = Depends(require_user),
):
    goals = session.exec(
        select(Goal).where(Goal.business_line_id == business_line_id).order_by(Goal.sort_order, Goal.id)
    ).all()
    by_id = {g.id: g for g in goals}
    children: dict[int, list[Goal]] = {}
    for g in goals:
        if g.parent_id is not None:
            children.setdefault(g.parent_id, []).append(g)

    def in_cycle(g: Goal) -> bool:
        return cycle_id is None or g.cycle_id == cycle_id

    if user.role == UserRole.manager:
        roots = [g for g in goals if g.parent_id is None and in_cycle(g)]
    else:
        mine = {g.id for g in goals if g.owner_user_id == user.id}

        def has_my_ancestor(g: Goal) -> bool:
            cur = g
            while cur.parent_id is not None:
                cur = by_id.get(cur.parent_id)
                if cur is None:
                    return False
                if cur.id in mine:
                    return True
            return False

        roots = [g for g in goals if g.id in mine and not has_my_ancestor(g) and in_cycle(g)]

    total = len(roots)
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)  # 越界回落
    page_roots = roots[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    items: list[dict] = []
    root_ids: list[int] = []
    for root in page_roots:
        root_ids.append(root.id)
        stack = [root]
        while stack:
            g = stack.pop(0)
            items.append(goal_dict(g, session))
            stack.extend(children.get(g.id, []))

    return {"items": items, "root_ids": root_ids, "total": total, "page": page, "page_size": PAGE_SIZE}
