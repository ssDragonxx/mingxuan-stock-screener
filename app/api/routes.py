"""FastAPI routes for the 明选 product."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from ..config import settings
from ..db import get_db, now_iso
from ..engine import diagnose, run_preview, run_screen
from ..facts import build_facts, template_explanation
from ..intent import parse_intent
from ..llm import LLMError, explain_with_deepseek, parse_with_deepseek
from ..monitor import run_strategy
from ..providers import get_provider
from ..schemas import (
    DiagnoseRequest,
    ExplainRequest,
    ParseRequest,
    ScreenRequest,
    StrategyCreateRequest,
)
from ..validator import validate_dsl
from .jobs import jobs

router = APIRouter(prefix="/api")


def _validated(dsl: dict[str, Any], universe: str = "all_a_share") -> dict[str, Any]:
    valid, errors = validate_dsl(dsl, universe)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DSL",
                "message": "DSL 校验失败",
                "errors": errors,
            },
        )
    return valid


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "live" if settings.live_data else "mock",
        "llm_enabled": settings.llm_enabled,
        "version": "0.2.0",
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    provider = get_provider()
    return await provider.get_status()


@router.post("/parse")
async def parse(payload: ParseRequest) -> dict[str, Any]:
    provider = get_provider()
    data_status = await provider.get_status()
    result: dict[str, Any] | None = None
    fallback_reason: str | None = None

    if settings.deepseek_api_key:
        try:
            result = await parse_with_deepseek(payload.query, payload.universe)
        except LLMError as exc:
            fallback_reason = str(exc)
    if result is None:
        result = parse_intent(payload.query, payload.universe)
        if fallback_reason:
            result.setdefault("meta", {})["fallback_reason"] = fallback_reason
    result["data_status"] = data_status
    result.setdefault("meta", {})["llm_enabled"] = settings.llm_enabled
    return result


@router.post("/preview")
async def preview(payload: ScreenRequest) -> dict[str, Any]:
    dsl = _validated(payload.dsl)
    provider = get_provider()
    result = await run_preview(dsl, provider)
    return {
        "summary": result["summary"],
        "funnel": result["funnel"],
        "warnings": result["warnings"],
        "data_status": result["data_status"],
        "meta": result["meta"],
    }


@router.post("/screen")
async def screen(payload: ScreenRequest) -> dict[str, Any]:
    dsl = _validated(payload.dsl)
    provider = get_provider()
    return await run_screen(dsl, provider, fetch=True)


@router.post("/screen/jobs")
async def create_screen_job(payload: ScreenRequest) -> dict[str, Any]:
    dsl = _validated(payload.dsl)
    provider = get_provider()
    job = await jobs.create(dsl, provider)
    return {"job_id": job.id}


@router.get("/screen/jobs/{job_id}")
async def get_screen_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "JOB_NOT_FOUND", "message": "任务不存在或已过期"},
        )
    return job.to_dict(include_result=True)


@router.post("/diagnose")
async def diagnose_stock(payload: DiagnoseRequest) -> dict[str, Any]:
    dsl = _validated(payload.dsl)
    provider = get_provider()
    stock = await diagnose(payload.query, dsl, provider)
    if stock is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "STOCK_NOT_FOUND",
                "message": "未找到该股票；真实模式下请先在本地初始化全市场代码表",
            },
        )
    return {"stock": stock}


@router.post("/explain")
async def explain_stock(payload: ExplainRequest) -> dict[str, Any]:
    dsl = _validated(payload.dsl)
    provider = get_provider()
    stock = await diagnose(payload.query, dsl, provider)
    if stock is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "STOCK_NOT_FOUND", "message": "未找到该股票"},
        )
    try:
        history = await provider.get_financial_history(stock["thscode"], periods=4)
    except Exception:  # noqa: BLE001 - history is an enrichment, not fatal
        history = []
    facts = build_facts(stock, history, mode=provider.mode)
    explanation = await explain_with_deepseek(stock, facts)
    if explanation is None:
        explanation = template_explanation(stock, facts)
        explanation["fallback_reason"] = (
            "DeepSeek 调用失败或数字校验未通过"
            if settings.deepseek_api_key
            else "未配置 DeepSeek"
        )
    return {"stock": stock, "explanation": explanation}


# ---------------------------------------------------------------------------
# Strategies / monitor
# ---------------------------------------------------------------------------
@router.get("/strategies")
async def list_strategies() -> dict[str, Any]:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, name, query, created_at, monitor_enabled, last_run_at
            FROM strategies ORDER BY created_at DESC LIMIT 50
            """
        )
        rows = [dict(row) for row in await cursor.fetchall()]
    return {"items": rows}


@router.post("/strategies")
async def create_strategy(payload: StrategyCreateRequest) -> dict[str, Any]:
    dsl = _validated(payload.dsl)
    strategy_id = uuid.uuid4().hex[:12]
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO strategies(id, name, query, dsl_json, data_version, created_at, monitor_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_id,
                payload.name,
                payload.query,
                json.dumps(dsl, ensure_ascii=False),
                settings.financial_report,
                now_iso(),
                1 if payload.monitor_enabled else 0,
            ),
        )
        await db.commit()
    return {"id": strategy_id, "monitor_enabled": payload.monitor_enabled}


@router.post("/strategies/{strategy_id}/run")
async def run_strategy_route(strategy_id: str) -> dict[str, Any]:
    provider = get_provider()
    try:
        return await run_strategy(strategy_id, provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "STRATEGY_NOT_FOUND", "message": str(exc)},
        ) from exc


@router.get("/strategies/{strategy_id}/runs")
async def strategy_runs(strategy_id: str, limit: int = 20) -> dict[str, Any]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM monitor_runs WHERE strategy_id = ? ORDER BY run_at DESC LIMIT ?",
            (strategy_id, max(1, min(limit, 100))),
        )
        items = []
        for row in await cursor.fetchall():
            item = dict(row)
            for key in ("summary_json", "diff_json"):
                if item.get(key):
                    try:
                        item[key] = json.loads(item[key])
                    except json.JSONDecodeError:
                        pass
            items.append(item)
    return {"items": items}


@router.post("/admin/ingest")
async def admin_ingest(x_admin_token: str = Header(default="")) -> dict[str, Any]:
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "ADMIN_TOKEN 未配置或 header 不正确"},
        )
    from ..data.ingest import run_all

    asyncio.create_task(run_all(include_dump=True))
    return {"status": "started", "message": "数据初始化已在后台启动，请查看服务日志"}
