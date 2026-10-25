"""Deterministic screening engine.

The LLM never touches this module. It evaluates a validated DSL against the
provider data with three-state logic (pass / fail / unknown), builds evidence,
exclusion breakdowns and sensitivity curves.
"""

from __future__ import annotations

import copy
import time
from typing import Any

from .config import settings
from .field_registry import (
    FIELD_META,
    FINANCIAL_FIELDS,
    TECH_FIELDS,
)
from .providers.base import DataProvider, ProgressCallback

STATUS_ORDER = {"included": 0, "near_miss": 1, "excluded": 2, "unknown": 3}

SWEEPS: dict[str, list[float]] = {
    "revenue_yoy": [0, 5, 10, 15, 20],
    "net_profit_yoy": [-10, -5, 0, 5, 10],
    "operating_profit_yoy": [-10, 0, 10, 20, 30],
    "pe_industry_pct": [20, 40, 60, 80, 100],
    "pb_industry_pct": [20, 40, 60, 80, 100],
    "pe_ttm": [10, 15, 20, 25, 30],
    "pb_mrq": [1, 2, 3, 5, 8],
    "volatility_20d": [15, 20, 25, 30, 35],
    "volatility_60d": [15, 20, 25, 30, 35, 40],
    "max_drawdown_60d": [-30, -25, -20, -15, -10],
    "max_drawdown_120d": [-30, -25, -20, -15, -10],
    "dividend_yield_ttm": [1, 2, 3, 4, 5],
    "return_20d": [-25, -20, -15, -10, -5],
    "gross_margin": [10, 20, 30, 40, 50],
    "net_margin": [0, 5, 10, 15, 20],
    "roe": [5, 10, 15, 20, 25],
    "debt_ratio": [30, 40, 50, 60, 70],
    "current_ratio": [0.8, 1.0, 1.5, 2.0, 3.0],
    "net_profit_cash_content": [0.5, 0.8, 1.0, 1.2, 1.5],
    "avg_turnover_20d": [0.5, 1, 2, 5, 10],
}


# ---------------------------------------------------------------------------
# Formatting / metadata
# ---------------------------------------------------------------------------
def op_label(op: str) -> str:
    return {">=": "≥", "<=": "≤", ">": ">", "<": "<", "==": "=", "!=": "≠"}.get(op, op)


def fmt_value(value: Any, field: str) -> str:
    if value is None:
        return "—"
    meta = FIELD_META.get(field, {})
    unit = meta.get("unit", "")
    signed = bool(meta.get("signed"))
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if unit == "%":
        text = f"{number:.1f}%"
        return f"+{text}" if signed and number > 0 else text
    if unit == "x":
        return f"{number:.2f}x"
    if unit == "次":
        return f"{number:.2f}次"
    if unit == "亿元":
        return f"{number:.2f}亿元"
    if unit == "元":
        return f"{number:.2f}元"
    if unit == "名":
        return f"{number:.0f}名"
    return f"{number:.2f}{unit}"


def _period_end(report: str | None) -> str | None:
    if not report:
        return None
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


def _source_for(row: dict[str, Any], field: str) -> tuple[str, str | None, str | None]:
    meta = FIELD_META.get(field, {})
    source = meta.get("source", "扶摇")
    category = meta.get("category")
    if category == "financial":
        report = row.get("_report") or settings.financial_report
        return source, row.get("_period_end") or _period_end(report), _report_label(report)
    if category == "valuation":
        return source, row.get("valuation_as_of"), "当前截面"
    if category == "technical":
        return source, row.get("tech_as_of"), "未复权"
    if category == "dividend":
        return source, row.get("valuation_as_of") or row.get("quote_as_of"), "近 12 个月"
    return source, row.get("quote_as_of"), None


def _missing_note(row: dict[str, Any], field: str) -> str:
    meta = FIELD_META.get(field, {})
    category = meta.get("category")
    if category == "financial":
        if row.get("_cheap_failed"):
            return "前置条件已失败，未取财务数据"
        if row.get("_preview"):
            return "预览未取数（点击开始筛选后按需取数）"
        report = row.get("_report")
        if report and report != settings.financial_report:
            return f"报告期 {report} 无可用数据"
        return "财务数据未披露或未取到"
    if category == "valuation":
        if field.endswith("_industry_pct"):
            pe = row.get("pe_ttm") if field.startswith("pe") else row.get("pb_mrq")
            if pe is not None and pe <= 0:
                return "负值，分位不适用"
            return "行业分位缺失（行业样本不足或数据未初始化）"
        return "估值数据缺失"
    if category == "technical":
        return "技术因子未初始化或日 K 不足"
    if category == "dividend":
        return "股息数据未初始化"
    if category == "quote":
        return "行情数据缺失"
    return "数据缺失"


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == ">=":
        return value >= threshold
    if op == ">":
        return value > threshold
    if op == "<=":
        return value <= threshold
    if op == "<":
        return value < threshold
    if op == "==":
        return value == threshold
    if op == "!=":
        return value != threshold
    return False


