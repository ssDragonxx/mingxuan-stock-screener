"""Field registry: the contract between the LLM, the validator and the engine.

Every condition must reference a field in this registry. Each field declares
its unit, allowed operators, data source, update frequency, window and the
dataset it depends on.
"""

from __future__ import annotations

from typing import Any


def _field(
    label: str,
    unit: str,
    category: str,
    dataset: str,
    source: str,
    frequency: str,
    window: str,
    desc: str,
    *,
    step: float = 1,
    minimum: float | None = None,
    maximum: float | None = None,
    ops: list[str] | None = None,
    signed: bool = False,
    index_id: str | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "unit": unit,
        "step": step,
        "min": minimum,
        "max": maximum,
        "ops": ops or [">=", "<=", ">", "<"],
        "source": source,
        "frequency": frequency,
        "window": window,
        "desc": desc,
        "signed": signed,
        "category": category,
        "dataset": dataset,
        "index_id": index_id,
    }


FIELD_META: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------
    # Quote / valuation (cheap, full market)
    # ------------------------------------------------------------------
    "last_price": _field(
        "最新价", "元", "quote", "snapshot", "扶摇 · 行情快照", "日频", "current",
        "最新成交价，原始货币；仅作展示，不建议直接作为选股条件",
        step=0.01, minimum=0, maximum=100000,
    ),
    "pct_chg": _field(
        "当日涨跌幅", "%", "quote", "snapshot", "扶摇 · 行情快照", "日频", "current",
        "相对前收盘价的涨跌幅",
        step=0.1, minimum=-30, maximum=30, signed=True,
    ),
    "turnover": _field(
        "成交额", "亿元", "quote", "snapshot", "扶摇 · 行情快照", "日频", "current",
        "当日成交额，已换算为亿元",
        step=0.1, minimum=0, maximum=10000,
    ),
    "pe_ttm": _field(
        "PE(TTM)", "x", "valuation", "valuation", "扶摇 · 估值快照", "日频", "current",
        "市盈率 TTM；负值保留但不参与行业分位计算",
        step=0.1, minimum=-1000, maximum=10000, ops=[">", "<", ">=", "<="],
    ),
    "pe_mrq": _field(
        "PE(MRQ)", "x", "valuation", "valuation", "扶摇 · 估值快照", "日频", "current",
        "市盈率 MRQ；负值保留",
        step=0.1, minimum=-1000, maximum=10000, ops=[">", "<", ">=", "<="],
    ),
    "pb_mrq": _field(
        "PB(MRQ)", "x", "valuation", "valuation", "扶摇 · 估值快照", "日频", "current",
        "市净率 MRQ；净资产为负时可能不具常规意义",
        step=0.1, minimum=-1000, maximum=10000, ops=[">", "<", ">=", "<="],
    ),
    "ps_ttm": _field(
        "PS(TTM)", "x", "valuation", "valuation", "扶摇 · 估值快照", "日频", "current",
        "市销率 TTM",
        step=0.1, minimum=-1000, maximum=10000, ops=[">", "<", ">=", "<="],
    ),
    "pcf_ttm": _field(
        "PCF(TTM)", "x", "valuation", "valuation", "扶摇 · 估值快照", "日频", "current",
        "市现率 TTM；经营现金流为负时可能为负",
        step=0.1, minimum=-1000, maximum=10000, ops=[">", "<", ">=", "<="],
    ),
    "pe_industry_pct": _field(
        "PE 行业分位", "%", "valuation", "valuation", "扶摇 · 估值快照 + 行业成分", "日频", "current",
        "当前截面同行业正 PE 样本中的百分位；负 PE 不参与计算",
        step=1, minimum=0, maximum=100, ops=["<=", "<", ">=", ">"],
    ),
    "pb_industry_pct": _field(
        "PB 行业分位", "%", "valuation", "valuation", "扶摇 · 估值快照 + 行业成分", "日频", "current",
        "当前截面同行业正 PB 样本中的百分位",
        step=1, minimum=0, maximum=100, ops=["<=", "<", ">=", ">"],
    ),
    # ------------------------------------------------------------------
    # Technical (from daily K factor table)
    # ------------------------------------------------------------------
    "return_20d": _field(
        "20 日涨跌幅", "%", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_20d",
        "近 20 个交易日收盘价涨跌幅；未复权口径，除权日附近可能有偏差",
        step=1, minimum=-100, maximum=300, ops=["<=", "<", ">=", ">"], signed=True,
    ),
    "return_60d": _field(
        "60 日涨跌幅", "%", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_60d",
        "近 60 个交易日收盘价涨跌幅；未复权口径",
        step=1, minimum=-100, maximum=300, ops=["<=", "<", ">=", ">"], signed=True,
    ),
    "return_120d": _field(
        "120 日涨跌幅", "%", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_120d",
        "近 120 个交易日收盘价涨跌幅；未复权口径",
        step=1, minimum=-100, maximum=300, ops=["<=", "<", ">=", ">"], signed=True,
    ),
    "volatility_20d": _field(
        "20 日年化波动率", "%", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_20d",
        "近 20 个交易日日收益率标准差 × √252；未复权口径",
        step=1, minimum=0, maximum=300, ops=["<=", "<", ">=", ">"],
    ),
    "volatility_60d": _field(
        "60 日年化波动率", "%", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_60d",
        "近 60 个交易日日收益率标准差 × √252；未复权口径",
        step=1, minimum=0, maximum=300, ops=["<=", "<", ">=", ">"],
    ),
    "volatility_120d": _field(
        "120 日年化波动率", "%", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_120d",
        "近 120 个交易日日收益率标准差 × √252；未复权口径",
        step=1, minimum=0, maximum=300, ops=["<=", "<", ">=", ">"],
    ),
    "max_drawdown_60d": _field(
        "60 日最大回撤", "%", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_60d",
        "近 60 个交易日收盘价相对累计最高点的最大跌幅；未复权口径",
        step=1, minimum=-100, maximum=0, ops=[">=", ">", "<=", "<"], signed=True,
    ),
    "max_drawdown_120d": _field(
        "120 日最大回撤", "%", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_120d",
        "近 120 个交易日收盘价相对累计最高点的最大跌幅；未复权口径",
        step=1, minimum=-100, maximum=0, ops=[">=", ">", "<=", "<"], signed=True,
    ),
    "avg_turnover_20d": _field(
        "20 日平均成交额", "亿元", "technical", "tech_factors", "扶摇 · 日 K（未复权）", "日频", "last_20d",
        "近 20 个交易日成交额均值，已换算为亿元",
        step=0.1, minimum=0, maximum=10000,
    ),
    # ------------------------------------------------------------------
    # Dividend
    # ------------------------------------------------------------------
    "dividend_yield_ttm": _field(
        "股息率(TTM)", "%", "dividend", "dividend", "扶摇 · 复权因子 + 行情", "日频 / 事件", "ttm",
        "近 365 天每股现金分红（税前）之和 / 最新价",
        step=0.1, minimum=0, maximum=30, ops=[">=", ">", "<=", "<"],
    ),
    # ------------------------------------------------------------------
    # Financial indicators (on demand)
    # ------------------------------------------------------------------
    "revenue_yoy": _field(
        "营业收入同比", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期营业收入同比增长率",
        step=1, minimum=-100, maximum=300, signed=True,
        index_id="calculate_operating_income_yoy_growth_ratio",
    ),
    "net_profit_yoy": _field(
        "归母净利润同比", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期归属于母公司股东的净利润同比增长率",
        step=1, minimum=-300, maximum=500, signed=True,
        index_id="calculate_parent_holder_net_profit_yoy_growth_ratio",
    ),
    "operating_profit_yoy": _field(
        "营业利润同比", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期营业利润同比增长率",
        step=1, minimum=-300, maximum=500, signed=True,
        index_id="calculate_operating_profit_yoy_growth_ratio",
    ),
    "total_assets_growth_ratio": _field(
        "总资产增长率", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期总资产增长率",
        step=1, minimum=-100, maximum=300, signed=True,
        index_id="total_assets_growth_ratio",
    ),
    "gross_margin": _field(
        "销售毛利率", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期销售毛利率",
        step=0.1, minimum=-100, maximum=100,
        index_id="sale_gross_margin",
    ),
    "net_margin": _field(
        "销售净利率", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期销售净利率",
        step=0.1, minimum=-100, maximum=100,
        index_id="sale_net_interest_ratio",
    ),
    "roe": _field(
        "净资产收益率", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期加权平均净资产收益率",
        step=0.1, minimum=-100, maximum=100,
        index_id="index_weighted_avg_roe",
    ),
    "roe_deducted": _field(
        "扣非 ROE", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期扣非加权平均净资产收益率",
        step=0.1, minimum=-100, maximum=100,
        index_id="index_deduct_weighted_avg_roe",
    ),
    "total_assets_net_ratio": _field(
        "总资产收益率", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期总资产收益率",
        step=0.1, minimum=-100, maximum=100,
        index_id="total_assets_net_ratio",
    ),
    "debt_ratio": _field(
        "资产负债率", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期资产负债率",
        step=0.1, minimum=0, maximum=200,
        index_id="assets_debt_ratio",
    ),
    "current_ratio": _field(
        "流动比率", "x", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期流动比率",
        step=0.1, minimum=0, maximum=100,
        index_id="current_ratio",
    ),
    "quick_ratio": _field(
        "速动比率", "x", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期速动比率",
        step=0.1, minimum=0, maximum=100,
        index_id="quick_ratio",
    ),
    "cash_ratio": _field(
        "现金比率", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期现金比率",
        step=0.1, minimum=0, maximum=500,
        index_id="cash_ratio",
    ),
    "net_profit_cash_content": _field(
        "净利润现金含量", "x", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期净利润现金含量；接口返回百分数，系统换算为倍数，大于 1 表示利润有现金支撑",
        step=0.1, minimum=-100, maximum=100,
        index_id="net_profit_cash_content",
    ),
    "ocf_to_income": _field(
        "销售现金比率", "%", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期经营现金流净额 / 营业收入",
        step=0.1, minimum=-100, maximum=200,
        index_id="operating_cash_flow_net_divide_income",
    ),
    "cash_operating_index": _field(
        "现金营运指数", "x", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期现金营运指数",
        step=0.1, minimum=-100, maximum=100,
        index_id="cash_operating_index",
    ),
    "total_assets_turnover_ratio": _field(
        "总资产周转率", "次", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期总资产周转率",
        step=0.01, minimum=0, maximum=100,
        index_id="total_assets_turnover_ratio",
    ),
    "inventory_turnover_ratio": _field(
        "存货周转率", "次", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期存货周转率",
        step=0.01, minimum=0, maximum=1000,
        index_id="inventory_turnover_ratio",
    ),
    "receive_account_turnover_ratio": _field(
        "应收账款周转率", "次", "financial", "financials", "扶摇 · 财务指标", "季频", "latest_report",
        "最新报告期应收账款周转率",
        step=0.01, minimum=0, maximum=1000,
        index_id="receive_account_turnover_ratio",
    ),
}

