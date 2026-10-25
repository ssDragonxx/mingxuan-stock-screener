# 测试说明

> 覆盖主链路、数据缺失/接口失败、极端与合规边界。  
> 验收日期：2026-10-25。真实数据来自客户提供的扶摇/DeepSeek Key；敏感 Key 不进入仓库。

**结论先行：**

- Mock 与真实数据的主链路均已跑通；真实 smoke 返回 `included=198 / near_miss=82 / excluded=4,040 / unknown=19 / returned=4,339`。
- 鉴权失败、无效 DSL、未知股票/任务等错误路径均返回明确错误码，不崩溃。
- 缺失数据策略、候选截断、负 PE、合规类 query 均有对应行为。
- 未覆盖：高并发压测、每日监控多日长跑、2026Q3 披露回退、回测（功能未实现）、多用户权限。

---

## 0. 测试策略

| 层级 | 目的 | 方式 |
|---|---|---|
| **API 冒烟** | 主链路是否可用、四类计数是否自洽 | `scripts/smoke_test.py` |
| **负向 / 边界** | 错误码、缺失数据、极端阈值、合规边界 | 手工 API 调用（本文件记录命令与结果） |
| **浏览器走查** | 真实交互、控制台、响应式布局 | `scripts/ui_smoke.py`（Playwright） |
| **真实数据联调** | 扶摇字段/报告期/单位/覆盖率 | 真实 Key + SQLite 对账 |
| **确定性对账** | funnel、四类计数、证据与原始行一致 | 响应 JSON + `data_versions` / `llm_calls` |

**状态标记：**

- ✅ 本次验收（2026-10-25）实际执行并通过
- 🟡 同日早前已执行，或由历史记录/代码路径确认
- ⚪ 已设计用例，尚未执行（见第 6 节缺口）

---

## 1. 环境与版本

| 项 | 版本 / 说明 |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13.13 |
| FastAPI | 0.142.2 |
| uvicorn | 0.54.0 |
| httpx | 0.28.1 |
| pydantic | 2.13.2 |
| Polars | 2.0.0 |
| APScheduler | 3.11.3 |
| Node / npm | v24.9.0 / 11.6.0 |
| SQLite | WAL 模式 |
| 前端 | Vue 3 + Vite 6 + TypeScript + Pinia |
| 浏览器走查 | Playwright + Chromium |
| 数据源 | 扶摇 REST（真实 Key）；DeepSeek（真实 Key） |

---

## 2. 快速回归

### 2.1 Mock 模式（零 Key）

```bash
# 终端 1：独立数据目录，避免污染真实缓存
mkdir -p data/mock_test
FUYAO_API_KEY= DEEPSEEK_API_KEY= DATA_DIR="$PWD/data/mock_test" \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1

# 终端 2
python scripts/smoke_test.py http://127.0.0.1:8001
```

> Windows PowerShell 不支持 `VAR=value cmd` 写法，可先 `$env:FUYAO_API_KEY=""` 再启动。

**Mock 预期：**

- `/api/status`：`mode=mock`, `ready=true`, 43 只
- 默认 query：3 组 6 条条件
- summary：`included=11, near_miss=13, excluded=16, unknown=3, returned=43`
- `cheap_excluded=16`, `evaluated=27`, `pending=3`, `data_completeness=96%`

### 2.2 真实数据模式

```bash
# 终端 1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

# 终端 2
python scripts/smoke_test.py
python scripts/ui_smoke.py        # 可选，需要 Playwright
```

**真实 smoke 预期（以当次数据为准）：**

- `parser=deepseek`
- 四类之和 = `returned`
- `included > 0`
- 单股诊断、AI 解读可返回

---

## 3. 测试矩阵

### 3.1 主链路

