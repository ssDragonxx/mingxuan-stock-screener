"""DeepSeek intent parsing and grounded explanation.

The LLM is used for two narrow jobs:
1. translate a natural-language query into a DSL (then validate + repair)
2. turn an evidence packet into a short narrative (then number-check)

It never produces the stock list and never computes numbers.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

import httpx
from openai import AsyncOpenAI

from .config import settings
from .db import get_db, now_iso
from .field_registry import FIELD_META, public_field_meta
from .validator import validate_dsl

_client: AsyncOpenAI | None = None
_http_client: httpx.AsyncClient | None = None


class LLMError(Exception):
    pass


def _get_client() -> AsyncOpenAI:
    global _client, _http_client
    if _client is None:
        # trust_env=False: on Windows, httpx otherwise reads the registry proxy
        # (e.g. a local Clash/V2Ray at 127.0.0.1:7897). If that proxy is not
        # running, every DeepSeek call fails with WinError 10061 even though
        # direct access works.
        _http_client = httpx.AsyncClient(trust_env=False, timeout=45.0)
        _client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=45.0,
            max_retries=1,
            http_client=_http_client,
        )
    return _client


def _field_catalog() -> str:
    lines = []
    for field, meta in FIELD_META.items():
        lines.append(
            f"- {field}: {meta['label']}（{meta['unit']}）；"
            f"可用算子 {', '.join(meta['ops'])}；{meta['desc']}"
        )
    return "\n".join(lines)


SYSTEM_PROMPT = f"""你是“选股意图编译器”，不是投资顾问。
你的唯一任务：把用户的自然语言选股想法翻译成 DSL JSON，供确定性筛选引擎执行。

可用字段（只能使用这些字段，不得发明）：
{_field_catalog()}

输出 JSON 结构：
{{
  "groups": [
    {{
      "id": "g1",
      "label": "经营改善",
      "logic": "AND",
      "source_phrase": "经营改善",
      "conditions": [
        {{"id": "c1", "field": "revenue_yoy", "op": ">=", "value": 10, "confidence": 0.85}}
      ]
    }}
  ],
  "assumptions": [
    {{"text": "经营改善按营收增长与利润增长理解", "confidence": 0.85, "alternatives": ["仅营收增长", "仅利润增长"]}}
  ],
  "clarifications": [
    {{"id": "cl1", "group_id": "g1", "question": "更看重低波动还是小回撤？", "default": "both", "options": [{{"id": "both", "label": "两者都要"}}]}}
  ],
  "conflicts": [],
  "unsupported": []
}}

规则：
1. 只能使用上面列出的字段；不得使用未列出的字段。
2. 每个 group 至少一条 condition；condition 必须有 field / op / value。
3. 模糊短语（经营改善、估值合理、走势稳定）必须拆成可执行的字段+阈值+时间窗。
4. 用户没有明确口径时，给出 assumptions，并在 clarifications 中提出一个最关键的问题。
5. 当前数据能力不支持的条件，放入 unsupported，并给出替代字段。
6. 不得输出股票名单、涨跌预测、收益承诺、买卖建议。
7. 只输出合法 JSON，不要 Markdown、不要解释、不要代码块。
8. 不要生成 options 字段；后端会根据条件自动补齐口径选项。
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    raise LLMError("DeepSeek 返回的内容不是合法 JSON")


async def _log_call(
    purpose: str,
    model: str,
    input_text: str,
    output: Any,
    validation: str,
    retries: int,
    latency_ms: int,
) -> None:
    try:
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO llm_calls(id, purpose, model, prompt_version, input_digest,
                  output_json, validation, retries, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hashlib.sha1(f"{purpose}{time.time()}".encode()).hexdigest()[:16],
                    purpose,
                    model,
                    "v1",
                    hashlib.sha256(input_text.encode()).hexdigest(),
                    json.dumps(output, ensure_ascii=False)[:20000],
                    validation,
                    retries,
                    latency_ms,
                    now_iso(),
                ),
            )
            await db.commit()
    except Exception:  # noqa: BLE001 - logging must never break the request
        pass


