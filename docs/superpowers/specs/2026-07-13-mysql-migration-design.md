# 数据存储从 SQLite 迁移到 MySQL — 设计

日期:2026-07-13

## 背景与需求

- 现状:FastAPI + SQLModel,嵌入式 SQLite(`backend/goalplatform.db`,Docker 里落 `/data` 卷)。
- 目标:生产连**公司已有的 MySQL 实例**;**保留 SQLite 作为本地开发后备**(不配 MySQL 环境变量即用 SQLite)。
- 现有 SQLite 数据**不迁移**,MySQL 建库后由现有种子逻辑重新初始化。

## 连接配置(方案 B:拆开的环境变量)

| 变量 | 说明 | 默认 |
|---|---|---|
| `GOALPLATFORM_MYSQL_HOST` | 设了即启用 MySQL;不设走 SQLite | (空) |
| `GOALPLATFORM_MYSQL_PORT` | 端口 | 3306 |
| `GOALPLATFORM_MYSQL_USER` | 账号 | root |
| `GOALPLATFORM_MYSQL_PASSWORD` | 密码 | (空) |
| `GOALPLATFORM_MYSQL_DB` | 库名 | goalplatform |

- 用 `sqlalchemy.URL.create("mysql+pymysql", ...)` 拼连接串(密码特殊字符安全),`charset=utf8mb4`。
- 引擎参数:`pool_pre_ping=True`、`pool_recycle=3600`(防服务器掐空闲连接)。
- MySQL 连不上 → 启动即失败(fail fast),**不**静默回退 SQLite;回退只由「是否配置 HOST」决定。

## 模型字段(models.py)

MySQL 的 VARCHAR 必须有长度,所有 `str` 字段显式声明:

- 普通短字段(name/title/owner/email 等):`max_length=255`
- 短标识(`AppSetting.key` 主键、`jira_key`、`jira_id`、`jira_project_key`):`max_length=64`
- URL(`jira_url`):`max_length=512`
- 长文本改 TEXT(`sa_type=Text`):`Stage.note`、`Stage.deliverables`、`Stage.approve_comment`、`BusinessLine.description`、`User.jira_password_enc`、`AppSetting.value`
- 枚举字段由 SQLModel 映射为 SQLAlchemy Enum,MySQL 下是原生 ENUM,无需长度

对 SQLite 无副作用(SQLite 不强制 VARCHAR 长度)。

## 迁移逻辑(db.py `_migrate()`)

- `PRAGMA table_info` 换成 SQLAlchemy `inspect(engine).get_columns()`(方言通用)。
- 补列的 `ALTER TABLE` 分支只在 **SQLite 方言**下执行 —— MySQL 是全新库,`create_all` 直接建全表,不存在旧表补列。
- `admin_password_hash` 种子改为 ORM 写法,两种方言都跑。

## 依赖与部署

- `requirements.txt` 加 `pymysql`(纯 Python 驱动)。
- `docker-compose.yml`:透传 5 个 MySQL 环境变量;`/data` 卷保留(加密密钥 + SQLite 后备);更新「单写库」注释(用 MySQL 时可多副本)。
- `README`:说明需预先在 MySQL 上 `CREATE DATABASE goalplatform CHARACTER SET utf8mb4`,表由应用启动自动建。

## 验证

1. 不设 MySQL 变量启动 → SQLite 照常(回归)。
2. 本地临时 MySQL 8 容器 + 环境变量启动 → 建表、种子、登录、增删改查、审批流正常。
