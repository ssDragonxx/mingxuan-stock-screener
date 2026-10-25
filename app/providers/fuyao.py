"""Live Fuyao provider: SQLite universe + on-demand financial fetch."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from ..config import settings
from ..db import get_db, latest_version
from ..field_registry import FIELD_META
from .base import DataNotReady, DataProvider, ProgressCallback
from ..data.fuyao_client import FuyaoClient, FuyaoError

CN_TZ = timezone(timedelta(hours=8))
INDEX_MAP = {
    "csi300": "000300.SH",
    "csi500": "000905.SH",
    "csi1000": "000852.SH",
}


def _period_end(report: str) -> str | None:
    try:
        year, quarter = report.split("-")
        ends = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}
        return f"{year}-{ends[quarter]}"
    except (ValueError, KeyError):
        return None


def _report_label(report: str | None) -> str | None:
    if not report:
        return None
    try:
        year, quarter = report.split("-")
        return f"{year} " + {"1": "一季报", "2": "中报", "3": "三季报", "4": "年报"}[quarter]
    except (ValueError, KeyError):
        return report


def _previous_report(report: str) -> str | None:
    try:
        year, quarter = report.split("-")
        year_i = int(year)
        quarter_i = int(quarter)
    except (ValueError, TypeError):
        return None
    if quarter_i > 1:
        return f"{year_i}-{quarter_i - 1}"
    return f"{year_i - 1}-4"


def _report_sequence(report: str, periods: int) -> list[str]:
    result: list[str] = []
    current: str | None = report
    for _ in range(max(1, periods)):
        if not current:
            break
        result.append(current)
        current = _previous_report(current)
    return result


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    item = dict(row)
    if item.get("turnover") is not None:
        item["turnover"] = round(float(item["turnover"]) / 1e8, 4)
    if item.get("avg_turnover_20d") is not None:
        item["avg_turnover_20d"] = round(float(item["avg_turnover_20d"]) / 1e8, 4)
    if item.get("above_ma60") is not None:
        item["above_ma60"] = bool(item["above_ma60"])
    return item


def _normalize_value(field: str, value: Any) -> Any:
    """Normalize Fuyao indicator units to the field registry units."""
    if value is None:
        return None
    if field == "net_profit_cash_content":
        try:
            return round(float(value) / 100, 4)
        except (TypeError, ValueError):
            return None
    return value


class FuyaoProvider(DataProvider):
    mode = "live"

    def __init__(self) -> None:
        self.client = FuyaoClient(settings.fuyao_api_key, settings.fuyao_base_url)
        self._write_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.close()

    # ------------------------------------------------------------------
    # Universe
    # ------------------------------------------------------------------
    async def get_universe(self, dsl: dict) -> list[dict[str, Any]]:
        universe = dsl.get("universe") or {}
        universe_type = universe.get("type") or "all_a_share"
        async with get_db() as db:
            cursor = await db.execute("SELECT COUNT(*) AS n FROM tickers")
            ticker_count = int((await cursor.fetchone())["n"])
            if ticker_count == 0:
                raise DataNotReady(
                    "本地数据尚未初始化，无法筛选全市场。",
                    "在 .env 配置 FUYAO_API_KEY 后运行：python -m app.data.ingest --all",
                )
            if universe_type in INDEX_MAP:
                index_code = INDEX_MAP[universe_type]
                cursor = await db.execute(
                    "SELECT COUNT(*) AS n FROM index_members WHERE index_code = ?",
                    (index_code,),
                )
                member_count = int((await cursor.fetchone())["n"])
                if member_count == 0:
                    raise DataNotReady(
                        f"{universe_type} 成分股尚未初始化。",
                        "运行：python -m app.data.ingest --all",
                    )

            where = ["1=1"]
            params: list[Any] = []
            if universe.get("exclude_st", True):
                where.append("(name IS NULL OR (name NOT LIKE '%ST%' AND name NOT LIKE '%退%'))")
            if universe.get("exclude_suspended", True):
                where.append("last_price IS NOT NULL AND last_price > 0")
            if universe.get("exclude_bse", True):
                where.append("(exchange IS NULL OR exchange != 'BJ')")
            min_days = universe.get("min_listed_days", 250)
            if min_days:
                where.append("(list_date IS NULL OR list_date <= date('now', ?))")
                params.append(f"-{int(min_days)} days")
            if universe_type in INDEX_MAP:
                where.append(
                    "thscode IN (SELECT thscode FROM index_members WHERE index_code = ?)"
                )
                params.append(INDEX_MAP[universe_type])

            sql = "SELECT * FROM universe_view WHERE " + " AND ".join(where)
            cursor = await db.execute(sql, params)
            rows = [dict(row) for row in await cursor.fetchall()]
        return [_row_to_dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Financials (on demand)
    # ------------------------------------------------------------------
    async def _load_cached(
        self, codes: list[str], report: str
    ) -> dict[str, dict[str, Any]]:
        cached: dict[str, dict[str, Any]] = {}
        async with get_db() as db:
            for start in range(0, len(codes), 400):
                chunk = codes[start : start + 400]
                placeholders = ",".join("?" for _ in chunk)
                cursor = await db.execute(
                    f"""
                    SELECT thscode, index_id, value
                    FROM financial_indicators
                    WHERE report = ? AND thscode IN ({placeholders})
                    """,
                    [report, *chunk],
                )
                for row in await cursor.fetchall():
                    cached.setdefault(row["thscode"], {})[row["index_id"]] = row["value"]
        return cached

    async def get_financials(
        self,
        codes: list[str],
        fields: set[str],
        progress: ProgressCallback | None = None,
    ) -> dict[str, dict[str, Any]]:
        if not codes:
            return {}
        report = settings.financial_report or "2026-2"
        index_ids = {
            FIELD_META[field]["index_id"]
            for field in fields
            if field in FIELD_META and FIELD_META[field].get("index_id")
        }
        cached = await self._load_cached(codes, report)

        missing: list[str] = []
        for code in codes:
            values = cached.get(code) or {}
            if not values or any(index_id not in values for index_id in index_ids):
                missing.append(code)

        used_report: dict[str, str] = {code: report for code in codes}
        fetched: dict[str, dict[str, Any]] = {}
        if missing:
            semaphore = asyncio.Semaphore(max(settings.fetch_concurrency, 1))
            total = len(missing)
            done = 0

            async def fetch_one(code: str) -> None:
                nonlocal done
                async with semaphore:
                    try:
                        data = await self.client.financial_indicators(code, report)
                        indicators = data.get("indicators") or {}
                        current_report = report
                        if not any(value is not None for value in indicators.values()):
                            previous = _previous_report(report)
                            if previous:
                                data_prev = await self.client.financial_indicators(code, previous)
                                prev_indicators = data_prev.get("indicators") or {}
                                if any(value is not None for value in prev_indicators.values()):
                                    indicators = prev_indicators
                                    current_report = previous
                        fetched[code] = indicators
                        used_report[code] = current_report
                    except FuyaoError as exc:
                        fetched[code] = {"__error__": str(exc)}
                    finally:
                        done += 1
                        if progress:
                            await progress(
                                "financials",
                                done,
                                total,
                                f"按需取财务 {done}/{total}",
                            )

            await asyncio.gather(*(fetch_one(code) for code in missing))

            # Persist fetched indicators in one batch.
            rows: list[tuple] = []
            fetched_at = datetime.now(CN_TZ).isoformat(timespec="seconds")
            for code, indicators in fetched.items():
                if "__error__" in indicators:
                    continue
                current_report = used_report.get(code, report)
                period_end = _period_end(current_report)
                for index_id, value in indicators.items():
                    rows.append((code, current_report, index_id, value, period_end, fetched_at))
            if rows:
                async with self._write_lock:
                    async with get_db() as db:
                        await db.executemany(
                            """
                            INSERT INTO financial_indicators(thscode, report, index_id, value, period_end, fetched_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(thscode, report, index_id) DO UPDATE SET
                              value=excluded.value, period_end=excluded.period_end, fetched_at=excluded.fetched_at
                            """,
                            rows,
                        )
                        await db.commit()
                for code, indicators in fetched.items():
                    if "__error__" not in indicators:
                        cached.setdefault(code, {}).update(indicators)

        result: dict[str, dict[str, Any]] = {}
        for code in codes:
            values = cached.get(code) or {}
            mapped: dict[str, Any] = {}
            for field in fields:
                meta = FIELD_META.get(field) or {}
                index_id = meta.get("index_id")
                mapped[field] = _normalize_value(field, values.get(index_id)) if index_id else None
            mapped["_report"] = used_report.get(code, report)
            mapped["_period_end"] = _period_end(mapped["_report"])
            result[code] = mapped
        return result

    async def get_cached_financials(
        self,
        codes: list[str],
        fields: set[str],
    ) -> dict[str, dict[str, Any]]:
        report = settings.financial_report or "2026-2"
        cached = await self._load_cached(codes, report)
        result: dict[str, dict[str, Any]] = {}
        for code in codes:
            values = cached.get(code) or {}
            mapped: dict[str, Any] = {}
            for field in fields:
                meta = FIELD_META.get(field) or {}
                index_id = meta.get("index_id")
                mapped[field] = _normalize_value(field, values.get(index_id)) if index_id else None
            mapped["_report"] = report
            mapped["_period_end"] = _period_end(report)
            result[code] = mapped
        return result

    async def get_financial_history(
        self,
        code: str,
        periods: int = 4,
    ) -> list[dict[str, Any]]:
        report = settings.financial_report or "2026-2"
        history: list[dict[str, Any]] = []
        for report_item in _report_sequence(report, periods):
            cached = await self._load_cached([code], report_item)
            values = cached.get(code) or {}
            if not any(value is not None for value in values.values()):
                try:
                    data = await self.client.financial_indicators(code, report_item)
                    fetched = data.get("indicators") or {}
                except FuyaoError as exc:
                    history.append(
                        {
                            "report": report_item,
                            "label": _report_label(report_item),
                            "period_end": _period_end(report_item),
                            "indicators": {},
                            "error": str(exc),
                        }
                    )
                    continue
                if any(value is not None for value in fetched.values()):
                    values = fetched
                    fetched_at = datetime.now(CN_TZ).isoformat(timespec="seconds")
                    rows = [
                        (
                            code,
                            report_item,
                            index_id,
                            value,
                            _period_end(report_item),
                            fetched_at,
                        )
                        for index_id, value in fetched.items()
                    ]
                    if rows:
                        async with self._write_lock:
                            async with get_db() as db:
                                await db.executemany(
                                    """
                                    INSERT INTO financial_indicators(thscode, report, index_id, value, period_end, fetched_at)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(thscode, report, index_id) DO UPDATE SET
                                      value=excluded.value, period_end=excluded.period_end, fetched_at=excluded.fetched_at
                                    """,
                                    rows,
                                )
                                await db.commit()
            history.append(
                {
                    "report": report_item,
                    "label": _report_label(report_item),
                    "period_end": _period_end(report_item),
                    "indicators": values,
                }
            )
        return history

    # ------------------------------------------------------------------
    # Single stock (diagnose)
    # ------------------------------------------------------------------
    async def get_stock(self, query: str) -> dict[str, Any] | None:
        q = (query or "").strip()
        if not q:
            return None
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT * FROM universe_view
                WHERE lower(thscode) = lower(?) OR ticker = ? OR name = ?
                LIMIT 1
                """,
                (q, q, q),
            )
            row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    async def get_status(self) -> dict[str, Any]:
        async with get_db() as db:
            async def count(table: str) -> int:
                cursor = await db.execute(f"SELECT COUNT(*) AS n FROM {table}")
                return int((await cursor.fetchone())["n"])

            tickers = await count("tickers")
            snapshot = await count("snapshot")
            valuation = await count("valuation")
            tech = await count("tech_factors")
            industries = await count("industry_map")
            dividends = await count("dividend")
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT thscode) AS n FROM financial_indicators WHERE report = ?",
                (settings.financial_report,),
            )
            financial_stocks = int((await cursor.fetchone())["n"])
            cursor = await db.execute("SELECT MAX(as_of) AS as_of FROM snapshot")
            quote_as_of = (await cursor.fetchone())["as_of"]
            cursor = await db.execute("SELECT MAX(as_of) AS as_of FROM valuation")
            valuation_as_of = (await cursor.fetchone())["as_of"]
            cursor = await db.execute("SELECT MAX(as_of) AS as_of FROM tech_factors")
            tech_as_of = (await cursor.fetchone())["as_of"]

        versions = {}
        for dataset in ("tickers", "snapshot", "valuation", "industry", "tech_factors", "dividend"):
            versions[dataset] = await latest_version(dataset)

        ready = tickers > 0 and snapshot > 0 and valuation > 0
        coverage = round(financial_stocks / tickers, 4) if tickers else 0.0
        hint = None
        if not ready:
            hint = "运行 python -m app.data.ingest --all 初始化行情、估值和行业数据；2C2G 可加 --skip-dump"
        elif tech == 0:
            hint = "技术因子尚未初始化；如需“走势稳定”等条件，运行 python -m app.data.ingest --all（会下载全市场日 K）"

        datasets = {
            "tickers": {"count": tickers, "as_of": (versions.get("tickers") or {}).get("as_of"), "ready": tickers > 0},
            "snapshot": {"count": snapshot, "as_of": quote_as_of, "ready": snapshot > 0},
            "valuation": {"count": valuation, "as_of": valuation_as_of, "ready": valuation > 0},
            "tech_factors": {"count": tech, "as_of": tech_as_of, "ready": tech > 0},
            "industry": {"count": industries, "as_of": (versions.get("industry") or {}).get("as_of"), "ready": industries > 0},
            "dividend": {"count": dividends, "as_of": (versions.get("dividend") or {}).get("as_of"), "ready": dividends > 0},
            "financials": {
                "count": financial_stocks,
                "as_of": _period_end(settings.financial_report),
                "report": settings.financial_report,
                "coverage": coverage,
                "ready": True,
                "note": "财务数据按需取数并缓存，不在启动时全量预热",
            },
        }

        return {
            "mode": "live",
            "ready": ready,
            "universe": {"count": tickers, "label": "全 A 股"},
            "quote": {"as_of": quote_as_of, "status": "ok" if snapshot else "missing"},
            "valuation": {"as_of": valuation_as_of, "status": "ok" if valuation else "missing"},
            "daily_k": {"as_of": tech_as_of, "status": "ok" if tech else "missing"},
            "financials": {
                "latest_report": settings.financial_report,
                "label": _report_label(settings.financial_report) or settings.financial_report,
                "coverage": coverage,
                "status": "partial" if financial_stocks < tickers else "ok",
                "note": "财务数据按需取数并缓存",
            },
            "datasets": datasets,
            "sources": [{"name": "扶摇", "status": "ok" if ready else "degraded", "note": "本地 SQLite 缓存"}],
            "definitions": [
                {"key": "pe_ttm", "label": "PE(TTM)", "text": "最近 12 个月归母净利润口径；负值保留但不参与分位计算"},
                {"key": "pe_industry_pct", "label": "PE 行业分位", "text": "当前截面同花顺行业成分内正 PE 样本的百分位；行业成分少于 5 只时不计算"},
                {"key": "volatility_60d", "label": "60 日年化波动率", "text": "近 60 个交易日日收益率标准差 × √252；基于未复权日 K，除权日附近可能有偏差"},
                {"key": "max_drawdown_120d", "label": "120 日最大回撤", "text": "近 120 个交易日收盘价相对累计最高点的最大跌幅；未复权口径"},
                {"key": "dividend_yield_ttm", "label": "股息率(TTM)", "text": "近 365 天每股现金分红（税前）之和 / 最新价"},
                {"key": "net_profit_cash_content", "label": "净利润现金含量", "text": "经营现金流净额 / 净利润；接口返回百分数，系统换算为倍数（1.0x 表示利润有现金支撑）"},
                {"key": "financial_report", "label": "财务口径", "text": f"使用报告期 {settings.financial_report}；未披露时回退上一期，并在证据中标注"},
            ],
            "hint": hint,
        }
