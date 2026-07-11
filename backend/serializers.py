"""把表对象组装成前端要的 dict（含嵌套 KR / 阶段）。"""
from __future__ import annotations

from sqlmodel import Session, select

from models import Goal, KeyResult, Stage


def stage_dict(st: Stage) -> dict:
    return {
        "id": st.id,
        "stage_index": st.stage_index,
        "name": st.name,
        "deliverable": st.deliverable,
        "status": st.status,
        "start_date": st.start_date,
        "end_date": st.end_date,
        "jira_key": st.jira_key,
    }


def kr_dict(kr: KeyResult) -> dict:
    return {
        "id": kr.id,
        "goal_id": kr.goal_id,
        "title": kr.title,
        "current_value": kr.current_value,
        "sort_order": kr.sort_order,
    }


def goal_dict(goal: Goal, session: Session, *, with_children: bool = False) -> dict:
    krs = session.exec(
        select(KeyResult).where(KeyResult.goal_id == goal.id).order_by(KeyResult.sort_order, KeyResult.id)
    ).all()
    stages = session.exec(
        select(Stage).where(Stage.goal_id == goal.id).order_by(Stage.stage_index)
    ).all()
    child_ids = session.exec(
        select(Goal.id).where(Goal.parent_id == goal.id)
    ).all()

    d = {
        "id": goal.id,
        "business_line_id": goal.business_line_id,
        "cycle_id": goal.cycle_id,
        "parent_id": goal.parent_id,
        "title": goal.title,
        "owner": goal.owner,
        "health": goal.health,
        "start_date": goal.start_date,
        "end_date": goal.end_date,
        "sort_order": goal.sort_order,
        "child_ids": list(child_ids),
        "krs": [kr_dict(k) for k in krs],
        "stages": [stage_dict(s) for s in stages],
    }
    if with_children:
        children = session.exec(
            select(Goal).where(Goal.parent_id == goal.id).order_by(Goal.sort_order, Goal.id)
        ).all()
        d["children"] = [goal_dict(c, session, with_children=True) for c in children]
    return d
