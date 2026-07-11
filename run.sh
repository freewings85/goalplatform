#!/usr/bin/env bash
# GoalPlatform 一键启动：装依赖（首次）→ 起后端（自动建库 + 播种）→ 托管前端
# 用法：./run.sh   然后浏览器打开 http://127.0.0.1:8000/
set -euo pipefail
cd "$(dirname "$0")/backend"

if [ ! -d .venv ]; then
  echo "· 首次运行：创建 venv 并安装依赖…"
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
    uv pip install --python .venv/bin/python -r requirements.txt
  else
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
  fi
fi

echo "· 启动：http://127.0.0.1:8000/   （API 文档 /docs，Ctrl+C 退出）"
exec .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --reload
