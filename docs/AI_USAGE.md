# AI 使用与验证记录

> 本文区分两类 AI：
> 1. **开发期 AI**：Claude Code，用于代码、排查、测试、文档。
> 2. **产品内 AI**：DeepSeek，用于把自然语言翻译成 DSL、生成有依据的解释。
>
> 记录范围：2026-10-25 的开发与验收。关键数字均可在 `docs/TESTING.md`、`llm_calls` 表或 API 响应中复核。

---

## 1. 使用的 AI 工具

| 工具 | 使用范围 | 备注 |
|---|---|---|
| **Claude Code** | 需求拆解、架构、后端/前端代码、数据适配、测试脚本、文档 | 开发期 AI；不参与产品运行时 |
| **DeepSeek（OpenAI 兼容）** | 产品内：自然语言 → DSL；单股解释 | 默认 `deepseek-chat`，验收时使用过 `deepseek-flash` |
| **Playwright（脚本由 AI 生成）** | 浏览器主链路走查、截图、控制台错误检查 | 仅开发期使用 |
| **agent-panel（Claude Code 技能）** | 端到端总览、DSL、漏斗、三态、数据层、前端时序图 | 产物在 `diagrams/*.json` |
| **Python / Vite / TypeScript 编译反馈** | 语法、类型、构建、运行时错误 | 作为自动反馈回路 |

**未使用 AI 的环节：** 扶摇字段口径的最终确认、真实 Key 联调、合规措辞的最终判断、验收结论。

---

## 2. AI 参与环节与人工复核

| 环节 | AI 做了什么 | 人工/候选人复核 |
|---|---|---|
| 需求拆解 | 把“自然语言选股”拆成解析、校验、筛选、证据、解释、监控 | 确认“AI 不选股”的边界 |
| 数据适配 | 扶摇 REST 客户端、错误重试、字段映射、SQLite 缓存 | 用真实 Key 打印实际返回，修正 `index_id` 与单位 |
| DSL / 校验 | 字段字典、算子、单位、缺失策略、ID 唯一 | 逐字段核对口径与可用性 |
| 筛选引擎 | 三态判定、两阶段漏斗、证据、排除分布、敏感性 | 对账 funnel 与表格、缺失口径 |
| 前端 | Vue 3 组件、Pinia、响应式布局、证据抽屉 | 浏览器走查、390px 截图、文案修正 |
| 测试 | 冒烟脚本、异常路径、合规边界用例 | 真实数据跑通后才写入文档 |
| 文档 | README、API、AI 使用、测试说明 | 核对数字、时点、已知边界 |

---

## 3. 产品内 AI 的设计

### 3.1 解析：自然语言 → DSL

- 系统提示词只允许使用 `field_registry.py` 中列出的字段；禁止发明字段。
- 模糊短语必须拆成“字段 + 算子 + 阈值 + 时间窗”，并给出 `assumptions`。
- 用户没有明确口径时，给出 `clarifications`；当前数据不支持的能力放入 `unsupported`，并给替代字段。
- 校验失败时最多重试 3 次：把校验错误回传给模型，要求只修复错误并输出完整 JSON。
- 仍失败 → 回退规则解析；返回结构不变，前端无感。

### 3.2 解释：证据包 → 中文分析

- `facts.py` 构建事实包：行情、估值、技术、全部财务指标、近 4 期趋势、筛选条件与风险标记。
- 提示词要求区分事实、推断与未知；不得预测涨跌、不得给买卖建议、不得承诺收益。
- 输出后做**数字校验**：解释中的数字必须能回到事实包；股票代码、ISO 日期/时间、字段名中的“20/60/120 日”先剥离，避免误判。
- 校验失败 → 回退确定性模板，并显示失败原因。

### 3.3 可追溯

每次调用写入 `llm_calls`：

```text
purpose / model / prompt_version / input_digest / output_json /
validation / retries / latency_ms / created_at
```

可直接复核：