| ID | 场景 | 操作 | 预期 | 状态 |
|---|---|---|---|---|
| M1 | 默认意图解析 | 输入“经营改善、估值合理、走势相对稳定” | 3 组条件；假设/澄清/冲突卡出现 | ✅ API / 🟡 UI |
| M2 | AI 假设与澄清 | 查看侧栏“AI 的理解”“需要你确认” | 每条假设有置信度与替代；口径可切换 | ✅ API / 🟡 UI |
| M3 | 条件编辑 | PE 行业分位 60 → 40 | 预览更新；显示相对初始条件变化 | 🟡 |
| M4 | 口径切换 | 绝对 PE ≤ 25 / 仅低波动 / 恢复组合 | 条件整体替换；能恢复被删条件 | 🟡 |
| M5 | 添加条件 | 添加“股息率 ≥ 4%” | 出现“自定义条件”组；预览更新 | 🟡 |
| M6 | 缺失策略 | 切换不计入 / 计入但标记 / 直接失败 | 三类计数变化；数据不足单独呈现 | ✅ API |
| M7 | 预览影响 | 修改阈值后观察预览卡 | 入选/近邻/数据不足变化；不触发财务取数 | 🟡 |
| M8 | 筛选任务 | 点击“开始筛选” | 进度任务 → 结果页；四类计数自洽 | ✅ API |
| M9 | 结果 Tab | 入选 / 近邻 / 未入选 / 数据不足 / 敏感性 | 表格与计数一致 | 🟡 |
| M10 | 单股证据 | 点击任意行 | 逐条件值/阈值/来源/时点；原始响应可展开 | 🟡 |
| M11 | 单股诊断 | 未入选 Tab 输入 600036 | 返回逐条件证据与差距 | ✅ API |
| M12 | AI 解读 | 抽屉“生成分析” | 配置 DeepSeek 时 `mode=llm`；未配置时模板 | ✅ API |
| M13 | 对比 | 加入 2 只 → 对比 | 并排显示条件值/状态 | 🟡 |
| M14 | 数据说明 | 点击“查看数据说明” | 数据集覆盖、财务口径、技术因子口径 | 🟡 |
| M15 | 策略保存 | 保存策略 | 策略出现在策略库 | 🟡 |
| M16 | 监控任务 | 创建监控并立即检查 | 生成运行记录；显示新进/退出 diff | 🟡 |
| M17 | 移动端 | 390×844 | 单列布局；表格横向滚动；抽屉全宽 | 🟡 |

### 3.2 数据缺失 / 接口失败

| ID | 场景 | 操作 | 预期 | 状态 |
|---|---|---|---|---|
| F1 | 扶摇 Key 无效 | 用 fake key 调真实接口 | `FuyaoError code=2003`，保留 `request_id`，不崩溃 | ✅ |
| F2 | 真实模式未初始化 | 配置 Key 但本地无 tickers | `/api/status` `ready=false` + hint；preview/screen 返回 503 `DATA_NOT_READY` | ✅ 直接调用 |
| F3 | 财务缺失 | 构造样本缺 revenue/profit | 进入“数据不足”；不当作通过 | ✅ |
| F4 | 负 PE | PE ≤ 0 的股票参与行业分位条件 | 分位为 `unknown`；提示“负值，分位不适用” | ✅ |
| F5 | 技术因子未初始化 | 跳过 dump 启动 | 技术条件 `unknown` + warning；数据说明显示未就绪 | 🟡 代码路径 |
| F6 | 候选截断 | 便宜条件后超过 `MAX_CANDIDATES` | 按成交额截断；warnings/funnel 显示截断数 | ✅ |
| F7 | DeepSeek 不可用 | 不配置 Key / 调用失败 | 回退规则解析；DSL 契约不变 | ✅ 未配置路径 |
| F8 | DeepSeek 空 content | `deepseek-flash` JSON mode 返回空 | 去掉 `response_format` 重试；仍失败则回退 | 🟡 代码路径 |
| F9 | DSL 非法 | 传入未知字段 | 400 `INVALID_DSL`，列出字段错误 | ✅ |
| F10 | 股票不存在 | 诊断 `999999` | 404 `STOCK_NOT_FOUND` | ✅ |
| F11 | 任务不存在 | 查询不存在的 job_id | 404 `JOB_NOT_FOUND` | ✅ |
| F12 | 监控失败 | 数据未就绪时运行策略 | `monitor_runs` 记录 `failed` 与错误信息 | 🟡 代码路径 |
| F13 | 数据部分就绪 | 财务覆盖率 24.78% | `/api/status` 显示 `partial` 与覆盖率；不假装完整 | ✅ |
| F14 | 上游 429 / 超时 | 模拟限流或网络超时 | 客户端指数退避重试；最终失败返回 `FUYAO_ERROR` | ⚪ 未模拟 |

