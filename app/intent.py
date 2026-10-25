"""Rule-based intent parser (fallback when DeepSeek is not configured/fails).

The output shape is the real product contract. DeepSeek returns the same shape;
the validator and engine do not care which parser produced it.
"""

from __future__ import annotations

from .field_registry import FIELD_META, public_field_meta

DEFAULT_QUERY = "经营改善、估值合理、走势相对稳定"


def _cond(counter: list[int], field: str, op: str, value, confidence: float = 0.8, window: str | None = None) -> dict:
    counter[0] += 1
    meta = FIELD_META[field]
    return {
        "id": f"c{counter[0]}",
        "field": field,
        "op": op,
        "value": value,
        "unit": meta["unit"],
        "window": window or meta["window"],
        "confidence": confidence,
    }


def _replace(cond: dict, field: str, op: str, value) -> dict:
    meta = FIELD_META[field]
    return {
        **cond,
        "field": field,
        "op": op,
        "value": value,
        "unit": meta["unit"],
        "window": meta["window"],
    }


def parse_intent(query: str, universe: str = "all_a_share") -> dict:
    q = (query or "").strip()
    groups: list[dict] = []
    counter = [0]
    assumptions: list[dict] = []
    clarifications: list[dict] = []
    conflicts: list[dict] = []
    unsupported: list[dict] = []

    def add_group(
        label: str,
        phrase: str,
        conditions: list[dict],
        options: list[dict] | None = None,
        logic: str = "AND",
    ) -> dict:
        group = {
            "id": f"g{len(groups) + 1}",
            "label": label,
            "logic": logic,
            "source_phrase": phrase,
            "conditions": conditions,
        }
        if options:
            group["options"] = options
            group["definition"] = options[0]["id"]
        groups.append(group)
        return group

    def add_growth() -> dict:
        c1 = _cond(counter, "revenue_yoy", ">=", 10, 0.85)
        c2 = _cond(counter, "net_profit_yoy", ">=", 0, 0.8)
        options = [
            {"id": "both", "label": "营收 + 利润双增", "conditions": [c1, c2]},
            {"id": "rev", "label": "仅营收增长", "conditions": [c1]},
            {"id": "profit", "label": "仅利润增长", "conditions": [c2]},
        ]
        assumptions.append(
            {
                "text": "经营改善按“营业收入同比 ≥ 10% 且 归母净利润同比 ≥ 0%”理解",
                "confidence": 0.85,
                "alternatives": ["仅营收增长", "仅利润增长", "毛利率提升"],
            }
        )
        return add_group("经营改善", "经营改善", [c1, c2], options)

    def add_fundamental() -> dict:
        c1 = _cond(counter, "revenue_yoy", ">=", 0, 0.8)
        c2 = _cond(counter, "net_profit_yoy", ">=", 0, 0.8)
        options = [
            {"id": "both", "label": "营收 + 利润不恶化", "conditions": [c1, c2]},
            {"id": "rev", "label": "仅营收不恶化", "conditions": [c1]},
            {"id": "profit", "label": "仅利润不恶化", "conditions": [c2]},
        ]
        assumptions.append(
            {
                "text": "“基本面没有恶化”按“营业收入同比 ≥ 0% 且 归母净利润同比 ≥ 0%”理解",
                "confidence": 0.8,
                "alternatives": ["仅营收不恶化", "仅利润不恶化"],
            }
        )
        return add_group("基本面未恶化", "基本面没有恶化", [c1, c2], options)

    def add_valuation() -> dict:
        c1 = _cond(counter, "pe_ttm", ">", 0, 0.9)
        c2 = _cond(counter, "pe_industry_pct", "<=", 60, 0.8)
        options = [
            {"id": "pct", "label": "PE 行业分位 ≤ 60%", "replace_condition": dict(c2)},
            {"id": "abs", "label": "绝对 PE ≤ 25", "replace_condition": _replace(c2, "pe_ttm", "<=", 25)},
        ]
        assumptions.append(
            {
                "text": "估值合理按“剔除负 PE，且 PE 行业分位 ≤ 60%”理解",
                "confidence": 0.8,
                "alternatives": ["绝对 PE 区间", "PB 行业分位"],
            }
        )
        group = add_group("估值合理", "估值合理", [c1, c2], options)
        clarifications.append(
            {
                "id": "cl_valuation",
                "group_id": group["id"],
                "question": "“估值合理”希望用行业分位还是绝对 PE？",
                "default": "pct",
                "options": options,
            }
        )
        return group

    def add_stability() -> dict:
        c1 = _cond(counter, "volatility_60d", "<=", 30, 0.8)
        c2 = _cond(counter, "max_drawdown_120d", ">=", -20, 0.8)
        options = [
            {"id": "both", "label": "低波动 + 小回撤", "conditions": [c1, c2]},
            {"id": "low_vol", "label": "仅低波动", "conditions": [c1]},
            {"id": "drawdown", "label": "仅小回撤", "conditions": [c2]},
        ]
        assumptions.append(
            {
                "text": "走势相对稳定按“60 日年化波动 ≤ 30% 且 120 日最大回撤 ≥ -20%”理解",
                "confidence": 0.75,
                "alternatives": ["仅低波动", "仅小回撤", "站上 60 日均线"],
            }
        )
        group = add_group("走势相对稳定", "走势相对稳定", [c1, c2], options)
        clarifications.append(
            {
                "id": "cl_stability",
                "group_id": group["id"],
                "question": "“走势相对稳定”更看重低波动还是小回撤？",
                "default": "both",
                "options": options,
            }
        )
        return group

    def add_dividend() -> dict:
        c1 = _cond(counter, "dividend_yield_ttm", ">=", 3, 0.8)
        options = [
            {"id": "3", "label": "股息率 ≥ 3%", "set_value": 3},
            {"id": "4", "label": "股息率 ≥ 4%", "set_value": 4},
        ]
        assumptions.append(
            {
                "text": "高股息按“近 12 个月股息率 ≥ 3%（税前）”理解",
                "confidence": 0.8,
                "alternatives": ["连续分红 ≥ 3 年（待接入）", "股息率行业分位"],
            }
        )
        return add_group("高股息", "高股息", [c1], options)

    def add_oversold() -> dict:
        c1 = _cond(counter, "return_20d", "<=", -15, 0.8)
        options = [
            {"id": "15", "label": "20 日跌幅 ≥ 15%", "set_value": -15},
            {"id": "20", "label": "20 日跌幅 ≥ 20%", "set_value": -20},
        ]
        assumptions.append(
            {
                "text": "超跌按“近 20 日涨跌幅 ≤ -15%”理解",
                "confidence": 0.8,
                "alternatives": ["偏离 60 日均线 ≤ -10%", "RSI 低位"],
            }
        )
        return add_group("近 20 日超跌", "近20日超跌", [c1], options)

    def add_cashflow() -> dict:
        c1 = _cond(counter, "net_profit_cash_content", ">=", 1.0, 0.8)
        options = [
            {"id": "1.0", "label": "现金含量 ≥ 1.0x", "set_value": 1.0},
            {"id": "1.2", "label": "现金含量 ≥ 1.2x", "set_value": 1.2},
        ]
        assumptions.append(
            {
                "text": "现金流健康按“净利润现金含量 ≥ 1.0x”理解（利润有现金支撑）",
                "confidence": 0.8,
                "alternatives": ["销售现金比率 ≥ 10%", "现金营运指数 ≥ 1"],
            }
        )
        return add_group("现金流健康", "现金流健康", [c1], options)

    # ------------------------------------------------------------------
    # Keyword routing
    # ------------------------------------------------------------------
    wants_fundamental = "基本面" in q and any(
        phrase in q for phrase in ("没有恶化", "未恶化", "没恶化", "不差", "稳健")
    )
    wants_growth = any(keyword in q for keyword in ("经营", "改善", "成长", "增长")) or (
        "基本面" in q and not wants_fundamental
    )
    wants_valuation = any(keyword in q.lower() for keyword in ("估值", "便宜", "pe", "pb", "分位"))
    wants_stability = any(keyword in q for keyword in ("稳定", "波动", "回撤", "稳"))
    wants_dividend = any(keyword in q for keyword in ("股息", "分红", "红利"))
    wants_oversold = any(keyword in q for keyword in ("超跌", "大跌", "回调", "跌"))
    wants_cashflow = any(keyword in q for keyword in ("现金流", "现金含量", "盈利质量"))
    wants_leader = any(keyword in q for keyword in ("龙头", "市值", "行业前"))

    if wants_fundamental:
        add_fundamental()
    elif wants_growth:
        add_growth()
    if wants_valuation:
        add_valuation()
    if wants_stability:
        add_stability()
    if wants_dividend:
        add_dividend()
    if wants_oversold:
        add_oversold()
    if wants_cashflow:
        add_cashflow()

    if not groups:
        add_growth()
        add_valuation()
        add_stability()
        assumptions.insert(
            0,
            {
                "text": "未识别到明确条件，已使用演示默认条件（经营改善 + 估值合理 + 走势稳定）",
                "confidence": 0.5,
                "alternatives": ["重新描述", "只保留其中一个条件"],
            },
        )

    # ------------------------------------------------------------------
    # Conflicts
    # ------------------------------------------------------------------
    def add_conflict(severity: str, code: str, message: str, suggestion: str) -> None:
        if not any(item["code"] == code for item in conflicts):
            conflicts.append(
                {
                    "severity": severity,
                    "code": code,
                    "message": message,
                    "suggestion": suggestion,
                }
            )

    if wants_dividend and ("成长" in q or "增长" in q or "高成长" in q):
        add_conflict(
            "soft",
            "DIVIDEND_AND_GROWTH",
            "高股息与高成长同时满足的样本通常很少，结果可能过窄",
            "可先放宽股息率到 2.5%，或把成长条件改为“营收不下降”",
        )
    if ("低估值" in q or "便宜" in q) and ("成长" in q or "高成长" in q):
        add_conflict(
            "soft",
            "VALUE_AND_GROWTH",
            "低估值与高成长存在天然张力，候选可能很少",
            "可先放宽 PE 行业分位到 70%，观察新增候选",
        )
    if wants_oversold and wants_stability:
        add_conflict(
            "semantic",
            "OVERSOLD_AND_STABLE",
            "“超跌”与“走势稳定”可能互相制约：超跌本身往往意味着近期波动较大",
            "可把“稳定”改为“回撤可控”，或分开做两个策略",
        )
    if "涨停" in q and ("低波动" in q or "稳定" in q):
        add_conflict(
            "soft",
            "LIMIT_UP_AND_LOW_VOL",
            "涨停与低波动通常不会同时出现",
            "建议拆成“强势”与“稳健”两个独立策略",
        )

    # ------------------------------------------------------------------
    # Unsupported capabilities
    # ------------------------------------------------------------------
    unsupported_map = {
        "主力资金": ("主力资金净流入", ["成交额", "换手率", "龙虎榜净买入"]),
        "北向": ("北向资金", ["成交额", "龙虎榜净买入"]),
        "资金流": ("资金流向", ["成交额", "换手率"]),
        "筹码": ("筹码分布", ["成交额", "换手率", "股价位置"]),
        "机构持仓": ("机构持仓", ["十大股东（待接入）", "龙虎榜机构席位"]),
        "研报": ("研报观点", ["公告/新闻上下文（后续接入）"]),
        "龙头": ("行业龙头/市值排名", ["行业营收排名（待接入）", "成交额排名"]),
        "市值": ("总市值", ["成交额排名", "流通市值（待接入）"]),
    }
    for keyword, (phrase, alternatives) in unsupported_map.items():
        if keyword in q:
            unsupported.append(
                {
                    "phrase": phrase,
                    "reason": "当前公开数据源暂不提供该字段的结构化筛选",
                    "alternatives": alternatives,
                }
            )

    # ------------------------------------------------------------------
    # Universe
    # ------------------------------------------------------------------
    universe_type = universe or "all_a_share"
    if "沪深300" in q:
        universe_type = "csi300"
    elif "中证500" in q or "沪深500" in q:
        universe_type = "csi500"
    elif "中证1000" in q:
        universe_type = "csi1000"

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
        "missing_policy": "exclude_with_flag",
        "ranking": {"field": "composite_strength", "direction": "desc", "limit": 50},
    }

    assumptions.append(
        {
            "text": "使用最新已披露报告期；缺失数据默认不计入入选",
            "confidence": 1.0,
            "alternatives": ["缺失视为通过（需显式开启）", "缺失视为失败"],
        }
    )
    assumptions.append(
        {
            "text": "剔除 ST、停牌、上市不足 250 天的股票",
            "confidence": 1.0,
            "alternatives": ["包含 ST", "包含次新股"],
        }
    )

    return {
        "query": q or DEFAULT_QUERY,
        "parser": "rule-based",
        "dsl": dsl,
        "field_meta": public_field_meta(),
        "assumptions": assumptions,
        "clarifications": clarifications,
        "conflicts": conflicts,
        "unsupported": unsupported,
        "meta": {
            "model": "rule-based",
            "mode": "rule",
            "latency_ms": 5,
            "note": "未配置 DeepSeek 或调用失败时使用规则解析；DSL 契约不变",
        },
    }
