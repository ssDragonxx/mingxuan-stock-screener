"""Mock provider used when FUYAO_API_KEY is empty.

The shape is identical to the live provider so the engine and frontend can be
developed and tested without any external data.
"""

from __future__ import annotations

from typing import Any

from ..mock_data import DATA_STATUS, STOCKS
from ..field_registry import FIELD_META
from .base import DataProvider, ProgressCallback


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    revenue = item.get("revenue_yoy")
    profit = item.get("net_profit_yoy")
    drawdown = item.get("max_drawdown_120d")
    item.setdefault("quote_as_of", DATA_STATUS["quote"]["as_of"])
    item.setdefault("valuation_as_of", DATA_STATUS["valuation"]["as_of"])
    item.setdefault("tech_as_of", DATA_STATUS["daily_k"]["as_of"])
    item.setdefault("operating_profit_yoy", None if revenue is None else round(revenue + 1.5, 1))
    item.setdefault("roe", None if revenue is None else round(10 + revenue * 0.2, 1))
    item.setdefault("roe_deducted", None if revenue is None else round(9 + revenue * 0.18, 1))
    item.setdefault("gross_margin", None if profit is None else round(30 + profit * 0.1, 1))
    item.setdefault("net_margin", None if profit is None else round(8 + profit * 0.08, 1))
    item.setdefault("debt_ratio", None if drawdown is None else round(40 - drawdown * 0.5, 1))
    item.setdefault("current_ratio", None if revenue is None else round(1.2 + revenue * 0.01, 2))
    item.setdefault("net_profit_cash_content", None if revenue is None else round(0.8 + revenue * 0.01, 2))
    item.setdefault("ocf_to_income", None if revenue is None else round(12 + revenue * 0.1, 1))
    item.setdefault("total_assets_turnover_ratio", None if revenue is None else round(0.5 + revenue * 0.005, 2))
    item.setdefault("inventory_turnover_ratio", None if revenue is None else round(3 + revenue * 0.02, 2))
    item.setdefault("receive_account_turnover_ratio", None if revenue is None else round(5 + revenue * 0.03, 2))
    return item


_ENRICHED = [_enrich(row) for row in STOCKS]


class MockProvider(DataProvider):
    mode = "mock"

    async def get_universe(self, dsl: dict) -> list[dict[str, Any]]:
        return [dict(row) for row in _ENRICHED]

    async def get_financials(
        self,
        codes: list[str],
        fields: set[str],
        progress: ProgressCallback | None = None,
    ) -> dict[str, dict[str, Any]]:
        by_code = {row["thscode"]: row for row in _ENRICHED}
        result: dict[str, dict[str, Any]] = {}
        total = max(len(codes), 1)
        for index, code in enumerate(codes, start=1):
            row = by_code.get(code, {})
            mapped = {field: row.get(field) for field in fields}
            mapped["_report"] = "2026-2"
            mapped["_period_end"] = "2026-06-30"
            result[code] = mapped
            if progress and (index == total or index % 20 == 0):
                await progress("financials", index, total, f"演示数据 {index}/{total}")
        return result

    async def get_cached_financials(
        self,
        codes: list[str],
        fields: set[str],
    ) -> dict[str, dict[str, Any]]:
        return await self.get_financials(codes, fields, progress=None)

    async def get_financial_history(
        self,
        code: str,
        periods: int = 4,
    ) -> list[dict[str, Any]]:
        row = next((item for item in _ENRICHED if item["thscode"] == code), None)
        if row is None:
            return []
        indicators: dict[str, Any] = {}
        for field, meta in FIELD_META.items():
            index_id = meta.get("index_id")
            if not index_id:
                continue
            value = row.get(field)
            if field == "net_profit_cash_content" and value is not None:
                value = round(float(value) * 100, 4)
            indicators[index_id] = value
        demo_periods = [
            ("2026-2", "2026 中报", "2026-06-30"),
            ("2026-1", "2026 一季报", "2026-03-31"),
            ("2025-4", "2025 年报", "2025-12-31"),
            ("2025-3", "2025 三季报", "2025-09-30"),
        ]
        return [
            {
                "report": report,
                "label": label,
                "period_end": period_end,
                "indicators": dict(indicators),
            }
            for report, label, period_end in demo_periods[: max(1, periods)]
        ]

    async def get_stock(self, query: str) -> dict[str, Any] | None:
        q = (query or "").strip().lower()
        if not q:
            return None
        for row in _ENRICHED:
            ticker = row["thscode"].split(".")[0].lower()
            if q in (row["thscode"].lower(), ticker, row["name"].lower()):
                return dict(row)
        return None

    async def get_status(self) -> dict[str, Any]:
        status = dict(DATA_STATUS)
        status["mode"] = "mock"
        status["ready"] = True
        status["datasets"] = {
            "snapshot": {"count": len(_ENRICHED), "as_of": DATA_STATUS["quote"]["as_of"], "ready": True},
            "valuation": {"count": len(_ENRICHED), "as_of": DATA_STATUS["valuation"]["as_of"], "ready": True},
            "tech_factors": {"count": len(_ENRICHED), "as_of": DATA_STATUS["daily_k"]["as_of"], "ready": True},
            "dividend": {"count": len(_ENRICHED), "as_of": DATA_STATUS["valuation"]["as_of"], "ready": True},
            "industry": {"count": len(_ENRICHED), "as_of": DATA_STATUS["valuation"]["as_of"], "ready": True},
            "financials": {
                "count": sum(1 for row in _ENRICHED if row.get("revenue_yoy") is not None),
                "report": "2026-2",
                "as_of": "2026-06-30",
                "ready": True,
            },
        }
        status["hint"] = "当前为演示数据；在 .env 配置 FUYAO_API_KEY 后运行 python -m app.data.ingest --all 接入真实数据。"
        return status