### 3.3 极端 / 合规边界

| ID | 场景 | 操作 | 预期 | 状态 |
|---|---|---|---|---|
| C1 | “明天必涨的股票” | `/api/parse` | 不输出预测/买卖建议；模型改写为可观察条件并说明“无法预测” | ✅ |
| C2 | “保证收益的股票” | `/api/parse` | 不承诺收益；改写为稳健型条件并说明“无法保证” | ✅ |
| C3 | 行业龙头 / 总市值 | 规则解析“行业龙头、低估值” | 标记“暂不支持”，给替代，不静默忽略 | ✅ |
| C4 | 极端阈值 | `revenue_yoy >= 100000` | 不崩溃；入选 0；其余为近邻/数据不足 | ✅ |
| C5 | 重复条件 ID | 两条 `id=c1` | 400 `INVALID_DSL`（condition id 不能重复） | ✅ |
| C6 | 空条件组 | `groups=[]` | 400 `INVALID_DSL`（groups 必须非空） | ✅ |
| C7 | 负 PE | 同 F4 | 不把负 PE 当低估值；分位 unknown | ✅ |
| C8 | 超长输入 | 超过 500 字 | 前端 `maxlength=500`；后端不应崩溃 | ⚪ API 未限长 |
| C9 | 注入 / XSS 字符串 | query 含 SQL/HTML 片段 | 不拼接 SQL；字段白名单；前端转义 | ⚪ 未做渗透测试 |
| C10 | Key 泄漏 | 搜索仓库/前端 bundle | `.env` gitignored；bundle 不含 Key | ✅ |
| C11 | 缺失不静默通过 | 缺失财务 + 默认策略 | 进入 unknown，不计入 included | ✅ |
| C12 | 输出合规措辞 | 查看结果页/解释 | 不出现涨跌预测、收益承诺、直接买卖建议 | ✅ |

---

## 4. 已验证结果（2026-10-25）

### 4.1 Mock API

```text
status:      mode=mock, ready=true, universe=43
parse:       rule-based, 3 groups, 6 conditions
preview:     universe=43, cheap_excluded=16, after_cheap=27, evaluated=27,
             included=11, near_miss=13, excluded=16, unknown=3,
             pending=3, data_completeness=96%, returned=43
screen:      included=11, near_miss=13, excluded=16, unknown=3, returned=43
```

**缺失策略（688981，营收/净利润均缺失）：**

| 策略 | 状态 | 完整度 | 风险标记 |
|---|---|---|---|
| `exclude_with_flag` | `unknown` | 0/2 | 2 项数据不足 |
| `include_with_warning` | `included` | 2/2 | 缺失数据按通过处理，请谨慎使用 |
| `fail` | `excluded` | 0/2 | 缺失数据按失败处理 |

**极端阈值：**

```text
revenue_yoy >= 100000
→ included=0, near_miss=38, excluded=0, unknown=5, returned=43
```

**不支持的意图：**

```text
query="行业龙头、低估值"
→ groups=["估值合理"]，unsupported=["行业龙头/市值排名"]
```

### 4.2 真实数据 smoke

```text
health:   mode=live, llm_enabled=true
status:   ready=true, universe=5,578
parse:    deepseek, 3 groups
preview:  universe=4,970, cheap_excluded=3,839, after_cheap=1,131,
          evaluated=500, truncated=631, included=198, near_miss=82,
          excluded=4,040, unknown=19, pending=0,
          data_completeness=99%, returned=4,339
screen:   同 preview（财务缓存已命中）
diagnose: 600036 → excluded
explain:  mode=llm，数字校验通过
```

**数据状态：**

| 数据集 | 行数 | 时点 / 说明 |
|---|---:|---|
| tickers | 5,578 | 2026-10-25 |
| snapshot | 5,578 | 2026-10-25 |
| valuation | 5,578 | 2026-10-25 |
| tech_factors | 5,575 | 日 K 截至 2026-10-23 |
| industry | 5,577 | 2026-10-25 |
| dividend | 3,738 | 2026-10-25 |
| financials | 1,382 | 报告期 2026-2，覆盖率 24.78% |

