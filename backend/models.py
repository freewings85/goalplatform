"""数据模型（SQLModel / MySQL 或 SQLite）。

设计原则（本版做减法）：
- 重点是「目标 + 计划」的增删改查与持久化。
- 不做任何达成度 / 百分比计算：健康度、阶段状态都是**人工选择的枚举字段**，不落任何 rollup 数字。

字段类型约定（MySQL 的 VARCHAR 必须有长度，SQLite 不强制但兼容）：
- 普通短字段 max_length=255；短标识（jira key 等）64；URL 512
- 不限长度的文本（备注 / 审批意见 / 密文等）用 TEXT
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Text
from sqlmodel import Field, SQLModel


# ---- 枚举（都是人工选择，不是计算得来） ----
class CycleStatus(str, Enum):
    active = "active"       # 进行中
    archived = "archived"   # 已归档


class StageStatus(str, Enum):
    todo = "todo"           # 未开始 ⚪
    running = "running"     # 进行中 🟡
    done = "done"           # 已完成 🟢


class UserRole(str, Enum):
    normal = "normal"       # 普通用户：只能看审批状态
    manager = "manager"     # 管理用户：可审批 / 撤销审批


class ApprovalStatus(str, Enum):
    pending = "pending"     # 未审批
    approved = "approved"   # 审批通过


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
    name: str = Field(max_length=255)
    description: str = Field(default="", sa_type=Text)
    owner: str = Field(default="", max_length=255)
    jira_project_key: str = Field(default="", max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Cycle(SQLModel, table=True):
    """周期：季度 / 月迭代桶，可归档。"""
    __tablename__ = "cycle"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=255)           # 如 "2026 Q3"
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
    name: str = Field(max_length=255)           # 显示名（Jira displayName），如 陈自飞
    email: str = Field(default="", max_length=255)
    jira_username: str = Field(default="", index=True, max_length=255)  # Jira 登录名 / key，如 chenzifei（也是 assignee 用的 name）
    jira_password_enc: str = Field(default="", sa_type=Text)  # Fernet 加密的 Jira 密码（只写不读）
    role: UserRole = UserRole.normal            # 普通 / 管理（管理才可审批）
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppSetting(SQLModel, table=True):
    """全局键值配置：jira_base_url（Jira 站点）、jira_issue_type（建 issue 用的类型名）。"""
    __tablename__ = "app_setting"
    key: str = Field(primary_key=True, max_length=64)
    value: str = Field(default="", sa_type=Text)


class Goal(SQLModel, table=True):
    """目标：递归成树（大目标 → 子目标，层数不限）。"""
    __tablename__ = "goal"
    id: Optional[int] = Field(default=None, primary_key=True)
    business_line_id: int = Field(foreign_key="business_line.id", index=True)
    cycle_id: Optional[int] = Field(default=None, foreign_key="cycle.id", index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="goal.id", index=True)
    title: str = Field(max_length=255)
    owner: str = Field(default="", max_length=255)
    owner_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    sort_order: int = 0
    # 该目标对应的 Jira issue（每个目标 = 1 个 issue）
    jira_key: str = Field(default="", max_length=64)
    jira_id: str = Field(default="", max_length=64)
    jira_url: str = Field(default="", max_length=512)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KeyResult(SQLModel, table=True):
    """关键结果（KR）：挂在目标下，当前值人工填（纯文本，不算进度）。"""
    __tablename__ = "key_result"
    id: Optional[int] = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goal.id", index=True)
    title: str = Field(max_length=255)
    current_value: str = Field(default="", max_length=255)  # 如 "当前 92%" —— 纯文案，不做计算
    sort_order: int = 0


class Stage(SQLModel, table=True):
    """交付阶段节点：每个目标固定 5 个，与 FIXED_STAGES 一一对应。"""
    __tablename__ = "stage"
    id: Optional[int] = Field(default=None, primary_key=True)
    goal_id: int = Field(foreign_key="goal.id", index=True)
    stage_index: int                            # 0..4
    name: str = Field(max_length=255)
    deliverable: str = Field(default="", max_length=255)
    status: StageStatus = StageStatus.todo      # 标准状态：人工更新
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    jira_key: str = Field(default="", max_length=64)
    note: str = Field(default="", sa_type=Text)          # 备注（业务需求确定 / 方案确定阶段用，带方法论提示）
    deliverables: str = Field(default="", sa_type=Text)  # 产出物列表（JSON：[{name,url}]，用户手填的名称+链接）
    # 审批状态（独立于标准状态；只有管理用户能改。撤销即清空下面三项记录）
    approval_status: ApprovalStatus = ApprovalStatus.pending
    approved_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    approved_at: Optional[datetime] = None
    approve_comment: str = Field(default="", sa_type=Text)  # 审批意见
