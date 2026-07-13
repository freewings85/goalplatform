# GoalPlatform —— 单容器：FastAPI 后端（同时托管前端静态页）+ 嵌入式 SQLite
# 不需要单独的数据库服务；数据（SQLite 库 + 加密密钥）落在挂载卷 /data。
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

# 数据落到卷：重启 / 重发布都不丢
#  - GOALPLATFORM_DB_PATH         SQLite 库路径
#  - GOALPLATFORM_SECRET_KEY_FILE 自动生成的加密密钥落盘位置（若未显式给 KEY）
#  也可用 GOALPLATFORM_SECRET_KEY 直接注入一个固定密钥（推荐，见 README/compose）
ENV GOALPLATFORM_DB_PATH=/data/goalplatform.db \
    GOALPLATFORM_SECRET_KEY_FILE=/data/.secret_key
VOLUME ["/data"]

WORKDIR /app/backend
EXPOSE 8000

# 健康检查用内置 /api/health（slim 镜像没 curl，用 python）
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

# 生产启动：绑 0.0.0.0，不加 --reload
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