async def _chat(messages: list[dict[str, str]], *, json_mode: bool = True) -> str:
    client = _get_client()
    kwargs: dict[str, Any] = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 4096,
    }

    async def call_once(use_json_mode: bool) -> str:
        local = dict(kwargs)
        if use_json_mode:
            local["response_format"] = {"type": "json_object"}
        try:
            response = await client.chat.completions.create(**local)
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"DeepSeek 调用失败：{exc}") from exc
        content = response.choices[0].message.content if response.choices else None
        return content or ""

    content = ""
    if json_mode:
        try:
            content = await call_once(True)
        except LLMError:
            content = ""
    if not content:
        # Some OpenAI-compatible / reasoning models return empty content when
        # response_format is set, or need a no-JSON retry.
        content = await call_once(False)
    if not content:
        raise LLMError("DeepSeek 返回空内容")
    return content


def _options_for(fields: set[str], conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_field = {cond["field"]: cond for cond in conditions}

    if "revenue_yoy" in fields and "net_profit_yoy" in fields:
        c1, c2 = by_field["revenue_yoy"], by_field["net_profit_yoy"]
        return [
            {"id": "both", "label": "营收 + 利润双增", "conditions": [c1, c2]},
            {"id": "rev", "label": "仅营收增长", "conditions": [c1]},
            {"id": "profit", "label": "仅利润增长", "conditions": [c2]},
        ]
    if "pe_industry_pct" in fields:
        pct = by_field["pe_industry_pct"]
        absolute = {
            **pct,
            "field": "pe_ttm",
            "op": "<=",
            "value": 25,
            "unit": FIELD_META["pe_ttm"]["unit"],
            "window": FIELD_META["pe_ttm"]["window"],
        }
        return [
            {"id": "pct", "label": "PE 行业分位 ≤ 60%", "replace_condition": pct},
            {"id": "abs", "label": "绝对 PE ≤ 25", "replace_condition": absolute},
        ]
    if "volatility_60d" in fields and "max_drawdown_120d" in fields:
        low = by_field["volatility_60d"]
        drawdown = by_field["max_drawdown_120d"]
        return [
            {"id": "both", "label": "低波动 + 小回撤", "conditions": [low, drawdown]},
            {"id": "low_vol", "label": "仅低波动", "conditions": [low]},
            {"id": "drawdown", "label": "仅小回撤", "conditions": [drawdown]},
        ]
    if "dividend_yield_ttm" in fields:
        return [
            {"id": "3", "label": "股息率 ≥ 3%", "set_value": 3},
            {"id": "4", "label": "股息率 ≥ 4%", "set_value": 4},
        ]
    if "return_20d" in fields:
        return [
            {"id": "15", "label": "20 日跌幅 ≥ 15%", "set_value": -15},
            {"id": "20", "label": "20 日跌幅 ≥ 20%", "set_value": -20},
        ]
    if "net_profit_cash_content" in fields:
        return [
            {"id": "1.0", "label": "现金含量 ≥ 1.0x", "set_value": 1.0},
            {"id": "1.2", "label": "现金含量 ≥ 1.2x", "set_value": 1.2},
        ]
    return []


def _decorate(dsl: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    groups = dsl["groups"]
    assumptions = raw.get("assumptions") if isinstance(raw.get("assumptions"), list) else []
    clarifications = raw.get("clarifications") if isinstance(raw.get("clarifications"), list) else []
    conflicts = raw.get("conflicts") if isinstance(raw.get("conflicts"), list) else []
    unsupported = raw.get("unsupported") if isinstance(raw.get("unsupported"), list) else []

    for group in groups:
        fields = {cond["field"] for cond in group["conditions"]}
        options = _options_for(fields, group["conditions"])
        if options:
            group["options"] = options
            group["definition"] = options[0]["id"]
        else:
            group.pop("options", None)
            group.pop("definition", None)

    # Only keep clarifications whose options can actually mutate the DSL.
    functional_clarifications: list[dict[str, Any]] = []
    for item in clarifications:
        if not isinstance(item, dict):
            continue
        options = item.get("options")
        if not isinstance(options, list) or not options:
            continue
        if not all(
            isinstance(option, dict)
            and any(key in option for key in ("conditions", "replace_condition", "set_value"))
            for option in options
        ):
            continue
        functional_clarifications.append(item)
    clarifications = functional_clarifications

    # Add high-value clarifications if the LLM did not already return them.
    existing_group_ids = {item.get("group_id") for item in clarifications if isinstance(item, dict)}
    for group in groups:
        fields = {cond["field"] for cond in group["conditions"]}
        if "pe_industry_pct" in fields and group["id"] not in existing_group_ids:
            clarifications.append(
                {
                    "id": f"cl_val_{group['id']}",
                    "group_id": group["id"],
                    "question": "“估值合理”希望用行业分位还是绝对 PE？",
                    "default": group.get("definition") or "pct",
                    "options": group.get("options") or [],
                }
            )
        if (
            "volatility_60d" in fields
            and "max_drawdown_120d" in fields
            and group["id"] not in existing_group_ids
        ):
            clarifications.append(
                {
                    "id": f"cl_stab_{group['id']}",
                    "group_id": group["id"],
                    "question": "“走势相对稳定”更看重低波动还是小回撤？",
                    "default": group.get("definition") or "both",
                    "options": group.get("options") or [],
                }
            )

    # Normalize assumptions and always add the global data assumptions.
    clean_assumptions: list[dict[str, Any]] = []
    for item in assumptions:
        if isinstance(item, dict) and item.get("text"):
            try:
                confidence = float(item.get("confidence", 0.7) or 0.7)
            except (TypeError, ValueError):
                confidence = 0.7
            clean_assumptions.append(
                {
                    "text": str(item["text"]),
                    "confidence": max(0.0, min(1.0, confidence)),
                    "alternatives": item.get("alternatives") if isinstance(item.get("alternatives"), list) else [],
                }
            )
    if not clean_assumptions:
        for group in groups:
            cond_text = "；".join(
                f"{FIELD_META[c['field']]['label']} {c['op']} {c['value']}{FIELD_META[c['field']]['unit']}"
                for c in group["conditions"]
            )
            clean_assumptions.append(
                {
                    "text": f"“{group['label']}”按“{cond_text}”理解",
                    "confidence": 0.7,
                    "alternatives": [],
                }
            )
    clean_assumptions.append(
        {
            "text": "使用最新已披露报告期；缺失数据默认不计入入选",
            "confidence": 1.0,
            "alternatives": ["缺失视为通过（需显式开启）", "缺失视为失败"],
        }
    )
    clean_assumptions.append(
        {
            "text": "剔除 ST、停牌、上市不足 250 天的股票",
            "confidence": 1.0,
            "alternatives": ["包含 ST", "包含次新股"],
        }
    )

    # Deduplicate assumptions by text.
    seen = set()
    unique_assumptions = []
    for item in clean_assumptions:
        if item["text"] in seen:
            continue
        seen.add(item["text"])
        unique_assumptions.append(item)

    return {
        "dsl": dsl,
        "assumptions": unique_assumptions,
        "clarifications": clarifications,
        "conflicts": conflicts,
        "unsupported": unsupported,
    }


async def parse_with_deepseek(query: str, universe: str = "all_a_share") -> dict[str, Any]:
    if not settings.deepseek_api_key:
        raise LLMError("DeepSeek 未配置")
    started = time.perf_counter()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"用户输入：{query}\n数据范围：{universe}"},
    ]
    retries = 0
    last_raw: dict[str, Any] = {}
    last_errors: list[str] = []
    content = ""
    for attempt in range(3):
        content = await _chat(messages, json_mode=True)
        try:
            last_raw = _extract_json(content)
        except LLMError as exc:
            last_errors = [str(exc)]
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"输出不是合法 JSON：{exc}。请只输出 JSON。"})
            retries += 1
            continue
        dsl, errors = validate_dsl(last_raw, universe)
        if not errors:
            decorated = _decorate(dsl, last_raw)
            latency_ms = round((time.perf_counter() - started) * 1000)
            await _log_call("parse", settings.deepseek_model, query, last_raw, "ok", retries, latency_ms)
            return {
                "query": query,
                "parser": "deepseek",
                "dsl": decorated["dsl"],
                "field_meta": public_field_meta(),
                "assumptions": decorated["assumptions"],
                "clarifications": decorated["clarifications"],
                "conflicts": decorated["conflicts"],
                "unsupported": decorated["unsupported"],
                "meta": {
                    "model": settings.deepseek_model,
                    "mode": "llm",
                    "latency_ms": latency_ms,
                    "retries": retries,
                    "validation": "ok",
                },
            }
        last_errors = errors
        retries += 1
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": "上次 DSL 未通过校验，请只修复以下错误并重新输出完整 JSON：\n- "
                + "\n- ".join(errors),
            }
        )
    latency_ms = round((time.perf_counter() - started) * 1000)
    await _log_call(
        "parse",
        settings.deepseek_model,
        query,
        last_raw,
        "failed: " + "; ".join(last_errors),
        retries,
        latency_ms,
    )
    raise LLMError("DeepSeek 输出未通过校验：" + "; ".join(last_errors))


