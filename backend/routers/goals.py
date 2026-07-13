"""目标 CRUD（含递归树、KR、固定 5 阶段计划）。这是系统的核心。"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from db import get_session, make_stages
from deps import current_user
from jira_client import JiraError, add_link, assign_issue, create_issue, get_attachments, get_issue
from jira_config import LINK_TYPE, auth_for_user, jira_issue_type
from models import BusinessLine, Goal, KeyResult, Stage, User
from schemas import GoalIn, GoalUpdate, JiraLinkIn, KRIn, KRUpdate, StageUpdate
from serializers import goal_dict, kr_dict, stage_dict

router = APIRouter(prefix="/api", tags=["goals"])


def _dump_deliverables(items) -> str:
    """把 [DeliverableIn] 存成 JSON 文本；过滤全空条目。"""
    if not items:
        return ""
    rows = []
    for it in items:
        name = (it.name or "").strip()
        url = (it.url or "").strip()
        if name or url:
            rows.append({"name": name, "url": url})
    return json.dumps(rows, ensure_ascii=False) if rows else ""


def _sync_goal_to_jira(session: Session, goal: Goal, user: User | None) -> str | None:
    """把目标同步成一个 Jira issue。成功回填 goal.jira_*；失败返回错误文案（不抛）。"""
    auth = auth_for_user(session, user)
    if not auth.ok:
        return "当前用户未用 Jira 账号登录，无法同步"
    bl = session.get(BusinessLine, goal.business_line_id)
    project_key = bl.jira_project_key if bl else ""
    if not project_key:
        return "该业务线没设默认 Jira 项目 Key"

    try:
        issue = create_issue(
            auth, project_key, goal.title,
            f"GoalPlatform 目标 · 负责人 {goal.owner or '—'}",
            issue_type=jira_issue_type(session),
        )
    except JiraError as e:
        return f"建 Jira issue 失败：{e.message}"
    except Exception as e:
        return f"建 Jira issue 失败：{e}"

    goal.jira_key, goal.jira_id, goal.jira_url = issue["key"], issue["id"], issue["url"]
    session.add(goal)
    session.commit()
    session.refresh(goal)

    # 指派给目标负责人（若其也用 Jira 登录过、有用户名）——尽力而为，失败不影响
    if goal.owner_user_id:
        ow = session.get(User, goal.owner_user_id)
        if ow and ow.jira_username:
            try:
                assign_issue(auth, goal.jira_key, ow.jira_username)
            except Exception:
                pass

    # 父目标若已同步，建一条弱关联（尽力而为，失败不影响主流程）
    if goal.parent_id:
        parent = session.get(Goal, goal.parent_id)
        if parent and parent.jira_key:
            try:
                add_link(auth, parent.jira_key, goal.jira_key, LINK_TYPE)
            except Exception:
                pass
    return None


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
def create_goal(payload: GoalIn, session: Session = Depends(get_session), user: User | None = Depends(current_user)):
    if payload.parent_id is not None and not session.get(Goal, payload.parent_id):
        raise HTTPException(400, "父目标不存在")
    g = Goal(
        business_line_id=payload.business_line_id,
        cycle_id=payload.cycle_id,
        parent_id=payload.parent_id,
        title=payload.title,
        owner=payload.owner,
        owner_user_id=payload.owner_user_id,
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
        if s.deliverables is not None:
            stages[i].deliverables = _dump_deliverables(s.deliverables)
    session.add_all(stages)
    session.commit()
    session.refresh(g)

    # 建目标即同步到 Jira（默认开）。失败不影响目标创建，只在响应里带 jira_error。
    jira_error = _sync_goal_to_jira(session, g, user) if payload.sync_to_jira else None
    out = goal_dict(g, session, with_children=True)
    if jira_error:
        out["jira_error"] = jira_error
    return out


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
    data = payload.model_dump(exclude_unset=True)
    if "deliverables" in data:
        st.deliverables = _dump_deliverables(payload.deliverables)
        data.pop("deliverables")
    for k, v in data.items():
        setattr(st, k, v)
    session.add(st)
    session.commit()
    session.refresh(st)
    return stage_dict(st)


# ============ 目标 ↔ Jira ============
@router.post("/goals/{goal_id}/jira/sync")
def jira_sync(goal_id: int, session: Session = Depends(get_session), user: User | None = Depends(current_user)):
    """事后把目标同步成 Jira issue（若已关联则报错，避免重复建）。"""
    g = session.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    if g.jira_key:
        raise HTTPException(400, f"该目标已关联 {g.jira_key}，请先解除再同步")
    err = _sync_goal_to_jira(session, g, user)
    if err:
        raise HTTPException(502, err)
    return goal_dict(g, session, with_children=True)


@router.get("/goals/{goal_id}/jira/attachments")
def jira_attachments(goal_id: int, session: Session = Depends(get_session), user: User | None = Depends(current_user)):
    """列出该目标 Jira issue 上已上传的附件（产出物）。未同步或取不到则返回空。"""
    g = session.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    if not g.jira_key:
        return {"jira_key": "", "jira_url": "", "attachments": []}
    auth = auth_for_user(session, user)
    items = []
    if auth.ok:
        try:
            items = get_attachments(auth, g.jira_key)
        except Exception:
            items = []
    return {"jira_key": g.jira_key, "jira_url": g.jira_url, "attachments": items}


@router.post("/goals/{goal_id}/jira/link")
def jira_link(goal_id: int, payload: JiraLinkIn, session: Session = Depends(get_session), user: User | None = Depends(current_user)):
    """手动关联一个已有的 Jira issue（会校验其存在）。"""
    g = session.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    auth = auth_for_user(session, user)
    key = payload.key.strip()
    if not key:
        raise HTTPException(400, "请填 Jira issue key")
    if auth.ok:
        try:
            issue = get_issue(auth, key)
            g.jira_key, g.jira_id, g.jira_url = issue["key"], issue["id"], issue["url"]
        except JiraError as e:
            raise HTTPException(404 if e.status == 404 else 502, f"校验 Jira issue 失败：{e.message}")
        except Exception as e:
            raise HTTPException(502, f"校验 Jira issue 失败：{e}")
    else:
        # 未登录时也允许弱关联（只存 key，url 按站点拼；无站点则留空）
        g.jira_key = key
        g.jira_url = f"{auth.site_url.rstrip('/')}/browse/{key}" if auth.site_url else ""
    session.add(g)
    session.commit()
    session.refresh(g)
    return goal_dict(g, session, with_children=True)


@router.delete("/goals/{goal_id}/jira/link")
def jira_unlink(goal_id: int, session: Session = Depends(get_session)):
    """解除关联（只清平台侧字段，不动 Jira 里的 issue）。"""
    g = session.get(Goal, goal_id)
    if not g:
        raise HTTPException(404, "目标不存在")
    g.jira_key = g.jira_id = g.jira_url = ""
    session.add(g)
    session.commit()
    session.refresh(g)
    return goal_dict(g, session, with_children=True)
