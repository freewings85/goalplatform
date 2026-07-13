#!/usr/bin/env bash
# Jenkins 发布脚本（构建机执行）：构建镜像 → 推仓库 → SSH 到目标机重启容器
# 参照 mainagent 的发布方式改的；差异见文件底部注释。
set -euo pipefail

dockertag=$(date +"%Y%m%d%H%M")
projectname="com.celiang.hlsc.service.ai.goalplatform"
dockerimage="registry.cn-shanghai.aliyuncs.com/51cjml/test-${projectname}:${dockertag}"
deployhost="root@192.168.100.108"

# ---- MySQL 连接（建议在 Jenkins 里用「凭据 + 环境变量」注入，别写死在脚本里）----
# 库要先建好：CREATE DATABASE goalplatform CHARACTER SET utf8mb4;（表由应用启动自动建）
MYSQL_HOST="${GOALPLATFORM_MYSQL_HOST:?请在 Jenkins 环境里配置 GOALPLATFORM_MYSQL_HOST}"
MYSQL_PORT="${GOALPLATFORM_MYSQL_PORT:-3306}"
MYSQL_USER="${GOALPLATFORM_MYSQL_USER:?请配置 GOALPLATFORM_MYSQL_USER}"
MYSQL_PASSWORD="${GOALPLATFORM_MYSQL_PASSWORD:?请配置 GOALPLATFORM_MYSQL_PASSWORD}"
MYSQL_DB="${GOALPLATFORM_MYSQL_DB:-goalplatform}"

# ---- 构建 + 推送（Dockerfile 在仓库根目录）----
docker build -f Dockerfile -t "${dockerimage}" .
docker push "${dockerimage}"

# ---- 部署：删旧容器，起新容器（无状态，不挂任何卷）----
ssh "${deployhost}" "docker rm -f ${projectname} || true"
ssh "${deployhost}" "docker run -itd --restart=always \
  -e TZ=Asia/Shanghai \
  -e GOALPLATFORM_MYSQL_HOST='${MYSQL_HOST}' \
  -e GOALPLATFORM_MYSQL_PORT='${MYSQL_PORT}' \
  -e GOALPLATFORM_MYSQL_USER='${MYSQL_USER}' \
  -e GOALPLATFORM_MYSQL_PASSWORD='${MYSQL_PASSWORD}' \
  -e GOALPLATFORM_MYSQL_DB='${MYSQL_DB}' \
  --name=${projectname} --net=host \
  ${dockerimage}"

# ---- 发布后冒烟：等健康检查通过 ----
ssh "${deployhost}" 'for i in $(seq 1 15); do
  curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && echo "health OK" && exit 0
  sleep 2
done; echo "health check FAILED"; docker logs --tail 50 '"${projectname}"'; exit 1'

# 与 mainagent 模板的差异说明：
# - 没有 ACTIVE=test：本项目所有配置都走 GOALPLATFORM_* 环境变量，没有 profile 概念
# - 没挂 /app/logs：应用日志走 stdout，用 `docker logs com.celiang...` 看
# - 不挂任何卷：数据在 MySQL；加密密钥首次启动自动生成并存 MySQL（app_setting.secret_key），
#   容器完全无状态。若想显式控制密钥，加 -e GOALPLATFORM_SECRET_KEY=<Fernet key> 即可（优先生效）
# - --net=host：服务占目标机 8000 端口；被占用的话改走端口映射：
#     去掉 --net=host，加 -p 8000:8000（宿主端口按需改左边）
# - docker rm -f 加了 || true：首次发布没有旧容器时不至于失败