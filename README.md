# GoalPlatform · 目标与计划管理平台（原型）

面向 **agent 业务开发** 的目标（OKR）与计划管理系统。从公司 / 业务线的目标出发，递归拆解到子目标，每个目标按**固定 5 阶段交付流水线**推进，人工更新达成度，用一条 **目标 → 计划 → 执行 → 复盘** 的追溯线把关发布。

> 从 [EddPlatform](../eddplatform)（评估驱动研发平台）抽取「目标 / 计划追溯」概念，独立成项目。上层目标 / 计划**原生托管**在本平台；执行层（开发任务）**链接到 Jira**；达成度以**人工更新为主**，预留对接 EddPlatform 评估结果的接口。

## 核心模型

- **业务线（BusinessLine）** — 一条 agent 产品线，目标与计划按业务线分组
- **周期（Cycle）** — 季度 / 月迭代桶，可归档、看历史、结转下一周期
- **目标（Goal）** — 递归成树（大目标 → 子目标，不限层），带负责人 / 周期窗口 / 健康度
- **关键结果（KR）** — 挂在目标下，人工更新当前值，进度自动算
- **固定 5 阶段节点** — 每个目标（大 / 小通用）都走同一条流水线，每阶段带开始 / 结束时间、产出物、Jira 关联：

  | # | 阶段 | 产出物 |
  |---|------|--------|
  | ① | 业务需求确定 | 业务流程图 + 建模图 |
  | ② | 方案确定 | 方案 spec |
  | ③ | 开发完成 | 测试 spec |
  | ④ | 测试 | 测试报告 |
  | ⑤ | 发布上线 | 上线 |

- **健康度 / 阶段状态** — 全部**人工选择**的枚举（🟢 on-track / 🟡 at-risk / 🔴 off-track；阶段：待开始 / 进行中 / 已完成 / 阻塞）

## 运行

```bash
./run.sh          # 首次自动建 venv、装依赖；之后起服务
```

浏览器打开 **http://127.0.0.1:8000/**（前端由后端同源托管）。
API 文档见 **http://127.0.0.1:8000/docs**。首次启动自动建库并播种示例数据（SQLite，落在 `backend/goalplatform.db`）。

> 手动方式：`cd backend && uv pip install --python .venv/bin/python -r requirements.txt && .venv/bin/uvicorn main:app --reload`

## 本版范围（做了减法）

重点是**目标 + 计划的增删改查与持久化**，其余先不做：

- ✅ 业务线 / 周期 / 目标（递归树）/ KR / 固定 5 阶段计划 —— 全链路 CRUD + 持久化
- ✅ 目标树展开、健康度过滤、按周期切换；目标详情里改 KR、逐阶段排期与关联 Jira Key、加/删子目标（级联删除）
- ❌ **不做任何达成度 / 百分比计算与自动汇总**（健康度、阶段状态改为人工设置）
- ➖ Jira / EddPlatform 仅存 Key、留接口，未真正对接

## 技术栈

- 后端：**Python / FastAPI + SQLModel + SQLite**（`backend/`）
- 前端：**单文件原生 SPA**（`frontend/index.html`，复用原型设计，直连 API；本版从简，未上 React/Vite）
- `prototype/index.html` 为最初的静态高保真原型，保留作设计参照。

## 目录

```
backend/    FastAPI 服务：models / schemas / db(种子) / serializers / routers(business_lines,cycles,goals)
frontend/   功能版 SPA（同源托管）
prototype/  最初的静态原型
run.sh      一键启动
```

## 状态

可运行的最小可用版本（目标 + 计划管理）· 私有仓库。
