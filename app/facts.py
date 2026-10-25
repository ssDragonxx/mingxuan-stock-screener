"""Build the comprehensive fact packet used by the AI explanation.

The screening engine only needs the fields referenced by conditions. The
explanation layer is intentionally richer: it receives the full valuation /
technical / quote snapshot, all 24 financial indicators and the latest four
report periods. Every number is still structured and traceable; the LLM only
verbalises it and a number checker verifies the output.
"""

from __future__ import annotations

import re
from typing import Any

from .field_registry import FIELD_META, indicator_meta

CATEGORY_ORDER = ["成长", "盈利", "偿债", "营运", "现金流", "其他"]

HISTORY_KEYS = [
    "revenue_yoy",
    "net_profit_yoy",
    "operating_profit_yoy",
    "gross_margin",
    "net_margin",
    "roe",
    "roe_deducted",
    "debt_ratio",
    "current_ratio",
    "net_profit_cash_content",
    "ocf_to_income",
    "total_assets_turnover_ratio",
    "inventory_turnover_ratio",
    "receive_account_turnover_ratio",
]


def report_label(report: str | None) -> str:
    if not report:
        return "—"
    try:
        year, quarter = report.split("-")
        return f"{year} " + {"1": "一季报", "2": "中报", "3": "三季报", "4": "年报"}[quarter]
    except (ValueError, KeyError):
        return report


def _bool_label(value: Any) -> str:
    if value is None:
        return "—"
    return "是" if value else "否"


def _status_label(value: Any) -> str:
    return {
        "included": "入选",
        "near_miss": "近邻",
        "excluded": "未入选",
        "unknown": "数据不足",
    }.get(str(value), str(value))


def _fmt(value: Any, unit: str) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if unit == "%":
        return f"{number:.2f}%"
    if unit == "x":
        return f"{number:.2f}x"
    if unit == "次":
        return f"{number:.2f}次"
    if unit == "亿元":
        return f"{number:.2f}亿元"
    if unit == "元":
        return f"{number:.2f}元"
    return f"{number:.2f}{unit}"


def _normalize(index_id: str, value: Any) -> Any:
    if value is None:
        return None
    meta = indicator_meta(index_id)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if meta.get("divide_100"):
        number /= 100
    return round(number, 4)


def _indicator_rows(indicators: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index_id, raw_value in (indicators or {}).items():
        meta = indicator_meta(index_id)
        value = _normalize(index_id, raw_value)
        if value is None:
            continue
        key = meta.get("key") or index_id
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "key": key,
                "index_id": index_id,
                "label": meta.get("label") or index_id,
                "unit": meta.get("unit") or "",
                "category": meta.get("category") or "其他",
                "value": value,
            }
        )
    rows.sort(
        key=lambda row: (
            CATEGORY_ORDER.index(row["category"])
            if row["category"] in CATEGORY_ORDER
            else 99,
            row["label"],
        )
    )
    return rows


def _history_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for period in history or []:
        indicators = _indicator_rows(period.get("indicators") or {})
        by_key = {row["key"]: row for row in indicators}
        values: dict[str, dict[str, Any]] = {}
        for key in HISTORY_KEYS:
            row = by_key.get(key)
            if row:
                values[key] = row
        rows.append(
            {
                "report": period.get("report"),
                "label": period.get("label") or report_label(period.get("report")),
                "period_end": period.get("period_end"),
                "values": values,
                "indicator_count": len(indicators),
            }
        )
    return rows