# ---------------------------------------------------------------------------
# Grounded explanation
# ---------------------------------------------------------------------------
EXPLAIN_PROMPT = """你是金融研究助手。
基于 <facts> 中的结构化事实，对这只股票做一次完整分析：筛选结论、财务质量、估值与走势、技术面、风险与未知。
规则：
1. 只能使用 <facts> 中的数字与事实，不得引入任何新数字，不得自行计算新数字。
2. 区分事实、推断与未知；缺失的数据要明确说“数据缺失/未知”。
3. 不得预测涨跌、不得给买卖建议、不得承诺收益。
4. 财务分析要引用具体指标和报告期；趋势分析要引用至少两个报告期。
5. 每个部分 2-4 句，中文，简洁。
6. 输出 JSON：{"summary":"一句话结论","financial":"财务质量与趋势","valuation":"估值","technical":"技术面","risks":"风险与未知"}
"""


def _numbers(text: str) -> list[float]:
    """Extract numbers for the hallucination check.

    Stock codes and dates are removed first: they are identifiers/timestamps,
    not financial values, and would otherwise cause false failures.
    """
    cleaned = re.sub(r"\b\d{6}\.(?:SH|SZ|BJ)\b", " ", text or "", flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?",
        " ",
        cleaned,
    )
    values: list[float] = []
    for match in re.findall(r"-?\d+(?:\.\d+)?", cleaned):
        try:
            number = float(match)
        except ValueError:
            continue
        # Ignore bare 6-digit identifiers such as 603986 or 600519.
        if number.is_integer() and 100000 <= abs(number) <= 999999:
            continue
        values.append(number)
    return values