FINANCIAL_FIELDS = {key for key, meta in FIELD_META.items() if meta["category"] == "financial"}
TECH_FIELDS = {key for key, meta in FIELD_META.items() if meta["category"] == "technical"}
VALUATION_FIELDS = {key for key, meta in FIELD_META.items() if meta["category"] == "valuation"}
DIVIDEND_FIELDS = {key for key, meta in FIELD_META.items() if meta["category"] == "dividend"}
QUOTE_FIELDS = {key for key, meta in FIELD_META.items() if meta["category"] == "quote"}
CHEAP_FIELDS = VALUATION_FIELDS | TECH_FIELDS | DIVIDEND_FIELDS | QUOTE_FIELDS

INDEX_ID_TO_FIELD = {
    meta["index_id"]: field
    for field, meta in FIELD_META.items()
    if meta.get("index_id")
}

DATASET_LABELS = {
    "snapshot": "行情快照",
    "valuation": "估值快照",
    "tech_factors": "技术因子",
    "dividend": "股息率",
    "financials": "财务指标",
    "industry": "行业成分",
}


def public_field_meta(fields: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Return the metadata safe to send to the frontend."""
    result: dict[str, dict[str, Any]] = {}
    for key, meta in FIELD_META.items():
        if fields is not None and key not in fields:
            continue
        item = {k: v for k, v in meta.items() if k not in {"index_id"}}
        result[key] = item
    return result


# ---------------------------------------------------------------------------
# Full financial indicator catalog (24 indicators returned by Fuyao)
#
# The screening field registry above is a subset used by conditions. The
# explanation layer intentionally receives the full snapshot + history so the
# AI can analyze the company beyond the few screening conditions.
# ---------------------------------------------------------------------------
INDICATOR_META: dict[str, dict[str, Any]] = {
    # 成长
    "total_assets_growth_ratio": {
        "key": "total_assets_growth_ratio", "label": "总资产增长率", "unit": "%", "category": "成长"
    },
    "operating_income_yoy_growth_ratio": {
        "key": "revenue_yoy", "label": "营业收入同比", "unit": "%", "category": "成长"
    },
    "calculate_operating_income_yoy_growth_ratio": {
        "key": "revenue_yoy", "label": "营业收入同比", "unit": "%", "category": "成长"
    },
    "net_profit_yoy_growth_ratio": {
        "key": "net_profit_yoy", "label": "归母净利润同比", "unit": "%", "category": "成长"
    },
    "calculate_net_profit_yoy_growth_ratio": {
        "key": "net_profit_yoy", "label": "归母净利润同比", "unit": "%", "category": "成长"
    },
    "calculate_parent_holder_net_profit_yoy_growth_ratio": {
        "key": "net_profit_yoy", "label": "归母净利润同比", "unit": "%", "category": "成长"
    },
    "operating_profit_yoy_growth_ratio": {
        "key": "operating_profit_yoy", "label": "营业利润同比", "unit": "%", "category": "成长"
    },
    "calculate_operating_profit_yoy_growth_ratio": {
        "key": "operating_profit_yoy", "label": "营业利润同比", "unit": "%", "category": "成长"
    },
    "fixed_asset_invest_expansion_ratio": {
        "key": None, "label": "固定资产扩张率", "unit": "%", "category": "成长"
    },
    # 盈利
    "sale_gross_margin": {
        "key": "gross_margin", "label": "销售毛利率", "unit": "%", "category": "盈利"
    },
    "sale_net_interest_ratio": {
        "key": "net_margin", "label": "销售净利率", "unit": "%", "category": "盈利"
    },
    "total_assets_net_ratio": {
        "key": "total_assets_net_ratio", "label": "总资产收益率", "unit": "%", "category": "盈利"
    },
    "index_weighted_avg_roe": {
        "key": "roe", "label": "加权ROE", "unit": "%", "category": "盈利"
    },
    "index_deduct_weighted_avg_roe": {
        "key": "roe_deducted", "label": "扣非加权ROE", "unit": "%", "category": "盈利"
    },
    # 偿债
    "current_ratio": {
        "key": "current_ratio", "label": "流动比率", "unit": "x", "category": "偿债"
    },
    "quick_ratio": {
        "key": "quick_ratio", "label": "速动比率", "unit": "x", "category": "偿债"
    },
    "assets_debt_ratio": {
        "key": "debt_ratio", "label": "资产负债率", "unit": "%", "category": "偿债"
    },
    "cash_ratio": {
        "key": "cash_ratio", "label": "现金比率", "unit": "%", "category": "偿债"
    },
    "earned_interest_multiple": {
        "key": None, "label": "已获利息倍数", "unit": "x", "category": "偿债"
    },
    "long_term_debt_equity_ratio": {
        "key": None, "label": "长期负债权益比率", "unit": "%", "category": "偿债"
    },
    # 营运
    "total_assets_turnover_ratio": {
        "key": "total_assets_turnover_ratio", "label": "总资产周转率", "unit": "次", "category": "营运"
    },
    "inventory_turnover_ratio": {
        "key": "inventory_turnover_ratio", "label": "存货周转率", "unit": "次", "category": "营运"
    },
    "current_assets_turnover_ratio": {
        "key": None, "label": "流动资产周转率", "unit": "次", "category": "营运"
    },
    "receive_account_turnover_ratio": {
        "key": "receive_account_turnover_ratio", "label": "应收账款周转率", "unit": "次", "category": "营运"
    },
    # 现金流
    "cash_operating_index": {
        "key": "cash_operating_index", "label": "现金营运指数", "unit": "x", "category": "现金流"
    },
    "operating_cash_flow_net_divide_income": {
        "key": "ocf_to_income", "label": "销售现金比率", "unit": "%", "category": "现金流"
    },
    "net_profit_cash_content": {
        "key": "net_profit_cash_content", "label": "净利润现金含量", "unit": "x",
        "category": "现金流", "divide_100": True,
    },
    "operating_cash_net_yoy_growth_ratio": {
        "key": None, "label": "经营现金流净额同比", "unit": "%", "category": "现金流"
    },
    "cash_meet_invest_ratio": {
        "key": None, "label": "现金满足投资比率", "unit": "x", "category": "现金流"
    },
}


def indicator_meta(index_id: str) -> dict[str, Any]:
    return INDICATOR_META.get(
        index_id,
        {"key": None, "label": index_id, "unit": "", "category": "其他"},
    )