def _gap(value: float, op: str, threshold: float) -> float:
    if op in (">=", ">"):
        return threshold - value
    if op in ("<=", "<"):
        return value - threshold
    return abs(value - threshold)


def _unit_label(field: str) -> str:
    unit = FIELD_META.get(field, {}).get("unit", "")
    return "个百分点" if unit == "%" else (unit or "")


def _gap_text(field: str, value: Any, gap: float, op: str) -> str:
    if field == "pe_ttm" and value is not None and float(value) <= 0:
        return "PE 为负，不满足 > 0"
    if field in ("max_drawdown_60d", "max_drawdown_120d"):
        return f"回撤比阈值深 {abs(gap):.1f} 个百分点"
    if field == "return_20d" and op in ("<=", "<"):
        return f"跌幅比阈值少 {abs(gap):.1f} 个百分点"
    label = _unit_label(field)
    if op in (">=", ">"):
        return f"低于阈值 {abs(gap):.2f} {label}"
    if op in ("<=", "<"):
        return f"高于阈值 {abs(gap):.2f} {label}"
    return f"差 {abs(gap):.2f} {label}"


# ---------------------------------------------------------------------------
# Condition / group / stock evaluation
# ---------------------------------------------------------------------------
def evaluate_condition(row: dict[str, Any], cond: dict[str, Any]) -> dict[str, Any]:
    field = cond["field"]
    meta = FIELD_META.get(field, {})
    value = row.get(field)
    source, as_of, note = _source_for(row, field)

    if value is None:
        missing = _missing_note(row, field)
        return {
            "condition_id": cond.get("id"),
            "field": field,
            "field_label": meta.get("label", field),
            "value": None,
            "unit": meta.get("unit", ""),
            "op": cond.get("op"),
            "threshold": cond.get("value"),
            "status": "unknown",
            "gap": None,
            "gap_text": missing,
            "source": source,
            "as_of": as_of,
            "note": note or missing,
            "category": meta.get("category"),
        }

    try:
        numeric = float(value)
        threshold = float(cond.get("value"))
    except (TypeError, ValueError):
        return {
            "condition_id": cond.get("id"),
            "field": field,
            "field_label": meta.get("label", field),
            "value": value,
            "unit": meta.get("unit", ""),
            "op": cond.get("op"),
            "threshold": cond.get("value"),
            "status": "unknown",
            "gap": None,
            "gap_text": "数值无法解析",
            "source": source,
            "as_of": as_of,
            "note": note,
            "category": meta.get("category"),
        }

    ok = _compare(numeric, cond.get("op"), threshold)
    if ok:
        gap = 0.0
        gap_text = None
    else:
        gap = _gap(numeric, cond.get("op"), threshold)
        gap_text = _gap_text(field, numeric, gap, cond.get("op"))

    return {
        "condition_id": cond.get("id"),
        "field": field,
        "field_label": meta.get("label", field),
        "value": numeric,
        "unit": meta.get("unit", ""),
        "op": cond.get("op"),
        "threshold": threshold,
        "status": "pass" if ok else "fail",
        "gap": round(gap, 4) if not ok else 0.0,
        "gap_text": gap_text,
        "source": source,
        "as_of": as_of,
        "note": note,
        "category": meta.get("category"),
    }


