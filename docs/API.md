# API 契约

Base URL：`/api`  
编码：UTF-8 · 请求/响应：`application/json`

错误响应：

```json
{
  "error": {
    "code": "DATA_NOT_READY",
    "message": "本地数据尚未初始化，无法筛选全市场。",
    "hint": "在 .env 配置 FUYAO_API_KEY 后运行：python -m app.data.ingest --all"
  }
}
```

常见错误码：

| code | HTTP | 含义 |
|---|---|---|
| `INVALID_DSL` | 400 | DSL 字段/算子/单位校验失败 |
| `DATA_NOT_READY` | 503 | 本地数据未初始化，或所选指数成分未初始化 |
| `STOCK_NOT_FOUND` | 404 | 未找到该股票 |
| `JOB_NOT_FOUND` | 404 | 筛选任务不存在或已过期 |
| `FUYAO_ERROR` | 502 | 扶摇上游错误（含 request_id） |
| `LLM_ERROR` | 502 | DeepSeek 调用/校验失败（通常已回退规则解析） |

---

## 1. 健康与数据状态

### GET `/api/health`

```json
{ "status": "ok", "mode": "mock | live", "llm_enabled": true, "version": "0.2.0" }
```

### GET `/api/status`

```json
{
  "mode": "live",
  "ready": true,
  "universe": { "count": 5412, "label": "全 A 股" },
  "quote": { "as_of": "2026-10-24T15:00:00+08:00", "status": "ok" },
  "valuation": { "as_of": "2026-10-24...", "status": "ok" },
  "daily_k": { "as_of": "2026-10-24...", "status": "ok" },
  "financials": {
    "latest_report": "2026-2",
    "label": "2026 中报",
    "coverage": 0.18,
    "status": "partial",
    "note": "财务数据按需取数并缓存"
  },
  "datasets": {
    "tickers": { "count": 5412, "as_of": "...", "ready": true },
    "snapshot": { "count": 5412, "as_of": "...", "ready": true },
    "valuation": { "count": 5412, "as_of": "...", "ready": true },
    "tech_factors": { "count": 5412, "as_of": "...", "ready": true },
    "industry": { "count": 5412, "as_of": "...", "ready": true },
    "dividend": { "count": 4200, "as_of": "...", "ready": true },
    "financials": { "count": 980, "report": "2026-2", "coverage": 0.18, "ready": true }
  },
  "sources": [{ "name": "扶摇", "status": "ok", "note": "本地 SQLite 缓存" }],
  "definitions": [{ "key": "pe_ttm", "label": "PE(TTM)", "text": "..." }],
  "hint": null
}
```

`mode = mock` 时 `universe.count = 43`，`datasets` 全部 ready。

---

## 2. 意图解析

### POST `/api/parse`

请求：

```json
{ "query": "经营改善、估值合理、走势相对稳定", "universe": "all_a_share" }
```

`universe`：`all_a_share` / `csi300` / `csi500` / `csi1000`

响应：

```json
{
  "query": "...",
  "parser": "deepseek | rule-based",
  "dsl": {
    "dsl_version": "1.0",
    "universe": {
      "type": "all_a_share",
      "exclude_st": true,
      "exclude_suspended": true,
      "min_listed_days": 250,
      "exclude_bse": true
    },
    "groups": [
      {
        "id": "g1",
        "label": "经营改善",
        "logic": "AND",
        "source_phrase": "经营改善",
        "conditions": [
          {
            "id": "c1",
            "field": "revenue_yoy",
            "op": ">=",
            "value": 10,
            "unit": "%",
            "window": "latest_report",
            "confidence": 0.85
          }
        ],
        "options": [
          {
            "id": "both",
            "label": "营收 + 利润双增",
            "conditions": [ /* 完整条件对象，切换口径时整体替换 */ ]
          }
        ],
        "definition": "both"
      }
    ],
    "group_logic": "AND",
    "missing_policy": "exclude_with_flag",
    "ranking": { "field": "composite_strength", "direction": "desc", "limit": 50 }
  },
  "field_meta": {
    "revenue_yoy": {
      "label": "营业收入同比",
      "unit": "%",
      "step": 1,
      "min": -100,
      "max": 300,
      "ops": [">=", "<=", ">", "<"],
      "source": "扶摇 · 财务指标",
      "frequency": "季频",
      "window": "latest_report",
      "desc": "最新报告期营业收入同比增长率",
      "signed": true,
      "category": "financial",
      "dataset": "financials"
    }
  },
  "assumptions": [
    { "text": "...", "confidence": 0.85, "alternatives": ["..."] }
  ],
  "clarifications": [
    {
      "id": "cl_valuation",
      "group_id": "g2",
      "question": "“估值合理”希望用行业分位还是绝对 PE？",
      "default": "pct",
      "options": [
        { "id": "pct", "label": "PE 行业分位 ≤ 60%", "replace_condition": { /* ... */ } }
      ]
    }
  ],
  "conflicts": [
    { "severity": "soft", "code": "VALUE_AND_GROWTH", "message": "...", "suggestion": "..." }
  ],
  "unsupported": [
    { "phrase": "行业龙头/市值排名", "reason": "...", "alternatives": ["..."] }
  ],
  "meta": {
    "model": "deepseek-chat",
    "mode": "llm",
    "latency_ms": 1800,
    "retries": 0,
    "validation": "ok",
    "fallback_reason": null
  },
  "data_status": { /* 同 GET /api/status */ }
}
```

