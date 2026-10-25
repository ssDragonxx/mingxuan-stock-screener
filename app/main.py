"""FastAPI application entrypoint.

Run:
    uvicorn app.main:app --host 0.0.0.0 --port 8000

The Vue frontend is built into web/dist and served by this app; the Vite dev
server proxies /api to this process during development.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.jobs import jobs
from .api.routes import router
from .config import BASE_DIR, settings
from .data.fuyao_client import FuyaoError
from .db import init_db
from .llm import LLMError
from .monitor import shutdown_scheduler, start_scheduler
from .providers import close_provider
from .providers.base import DataNotReady

WEB_DIR = BASE_DIR / "web"
DIST_DIR = WEB_DIR / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        await jobs.shutdown()
        await close_provider()


app = FastAPI(
    title="明选 · 自然语言选股与策略解释器",
    version="0.2.0",
    description="自然语言 → 可检查条件 → 确定性筛选 → 逐条证据",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DataNotReady)
async def data_not_ready_handler(request: Request, exc: DataNotReady) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "hint": exc.hint,
            }
        },
    )


@app.exception_handler(FuyaoError)
async def fuyao_error_handler(request: Request, exc: FuyaoError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "code": "FUYAO_ERROR",
                "message": exc.message,
                "upstream_code": exc.code,
                "request_id": exc.request_id,
            }
        },
    )


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "LLM_ERROR", "message": str(exc)}},
    )


app.include_router(router)

if (DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

PLACEHOLDER = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>明选 · 前端未构建</title>
<style>body{font-family:-apple-system,"Microsoft YaHei",sans-serif;background:#f5f5f1;color:#161a18;
display:grid;place-items:center;height:100vh;margin:0}main{max-width:680px;padding:32px;background:#fff;
border:1px solid #e3e4de;border-radius:16px}code{background:#f1f2f4;padding:2px 6px;border-radius:5px}</style></head>
<body><main><h1>前端尚未构建</h1>
<p>后端已经启动。请在 <code>web/</code> 目录运行：</p>
<pre><code>npm install
npm run build</code></pre>
<p>然后刷新本页；开发时也可以运行 <code>npm run dev</code>，访问 Vite 的 5173 端口。</p>
<p>API 文档：<a href="/docs">/docs</a> · 健康检查：<a href="/api/health">/api/health</a></p>
</main></body></html>"""


@app.get("/", include_in_schema=False)
async def index():
    target = DIST_DIR / "index.html"
    if target.exists():
        return FileResponse(target)
    return HTMLResponse(PLACEHOLDER)


@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str):
    if path.startswith("api/") or path.startswith("assets/"):
        return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": "Not found"}})
    target = DIST_DIR / "index.html"
    if target.exists():
        return FileResponse(target)
    return HTMLResponse(PLACEHOLDER)
