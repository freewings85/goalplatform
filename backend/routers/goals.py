"""目标 CRUD（含递归树、KR、固定 5 阶段计划）。这是系统的核心。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from db import get_session, make_stages
from models import Goal, KeyResult, Stage
from schemas import GoalIn, GoalUpdate, KRIn, KRUpdate, StageUpdate
from serializers import goal_dict, kr_dict, stage_dict

router = APIRouter(prefix="/api", tags=["goals"])


# ============ 目标 ============
@router.get("/goals")
def list_goals(
    business_line_id: Optional[int] = None,
    cycle_id: Optional[int] = None,
    session: Session = Depends(get_session),
):
    """扁平返回目标（含 KR + 阶段）；前端按 parent_id 自行拼树。"""
    q = select(Goal)
    if business_line_id is not None:
        q = q.where(Goal.business_line_id == business_line_id)
    if cycle_id is not None:
        q = q.where(Goal.cycle_id == cycle_id)
    q = q.order_by(Goal.sort_order, Goal.id)
    return [goal_dict(g, session) for g in session.exec(q).all()]


@router.get("/goals/{goal_id}")
def get_goal(goal_id: int, session: Session = Depends(get_session)):
    g = session.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    return goal_dict(g, session, with_children=True)


@router.post("/goals", status_code=201)
def create_goal(payload: GoalIn, session: Session = Depends(get_session)):
    if payload.parent_id is not None and not session.get(Goal, payload.parent_id):
        raise HTTPException(400, "父目标不存在")
    g = Goal(
        business_line_id=payload.business_line_id,
        cycle_id=payload.cycle_id,
        parent_id=payload.parent_id,
        title=payload.title,
        owner=payload.owner,
        health=payload.health,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    session.add(g)
    session.commit()
    session.refresh(g)

    for i, kr in enumerate(payload.krs):
        session.add(KeyResult(goal_id=g.id, title=kr.title, current_value=kr.current_value, sort_order=i))

    # 固定 5 阶段；如传了排期则按位置覆盖
    stages = make_stages(g.id)
    for i, s in enumerate(payload.stages[:5]):
        if s.status is not None:
            stages[i].status = s.status
        if s.start_date is not None:
            stages[i].start_date = s.start_date
        if s.end_date is not None:
            stages[i].end_date = s.end_date
        if s.jira_key is not None:
            stages[i].jira_key = s.jira_key
    session.add_all(stages)
    session.commit()
    session.refresh(g)
    return goal_dict(g, session, with_children=True)


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: int, payload: GoalUpdate, session: Session = Depends(get_session)):
    g = session.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data and data["parent_id"] is not None:
        if data["parent_id"] == goal_id:
            raise HTTPException(400, "目标不能以自己为父")
        if data["parent_id"] in _descendant_ids(goal_id, session):
            raise HTTPException(400, "不能把目标移动到它自己的子孙下")
        if not session.get(Goal, data["parent_id"]):
            raise HTTPException(400, "父目标不存在")
    for k, v in data.items():
        setattr(g, k, v)
    session.add(g)
    session.commit()
    session.refresh(g)
    return goal_dict(g, session, with_children=True)


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, session: Session = Depends(get_session)):
    g = session.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    ids = [goal_id] + list(_descendant_ids(goal_id, session))
    for gid in ids:
        for st in session.exec(select(Stage).where(Stage.goal_id == gid)).all():
            session.delete(st)
        for kr in session.exec(select(KeyResult).where(KeyResult.goal_id == gid)).all():
            session.delete(kr)
        session.delete(session.get(Goal, gid))
    session.commit()


def _descendant_ids(goal_id: int, session: Session) -> set[int]:
    """递归收集所有子孙目标 id。"""
    out: set[int] = set()
    frontier = [goal_id]
    while frontier:
        cur = frontier.pop()
        kids = session.exec(select(Goal.id).where(Goal.parent_id == cur)).all()
        for k in kids:
            if k not in out:
                out.add(k)
                frontier.append(k)
    return out


# ============ 关键结果（KR） ============
@router.post("/goals/{goal_id}/krs", status_code=201)
def add_kr(goal_id: int, payload: KRIn, session: Session = Depends(get_session)):
    if not session.get(Goal, goal_id):
        raise HTTPException(404, "目标不存在")
    n = len(session.exec(select(KeyResult).where(KeyResult.goal_id == goal_id)).all())
    kr = KeyResult(goal_id=goal_id, title=payload.title, current_value=payload.current_value, sort_order=n)
    session.add(kr)
    session.commit()
    session.refresh(kr)
    return kr_dict(kr)


@router.patch("/krs/{kr_id}")
def update_kr(kr_id: int, payload: KRUpdate, session: Session = Depends(get_session)):
    kr = session.get(KeyResult, kr_id)
    if not kr:
        raise HTTPException(404, "KR 不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(kr, k, v)
    session.add(kr)
    session.commit()
    session.refresh(kr)
    return kr_dict(kr)


@router.delete("/krs/{kr_id}", status_code=204)
def delete_kr(kr_id: int, session: Session = Depends(get_session)):
    kr = session.get(KeyResult, kr_id)
    if not kr:
        raise HTTPException(404, "KR 不存在")
    session.delete(kr)
    session.commit()


# ============ 阶段（固定 5 个，只能改） ============
@router.patch("/stages/{stage_id}")
def update_stage(stage_id: int, payload: StageUpdate, session: Session = Depends(get_session)):
    st = session.get(Stage, stage_id)
    if not st:
        raise HTTPException(404, "阶段不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(st, k, v)
    session.add(st)
    session.commit()
    session.refresh(st)
    return stage_dict(st)