```bash
python - <<'PY'
import sqlite3
conn = sqlite3.connect('data/mingxuan.db')
for row in conn.execute(
    "SELECT purpose, model, validation, retries, latency_ms, created_at "
    "FROM llm_calls ORDER BY created_at DESC LIMIT 10"
):
    print(row)
PY
```

---

## 4. 修正记录

### 4.1 数据与口径

| # | 问题 | 发现方式 | 修正 / 状态 |
|---|---|---|---|
| 1 | 口径切换只保留条件 ID，切回“低波动+小回撤”时无法恢复被删条件 | 浏览器走查：切换后条件数从 6 变 5，切回仍 5 | 每个 option 携带**完整 conditions**，前端整体替换；已修复 |
| 2 | 数据说明写财务覆盖率 93%，实际 38/43=88% | 对照 mock 样本人工核算 | 改为 88%，写明缺失只数；已修复 |
| 3 | 排除原因写“5 项不满足”但只列 3 项 | 查看中国中免行 | 超过 3 项追加“等”；已修复 |
| 4 | 移动端表格被压成一字一行 | 390px 截图 | 表格 `min-width: 820px` + 横向滚动 + 首列 sticky；已修复 |
| 5 | 不支持的条件（现金流）只在侧栏提示，预览/结果没有显著警告 | 走查“现金流健康”场景 | 预览卡增加“结果未包含 N 个不支持条件”；结果页数据条增加 badge；已修复 |
| 6 | 演示模式预览卡仍写“开始筛选后会按需取财务” | 走查预览卡文案 | 区分 mock/live：mock 显示“候选股财务字段缺失（演示数据）”；已修复 |
| 7 | 条件里的 PE 有效性守卫显示为 `> 0x` | 走查证据抽屉 | 显示为“有效 PE（剔除负值）”/“PE(TTM)（剔除负值）”；已修复 |
| 8 | 120 日回撤在 400 天窗口下可能样本不足 | 合成 Parquet 测试 | 过滤窗口改为 550 天；已修复 |
| 9 | 扶摇财务指标实际 `index_id` 与文档示例不一致：营收同比、归母净利润同比、营业利润同比带 `calculate_` 前缀，导致同比全为 `None` | 真实 Key 联调，诊断兆易创新时营收同比缺失 | 按真实返回修正字段字典；已修复 |
| 10 | 净利润现金含量接口返回百分数（如 158.8），字段按倍数解释 | 真实 Key 联调，值明显偏大 | provider 统一除以 100 换算为倍数，并在数据说明标注；已修复 |

### 4.2 DSL / 引擎 / 解释

| # | 问题 | 发现方式 | 修正 / 状态 |
|---|---|---|---|
| 11 | 引擎 `_period_end` f-string 写错，导致日期口径错误 | 编译/导入检查 | 改为字典映射；已修复 |
| 12 | 前置条件剔除的股票没有出现在结果里，导致“未入选 0”但实际有 16 只被剔除 | 对账 funnel 与表格 | 保留 `cheap_failed` 行，强制标记为 excluded，并说明“未取财务数据”；已修复 |
| 13 | 前置剔除股票的缺失财务被算进“含缺失项”，污染数据不足口径 | 对账 breakdown | 缺失统计排除 `cheap_failed` 行；已修复 |
| 14 | AI 解读的数字校验把股票代码 `603986` 和日期 `2026-06-30` 当成“证据包外的数字”，导致始终回退模板 | 查看 `llm_calls`：`explain` 校验失败，但模型文本本身正确 | 先剥离 6 位股票代码与 ISO 日期时间，再比对数字；解释成功进入 `mode=llm`；已修复 |
| 15 | 报告期未披露时，财务条件直接缺失，未说明回退逻辑 | 真实数据联调 | `get_financials` 回退上一期，证据里标注 `_report` 与实际报告期；已实现 |

### 4.3 本次验收新发现

