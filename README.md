# GoalPlatform · 目标与计划管理平台（原型）

面向 **agent 业务开发** 的目标（OKR）与计划管理系统。从公司 / 业务线的目标出发，递归拆解到子目标，每个目标按**固定 5 阶段交付流水线**推进，人工更新达成度，用一条 **目标 → 计划 → 执行 → 复盘** 的追溯线把关发布。

> 从 [EddPlatform](../eddplatform)（评估驱动研发平台）抽取「目标 / 计划追溯」概念，独立成项目。上层目标 / 计划**原生托管**在本平台；执行层（开发任务）**链接到 Jira**；达成度以**人工更新为主**，预留对接 EddPlatform 评估结果的接口。

## 核心模型

- **业务线（BusinessLine）** — 一条 agent 产品线，目标与计划按业务线分组
- **周期（Cycle）** — 季度 / 月迭代桶，可归档、看历史、结转下一周期
- **目标（Goal）** — 递归成树（大目标 → 子目标，不限层），带负责人 / 周期窗口 / 健康度
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

- ✅ 业务线 / 周期 / 目标（递归树）/ 固定 5 阶段计划 —— 全链路 CRUD + 持久化
- ✅ **一个「目标计划」工作台**：左侧目标树 + 右侧甘特时间线**同页对齐**，从时间维度直观看到各目标 5 阶段的进度与状态
  - 点甘特上的阶段条 → 改状态 / 排期；点目标标题 → 编辑目标；行内 ＋/🗑 加子目标 / 删除（级联）
  - 顶部切业务线、按健康度过滤、按周期切换；月份网格线 + 今天线；阶段条颜色 = 已完成 / 进行中 / 阻塞 / 待开始
- ✅ 不做独立「目标详情」页；**执行、文档、附件都放 Jira**（每个目标一个 issue，点 🔗 跳转）
- ❌ **不做任何达成度 / 百分比计算与自动汇总**（健康度、阶段状态改为人工设置）

## 用 Jira 账号登录（OAuth）+ Jira 联动

- **登录**：系统打开是一个登录门，点「用 Atlassian 账号登录」→ 走 **Atlassian OAuth 2.0 (3LO)** → 回来即登录。**平台不存密码**；用户按 Atlassian accountId 自动创建/认领。登录后你的 Jira 跳转链接通常也免再登（同浏览器已有 Atlassian 会话）。
- **每个目标 = 一个 Jira issue**（一对一）。目标树父子关系权威存本平台；父目标已同步时在 Jira 侧建一条 `Relates` link 弱表达（Jira 原生三层封顶、子任务不能嵌套，故不强求它表达无限层级树）。
- **建目标时「同步到 Jira」开关，默认开**：开=用你登录的授权在该业务线项目下建 issue、回填 key/链接；关=事后可「立即同步」或「关联已有 issue」。同步失败不阻断目标创建。
- **令牌安全**：OAuth access/refresh token 用 Fernet 加密存（`security.py`，密钥在 `backend/.secret_key`，gitignore），任何接口都不回显；会话是签名 cookie，不是密码。
- **真集成、可切换**：`jira_client.py` 按 Jira Cloud REST v3（Bearer + ADF）实现，走 `api.atlassian.com/ex/jira/{cloudid}`。设置里填 **client_id/secret + auth/api base** 即生效。

### 先用本地 mock 验证（无需注册、无需真 Atlassian）
`backend/jira_mock.py` 同时模拟了 Atlassian 的登录/授权（`/authorize`、`/oauth/token`、`/me`）和 Jira 数据接口。默认配置已指向它，开箱即可跑通「登录 → 拿账号 → 建 issue → 跳转」：
```bash
cd backend && .venv/bin/uvicorn jira_mock:app --port 8099   # 另开一个终端起 mock
# 然后打开 http://127.0.0.1:8000/ ，点登录，在假授权页选个身份即可
```

### 切到真 Jira（需你做一次性登记）
1. 去 `developer.atlassian.com` 建一个 **OAuth 2.0 (3LO)** 应用，勾权限 `read:me read:jira-work write:jira-work offline_access`，回调填 `http://<你的域名>/api/auth/callback`，拿到 **client_id + client_secret**。
2. 在「👥 用户 / 集成」页把 `auth_base` 改 `https://auth.atlassian.com`、`api_base` 改 `https://api.atlassian.com`，填入 client_id/secret。代码不用改。

## 技术栈

- 后端：**Python / FastAPI + SQLModel + SQLite + httpx + cryptography**（`backend/`）
- 前端：**单文件原生 SPA**（`frontend/index.html`，复用原型设计，直连 API；本版从简，未上 React/Vite）
- `prototype/index.html` 为最初的静态高保真原型，保留作设计参照。

## 目录

```
backend/    FastAPI 服务
  models / schemas / serializers / security(加密+会话) / db(种子)
  oauth(Atlassian 3LO) / jira_client(真v3·Bearer) / jira_config / jira_mock(登录+数据 mock) / deps(会话)
  routers/  auth(登录) · business_lines · cycles · goals(含 Jira 同步/关联) · users · settings(OAuth 配置)
frontend/   功能版 SPA（登录门 + 同源托管）
prototype/  最初的静态原型
docs/       设计文档（specs）
run.sh      一键启动
```

## 状态

可运行的最小可用版本（目标 + 计划管理）· 私有仓库。
