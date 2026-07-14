"""GoalPlatform 后端入口。

运行：
    cd backend && .venv/bin/uvicorn main:app --reload
然后浏览器打开 http://127.0.0.1:8000/
API 文档：http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from db import init_db
from routers import admin, auth, board, business_lines, cycles, goals, settings, users

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # 建表 + 首次种子
    yield


app = FastAPI(title="GoalPlatform API", version="0.1.0", lifespan=lifespan)

# 方便本地分离式前端联调（同源部署时其实用不到）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 先挂 API 路由（更具体，优先匹配）
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(business_lines.router)
app.include_router(cycles.router)
app.include_router(goals.router)
app.include_router(board.router)
app.include_router(users.router)
app.include_router(settings.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# 管理控制台是独立页面（与主 SPA 分开），显式路由到 management.html
@app.get("/management")
def management_page():
    return FileResponse(str(FRONTEND_DIR / "management.html"))


# 再挂静态前端（html=True → "/" 返回 index.html）；放最后，避免盖住 /api
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
