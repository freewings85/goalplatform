"""业务线看板:按角色出内容(管理用户看全部,普通用户看自己参与的树)+ 按根条目分页。

范围规则与 /api/goals 一致(树级,见 scope.py 与
docs/superpowers/specs/2026-07-14-goal-tree-visibility-design.md);
周期过滤只作用在根条目上,子树完整展示。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from db import get_session
from deps import require_user
from models import Goal, User
from scope import visible_tree_roots
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
    children: dict[int, list[Goal]] = {}
    for g in goals:
        if g.parent_id is not None:
            children.setdefault(g.parent_id, []).append(g)

    # 树级可见性(与 /api/goals 同一规则):manager 全部,normal 只有参与的树
    roots = [g for g in visible_tree_roots(goals, user) if cycle_id is None or g.cycle_id == cycle_id]

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
