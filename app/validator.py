"""DSL validation and normalization.

The LLM is allowed to be creative; this module is not. Every field, operator,
unit and window is checked against the registry before the engine sees it.
"""

from __future__ import annotations

from typing import Any

from .field_registry import FIELD_META

VALID_UNIVERSES = {"all_a_share", "csi300", "csi500", "csi1000"}
VALID_POLICIES = {"exclude_with_flag", "include_with_warning", "fail"}
VALID_OPS = {">=", "<=", ">", "<", "==", "!="}


def validate_dsl(raw: dict[str, Any], universe: str = "all_a_share") -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return {}, ["DSL 必须是 JSON 对象"]

    groups_raw = raw.get("groups")
    if not isinstance(groups_raw, list) or not groups_raw:
        return {}, ["groups 必须是非空数组"]

    groups: list[dict[str, Any]] = []
    condition_counter = 0
    for group_index, group_raw in enumerate(groups_raw, start=1):
        if not isinstance(group_raw, dict):
            errors.append(f"groups[{group_index}] 必须是对象")
            continue
        label = str(group_raw.get("label") or f"条件组 {group_index}").strip()
        logic = str(group_raw.get("logic") or "AND").upper()
        if logic not in {"AND", "OR"}:
            errors.append(f"groups[{group_index}].logic 必须是 AND 或 OR")
            logic = "AND"
        conditions_raw = group_raw.get("conditions")
        if not isinstance(conditions_raw, list) or not conditions_raw:
            errors.append(f"groups[{group_index}] 至少需要一条条件")
            continue
        conditions: list[dict[str, Any]] = []
        for cond_raw in conditions_raw:
            if not isinstance(cond_raw, dict):
                errors.append(f"groups[{group_index}].conditions 中存在非对象")
                continue
            field = str(cond_raw.get("field") or "").strip()
            meta = FIELD_META.get(field)
            if meta is None:
                errors.append(f"字段 {field!r} 不在字段字典中")
                continue
            op = str(cond_raw.get("op") or "").strip()
            if op not in meta["ops"]:
                errors.append(f"字段 {field} 不支持算子 {op!r}；可用：{meta['ops']}")
                continue
            value = cond_raw.get("value")
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                errors.append(f"字段 {field} 的阈值必须是数字")
                continue
            condition_counter += 1
            condition_id = str(cond_raw.get("id") or f"c{condition_counter}").strip()
            try:
                confidence = float(cond_raw.get("confidence", 0.7))
            except (TypeError, ValueError):
                confidence = 0.7
            conditions.append(
                {
                    "id": condition_id,
                    "field": field,
                    "op": op,
                    "value": numeric_value,
                    "unit": meta["unit"],
                    "window": meta["window"],
                    "confidence": max(0.0, min(1.0, confidence)),
                }
            )
        if not conditions:
            continue
        group_id = str(group_raw.get("id") or f"g{len(groups) + 1}").strip()
        group = {
            "id": group_id,
            "label": label,
            "logic": logic,
            "source_phrase": str(group_raw.get("source_phrase") or label),
            "conditions": conditions,
        }
        if isinstance(group_raw.get("options"), list) and group_raw["options"]:
            group["options"] = group_raw["options"]
        groups.append(group)

    if not groups:
        errors.append("没有可执行的条件组")

    # ID uniqueness
    group_ids = [group["id"] for group in groups]
    if len(group_ids) != len(set(group_ids)):
        errors.append("group id 不能重复")
    condition_ids = [cond["id"] for group in groups for cond in group["conditions"]]
    if len(condition_ids) != len(set(condition_ids)):
        errors.append("condition id 不能重复")

    universe_type = str((raw.get("universe") or {}).get("type") or universe or "all_a_share")
    if universe_type not in VALID_UNIVERSES:
        universe_type = universe if universe in VALID_UNIVERSES else "all_a_share"

    policy = str(raw.get("missing_policy") or "exclude_with_flag")
    if policy not in VALID_POLICIES:
        policy = "exclude_with_flag"

    dsl = {
        "dsl_version": "1.0",
        "universe": {
            "type": universe_type,
            "exclude_st": True,
            "exclude_suspended": True,
            "min_listed_days": 250,
            "exclude_bse": True,
        },
        "groups": groups,
        "group_logic": "AND",
        "missing_policy": policy,
        "ranking": {"field": "composite_strength", "direction": "desc", "limit": 50},
    }
    return dsl, errors