def _numbers_ok(text: str, facts: dict[str, Any]) -> bool:
    allowed = set(facts.get("allowed_numbers") or set())
    for number in _numbers(text):
        if 1900 <= abs(number) <= 2100:
            continue
        if round(number, 1) in allowed or round(abs(number), 1) in allowed:
            continue
        return False
    return True


async def explain_with_deepseek(
    stock: dict[str, Any],
    facts: dict[str, Any],
) -> dict[str, Any] | None:
    if not settings.deepseek_api_key:
        return None
    started = time.perf_counter()
    facts_text = facts.get("facts_text") or ""
    messages = [
        {"role": "system", "content": EXPLAIN_PROMPT},
        {"role": "user", "content": f"<facts>\n{facts_text}\n</facts>"},
    ]
    try:
        content = await _chat(messages, json_mode=True)
        raw = _extract_json(content)

        sections: list[dict[str, str]] = []
        for key, title in (
            ("summary", "结论"),
            ("financial", "财务质量"),
            ("valuation", "估值"),
            ("technical", "技术面"),
            ("risks", "风险与未知"),
        ):
            text = str(raw.get(key) or "").strip()
            if text:
                sections.append({"title": title, "text": text})
        if not sections:
            text = str(raw.get("text") or "").strip()
            if text:
                sections.append({"title": "分析", "text": text})
        if not sections:
            return None

        full_text = "\n\n".join(f"{section['title']}\n{section['text']}" for section in sections)
        latency_ms = round((time.perf_counter() - started) * 1000)
        ok = _numbers_ok(full_text, facts)
        await _log_call(
            "explain",
            settings.deepseek_model,
            facts_text,
            raw,
            "ok" if ok else "number_check_failed",
            0,
            latency_ms,
        )
        if not ok:
            return None
        return {
            "text": full_text,
            "mode": "llm",
            "number_check": "ok",
            "sections": sections,
            "facts_used": facts.get("facts_used"),
        }
    except Exception:  # noqa: BLE001
        return None
