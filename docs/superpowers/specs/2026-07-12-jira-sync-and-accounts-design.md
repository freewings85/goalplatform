# 设计:Jira 联动 + 账户体系

日期:2026-07-12 · 分支:`feat/goal-plan-system` · 状态:自主判断出的一版(待用户 review)

> 用户授权「全要,你完全自己判断,按最好方案出一版」。因无法自主注册 Jira 账号(需人工验邮箱),
> 采用 **B 路线**:写真集成代码,用忠实 mock 端到端验证,`站点URL + Token` 做成配置,拿到真站点改配置即切真连。

## 1. 目标

在已建成的「目标+计划管理系统」上增加三件事:

1. **真 Jira 集成**:按 Jira Cloud REST API v3 写真实客户端(建 issue / 查 issue / 建 link / 校验身份)。
2. **建目标时「同步到 Jira」开关(默认开)**:开=自动在 Jira 建对应 issue 并回填 key/链接;关=之后可手动「关联已有 issue」或「立即同步」。
3. **账户体系**:平台有「用户」,每个用户绑各自的 Jira 身份(邮箱 + API Token),Token 加密存;同步用「当前用户」的凭据鉴权,issue 指派给目标负责人对应的 Jira 账号。

## 2. 非目标(本版不做)

- 密码登录 / 注册 / SSO:用**轻量「当前用户」切换**(users 表 + 顶栏切换器 + `X-User-Id` 头),不做鉴权硬化。理由:用户反复强调「简化」,而全套鉴权是独立子系统。硬化留作后续。
- 让 Jira **原生**表达无限层级目标树(Jira 三层封顶且子任务不能嵌套)。改为:树权威关系存本平台,Jira 侧用 issue link 弱关联。
- 双向实时同步 / webhook 回写。本版单向(平台→Jira 建、查),状态仍以平台人工为准。

## 3. 数据模型变更

**新增 `User`**:`id, name, email, jira_email, jira_account_id, jira_token_enc(加密), is_active, created_at`
- `jira_token_enc`:Fernet 对称加密后的密文;API **只写不读**,响应里只回 `has_jira_token: bool`。

**新增 `AppSetting`**(键值):存全局 `jira_base_url`(单一 Jira 站点)。空 = 未配置 → 同步不可用。

**`Goal` 增列**:`jira_key, jira_id, jira_url`(该目标对应的 Jira issue),`owner_user_id`(FK→User,可空;指派用)。

> SQLite 无在线迁移;开发库直接删档重建 + 重新播种(仅示例数据)。生产才需迁移,超出本版范围。

## 4. Jira 映射(关键决定)

**每个目标 = 1 个 Jira issue(类型 Task),一对一。** 目标树的父子关系:
- 权威存本平台 `parent_id`;
- 同步某目标时,若其父目标已有 `jira_key`,则在 Jira 侧建一条 **issue link(类型 `Relates`,内置且必存在)** 把两个 issue 弱关联,作为可视线索。
- 不用 Jira `parent`/子任务字段(避免层级/类型硬约束)。目标 5 阶段的 `stage.jira_key` 保留为可选的执行项手动关联,不变。

## 5. Jira 客户端(真 v3)+ 配置

`backend/jira_client.py`,纯函数式,入参带 `JiraAuth(base_url, email, token)`:
- `create_issue(auth, project_key, summary, description, issue_type="Task", assignee_account_id=None) -> {key,id,url}` → `POST /rest/api/3/issue`,description 用 **ADF** 包装(v3 要求),Basic Auth = `email:token`。
- `get_issue(auth, key) -> {...}` → `GET /rest/api/3/issue/{key}`。
- `add_link(auth, inward_key, outward_key, type="Relates")` → `POST /rest/api/3/issueLink`。
- `myself(auth) -> {accountId,...}` → `GET /rest/api/3/myself`(用于「测试连接」+ 取 accountId)。
- 用 `httpx`(新增依赖)做 HTTP,带超时;明确异常 `JiraError(status, message)`。

配置来源:`jira_base_url` 取自 `AppSetting`;`email/token` 取自**当前用户**(`X-User-Id`)。缺任一 → 视为「未配置」。

## 6. 同步开关 + 手动关联

- `GoalIn` 增 `sync_to_jira: bool = True`。
- **建目标**:本地先落库(永远成功);若 `sync_to_jira` 且当前用户 Jira 配好 → 调 `create_issue`,回填 `jira_key/id/url`,父有 key 则 `add_link`。
- **容错**:Jira 调用失败**不影响目标创建**;响应带 `jira_error` 文案,前端提示「同步失败,可重试」。
- 新端点:
  - `POST /api/goals/{id}/jira/sync` — 事后立即同步(建 issue)。
  - `POST /api/goals/{id}/jira/link {key}` — 手动关联已有 issue(会 `get_issue` 校验并回填 url)。
  - `DELETE /api/goals/{id}/jira/link` — 解除关联(只清平台侧字段,不动 Jira)。
