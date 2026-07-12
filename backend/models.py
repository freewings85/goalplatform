"""数据模型（SQLModel / SQLite）。

设计原则（本版做减法）：
- 重点是「目标 + 计划」的增删改查与持久化。
- 不做任何达成度 / 百分比计算：健康度、阶段状态都是**人工选择的枚举字段**，不落任何 rollup 数字。
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


# ---- 枚举（都是人工选择，不是计算得来） ----
class CycleStatus(str, Enum):
    active = "active"       # 进行中
    archived = "archived"   # 已归档


class StageStatus(str, Enum):
    todo = "todo"           # 未开始 ⚪
    running = "running"     # 进行中 🟡
    done = "done"           # 已完成 🟢


# ---- 固定 5 阶段交付流水线：每个目标（大/小通用）都走同一条 ----
# (阶段名, 产出物)
FIXED_STAGES: list[tuple[str, str]] = [
    ("业务需求确定", "业务流程图 + 建模图"),
    ("方案确定", "方案 spec"),
    ("开发完成", "测试 spec"),
    ("测试", "测试报告"),
    ("发布上线", "上线（release note）"),
]


# ---- 表 ----
class BusinessLine(SQLModel, table=True):
    """业务线：一条 agent 产品线。目标与计划都按业务线分组。"""
    __tablename__ = "business_line"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    owner: str = ""
    jira_project_key: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Cycle(SQLModel, table=True):
    """周期：季度 / 月迭代桶，可归档。"""
    __tablename__ = "cycle"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str                                   # 如 "2026 Q3"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: CycleStatus = CycleStatus.active
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    """平台用户 = 一个 Jira（Server/DC）账号。

    登录就是「用 Jira 的用户名+密码」：校验通过即建/认用户。为了之后能代表该用户
    调 Jira（建 issue / 关联），密码用 Fernet 加密存（只写不读，任何 GET 都不回显）。
    Jira Server 8.1 无 OAuth 3LO、无 PAT（8.14+ 才有），故只能存密码。
    """
    __tablename__ = "user"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str                                   # 显示名（Jira displayName），如 陈自飞
    email: str = ""
    jira_username: str = Field(default="", index=True)  # Jira 登录名 / key，如 chenzifei（也是 assignee 用的 name）
    jira_password_enc: str = ""                 # Fernet 加密的 Jira 密码（只写不读）
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppSetting(SQLModel, table=True):
    """全局键值配置：jira_base_url（Jira 站点）、jira_issue_type（建 issue 用的类型名）。"""
    __tablename__ = "app_setting"
    key: str = Field(primary_key=True)
    value: str = ""


class Goal(SQLModel, table=True):
    """目标：递归成树（大目标 → 子目标，层数不限）。"""
    __tablename__ = "goal"
    id: Optional[int] = Field(default=None, primary_key=True)
    business_line_id: int = Field(foreign_key="business_line.id", index=True)
    cycle_id: Optional[int] = Field(default=None, foreign_key="cycle.id", index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="goal.id", index=True)
    title: str
    owner: str = ""
    owner_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    sort_order: int = 0
    # 该目标对应的 Jira issue（每个目标 = 1 个 issue）
    jira_key: str = ""
    jira_id: str = ""
    jira_url: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KeyResult(SQLModel, table=True):
    """关键结果（KR）：挂在目标下，当前值人工填（纯文本，不算进度）。"""
    __tablename__ = "key_result"
    id: Optional[int] = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goal.id", index=True)
    title: str
    current_value: str = ""                     # 如 "当前 92%" —— 纯文案，不做计算
    sort_order: int = 0


class Stage(SQLModel, table=True):
    """交付阶段节点：每个目标固定 5 个，与 FIXED_STAGES 一一对应。"""
    __tablename__ = "stage"
    id: Optional[int] = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goal.id", index=True)
    stage_index: int                            # 0..4
    name: str
    deliverable: str = ""
    status: StageStatus = StageStatus.todo      # 人工更新
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    jira_key: str = ""