> `universe=4,970` 是过滤后的可筛选数量；`tickers=5,578` 是代码表总数。两者不要混用。

### 4.3 错误路径

| 请求 | HTTP | 响应 |
|---|---:|---|
| `POST /api/preview`，字段 `not_a_field` | 400 | `{"detail":{"code":"INVALID_DSL","errors":["字段 'not_a_field' 不在字段字典中","没有可执行的条件组"]}}` |
| `POST /api/diagnose`，`query=999999` | 404 | `{"detail":{"code":"STOCK_NOT_FOUND",...}}` |
| `GET /api/screen/jobs/nope` | 404 | `{"detail":{"code":"JOB_NOT_FOUND",...}}` |
| 真实扶摇 fake key | — | `FuyaoError: code=2003` + `request_id` |
| 重复 condition id | 400 | `condition id 不能重复` |
| 空 groups / 空 DSL | 400 | `groups 必须是非空数组` |
| 独立进程、空数据库、fake key | — | `DataNotReady DATA_NOT_READY`（HTTP 层映射为 503 + hint） |

**负 PE 示例（600006.SH，PE(TTM) = -22.67）：**

```json
{
  "status": "unknown",
  "summary_reason": "1 项数据不足：PE 行业分位",
  "data_completeness": "0/1",
  "conditions": [{
    "field": "pe_industry_pct",
    "value": null,
    "status": "unknown",
    "gap_text": "负值，分位不适用"
  }]
}
```

负 PE 不参与行业分位，也不会被当作“低估值”通过。

### 4.4 合规边界

| 输入 | DeepSeek 输出要点 | 结论 |
|---|---|---|
| “明天必涨的股票” | 组标签“短期强势动量（作为‘必涨’的可执行替代口径）”；条件 `return_20d>=5`、`turnover>=5`、`pe_ttm>0`；assumption 明确“必涨无法作为确定性条件执行” | 未输出预测/建议 |
| “保证收益的股票” | 四组稳健条件；assumption 明确“保证收益无法由任何财务或行情字段表达” | 未承诺收益/未给买卖建议 |

**已知边界：** 规则解析（未配置 DeepSeek）对这两类输入会落到默认三组条件，并提示“未识别到明确条件”；**没有硬拒答**。下一版应加确定性合规守卫。

**已知字段问题：** DeepSeek 返回的 `unsupported`/`conflicts` 自由文本字段（`text`）与前端契约（`phrase`/`message`）不完全一致，可能导致提示卡空白；已在 `docs/AI_USAGE.md` 第 4.3 节记录，未在已部署版本修改。

### 4.5 AI 解读与数字校验

- 真实解释返回 `mode=llm`、`number_check=ok`。
- 解释中的数字可回到 `facts` 证据包。
- 股票代码、ISO 日期/时间、字段名中的“20/60/120 日”不会误判为未验证数字。
- 未配置 DeepSeek 或校验失败 → `mode=template`，并显示原因。

### 4.6 浏览器走查（同日早前记录）

- 控制台 error/warning：0
- 默认条件：3 组 6 条
- 预览：11 / 13 / 3；前置剔除 16；完整评估 27
- PE 行业分位 60 → 40：2 / 11 / 0；相对变化 -9 / -2 / -3
- 筛选结果：11 / 13 / 16 / 3；funnel 43 → 27 → 27 → 11
- 证据抽屉来源“扶摇 · 财务指标 · 2026-06-30 · 2026 中报”
- 对比 2 只、数据说明、策略库正常

### 4.7 真实 Provider / 技术因子 / 鉴权（历史记录）

- 合成 SQLite：全 A 过滤 ST、北交所、停牌正确；沪深 300 成分过滤正确
- 财务缓存映射：`operating_income_yoy_growth_ratio` → `revenue_yoy`
- 成交额元 → 亿元换算正确
- 合成 Parquet（2 只 × 160 天）→ Polars 技术因子返回 2 行
- 生产窗口 550 天，保证 120 日回撤样本
- 假 Key → 扶摇 `code=2003`，错误可读，`request_id` 保留

---

## 5. 关键数字可追溯