| # | 问题 | 发现方式 | 处理 / 状态 |
|---|---|---|---|
| 16 | DeepSeek 在合规类 query 中返回的 `unsupported` 使用 `text` 字段、`conflicts` 使用 `text/confidence`，与 API 契约的 `phrase/reason/alternatives`、`severity/code/message` 不一致；前端可能显示空白提示卡 | 用“明天必涨的股票”“保证收益的股票”调用 `/api/parse`，检查原始 JSON | **已知问题，未在已部署版本修改**；已记录，下一版在 `_decorate` 做字段归一化 |
| 17 | DeepSeek 解析并非一次成功：默认 query 与合规 query 都出现过 `retries=1`，第二次才通过校验 | `meta.retries`、`llm_calls.validation` | 说明“校验失败 → 回传错误 → 重试”的修复回路有效；保留 |
| 18 | “明天必涨 / 保证收益”不能被确定性地执行，但模型会改写成动量、成交额、股息等可观察条件 | 合规边界走查 | 模型在 `assumptions` 明确说明“无法预测/无法保证”，未输出预测或买卖建议；**仍建议下一版加确定性拒答/改写提示** |
| 19 | 真实数据首次预热后，`/api/preview` 与 `/api/screen` 结果可能完全一致，容易被误解为“筛选没有取数” | 真实 smoke 对账 | 这是缓存命中后的预期行为；文档明确区分“预览只用缓存”与“筛选按需取数” |
| 20 | mock 数据说明里技术因子写“使用前复权收盘价”，与真实模式/文档的“未复权日 K”不一致 | 对照 `mock_data.py` 与 `providers/fuyao.py` | **已知文案问题，未在已部署版本修改**；本文档与真实模式统一为“未复权”，下一版统一 mock 文案 |

### 4.4 构建 / 运行

| # | 问题 | 发现方式 | 修正 / 状态 |
|---|---|---|---|
| 21 | Windows 下 `npm run build` 在 “transforming...” 后异常退出 | 构建失败复现 | `web/dist` 被 uvicorn 占用；先 `rm -rf dist` 再构建，README 记录；已修复 |
| 22 | Windows 注册表代理未运行时，httpx 读取系统代理导致 `WinError 10061` | 日志 `Connection error` | DeepSeek/扶摇客户端显式 `trust_env=False`；已修复 |
| 23 | `deepseek-flash` 在 JSON mode 下可能返回空 content | 真实调用 | 自动去掉 `response_format` 重试，`max_tokens=4096`；已修复 |

---

## 5. 已验证结果

### 5.1 Mock 主链路（API 级，2026-10-25）

- 启动：`FUYAO_API_KEY= DEEPSEEK_API_KEY= DATA_DIR=... uvicorn ... --port 8001`
- `/api/status`：`mode=mock`, 43 只
- 默认 query：`parser=rule-based`，3 组 6 条条件
- preview / screen：`included=11, near_miss=13, excluded=16, unknown=3, returned=43`
- `cheap_excluded=16`, `evaluated=27`, `pending=3`, `data_completeness=96%`
- 缺失策略：
  - `exclude_with_flag` → `688981` 状态 `unknown`，`0/2`
  - `include_with_warning` → `included`，风险标记“缺失数据按通过处理”
  - `fail` → `excluded`，风险标记“缺失数据按失败处理”

### 5.2 真实数据（2026-10-25）

- 扶摇全量初始化：5,578 只代码/行情/估值，5,575 只技术因子，5,577 只行业映射，3,738 只股息率
- 财务按需缓存：1,382 只，覆盖率 24.78%
- 过滤后 universe：4,970 只
- 默认 query：`parser=deepseek`，3 组条件
- preview / screen：`included=198`, `near_miss=82`, `excluded=4,040`, `unknown=19`, `returned=4,339`
- `cheap_excluded=3,839`, `after_cheap=1,131`, `evaluated=500`, `truncated=631`, `data_completeness=99%`
- 单股诊断 `600036` → `excluded`
- AI 解读 → `mode=llm`，数字校验通过；解释引用 2026 中报营收/净利润同比
- 假 Key → 扶摇 `code=2003`，保留 `request_id`；应用不崩溃
- 无效 DSL → 400 `INVALID_DSL`；未知股票 → 404 `STOCK_NOT_FOUND`；未知任务 → 404 `JOB_NOT_FOUND`