def _collect_numbers(facts: dict[str, Any]) -> set[float]:
    allowed: set[float] = {0.0, *map(float, range(1, 11))}

    def add(value: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        allowed.add(round(number, 1))
        allowed.add(round(abs(number), 1))

    for section in ("quote", "valuation", "technical", "dividend"):
        for value in (facts.get(section) or {}).values():
            add(value)
    for row in facts.get("indicators") or []:
        add(row.get("value"))
    for period in facts.get("history") or []:
        for row in (period.get("values") or {}).values():
            add(row.get("value"))
    for item in (facts.get("screening") or {}).get("conditions") or []:
        add(item.get("value"))
        add(item.get("threshold"))
        for token in re.findall(r"\d+", str(item.get("field_label") or "")):
            add(token)
    screening = facts.get("screening") or {}
    add(len(screening.get("conditions") or []))
    add(sum(1 for item in screening.get("conditions") or [] if item.get("status") == "pass"))
    add(len(facts.get("indicators") or []))
    add(len(facts.get("history") or []))
    for token in re.findall(r"-?\d+(?:\.\d+)?", facts.get("facts_text") or ""):
        add(token)
    return allowed


def build_facts(
    stock: dict[str, Any],
    history: list[dict[str, Any]],
    mode: str = "live",
) -> dict[str, Any]:
    raw = stock.get("raw") or {}
    current_report = raw.get("_report")
    current_entry = None
    for entry in history or []:
        if entry.get("report") == current_report:
            current_entry = entry
            break
    if current_entry is None and history:
        current_entry = history[0]

    indicators = _indicator_rows((current_entry or {}).get("indicators") or {})
    if not indicators:
        # Fallback for providers that only expose the screening fields.
        for field, meta in FIELD_META.items():
            if meta.get("category") != "financial":
                continue
            value = raw.get(field)
            if value is None:
                continue
            index_id = meta.get("index_id") or field
            indicators.append(
                {
                    "key": field,
                    "index_id": index_id,
                    "label": meta.get("label") or field,
                    "unit": meta.get("unit") or "",
                    "category": meta.get("category") or "其他",
                    "value": value,
                }
            )

    facts: dict[str, Any] = {
        "mode": mode,
        "identity": {
            "name": raw.get("name") or stock.get("name"),
            "thscode": raw.get("thscode") or stock.get("thscode"),
            "industry": raw.get("industry_name") or raw.get("industry") or stock.get("industry"),
            "exchange": raw.get("exchange"),
            "list_date": raw.get("list_date"),
        },
        "screening": {
            "status": stock.get("status"),
            "summary_reason": stock.get("summary_reason"),
            "data_completeness": stock.get("data_completeness"),
            "conditions": stock.get("conditions") or [],
            "risk_flags": stock.get("risk_flags") or [],
        },
        "quote": {
            "last_price": raw.get("last_price"),
            "pct_chg": raw.get("pct_chg"),
            "turnover": raw.get("turnover"),
            "volume": raw.get("volume"),
            "as_of": raw.get("quote_as_of"),
        },
        "valuation": {
            "pe_ttm": raw.get("pe_ttm"),
            "pe_mrq": raw.get("pe_mrq"),
            "pb_mrq": raw.get("pb_mrq"),
            "ps_ttm": raw.get("ps_ttm"),
            "pcf_ttm": raw.get("pcf_ttm"),
            "pe_industry_pct": raw.get("pe_industry_pct"),
            "pb_industry_pct": raw.get("pb_industry_pct"),
            "as_of": raw.get("valuation_as_of"),
        },
        "technical": {
            "return_20d": raw.get("return_20d"),
            "return_60d": raw.get("return_60d"),
            "return_120d": raw.get("return_120d"),
            "volatility_20d": raw.get("volatility_20d"),
            "volatility_60d": raw.get("volatility_60d"),
            "volatility_120d": raw.get("volatility_120d"),
            "max_drawdown_60d": raw.get("max_drawdown_60d"),
            "max_drawdown_120d": raw.get("max_drawdown_120d"),
            "ma20": raw.get("ma20"),
            "ma60": raw.get("ma60"),
            "above_ma60": raw.get("above_ma60"),
            "avg_turnover_20d": raw.get("avg_turnover_20d"),
            "as_of": raw.get("tech_as_of"),
        },
        "dividend": {
            "dividend_yield_ttm": raw.get("dividend_yield_ttm"),
            "as_of": raw.get("valuation_as_of"),
        },
        "report": (current_entry or {}).get("report") or current_report,
        "period_end": (current_entry or {}).get("period_end") or raw.get("_period_end"),
        "indicators": indicators,
        "history": _history_rows(history),
    }
    facts["facts_used"] = {
        "indicators": len(indicators),
        "periods": sum(1 for item in facts["history"] if item.get("indicator_count")),
        "conditions": len(facts["screening"]["conditions"]),
    }
    facts["facts_text"] = _render_facts_text(facts)
    facts["allowed_numbers"] = _collect_numbers(facts)
    return facts


def _render_facts_text(facts: dict[str, Any]) -> str:
    identity = facts["identity"]
    screening = facts["screening"]
    quote = facts["quote"]
    valuation = facts["valuation"]
    technical = facts["technical"]
    dividend = facts["dividend"]
    lines = [
        f"【股票】{identity.get('name')}（{identity.get('thscode')}），"
        f"行业 {identity.get('industry')}，上市日期 {identity.get('list_date') or '—'}",
        f"【筛选状态】{screening.get('status')}；数据完整度 {screening.get('data_completeness')}",
        f"【筛选结论】{screening.get('summary_reason')}",
        "【口径提示】筛选结论中的数字为四舍五入展示，精确值以逐条件证据为准。",
        "【行情】"
        f"最新价 {_fmt(quote.get('last_price'), '元')}，"
        f"涨跌幅 {_fmt(quote.get('pct_chg'), '%')}，"
        f"成交额 {_fmt(quote.get('turnover'), '亿元')}，"
        f"时点 {quote.get('as_of') or '—'}",
        "【估值】"
        f"PE(TTM) {_fmt(valuation.get('pe_ttm'), 'x')}，"
        f"PE(MRQ) {_fmt(valuation.get('pe_mrq'), 'x')}，"
        f"PE 行业分位 {_fmt(valuation.get('pe_industry_pct'), '%')}，"
        f"PB(MRQ) {_fmt(valuation.get('pb_mrq'), 'x')}，"
        f"PB 行业分位 {_fmt(valuation.get('pb_industry_pct'), '%')}，"
        f"PS(TTM) {_fmt(valuation.get('ps_ttm'), 'x')}，"
        f"PCF(TTM) {_fmt(valuation.get('pcf_ttm'), 'x')}，"
        f"时点 {valuation.get('as_of') or '—'}",
        "【技术】"
        f"20 日涨跌 {_fmt(technical.get('return_20d'), '%')}，"
        f"60 日涨跌 {_fmt(technical.get('return_60d'), '%')}，"
        f"120 日涨跌 {_fmt(technical.get('return_120d'), '%')}，"
        f"20 日波动 {_fmt(technical.get('volatility_20d'), '%')}，"
        f"60 日波动 {_fmt(technical.get('volatility_60d'), '%')}，"
        f"120 日波动 {_fmt(technical.get('volatility_120d'), '%')}，"
        f"60 日回撤 {_fmt(technical.get('max_drawdown_60d'), '%')}，"
        f"120 日回撤 {_fmt(technical.get('max_drawdown_120d'), '%')}，"
        f"MA20 {_fmt(technical.get('ma20'), '元')}，"
        f"MA60 {_fmt(technical.get('ma60'), '元')}，"
        f"站上 MA60 {technical.get('above_ma60')}，"
        f"20 日平均成交额 {_fmt(technical.get('avg_turnover_20d'), '亿元')}，"
        f"时点 {technical.get('as_of') or '—'}",
        f"【股息】股息率(TTM) {_fmt(dividend.get('dividend_yield_ttm'), '%')}",
        f"【财务报告期】{facts.get('report') or '—'}（{facts.get('period_end') or '—'}）",
    ]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in facts.get("indicators") or []:
        grouped.setdefault(row["category"], []).append(row)
    for category in CATEGORY_ORDER:
        rows = grouped.get(category)
        if not rows:
            continue
        values = "；".join(
            f"{row['label']} {_fmt(row['value'], row['unit'])}" for row in rows
        )
        lines.append(f"{category}：{values}")

    history = facts.get("history") or []
    if history:
        lines.append("【近几期趋势】")
        for period in history:
            values = period.get("values") or {}
            if not values:
                lines.append(f"{period.get('label')}（{period.get('period_end')}）：无可用指标")
                continue
            parts = [
                f"{row['label']} {_fmt(row['value'], row['unit'])}"
                for row in values.values()
            ]
            lines.append(
                f"{period.get('label')}（{period.get('period_end')}）：" + "；".join(parts)
            )

    lines.append("【筛选条件证据】")
    for item in screening.get("conditions") or []:
        lines.append(
            f"- {item.get('field_label')}：值 {_fmt(item.get('value'), item.get('unit') or '')}，"
            f"阈值 {item.get('op')} {item.get('threshold')}{item.get('unit') or ''}，"
            f"状态 {item.get('status')}，来源 {item.get('source')}，时点 {item.get('as_of')}"
            + (f"，差距 {item.get('gap_text')}" if item.get("gap_text") else "")
        )
    if screening.get("risk_flags"):
        lines.append("【风险与未知】")
        lines.extend(f"- {flag}" for flag in screening["risk_flags"])
    if facts.get("mode") == "mock":
        lines.append("【说明】当前为演示数据，仅用于验证分析结构。")
    return "\n".join(lines)


def _trend_text(history: list[dict[str, Any]], key: str, unit: str) -> str | None:
    values = []
    for period in history:
        row = (period.get("values") or {}).get(key)
        if row and row.get("value") is not None:
            values.append((period.get("label"), row["value"]))
    if len(values) < 2:
        return None
    first_label, first_value = values[-1]
    last_label, last_value = values[0]
    delta = last_value - first_value
    direction = "上升" if delta > 0.05 else "下降" if delta < -0.05 else "基本持平"
    return f"{first_label} {_fmt(first_value, unit)} → {last_label} {_fmt(last_value, unit)}（{direction}）"


def template_sections(stock: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, str]]:
    identity = facts["identity"]
    screening = facts["screening"]
    indicator_map = {row["key"]: row for row in facts.get("indicators") or []}
    history = facts.get("history") or []
    valuation = facts["valuation"]
    technical = facts["technical"]

    def get(key: str) -> str:
        row = indicator_map.get(key)
        return _fmt(row["value"], row["unit"]) if row else "—"

    summary = (
        f"{identity.get('name')}（{identity.get('thscode')}）本次状态为"
        f"“{_status_label(screening.get('status'))}”。{screening.get('summary_reason') or ''}"
    )

    financial_parts = [
        f"成长：营业收入同比 {get('revenue_yoy')}，归母净利润同比 {get('net_profit_yoy')}，"
        f"营业利润同比 {get('operating_profit_yoy')}。",
        f"盈利：销售毛利率 {get('gross_margin')}，销售净利率 {get('net_margin')}，"
        f"加权ROE {get('roe')}，扣非ROE {get('roe_deducted')}。",
        f"偿债：资产负债率 {get('debt_ratio')}，流动比率 {get('current_ratio')}。",
        f"现金流：净利润现金含量 {get('net_profit_cash_content')}，"
        f"销售现金比率 {get('ocf_to_income')}，现金营运指数 {get('cash_operating_index')}。",
    ]
    trends = [
        _trend_text(history, "gross_margin", "%"),
        _trend_text(history, "net_margin", "%"),
        _trend_text(history, "roe", "%"),
        _trend_text(history, "debt_ratio", "%"),
        _trend_text(history, "net_profit_cash_content", "x"),
        _trend_text(history, "revenue_yoy", "%"),
    ]
    trend_text = "；".join(item for item in trends if item)
    financial = " ".join(financial_parts)
    if trend_text:
        financial += f" 趋势：{trend_text}。"

    valuation_text = (
        f"PE(TTM) {_fmt(valuation.get('pe_ttm'), 'x')}，"
        f"PE 行业分位 {_fmt(valuation.get('pe_industry_pct'), '%')}；"
        f"PB(MRQ) {_fmt(valuation.get('pb_mrq'), 'x')}，"
        f"PB 行业分位 {_fmt(valuation.get('pb_industry_pct'), '%')}。"
        f"20/60/120 日涨跌幅分别为 {_fmt(technical.get('return_20d'), '%')}、"
        f"{_fmt(technical.get('return_60d'), '%')}、{_fmt(technical.get('return_120d'), '%')}；"
        f"60 日年化波动率 {_fmt(technical.get('volatility_60d'), '%')}，"
        f"120 日最大回撤 {_fmt(technical.get('max_drawdown_120d'), '%')}；"
        f"站上 MA60：{_bool_label(technical.get('above_ma60'))}。"
    )

    risk_parts = list(screening.get("risk_flags") or [])
    if not any("技术因子" in item for item in risk_parts):
        risk_parts.append("技术因子基于未复权日 K，除权日附近可能有偏差。")
    if facts.get("mode") == "mock":
        risk_parts.append("当前为演示数据。")
    risk_parts.append("以上为数据整理，不构成投资建议。")
    risk_parts = list(dict.fromkeys(risk_parts))

    return [
        {"title": "结论", "text": summary},
        {"title": "财务质量", "text": financial},
        {"title": "估值与走势", "text": valuation_text},
        {"title": "风险与未知", "text": " ".join(risk_parts)},
    ]


def template_explanation(stock: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    sections = template_sections(stock, facts)
    text = "\n\n".join(f"{section['title']}\n{section['text']}" for section in sections)
    return {
        "text": text,
        "mode": "template",
        "number_check": "not_applicable",
        "sections": sections,
        "facts_used": facts.get("facts_used"),
    }
