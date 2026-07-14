"""目标可见范围(树级):normal 用户只看「自己参与的目标树」,manager 全可见。

规则见 docs/superpowers/specs/2026-07-14-goal-tree-visibility-design.md:
某顶层目标的子树(含自身)里存在 owner_user_id=我 的目标 → 整棵树可见。
"""
from __future__ import annotations

from models import Goal, User, UserRole


def visible_tree_roots(goals: list[Goal], user: User) -> list[Goal]:
    """从一条业务线的全量目标里,算出该用户可见的顶层目标(保持传入顺序)。"""
    tops = [g for g in goals if g.parent_id is None]
    if user.role == UserRole.manager:
        return tops

    by_id = {g.id: g for g in goals}

    def top_of(g: Goal) -> Goal | None:
        seen = set()
        while g.parent_id is not None:
            if g.id in seen:  # 数据坏了成环时兜底
                return None
            seen.add(g.id)
            parent = by_id.get(g.parent_id)
            if parent is None:
                return None  # 孤儿分支(父目标被周期外裁掉不会发生,这里只防脏数据)
            g = parent
        return g

    my_tree_ids = {t.id for g in goals if g.owner_user_id == user.id and (t := top_of(g))}
    return [t for t in tops if t.id in my_tree_ids]


def visible_goal_ids(goals: list[Goal], user: User) -> set[int]:
    """可见树内所有目标的 id 集合。"""
    roots = visible_tree_roots(goals, user)
    children: dict[int, list[Goal]] = {}
    for g in goals:
        if g.parent_id is not None:
            children.setdefault(g.parent_id, []).append(g)
    out: set[int] = set()
    stack = list(roots)
    while stack:
        g = stack.pop()
        out.add(g.id)
        stack.extend(children.get(g.id, []))
    return out
