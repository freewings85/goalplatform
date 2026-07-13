"""请求体 / 响应的输入校验模型（非表）。读取一律返回 dict，FastAPI 自动序列化。"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlmodel import SQLModel

from models import CycleStatus, StageStatus


# ---- 业务线 ----
class BusinessLineIn(SQLModel):
    name: str
    description: str = ""
    owner: str = ""
    jira_project_key: str = ""


class BusinessLineUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    jira_project_key: Optional[str] = None


# ---- 周期 ----
class CycleIn(SQLModel):
    name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: CycleStatus = CycleStatus.active


class CycleUpdate(SQLModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[CycleStatus] = None


# ---- KR ----
class KRIn(SQLModel):
    title: str
    current_value: str = ""


class KRUpdate(SQLModel):
    title: Optional[str] = None
    current_value: Optional[str] = None
    sort_order: Optional[int] = None


# ---- 阶段（固定 5 个，只能改，不能增删） ----
class DeliverableIn(SQLModel):
    name: str = ""
    url: str = ""


class StageIn(SQLModel):
    """新建目标时可选地为某阶段排期 / 设状态（按位置 0..4 对应固定 5 阶段）。"""
    status: Optional[StageStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    jira_key: Optional[str] = None
    deliverables: Optional[list[DeliverableIn]] = None


class StageUpdate(SQLModel):
    status: Optional[StageStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    jira_key: Optional[str] = None
    deliverables: Optional[list[DeliverableIn]] = None


# ---- 目标 ----
class GoalIn(SQLModel):
    business_line_id: int
    cycle_id: Optional[int] = None
    parent_id: Optional[int] = None
    title: str
    owner: str = ""
    owner_user_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    krs: list[KRIn] = []
    stages: list[StageIn] = []          # 可选，按位置排期；缺省则 5 个 todo
    sync_to_jira: bool = True           # 默认建目标即同步到 Jira


class GoalUpdate(SQLModel):
    title: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    cycle_id: Optional[int] = None
    parent_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    sort_order: Optional[int] = None


# ---- 登录（用 Jira 账号密码） ----
class LoginIn(SQLModel):
    username: str
    password: str


# ---- 设置 / Jira 关联 ----
class JiraSettingsIn(SQLModel):
    base_url: Optional[str] = None
    issue_type: Optional[str] = None


class JiraLinkIn(SQLModel):
    key: str                            # 已有 Jira issue key，如 AI-6