def _eval_group(row: dict[str, Any], group: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    evidence = []
    for cond in group.get("conditions") or []:
        item = evaluate_condition(row, cond)
        item["group_id"] = group.get("id")
        item["group_label"] = group.get("label")
        evidence.append(item)

    statuses = [item["status"] for item in evidence]
    if group.get("logic") == "OR":
        if "pass" in statuses:
            return "pass", evidence
        if "unknown" in statuses:
            return "unknown", evidence
        return "fail", evidence
    if "fail" in statuses:
        return "fail", evidence
    if "unknown" in statuses:
        return "unknown", evidence
    return "pass", evidence


def _classify(
    evidence: list[dict[str, Any]], policy: str
) -> tuple[str, int, int, int, int]:
    original_fail = sum(1 for item in evidence if item["status"] == "fail")
    original_unknown = sum(1 for item in evidence if item["status"] == "unknown")

    effective: list[str] = []
    for item in evidence:
        status = item["status"]
        if policy == "include_with_warning" and status == "unknown":
            status = "pass"
        elif policy == "fail" and status == "unknown":
            status = "fail"
        effective.append(status)

    fail_count = effective.count("fail")
    unknown_count = effective.count("unknown")

    if fail_count == 0 and unknown_count == 0:
        status = "included"
    elif fail_count == 1 and unknown_count == 0 and not (policy == "fail" and original_fail == 0):
        status = "near_miss"
    elif fail_count == 0 and unknown_count > 0:
        status = "unknown"
    else:
        status = "excluded"
    return status, fail_count, unknown_count, original_fail, original_unknown


def _summary_reason(
    status: str,
    evidence: list[dict[str, Any]],
    policy: str,
    original_unknown: int,
    preview: bool,
) -> str:
    total = len(evidence)
    fails = [item for item in evidence if item["status"] == "fail"]
    unknowns = [item for item in evidence if item["status"] == "unknown"]
    preview_missing = preview and any(item.get("category") == "financial" for item in unknowns)
    suffix = "（预览未取数）" if preview_missing else ""

    if status == "included":
        metrics = "、".join(
            f"{item['field_label']} {fmt_value(item['value'], item['field'])}"
            for item in evidence[:3]
        )
        text = f"{total}/{total} 条件通过；{metrics}"
        if policy == "include_with_warning" and original_unknown:
            text += f"；含 {original_unknown} 项未知（按通过处理）"
        return text

    if status == "near_miss" and fails:
        item = fails[0]
        if item["field"] == "pe_ttm" and item["value"] is not None and item["value"] <= 0:
            return f"差 1 项：PE(TTM) 为负（{fmt_value(item['value'], item['field'])}），不满足 > 0"
        return (
            f"差 1 项：{item['field_label']} {fmt_value(item['value'], item['field'])}"
            f"（{item['gap_text']}）"
        )

    if status == "unknown":
        labels = "、".join(item["field_label"] for item in unknowns)
        return f"{len(unknowns)} 项数据不足：{labels}{suffix}"

    if fails:
        parts = [
            f"{item['field_label']} {fmt_value(item['value'], item['field'])}（{item['gap_text']}）"
            for item in fails[:3]
        ]
        text = f"{len(fails)} 项不满足：" + "；".join(parts)
        if len(fails) > 3:
            text += " 等"
        if original_unknown:
            text += f"；另有 {original_unknown} 项数据不足{suffix}"
        if policy == "fail" and original_unknown:
            text += "（缺失按失败处理）"
        return text

    return "未满足条件"


def _risk_flags(
    row: dict[str, Any], evidence: list[dict[str, Any]], policy: str
) -> list[str]:
    flags: list[str] = []
    unknowns = [item for item in evidence if item["status"] == "unknown"]
    if unknowns:
        labels = "、".join(item["field_label"] for item in unknowns)
        flags.append(f"{len(unknowns)} 项数据不足：{labels}")
    uses_valuation = any(item.get("category") == "valuation" for item in evidence)
    pe = row.get("pe_ttm")
    if uses_valuation and (pe is None or pe <= 0):
        flags.append("PE 为负或缺失，估值分位不可用")
    if any(item["category"] == "technical" for item in evidence):
        flags.append("技术因子基于未复权日 K，除权日附近可能有偏差")
    report = row.get("_report")
    if report and report != settings.financial_report and any(
        item.get("category") == "financial" for item in evidence
    ):
        flags.append(f"财务使用报告期 {report}（不是 {settings.financial_report}）")
    if row.get("_preview") and any(item["category"] == "financial" for item in evidence):
        flags.append("预览仅使用已缓存财务数据")
    if policy == "include_with_warning" and unknowns:
        flags.append("缺失数据按通过处理，请谨慎使用")
    if policy == "fail" and unknowns:
        flags.append("缺失数据按失败处理")
    if any(str(item.get("field", "")).endswith("industry_pct") for item in evidence) and not (
        row.get("industry_name") or row.get("industry")
    ):
        flags.append("行业归属缺失，行业分位不可用")
    return list(dict.fromkeys(flags))


def _cheap_failed_reason(evidence: list[dict[str, Any]]) -> str:
    fails = [
        item
        for item in evidence
        if item["status"] == "fail" and item.get("category") != "financial"
    ]
    if not fails:
        fails = [item for item in evidence if item["status"] == "fail"]
    if not fails:
        return "前置条件不满足；未取财务数据"
    parts = [
        f"{item['field_label']} {fmt_value(item['value'], item['field'])}（{item['gap_text']}）"
        for item in fails[:2]
    ]
    return "前置条件不满足：" + "；".join(parts) + "；未取财务数据"


def evaluate_stock(row: dict[str, Any], dsl: dict[str, Any]) -> dict[str, Any]:
    policy = dsl.get("missing_policy", "exclude_with_flag")
    groups = dsl.get("groups") or []
    evidence: list[dict[str, Any]] = []
    group_statuses: list[dict[str, Any]] = []
    for group in groups:
        status, group_evidence = _eval_group(row, group)
        group_statuses.append({"group_id": group.get("id"), "status": status})
        evidence.extend(group_evidence)

    status, fail_count, unknown_count, _, original_unknown = _classify(evidence, policy)
    total = len(evidence)
    completeness = f"{total - original_unknown}/{total}" if total else "0/0"
    cheap_failed = bool(row.get("_cheap_failed"))
    if cheap_failed:
        status = "excluded"
        cheap_evidence = [item for item in evidence if item.get("category") != "financial"]
        cheap_unknown = sum(1 for item in cheap_evidence if item["status"] == "unknown")
        completeness = (
            f"{len(cheap_evidence) - cheap_unknown}/{len(cheap_evidence)}"
            if cheap_evidence
            else "0/0"
        )
    min_gap = min(
        (item["gap"] for item in evidence if item["status"] == "fail" and item["gap"] is not None),
        default=0.0,
    )
    preview = bool(row.get("_preview"))

    summary_reason = (
        _cheap_failed_reason(evidence)
        if cheap_failed
        else _summary_reason(status, evidence, policy, original_unknown, preview)
    )
    risk_flags = _risk_flags(row, evidence, policy)
    if cheap_failed:
        risk_flags = list(dict.fromkeys(risk_flags + ["前置条件已失败，未取财务数据"]))

    return {
        "thscode": row.get("thscode"),
        "name": row.get("name"),
        "industry": row.get("industry_name") or row.get("industry") or "未分类",
        "status": status,
        "data_completeness": completeness,
        "summary_reason": summary_reason,
        "conditions": evidence,
        "risk_flags": risk_flags,
        "raw": row,
        "fail_count": fail_count,
        "unknown_count": unknown_count,
        "original_unknown_count": original_unknown,
        "min_gap": round(min_gap, 4),
        "group_statuses": group_statuses,
        "cheap_failed": cheap_failed,
    }


# ---------------------------------------------------------------------------
# Cheap pruning
# ---------------------------------------------------------------------------
def _cheap_group_status(row: dict[str, Any], group: dict[str, Any]) -> str:
    conditions = group.get("conditions") or []
    cheap = [c for c in conditions if c.get("field") not in FINANCIAL_FIELDS]
    has_financial = len(cheap) < len(conditions)
    if not cheap:
        return "pending" if has_financial else "pass"

    statuses = [evaluate_condition(row, cond)["status"] for cond in cheap]
    if group.get("logic") == "OR":
        if "pass" in statuses:
            return "pass"
        if has_financial:
            return "pending"
        if "unknown" in statuses:
            return "unknown"
        return "fail"
    if "fail" in statuses:
        return "fail"
    if has_financial:
        return "pending"
    if "unknown" in statuses:
        return "unknown"
    return "pass"


# ---------------------------------------------------------------------------
# Breakdown / sensitivity
# ---------------------------------------------------------------------------
def _excluded_breakdown(dsl: dict[str, Any], stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels: dict[str, tuple[str, str]] = {}
    for group in dsl.get("groups") or []:
        for cond in group.get("conditions") or []:
            field = cond.get("field")
            labels[cond.get("id")] = (
                field,
                FIELD_META.get(field, {}).get("label", field),
            )

    counts: dict[str, int] = {cond_id: 0 for cond_id in labels}
    for stock in stocks:
        for item in stock.get("conditions") or []:
            if item["status"] == "fail":
                counts[item["condition_id"]] = counts.get(item["condition_id"], 0) + 1

    result = []
    for cond_id, count in counts.items():
        if count:
            field, label = labels[cond_id]
            result.append({"field": field, "label": label, "count": count, "kind": "fail"})
    result.sort(key=lambda item: item["count"], reverse=True)

    unknown_stocks = sum(
        1
        for stock in stocks
        if stock.get("original_unknown_count", 0) > 0 and not stock.get("cheap_failed")
    )
    if unknown_stocks:
        result.append(
            {
                "field": "__unknown__",
                "label": "含缺失项（任一条件）",
                "count": unknown_stocks,
                "kind": "unknown",
            }
        )
    return result


def _sensitivity(dsl: dict[str, Any], rows: list[dict[str, Any]], current_included: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for group in dsl.get("groups") or []:
        for cond in group.get("conditions") or []:
            field = cond.get("field")
            sweep = SWEEPS.get(field)
            if not sweep:
                continue
            if field == "pe_ttm" and cond.get("value") == 0 and cond.get("op") == ">":
                continue
            try:
                current_value = float(cond.get("value"))
            except (TypeError, ValueError):
                continue
            points = []
            for threshold in sweep:
                trial = copy.deepcopy(dsl)
                for trial_group in trial.get("groups") or []:
                    for trial_cond in trial_group.get("conditions") or []:
                        if trial_cond.get("id") == cond.get("id"):
                            trial_cond["value"] = threshold
                count = sum(
                    1 for row in rows if evaluate_stock(row, trial)["status"] == "included"
                )
                points.append({"threshold": threshold, "included": count})
            best = max(points, key=lambda point: point["included"])
            delta = best["included"] - current_included
            direction = "lower_is_looser" if cond.get("op") in (">=", ">") else "higher_is_looser"
            items.append(
                {
                    "condition_id": cond.get("id"),
                    "label": FIELD_META.get(field, {}).get("label", field),
                    "field": field,
                    "unit": FIELD_META.get(field, {}).get("unit", ""),
                    "current": current_value,
                    "points": points,
                    "binding": False,
                    "relax_to": best["threshold"] if delta > 0 else None,
                    "delta": delta,
                    "direction": direction,
                }
            )
    items.sort(key=lambda item: item["delta"], reverse=True)
    max_delta = items[0]["delta"] if items else 0
    for item in items:
        if max_delta > 0 and item["delta"] == max_delta:
            item["binding"] = True
            break
    return items


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------
async def run_screen(
    dsl: dict[str, Any],
    provider: DataProvider,
    fetch: bool = True,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    if progress:
        await progress("universe", 0, 1, "读取全市场快照、估值与行业数据…")

    universe_rows = await provider.get_universe(dsl)
    groups = dsl.get("groups") or []
    financial_fields = {
        cond["field"]
        for group in groups
        for cond in group.get("conditions") or []
        if cond.get("field") in FINANCIAL_FIELDS
    }

    candidates: list[dict[str, Any]] = []
    cheap_failed_rows: list[dict[str, Any]] = []
    cheap_excluded = 0
    for row in universe_rows:
        statuses = [_cheap_group_status(row, group) for group in groups]
        if "fail" in statuses:
            cheap_excluded += 1
            row["_cheap_failed"] = True
            cheap_failed_rows.append(row)
        else:
            candidates.append(row)

    after_cheap = len(candidates)
    truncated = 0
    if after_cheap > settings.max_candidates:
        candidates.sort(
            key=lambda row: (
                row.get("avg_turnover_20d")
                if row.get("avg_turnover_20d") is not None
                else (row.get("turnover") or 0)
            ),
            reverse=True,
        )
        truncated = after_cheap - settings.max_candidates
        candidates = candidates[: settings.max_candidates]

    if progress:
        await progress(
            "cheap",
            after_cheap,
            after_cheap,
            f"便宜条件完成：{after_cheap} 只候选" + (f"，截断 {truncated} 只" if truncated else ""),
        )

    if financial_fields and candidates:
        if fetch:
            financials = await provider.get_financials(
                [row["thscode"] for row in candidates], financial_fields, progress
            )
        else:
            financials = await provider.get_cached_financials(
                [row["thscode"] for row in candidates], financial_fields
            )
        for row in candidates:
            row.update(financials.get(row.get("thscode"), {}))
            if not fetch and provider.mode == "live":
                row["_preview"] = True

    pending = 0
    if financial_fields:
        pending = sum(
            1
            for row in candidates
            if any(row.get(field) is None for field in financial_fields)
        )

    if progress:
        await progress("evaluate", 0, 1, "执行确定性筛选与证据生成…")

    evaluated = [evaluate_stock(row, dsl) for row in candidates]
    cheap_stocks = [evaluate_stock(row, dsl) for row in cheap_failed_rows]
    all_stocks = evaluated + cheap_stocks
    counts = {
        "included": sum(1 for stock in evaluated if stock["status"] == "included"),
        "near_miss": sum(1 for stock in evaluated if stock["status"] == "near_miss"),
        "excluded": sum(1 for stock in evaluated if stock["status"] == "excluded") + len(cheap_stocks),
        "unknown": sum(1 for stock in evaluated if stock["status"] == "unknown"),
    }

    completeness_values = []
    for stock in evaluated:
        total = len(stock["conditions"])
        if total:
            completeness_values.append(
                (total - stock["original_unknown_count"]) / total
            )
    completeness = (
        round(sum(completeness_values) / len(completeness_values) * 100)
        if completeness_values
        else 0
    )

    all_stocks = evaluated + cheap_stocks
    all_stocks.sort(
        key=lambda stock: (
            STATUS_ORDER.get(stock["status"], 9),
            -(
                stock["raw"].get("avg_turnover_20d")
                or stock["raw"].get("turnover")
                or 0
            )
            if stock["status"] == "included"
            else 0,
            stock["min_gap"] if stock["status"] == "near_miss" else 0,
            -stock["fail_count"],
        )
    )

    data_status = await provider.get_status()
    sensitivity = _sensitivity(dsl, candidates, counts["included"])
    breakdown = _excluded_breakdown(dsl, all_stocks)

    warnings: list[str] = []
    if truncated:
        warnings.append(
            f"便宜条件后有 {after_cheap} 只候选，超过单次上限 {settings.max_candidates}，"
            f"已按成交额取前 {settings.max_candidates} 只；其余 {truncated} 只未评估。"
        )
    if after_cheap == len(universe_rows) and financial_fields:
        text = "本次没有便宜条件可先缩小范围，财务条件可能需要对全市场取数；"
        text += f"已按成交额截断 {truncated} 只。" if truncated else "已优先按成交额排序。"
        warnings.append(text)
    tech_used = {
        cond["field"]
        for group in groups
        for cond in group.get("conditions") or []
        if cond.get("field") in TECH_FIELDS
    }
    if tech_used and universe_rows and all(
        row.get(field) is None for row in universe_rows for field in tech_used
    ):
        warnings.append(
            "技术因子未初始化，技术类条件按未知处理；运行 python -m app.data.ingest --all 初始化。"
        )
    if pending and fetch:
        warnings.append(f"有 {pending} 只候选股财务字段缺失或未取到，已标记为数据不足。")
    if not fetch and provider.mode == "live":
        warnings.append("预览仅使用已缓存财务数据；点击开始筛选后会按需取数。")

    return {
        "summary": {
            "universe": len(universe_rows),
            "cheap_excluded": cheap_excluded,
            "after_cheap": after_cheap,
            "evaluated": len(evaluated),
            "truncated": truncated,
            "included": counts["included"],
            "near_miss": counts["near_miss"],
            "excluded": counts["excluded"],
            "unknown": counts["unknown"],
            "pending": pending,
            "data_completeness": f"{completeness}%",
            "financial_report": settings.financial_report,
            "returned": len(all_stocks),
        },
        "funnel": [
            {"label": "可用标的", "count": len(universe_rows)},
            {"label": "便宜条件后", "count": after_cheap},
            {"label": "完整评估", "count": len(evaluated)},
            {"label": "入选", "count": counts["included"]},
        ],
        "stocks": all_stocks,
        "excluded_breakdown": breakdown,
        "sensitivity": sensitivity,
        "data_status": data_status,
        "warnings": warnings,
        "meta": {
            "mode": provider.mode,
            "fetch": fetch,
            "max_candidates": settings.max_candidates,
            "financial_report": settings.financial_report,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    }


async def run_preview(dsl: dict[str, Any], provider: DataProvider) -> dict[str, Any]:
    return await run_screen(dsl, provider, fetch=False)


async def diagnose(
    query: str, dsl: dict[str, Any], provider: DataProvider
) -> dict[str, Any] | None:
    row = await provider.get_stock(query)
    if row is None:
        return None
    financial_fields = {
        cond["field"]
        for group in dsl.get("groups") or []
        for cond in group.get("conditions") or []
        if cond.get("field") in FINANCIAL_FIELDS
    }
    if financial_fields:
        financials = await provider.get_financials([row["thscode"]], financial_fields)
        row.update(financials.get(row["thscode"], {}))
    return evaluate_stock(row, dsl)