`options[]` 的三种应用方式：

- `conditions`：用完整条件数组替换当前组条件（可恢复被删除的条件）
- `replace_condition`：替换同 id 条件
- `set_value`：修改组内第一条条件的值

`conflicts[].severity`：`hard` / `soft` / `data` / `semantic`

---

## 3. 筛选

### POST `/api/preview`

请求：`{ "dsl": { ... } }`

只使用已缓存财务数据，不触发按需取数；用于条件工作台的实时预览。

响应：

```json
{
  "summary": {
    "universe": 5412,
    "cheap_excluded": 4231,
    "after_cheap": 1181,
    "evaluated": 500,
    "truncated": 681,
    "included": 23,
    "near_miss": 41,
    "excluded": 420,
    "unknown": 16,
    "pending": 300,
    "data_completeness": "94%",
    "financial_report": "2026-2",
    "returned": 500
  },
  "funnel": [
    { "label": "全 A 股票", "count": 5412 },
    { "label": "便宜条件后", "count": 1181 },
    { "label": "完整评估", "count": 500 },
    { "label": "入选", "count": 23 }
  ],
  "warnings": ["..."],
  "data_status": { /* ... */ },
  "meta": { "mode": "live", "fetch": false, "max_candidates": 500, "duration_ms": 120 }
}
```

### POST `/api/screen`

同步执行，会按需取财务数据；可能耗时 20–40 秒。前端一般使用下面的 job API。

响应：与 job 完成后的 `result` 相同。

### POST `/api/screen/jobs`

请求：`{ "dsl": { ... } }`  
响应：`{ "job_id": "abc123" }`

### GET `/api/screen/jobs/{job_id}`

```json
{
  "job_id": "abc123",
  "status": "queued | running | done | failed",
  "progress": {
    "stage": "universe | cheap | financials | evaluate | done",
    "done": 120,
    "total": 300,
    "message": "按需取财务 120/300"
  },
  "result": { /* status=done 时返回完整结果 */ },
  "error": null
}
```

失败时：

```json
{
  "status": "failed",
  "error": {
    "code": "DATA_NOT_READY",
    "message": "...",
    "hint": "python -m app.data.ingest --all"
  }
}
```

完整结果：

