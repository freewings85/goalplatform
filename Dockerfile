# GoalPlatform —— 单容器：FastAPI 后端（同时托管前端静态页）
# 存储：设 GOALPLATFORM_MYSQL_* 连公司 MySQL（生产，容器无状态）；不设回退嵌入式 SQLite。
# 加密密钥自动生成并存 MySQL（app_setting），无需挂载；也可用 GOALPLATFORM_SECRET_KEY 显式指定。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（单独一层，利用构建缓存）
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# 拷贝应用（前端 + 后端）；.dockerignore 已排除 .venv / *.db / .secret_key / __pycache__
COPY backend/ backend/
COPY frontend/ frontend/

# 环境变量：
#  - GOALPLATFORM_MYSQL_HOST 等   MySQL 连接（见 docker-compose.yml；设 HOST 即启用，此时无任何本地状态）
#  - GOALPLATFORM_DB_PATH         SQLite 后备库路径（仅未配 MySQL 时用到；要持久化就把 /data 挂出去）
ENV GOALPLATFORM_DB_PATH=/data/goalplatform.db

WORKDIR /app/backend
EXPOSE 8000

# 健康检查用内置 /api/health（slim 镜像没 curl，用 python）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

# 生产启动：绑 0.0.0.0，不加 --reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
