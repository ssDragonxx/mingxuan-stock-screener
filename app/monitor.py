"""Strategy persistence and daily monitor runs."""

from __future__ import annotations

import json
import uuid
from datetime import timezone
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .db import get_db, now_iso
from .engine import run_screen
from .providers import get_provider
from .providers.base import DataProvider

CN_TZ = ZoneInfo("Asia/Shanghai")

scheduler = AsyncIOScheduler(timezone=CN_TZ)


def _included_codes(result: dict[str, Any]) -> list[str]:
    return [
        stock["thscode"]
        for stock in result.get("stocks") or []
        if stock.get("status") == "included"
    ]


def _included_pairs(result: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"thscode": stock["thscode"], "name": stock.get("name") or ""}
        for stock in result.get("stocks") or []
        if stock.get("status") == "included"
    ]


async def run_strategy(strategy_id: str, provider: DataProvider) -> dict[str, Any]:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM strategies WHERE id = ?", (strategy_id,))
        strategy = await cursor.fetchone()
        if strategy is None:
            raise ValueError("策略不存在")
        cursor = await db.execute(
            "SELECT * FROM monitor_runs WHERE strategy_id = ? ORDER BY run_at DESC LIMIT 1",
            (strategy_id,),
        )
        last_run = await cursor.fetchone()

    dsl = json.loads(strategy["dsl_json"])
    result = await run_screen(dsl, provider, fetch=True)
    current_codes = _included_codes(result)
    current_pairs = _included_pairs(result)

    previous_codes: list[str] = []
    previous_run_at = None
    previous_success = last_run is not None and last_run["status"] == "success"
    if last_run and last_run["summary_json"]:
        try:
            previous = json.loads(last_run["summary_json"])
            previous_codes = previous.get("included_codes") or []
            previous_run_at = last_run["run_at"]
        except json.JSONDecodeError:
            previous_codes = []

    diff = {
        "first_run": not previous_success,
        "new": []
        if not previous_success
        else [code for code in current_codes if code not in set(previous_codes)],
        "exit": []
        if not previous_success
        else [code for code in previous_codes if code not in set(current_codes)],
        "previous_run_at": previous_run_at,
        "current_count": len(current_codes),
        "previous_count": len(previous_codes) if previous_success else 0,
    }
    run_at = now_iso()
    summary_payload = {
        "summary": result.get("summary"),
        "funnel": result.get("funnel"),
        "included_codes": current_codes,
        "included": current_pairs,
    }
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO monitor_runs(id, strategy_id, run_at, status, summary_json, diff_json, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex[:12],
                strategy_id,
                run_at,
                "success",
                json.dumps(summary_payload, ensure_ascii=False),
                json.dumps(diff, ensure_ascii=False),
                None,
            ),
        )
        await db.execute(
            "UPDATE strategies SET last_run_at = ? WHERE id = ?", (run_at, strategy_id)
        )
        await db.commit()

    return {
        "strategy_id": strategy_id,
        "run_at": run_at,
        "summary": result.get("summary"),
        "funnel": result.get("funnel"),
        "included": current_pairs,
        "diff": diff,
        "data_status": result.get("data_status"),
        "warnings": result.get("warnings"),
    }


async def run_enabled_strategies() -> None:
    provider = get_provider()
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM strategies WHERE monitor_enabled = 1")
        ids = [row["id"] for row in await cursor.fetchall()]
    for strategy_id in ids:
        try:
            await run_strategy(strategy_id, provider)
        except Exception as exc:  # noqa: BLE001
            async with get_db() as db:
                await db.execute(
                    """
                    INSERT INTO monitor_runs(id, strategy_id, run_at, status, summary_json, diff_json, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex[:12],
                        strategy_id,
                        now_iso(),
                        "failed",
                        None,
                        None,
                        str(exc),
                    ),
                )
                await db.commit()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        run_enabled_strategies,
        "cron",
        hour=18,
        minute=30,
        id="daily_monitor",
        replace_existing=True,
    )
    scheduler.start()


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