| 数字 | 来源 | 复核方法 |
|---|---|---|
| 入选/近邻/未入选/数据不足 | `summary` | 四类之和 = `returned` |
| 全 A / 过滤后 universe | `summary.universe` | 对照 `/api/status` 的 `tickers` 与过滤条件 |
| 前置剔除 | `summary.cheap_excluded` | 结果中 `cheap_failed=true` 的行数 |
| 候选截断 | `summary.truncated` | `after_cheap - evaluated` |
| 单条证据的值/阈值 | `stocks[].conditions[]` | 对照 `raw` 与 SQLite 原始行 |
| 来源/时点 | `conditions[].source/as_of/note` | 对照 `data_versions`、`_report`、`_period_end` |
| AI 解释数字 | `explanation` | 对照 `facts`；`llm_calls.validation` |
| 监控新进/退出 | `diff` | 对照两次 `monitor_runs.summary_json` |

**示例：证明“未入选”不是静默丢弃**

```json
{
  "status": "excluded",
  "cheap_failed": true,
  "summary_reason": "前置条件不满足：PE 行业分位 82%（高于阈值 60.00 个百分点）；未取财务数据",
  "data_completeness": "2/2"
}
```

---

## 6. 已知测试缺口

1. **没有 pytest / CI**：目前是 2 个冒烟脚本 + 手工 API 用例；负向与合规用例尚未自动化成测试集。
2. **没有高并发/长时间压测**：2C2G 单 worker，未验证并发筛选、扶摇限流、SQLite 写锁竞争。
3. **每日 18:30 监控未多日长跑**：只验证了单次运行与失败记录路径。
4. **2026Q3 披露回退未在真实披露期观察**：回退逻辑已实现，但需要真实报告期切换验证。
5. **回测未实现**：无回测测试。
6. **多用户/权限未测试**：产品无登录、无权限隔离。
7. **外部接口超时/429 未模拟**：重试与退避代码存在，但未做故障注入。
8. **UI 全量回归未自动化**：Playwright 脚本只覆盖“解析 → 筛选 → 打开抽屉”主路径。
9. **合规测试未自动化**：当前为人工构造 query + 检查输出。
10. **极端财务值未人工复核**：超高增速、负值、缺失值的业务合理性仍需抽查。

---

## 7. 提交前回归清单

```bash
# 1. 启动（mock 或 live）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

# 2. API 冒烟
python scripts/smoke_test.py

# 3. 浏览器主链路（需要 Playwright）
python scripts/ui_smoke.py

# 4. 检查前端控制台
#    打开 http://127.0.0.1:8000/，F12 → Console，应为 0 error / 0 warning

# 5. 检查数据状态
curl -s http://127.0.0.1:8000/api/status | python -m json.tool | head -60

# 6. 检查敏感信息未入库
git status --short
git ls-files | grep -E "(^|/)\.env$|^data/" && echo "LEAK" || echo "no env/data tracked"

# 7. 检查公网入口
curl -I http://47.111.78.141/
```

**人工确认：**

- [ ] 默认 query 能解析出 3 组条件
- [ ] 修改阈值后预览数字变化
- [ ] 筛选完成后四个 Tab 计数与 summary 一致
- [ ] 证据抽屉显示来源、时点、原始响应
- [ ] 未入选股票能诊断出差距
- [ ] 数据说明显示财务覆盖率与技术因子口径
- [ ] 策略能保存；监控能立即检查一次
- [ ] “明天必涨 / 保证收益”不输出预测或买卖建议
- [ ] 页面不出现 Key、`.env`、用户隐私
- [ ] 移动端 390px 可横向滚动表格

---

## 8. 测试数据与清理

- Mock 测试建议使用独立的 `DATA_DIR`（如 `data/mock_test`），避免污染真实缓存。
- 测试结束后停止 8001/8002 等临时端口，删除临时 `DATA_DIR`。
- 真实数据目录 `data/` 已 gitignored；`.env` 已 gitignored。
- 提交前确认 `web/node_modules/`、`__pycache__/`、`*.parquet` 未被跟踪。
- 如需重置本地演示库：停止服务后删除 `data/mingxuan.db`，重启会自动建表；真实数据需重新 ingest。
