# 明选 · 项目说明（供后续开发/Agent 使用）

## 这是什么

自然语言选股与策略解释器。核心不是“AI 荐股”，而是把模糊语言编译成**可检查、可修改、可执行**的条件，并用确定性引擎产出逐条证据。

- 数据源：**仅扶摇**（`https://fuyao.aicubes.cn`），不使用 iFinD
- LLM：**DeepSeek**（OpenAI 兼容），未配置时回退规则解析
- 部署：**不使用 Docker**；venv + uvicorn + systemd + Nginx
- 前端：Vue 3 + Vite + TypeScript + Pinia（无 Vue Router，单页 step 切换）
- 后端：FastAPI + SQLite + 按需取财务

## 运行

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

- 不配置 Key → mock 模式（43 只构造样本），完整可走。
- 配置 `FUYAO_API_KEY` → 需先运行 `python -m app.data.ingest --all`（2C2G 用 `--skip-dump`）。
- 配置 `DEEPSEEK_API_KEY` → `/api/parse` 走 DeepSeek，失败自动回退规则解析。

前端开发：

```bash
cd web && npm install && npm run dev   # 5173，代理 /api → 8000
cd web && npm run build                # 产物在 web/dist，FastAPI 直接托管
```

> Windows：如果 build 在 transforming 后退出，先 `rm -rf web/dist`（被 uvicorn 占用），或停服务再构建。

## 关键文件

| 文件 | 作用 |
|---|---|
| `app/field_registry.py` | 字段字典，LLM/校验/引擎/前端的唯一真相 |
| `app/validator.py` | DSL 校验（字段、算子、单位、ID 唯一） |
| `app/engine.py` | 三态筛选、证据、排除分布、敏感性 |
| `app/intent.py` | 规则解析兜底 |
| `app/llm.py` | DeepSeek 解析 + 修复 + 解释 + 数字校验 |
| `app/providers/mock.py` | 43 只演示样本 |
| `app/providers/fuyao.py` | 真实 universe + 按需财务 |
| `app/data/fuyao_client.py` | 扶摇 REST 客户端（重试/限流/request_id） |
| `app/data/ingest.py` | 数据初始化 CLI（含 Polars 技术因子） |
| `app/api/routes.py` | API 路由 |
| `app/api/jobs.py` | 筛选任务 + 进度轮询 |
| `app/monitor.py` | 策略保存 + 每日 18:30 监控 |
| `web/src/stores/screening.ts` | 前端状态与动作 |
| `web/src/csv.ts` | 筛选结果导出 CSV（全部四类 + 逐条件证据） |
| `docs/API.md` | API 契约 |
| `docs/AI_USAGE.md` | AI 使用与修正记录 |
| `docs/TESTING.md` | 测试矩阵与已验证结果 |

## 不可破坏的约定

1. **前端不算名单**：所有名单/数字来自后端；前端只渲染与编辑。
2. **LLM 不选股**：DeepSeek 只产出 DSL 或解释；筛选由 `engine.py` 执行。
3. **三态**：`pass` / `fail` / `unknown`；缺失数据绝不静默当通过。
4. **选项带完整 conditions**：口径切换用完整条件数组替换，不能只用 ID（会丢失被删条件）。
5. **按需取数**：不要在前端启动/定时任务里全量预热财务；候选默认上限 500，按成交额截断。
6. **Key 只在服务端**：`.env` gitignored；前端不出现 Key。
7. **技术因子口径**：基于未复权日 K，界面/文档必须标注除权日偏差。
8. **HTTP 客户端 trust_env=False**：Windows 注册表系统代理（例如本机的 127.0.0.1:7897）未运行时，httpx 会读代理并报 WinError 10061；DeepSeek 与扶摇客户端已显式 `trust_env=False` 直连，不要移除。
9. **DeepSeek reasoning 模型**：`deepseek-flash` 在 JSON mode 下可能返回空 content；`app/llm.py::_chat` 会自动去掉 `response_format` 重试，并把 `max_tokens` 设为 4096。AI 解读的数字校验会剥离股票代码、ISO 日期/时间和字段名中的数字（20/60/120 日），再比对证据。

## 数据口径

- 财务默认报告期 `2026-2`（中报），未披露回退上一期并在证据标注。
- **扶摇财务指标实际 index_id 可能带 `calculate_` 前缀**：营收同比是 `calculate_operating_income_yoy_growth_ratio`，归母净利润同比是 `calculate_parent_holder_net_profit_yoy_growth_ratio`，营业利润同比是 `calculate_operating_profit_yoy_growth_ratio`。改映射前先用真实 Key 打印实际返回，不要只信文档示例。
- 净利润现金含量接口返回百分数，`FuyaoProvider._normalize_value` 统一 /100 换算为倍数。
- PE 行业分位：当前截面、同花顺行业成分内正 PE 样本；行业 < 5 只不计算。
- 技术因子：日收益标准差 × √252；最大回撤 = 相对累计最高点最大跌幅；未复权。
- 股息率：近 365 天每股现金分红（税前）/ 最新价。
- 全 A 排除 ST、停牌、上市 < 250 天、北交所。

## 测试

```bash
python scripts/smoke_test.py
python scripts/ui_smoke.py   # 需要 Playwright
```

Mock 预期（会随样本变化）：默认 query 3 组；`included=11, near=13, excluded=16, unknown=3, returned=43`。

## 当前未完成

- 行业龙头/总市值（扶摇公开 API 暂无；规则解析标记不支持）
- 用户体系/多用户权限
- 高并发限流、每日监控长跑、2026Q3 披露回退（真实 Key 联调后仍需观察）
