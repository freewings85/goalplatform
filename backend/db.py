"""数据库引擎、会话、初始化与种子数据。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from models import (
    FIXED_STAGES,
    AppSetting,
    BusinessLine,
    Cycle,
    CycleStatus,
    Goal,
    KeyResult,
    Stage,
    StageStatus,
    User,
)
from jira_config import DEFAULT_BASE_URL, DEFAULT_ISSUE_TYPE

DB_PATH = Path(__file__).parent / "goalplatform.db"
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def get_session():
    with Session(engine) as session:
        yield session


def make_stages(goal_id: int, plan: list[tuple[str, str, str]] | None = None) -> list[Stage]:
    """为一个目标生成固定 5 个阶段节点。

    plan（可选）：[(status, start, end)]，长度 5，用于种子数据排期。
    """
    stages: list[Stage] = []
    for i, (name, deliverable) in enumerate(FIXED_STAGES):
        status, s, e = StageStatus.todo, None, None
        if plan and i < len(plan):
            st, ss, ee = plan[i]
            status = StageStatus(st)
            s = date.fromisoformat(ss) if ss else None
            e = date.fromisoformat(ee) if ee else None
        stages.append(
            Stage(
                goal_id=goal_id,
                stage_index=i,
                name=name,
                deliverable=deliverable,
                status=status,
                start_date=s,
                end_date=e,
            )
        )
    return stages


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate()
    with Session(engine) as s:
        if s.exec(select(BusinessLine)).first():
            return  # 已初始化，不重复种子
        _seed(s)


def _migrate() -> None:
    """轻量迁移：给已存在的库补新列 + 补种子（保留数据，不重建）。"""
    from security import hash_password

    with engine.connect() as conn:
        stage_cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(stage)").fetchall()]
        if "deliverables" not in stage_cols:
            conn.exec_driver_sql("ALTER TABLE stage ADD COLUMN deliverables TEXT DEFAULT ''")
        if "note" not in stage_cols:
            conn.exec_driver_sql("ALTER TABLE stage ADD COLUMN note TEXT DEFAULT ''")
        # 阶段审批（独立于标准状态）
        if "approval_status" not in stage_cols:
            conn.exec_driver_sql("ALTER TABLE stage ADD COLUMN approval_status VARCHAR DEFAULT 'pending'")
            conn.exec_driver_sql("ALTER TABLE stage ADD COLUMN approved_by_id INTEGER")
            conn.exec_driver_sql("ALTER TABLE stage ADD COLUMN approved_at DATETIME")
            conn.exec_driver_sql("ALTER TABLE stage ADD COLUMN approve_comment TEXT DEFAULT ''")

        user_cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(user)").fetchall()]
        if "role" not in user_cols:
            conn.exec_driver_sql("ALTER TABLE user ADD COLUMN role VARCHAR DEFAULT 'normal'")
            # 现有测试账号 chenzifei 设为管理用户，便于立刻测审批
            conn.exec_driver_sql("UPDATE user SET role='manager' WHERE jira_username='chenzifei'")

        # 管理控制台口令（单独 admin 账号，非 Jira 用户）：缺省播 admin123 的哈希
        has_admin = conn.exec_driver_sql(
            "SELECT 1 FROM app_setting WHERE key='admin_password_hash'"
        ).first()
        if not has_admin:
            conn.exec_driver_sql(
                "INSERT INTO app_setting (key, value) VALUES ('admin_password_hash', :v)",
                {"v": hash_password("admin123")},
            )
        conn.commit()


def _seed(s: Session) -> None:
    """从原型的示例数据播种一份可玩的初始库。"""
    # 全局设置：Jira 站点 + 建 issue 类型（登录、同步都用它）
    s.add(AppSetting(key="jira_base_url", value=DEFAULT_BASE_URL))
    s.add(AppSetting(key="jira_issue_type", value=DEFAULT_ISSUE_TYPE))

    # 示例用户（演示负责人用）。真身份由「用 Jira 账号登录」时创建/认领。
    seed_users = [("李明", "liming"), ("陈磊", "chenlei"), ("王芳", "wangfang"),
                  ("张伟", "zhangwei"), ("周琳", "zhoulin"), ("吴涛", "wutao")]
    for n, local in seed_users:
        s.add(User(name=n, email=f"{local}@goalplatform.local"))
    s.commit()
    user_id = {u.name: u.id for u in s.exec(select(User)).all()}

    # 周期
    q3 = Cycle(name="2026 Q3", start_date=date(2026, 7, 1), end_date=date(2026, 9, 30), status=CycleStatus.active)
    q2 = Cycle(name="2026 Q2", start_date=date(2026, 4, 1), end_date=date(2026, 6, 30), status=CycleStatus.archived)
    q1 = Cycle(name="2026 Q1", start_date=date(2026, 1, 1), end_date=date(2026, 3, 31), status=CycleStatus.archived)
    s.add_all([q3, q2, q1])
    s.commit()

    # 业务线
    bl_quote = BusinessLine(name="保险报价 Agent", description="车险 / 财险智能报价", owner="李明", jira_project_key="AI")
    bl_cs = BusinessLine(name="智能客服 Agent", description="在线客服首解", owner="周琳", jira_project_key="CS")
    bl_claim = BusinessLine(name="理赔审核 Agent", description="理赔材料智能审核", owner="吴涛", jira_project_key="CLAIM")
    s.add_all([bl_quote, bl_cs, bl_claim])
    s.commit()

    def add_goal(bl_id, cycle_id, parent_id, title, owner, win, order, krs, plan):
        start, end = None, None
        if win:
            a, b = [x.strip() for x in win.split("~")]
            start = date.fromisoformat(f"2026-{a}")
            end = date.fromisoformat(f"2026-{b}")
        g = Goal(
            business_line_id=bl_id, cycle_id=cycle_id, parent_id=parent_id,
            title=title, owner=owner, owner_user_id=user_id.get(owner),
            start_date=start, end_date=end, sort_order=order,
        )
        s.add(g)
        s.commit()
        s.refresh(g)
        for i, (kt, kv) in enumerate(krs):
            s.add(KeyResult(goal_id=g.id, title=kt, current_value=kv, sort_order=i))
        for stg in make_stages(g.id, plan):
            s.add(stg)
        s.commit()
        return g

    # 保险报价 Agent 的目标树
    o1 = add_goal(
        bl_quote.id, q3.id, None,
        "把报价 Agent 做成可规模化交付的标品", "李明", "07-01 ~ 09-30", 0,
        [("KR1 · 报价准确率 88% → 95%", "当前 92%"),
         ("KR2 · 平均报价时延 9s → 3s", "当前 5s"),
         ("KR3 · 接入业务方 2 → 8 家", "当前 4 家")],
        [("done", "2026-07-01", "2026-07-08"), ("done", "2026-07-08", "2026-07-15"),
         ("running", "2026-07-15", "2026-08-20"), ("todo", "2026-08-20", "2026-09-10"),
         ("todo", "2026-09-10", "2026-09-30")],
    )
    add_goal(
        bl_quote.id, q3.id, o1.id,
        "O1.1 报价引擎重构（可维护 / 可扩展）", "王芳", "07-01 ~ 08-20", 0,
        [("KR · 单测覆盖率 60% → 90%", "当前 84%")],
        [("done", "2026-07-01", "2026-07-04"), ("done", "2026-07-04", "2026-07-08"),
         ("running", "2026-07-08", "2026-07-30"), ("todo", "2026-07-30", "2026-08-12"),
         ("todo", "2026-08-12", "2026-08-20")],
    )
    add_goal(
        bl_quote.id, q3.id, o1.id,
        "O1.2 多业务方接入（SDK + SOP）", "张伟", "07-10 ~ 09-25", 1,
        [("KR1 · 接入文档完成度 0 → 100%", "当前 40%"),
         ("KR2 · 接入 SDK 就绪 0 → 1", "当前 0")],
        [("done", "2026-07-10", "2026-07-15"), ("running", "2026-07-15", "2026-07-22"),
         ("todo", "2026-07-22", "2026-08-30"), ("todo", "2026-08-30", "2026-09-15"),
         ("todo", "2026-09-15", "2026-09-25")],
    )
    o2 = add_goal(
        bl_quote.id, q3.id, None,
        "降本：单次报价 LLM 成本下降 40%", "陈磊", "07-01 ~ 09-30", 1,
        [("KR1 · 缓存命中率 30% → 80%", "当前 68%"),
         ("KR2 · 单次成本 ¥0.12 → ¥0.07", "当前 ¥0.085")],
        [("done", "2026-07-01", "2026-07-06"), ("done", "2026-07-06", "2026-07-12"),
         ("running", "2026-07-12", "2026-08-25"), ("todo", "2026-08-25", "2026-09-15"),
         ("todo", "2026-09-15", "2026-09-30")],
    )
    add_goal(
        bl_quote.id, q3.id, o2.id,
        "O2.1 Prompt 瘦身 + 缓存策略", "陈磊", "07-05 ~ 09-10", 0,
        [("KR · Prompt token 数下降 0 → 40%", "当前 28%")],
        [("done", "2026-07-05", "2026-07-09"), ("done", "2026-07-09", "2026-07-14"),
         ("running", "2026-07-14", "2026-08-15"), ("todo", "2026-08-15", "2026-08-30"),
         ("todo", "2026-08-30", "2026-09-10")],
    )

    # 智能客服 Agent（一个顶层目标，演示多业务线）
    add_goal(
        bl_cs.id, q3.id, None,
        "客服首解率提升到 80%", "周琳", "07-01 ~ 09-30", 0,
        [("KR · 首解率 62% → 80%", "当前 71%")],
        [("running", "2026-07-01", "2026-07-24"), ("todo", "2026-07-24", "2026-08-10"),
         ("todo", "2026-08-10", "2026-08-30"), ("todo", "2026-08-30", "2026-09-15"),
         ("todo", "2026-09-15", "2026-09-30")],
    )
