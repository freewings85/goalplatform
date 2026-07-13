# GoalPlatform · 目标与计划管理平台（原型）

面向 **agent 业务开发** 的目标（OKR）与计划管理系统。从公司 / 业务线的目标出发，递归拆解到子目标，每个目标按**固定 5 阶段交付流水线**推进，人工更新达成度，用一条 **目标 → 计划 → 执行 → 复盘** 的追溯线把关发布。

> 从 [EddPlatform](../eddplatform)（评估驱动研发平台）抽取「目标 / 计划追溯」概念，独立成项目。上层目标 / 计划**原生托管**在本平台；执行层（开发任务）**链接到 Jira**；达成度以**人工更新为主**，预留对接 EddPlatform 评估结果的接口。

## 核心模型

- **业务线（BusinessLine）** — 一条 agent 产品线，目标与计划按业务线分组
- **周期（Cycle）** — 季度 / 月迭代桶，可归档、看历史、结转下一周期
- **目标（Goal）** — 递归成树（大目标 → 子目标，不限层），带负责人 / 周期窗口
- **固定 5 阶段节点** — 每个目标（大 / 小通用）都走同一条流水线，每阶段带开始 / 结束时间、产出物、状态：

  | # | 阶段 | 产出物 |
  |---|------|--------|
  | ① | 业务需求确定 | 业务流程图 + 建模图 |
  | ② | 方案确定 | 方案 spec |
  | ③ | 开发完成 | 测试 spec |
  | ④ | 测试 | 测试报告 |
  | ⑤ | 发布上线 | 上线 |

- **阶段状态** — **人工选择**的枚举：未开始 / 进行中 / 已完成

## 运行

```bash
./run.sh          # 首次自动建 venv、装依赖；之后起服务
```

浏览器打开 **http://127.0.0.1:8000/**（前端由后端同源托管）。
API 文档见 **http://127.0.0.1:8000/docs**。首次启动自动建表并播种示例数据。

> 手动方式：`cd backend && uv pip install --python .venv/bin/python -r requirements.txt && .venv/bin/uvicorn main:app --reload`

### 数据存储（MySQL / SQLite）

生产用 **MySQL**（公司已有实例），本地开发不配任何变量即回退 **SQLite**（`backend/goalplatform.db`）：

| 环境变量 | 说明 | 默认 |
|---|---|---|
| `GOALPLATFORM_MYSQL_HOST` | 设了即启用 MySQL；不设走 SQLite | （空） |
| `GOALPLATFORM_MYSQL_PORT` | 端口 | `3306` |
| `GOALPLATFORM_MYSQL_USER` | 账号 | `root` |
| `GOALPLATFORM_MYSQL_PASSWORD` | 密码 | （空） |
| `GOALPLATFORM_MYSQL_DB` | 库名 | `goalplatform` |

- **库要预先建好**（表由应用启动时自动创建 + 播种）：
  ```sql
  CREATE DATABASE goalplatform CHARACTER SET utf8mb4;
  ```
- MySQL 连不上会**启动失败**（fail fast），不会静默回退 SQLite。
- 用 MySQL 时应用可起多副本；SQLite 是单写库，只能单实例。

## 本版范围（做了减法）

重点是**目标 + 计划的增删改查与持久化**，其余先不做：

- ✅ 业务线 / 周期 / 目标（递归树）/ 固定 5 阶段计划 —— 全链路 CRUD + 持久化
- ✅ **两级导航**：第一层是**业务线 / 周期**；点进某条业务线 = 第二层「**目标计划**」工作台
- ✅ **目标计划工作台**：左侧目标树 + 右侧甘特时间线**同页对齐**，默认全部展开（可收起），周期默认当前、可切换
  - 新建 / 编辑目标时可编辑它的 5 个阶段（各自开始 / 结束 / 状态 / 产出物）；产出物上传在该目标的 Jira issue，已上传的附件会列成可点链接
  - 甘特上拖阶段条改期、拖两端改起止、点条改状态；点目标标题编辑；行内 ＋/🗑 加子目标 / 删除（级联）
  - 月份网格线 + 今天线；阶段条颜色 = 已完成(绿) / 进行中(橙) / 未开始(灰)
- ✅ 不做独立「目标详情」页；**执行、文档、附件都放 Jira**（每个目标一个 issue，点 🔗 跳转）
- ❌ **不做健康度、也不做任何达成度 / 百分比计算与自动汇总**（阶段状态人工设置）

## 用 Jira 账号登录 + Jira 联动（真 Jira Server）

对接**自建 Jira Server / Data Center**（如 8.1.0），直连真站点，无 mock。

- **登录 = 用 Jira 的用户名 + 密码**：系统打开是登录门，填 Jira 账号密码 → 后端拿去 Jira 校验（`/rest/api/2/myself`）→ 通过即登录。用户由登录自动创建/认领。**不做独立系统账号**。
- **凭据安全**：Jira Server 8.1 无 OAuth 3LO、也无 PAT（8.14+ 才有），故用 Basic auth。密码用 Fernet 加密存（`security.py`），任何接口都不回显；会话是签名 cookie。密钥来源依次：环境变量 `GOALPLATFORM_SECRET_KEY` → 密钥文件（本地 `backend/.secret_key`，gitignore）→ 自动生成并存库（`app_setting.secret_key`），生产零配置。
- **每个目标 = 一个 Jira issue**（一对一），建在业务线的「默认 Jira 项目 Key」下（问题类型名可在设置里配，默认「任务」）。目标树父子关系权威存本平台；父目标已同步时在 Jira 侧建一条 `Relates` link 弱表达。指派给目标负责人（若其也用 Jira 登录过）。
- **建目标时「同步到 Jira」开关，默认开**：开=在该项目下建 issue、回填 key/链接；关=事后「立即同步」或「关联已有 issue」。同步失败不阻断目标创建。**执行、文档、附件都在 Jira**，平台只存目标/计划并链接过去。
- **REST v2 客户端**：`jira_client.py`（Basic auth + 纯文本描述，走 `{base}/rest/api/2/...`）。换别的 Jira 只改「站点地址」+ 各人登录名密码，代码不动。

### 配置
在「👥 用户 / 集成」页设 **Jira 站点地址**（默认 `http://192.168.100.130:18080`）和**建 issue 的问题类型**；在「🗂️ 业务线」里给每条线设**默认 Jira 项目 Key**（如 `AI`）。

## 技术栈

- 后端：**Python / FastAPI + SQLModel + MySQL（本地后备 SQLite）+ httpx + cryptography**（`backend/`）
- 前端：**单文件原生 SPA**（`frontend/index.html`，复用原型设计，直连 API；本版从简，未上 React/Vite）
- `prototype/index.html` 为最初的静态高保真原型，保留作设计参照。

## 目录

```
backend/    FastAPI 服务
  models / schemas / serializers / security(加密+会话) / db(种子)
  jira_client(Jira Server REST v2·Basic) / jira_config(站点+凭据) / deps(会话)
  routers/  auth(账号密码登录) · business_lines · cycles · goals(含 Jira 同步/关联) · users · settings(Jira 站点)
frontend/   功能版 SPA（登录门 + 同源托管）
prototype/  最初的静态原型
docs/       设计文档（specs）
run.sh      一键启动
```

## 状态

可运行的最小可用版本（目标 + 计划管理）· 私有仓库。