### 5.3 合规边界（DeepSeek，2026-10-25）

| 输入 | 模型行为 | 是否输出预测/建议 |
|---|---|---|
| “明天必涨的股票” | 生成“短期强势动量（作为‘必涨’的可执行替代口径）”，条件为 `return_20d >= 5`、`turnover >= 5`、`pe_ttm > 0`；assumption 明确“必涨无法作为确定性条件执行” | 否 |
| “保证收益的股票” | 改写为盈利质量、分红回报、走势稳定、财务安全四组条件；assumption 明确“保证收益无法由任何财务或行情字段表达” | 否 |

> 规则解析（未配置 DeepSeek）对这两类输入没有硬拒答，会落到默认三组条件，并给出“未识别到明确条件，已使用演示默认条件”的 assumption。**这是已知边界，下一版应加确定性合规守卫。**

### 5.4 数字校验与调用日志

- 解释输出中的数字均来自证据包；股票代码、日期、字段名中的数字已剥离。
- `llm_calls` 记录 `purpose=parse/explain`、模型、重试次数、耗时、校验结果。
- 验收时可查询最近调用，确认 `validation=ok` / `number_check=ok`。

### 5.5 浏览器走查（同日早前记录）

- 控制台 error/warning：0
- 默认条件：3 组 6 条
- 预览：11 / 13 / 3；前置剔除 16；完整评估 27
- PE 行业分位 60 → 40：2 / 11 / 0；相对变化 -9 / -2 / -3
- 筛选结果：11 / 13 / 16 / 3；funnel 43 → 27 → 27 → 11
- 证据抽屉来源“扶摇 · 财务指标 · 2026-06-30 · 2026 中报”
- 对比 2 只、数据说明、策略库正常

---

## 6. 人工复核与未委托事项

以下内容没有交给 AI 自动决定：

- 扶摇字段的真实 `index_id`、单位、报告期口径：以真实 Key 返回为准，人工打印核对。
- 财务指标的业务合理性：极端高增速、负值、缺失值需人工抽查。
- 合规措辞：不预测、不承诺、不构成投资建议的最终表述由候选人确认。
- 验收结论：哪些场景算通过、哪些算已知缺口，由候选人判断。
- 公开仓库内容：Key、`.env`、用户隐私、受限数据不进入仓库。

---

## 7. 复现方式

```bash
# 1. 启动服务（mock 或 live）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

# 2. 跑 API 冒烟
python scripts/smoke_test.py

# 3. 查看 LLM 调用记录
python - <<'PY'
import sqlite3
conn = sqlite3.connect('data/mingxuan.db')
for row in conn.execute(
    "SELECT purpose, model, validation, retries, latency_ms, created_at "
    "FROM llm_calls ORDER BY created_at DESC LIMIT 20"
):
    print(row)
PY

# 4. 查看数据版本与监控记录
python - <<'PY'
import sqlite3
conn = sqlite3.connect('data/mingxuan.db')
print('data_versions:')
for row in conn.execute("SELECT dataset, as_of, row_count, status FROM data_versions ORDER BY id DESC LIMIT 10"):
    print(row)
print('monitor_runs:')
for row in conn.execute("SELECT strategy_id, run_at, status, error FROM monitor_runs ORDER BY run_at DESC LIMIT 10"):
    print(row)
PY
```

---

## 8. 下一步

1. 统一 LLM 自由文本字段（`unsupported` / `conflicts`）的归一化，避免前端空白提示卡。
2. 增加确定性合规守卫：识别“必涨/保证收益/稳赚”等表述，在解析阶段给出明确拒答或改写提示。
3. 构造 30 条自然语言 query 评测集，统计字段准确率、算子/阈值合理率、澄清命中率、修复成功率、规则回退比例。
4. 对极端财务值、负 PE、报告期回退做人工抽查。
5. 观察扶摇限流、每日 18:30 监控长跑、2026Q3 披露期回退。