- 用户/设置端点:`GET/POST/PATCH/DELETE /api/users`;`PUT /api/users/{id}/jira-token`(单独设/清 token);`GET/PUT /api/settings/jira`(base_url);`POST /api/users/{id}/jira/test`(测连接)。

## 7. 账户与凭据安全

- 加密密钥:环境变量 `GOALPLATFORM_SECRET_KEY`;缺省则生成并持久化到 `backend/.secret_key`(gitignore)。Fernet 加解密 token。
- Token 永不出现在任何 GET 响应;只回 `has_jira_token`。
- 当前用户:前端存 localStorage,所有请求带 `X-User-Id`;后端 `current_user()` 依赖解析。无用户时播种默认用户。

## 8. 验证用 Jira Mock

`backend/jira_mock.py` = 独立小 FastAPI(端口 8099),忠实实现 `POST /rest/api/3/issue`、`GET /rest/api/3/issue/{key}`、`POST /rest/api/3/issueLink`、`GET /rest/api/3/myself`,返回真实形状(key 形如 `MOCK-1`、id、self url),校验 Basic Auth 存在。把 `jira_base_url` 指向它,端到端跑真集成代码。切真 Jira 仅改 `jira_base_url` + 用户填真 token。

## 9. 前端变更

- 顶栏「李」头像 → **用户切换器**(下拉选当前用户)。
- 新建目标表单加 **☑ 同步到 Jira(默认勾选)**;建完若同步成功,详情/树显示 Jira key(可点开链接)。
- 目标详情:显示 Jira 关联区(已同步→显示 key+链接+解除;未同步→「立即同步 / 关联已有」)。
- 新页面 **用户 / 集成设置**(全局):管理用户、填各自 Jira 邮箱/Token(写入不回显)、「测试连接」;设置 Jira 站点 URL。

## 10. 错误处理

- Jira 未配置:同步按钮给出「先在设置里配 Jira 站点 + 你的 Token」。
- 建 issue 失败:目标已建,提示可重试,不回滚。
- 关联无效 key:`get_issue` 404 → 前端提示「Jira 里没找到该 issue」。

## 11. 验证计划

1. 起 mock(8099)+ 主服务(8000,`jira_base_url=mock`)。
2. curl:建用户→设 token→测连接→建目标(sync=on)→断言回填 mock key→建子目标→断言 issue link→手动关联/解除。
3. Playwright:顶栏切用户、勾选同步建目标看到 key、详情里关联/解除、用户设置页填 token 测连接。
4. 关同步建目标→无 key→详情点「立即同步」→有 key。
5. 全程无 JS 报错;跑完清理回种子态。

## 12. 后续(明确留白)

- 换真 Jira:改 `jira_base_url`,各用户填真 email+token,`myself` 测通即可。
- 登录硬化(密码/SSO)、issue 状态双向同步(webhook)、按目标层级选 Epic/Story 类型、Advanced Roadmaps 多层级——都属后续。

---

## 附录：改为「用 Jira 账号登录」(OAuth 3LO) — 2026-07-12 追加

用户反馈：不想手动建用户/贴 API Token，希望系统打开就有「登录 Jira」链接，登录后即用其 Jira 账号，并顺带解决系统内 Jira 跳转的认证。据此把上文的「手动账户 + API Token」替换为 **Atlassian OAuth 2.0 (3LO)**：

- **登录门**：未登录时前端整屏挡住，只给「用 Atlassian 账号登录」。点击 → `GET /api/auth/login`（带 state 签名 cookie）→ 跳 `{auth_base}/authorize` → 用户授权 → `GET /api/auth/callback` 校验 state、换 token、取身份(`/me`)与站点(`accessible-resources`)、按 accountId/email upsert 用户、下发签名会话 cookie → 回 `/`。
- **不存密码**：会话是 Fernet 签名的 cookie（`security.make_session_token`）。用户由登录自动创建/认领（种子用户按 email 接上）。
- **令牌**：access/refresh token 加密存 user 行；`oauth.valid_access_token` 过期自动用 refresh 续期。Jira 调用改 Bearer，base 走 `{api_base}/ex/jira/{cloudid}`。
- **跳转认证**：登录时用户在浏览器认证过 Atlassian，故同浏览器点 `/browse/KEY` 一般免再登；但那是浏览器自身的 Jira 会话，跨浏览器/无痕仍可能要登（超链接无法注入认证）——已如实说明。
- **本地验证**：`jira_mock.py` 增加 `/authorize`(假授权页)、`/oauth/token`、`/me`、`/oauth/token/accessible-resources`，并把 Jira 数据接口挂到 `/ex/jira/{cloud}/rest/api/3/...`(Bearer)。默认配置指向 mock，开箱即可验证整套登录流程。
- **切真**：一次性在 developer.atlassian.com 注册 OAuth app 拿 client_id/secret，设置里改 auth_base/api_base 为真 Atlassian 域，代码不动。（注册需人工验邮箱，无法自动完成——本次仅用 mock 验证。）
- **被替换**：手动 `POST/PATCH /users`、`/users/{id}/jira-token`、`/users/{id}/jira/test`、全局 `jira_base_url` 设置、顶栏用户切换器 —— 均移除。