```json
{
  "summary": { /* 同 preview，含 evaluated/returned */ },
  "funnel": [ /* ... */ ],
  "stocks": [
    {
      "thscode": "600519.SH",
      "name": "贵州茅台",
      "industry": "白酒",
      "status": "included | near_miss | excluded | unknown",
      "data_completeness": "6/6",
      "summary_reason": "6/6 条件通过；...",
      "conditions": [
        {
          "condition_id": "c1",
          "group_id": "g1",
          "group_label": "经营改善",
          "field": "revenue_yoy",
          "field_label": "营业收入同比",
          "value": 18.2,
          "unit": "%",
          "op": ">=",
          "threshold": 10,
          "status": "pass | fail | unknown",
          "gap": 0,
          "gap_text": null,
          "source": "扶摇 · 财务指标",
          "as_of": "2026-06-30",
          "note": "2026 中报",
          "category": "financial"
        }
      ],
      "risk_flags": ["..."],
      "raw": { /* provider 行数据 */ },
      "fail_count": 0,
      "unknown_count": 0,
      "original_unknown_count": 0,
      "min_gap": 0,
      "group_statuses": [{ "group_id": "g1", "status": "pass" }],
      "cheap_failed": false
    }
  ],
  "excluded_breakdown": [
    { "field": "revenue_yoy", "label": "营业收入同比", "count": 18, "kind": "fail" },
    { "field": "__unknown__", "label": "含缺失项（任一条件）", "count": 3, "kind": "unknown" }
  ],
  "sensitivity": [
    {
      "condition_id": "c1",
      "label": "营业收入同比",
      "field": "revenue_yoy",
      "unit": "%",
      "current": 10,
      "points": [
        { "threshold": 0, "included": 23 },
        { "threshold": 5, "included": 17 },
        { "threshold": 10, "included": 11 }
      ],
      "binding": true,
      "relax_to": 0,
      "delta": 12,
      "direction": "lower_is_looser"
    }
  ],
  "data_status": { /* ... */ },
  "warnings": ["..."],
  "meta": {
    "mode": "live",
    "fetch": true,
    "max_candidates": 500,
    "financial_report": "2026-2",
    "duration_ms": 23456
  }
}
```

`cheap_failed = true` 的股票表示被前置便宜条件剔除、未取财务；其 `summary_reason` 以“前置条件不满足”开头。

---

## 4. 单股诊断

### POST `/api/diagnose`

请求：

```json
{ "query": "600036", "dsl": { "...": "..." } }
```

`query` 支持 `thscode`、六位代码或股票名称。

响应：`{ "stock": { /* 同上 stock 对象 */ } }`

---

## 5. AI 解读

### POST `/api/explain`

请求：`{ "query": "600036", "dsl": { ... } }`

响应：

```json
{
  "stock": { /* 同上 stock 对象 */ },
  "explanation": {
    "text": "招商银行本次为近邻...",
    "mode": "llm | template",
    "number_check": "ok | failed | not_applicable"
  }
}
```

- `mode=llm`：DeepSeek 生成，且所有数字通过证据包校验。
- `mode=template`：未配置 DeepSeek，或数字校验未通过时的确定性模板。

---

## 6. 策略与监控

### GET `/api/strategies`

```json
{
  "items": [
    {
      "id": "abc123",
      "name": "稳健组合",
      "query": "经营改善、估值合理...",
      "created_at": "2026-10-25T18:00:00+08:00",
      "monitor_enabled": 1,
      "last_run_at": "2026-10-25T18:30:00+08:00"
    }
  ]
}
```

### POST `/api/strategies`

```json
{
  "name": "稳健组合",
  "query": "经营改善、估值合理...",
  "dsl": { "...": "..." },
  "monitor_enabled": true
}
```

### POST `/api/strategies/{id}/run`

立即执行一次，返回：

```json
{
  "strategy_id": "abc123",
  "run_at": "...",
  "summary": { "...": "..." },
  "funnel": [ /* ... */ ],
  "included": [{ "thscode": "600519.SH", "name": "贵州茅台" }],
  "diff": {
    "first_run": false,
    "new": ["600519.SH"],
    "exit": ["000001.SZ"],
    "previous_run_at": "...",
    "current_count": 11,
    "previous_count": 10
  }
}
```

### GET `/api/strategies/{id}/runs?limit=20`

返回最近的监控运行记录（含 `summary_json` / `diff_json`）。

### POST `/api/admin/ingest`

需要 header `X-Admin-Token` 与 `.env` 中的 `ADMIN_TOKEN` 一致；否则 403。  
后台启动全量数据初始化，日志输出到服务端。

---

## 7. DSL 约束

- `groups` 至少 1 组，每组至少 1 条条件。
- `field` 必须在 `field_meta` 中。
- `op` 必须是字段允许的算子。
- `missing_policy` ∈ `exclude_with_flag` / `include_with_warning` / `fail`。
- `universe.type` ∈ `all_a_share` / `csi300` / `csi500` / `csi1000`。
- 负 PE 不参与行业分位；估值分位条件在负 PE 时返回 `unknown`，不会当作通过。
