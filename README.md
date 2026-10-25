# 明选 · 自然语言选股与策略解释器

把模糊的选股想法，变成**可检查、可修改、可执行**的条件，并用逐条证据解释每只股票为什么入选、为什么被排除、改一个条件会带来什么影响。

> 产品定位不是“AI 荐股”，而是“选股意图编译器”。  
> AI 只负责听懂和解释；选股由确定性引擎执行；每个数字都能回到字段、来源和时点。

---

## 0. 交付速览

| 项目 | 内容 |
|---|---|
| **本地地址** | <http://127.0.0.1:8000/> |
| **公网部署入口** | <http://47.111.78.141/>（阿里云 ECS，2C2G） |
| **源代码** | 本仓库（2026-10-25 初始化 Git；远程托管地址在推送后补充） |
| **API 文档** | 运行后访问 <http://127.0.0.1:8000/docs>，或看 [`docs/API.md`](docs/API.md) |
| **AI 使用记录** | [`docs/AI_USAGE.md`](docs/AI_USAGE.md) |
| **测试说明** | [`docs/TESTING.md`](docs/TESTING.md) |
| **数据源** | 仅扶摇（Fuyao），不使用 iFinD |
| **产品内 LLM** | DeepSeek（OpenAI 兼容），未配置时回退规则解析 |

> 公网入口依赖 ECS 安全组放行 80/443 与 nginx 已启动。若当前网络打不开，请先按第 8 节检查部署状态；本地 `127.0.0.1:8000` 不受影响。

---

## 1. 产品选择：为什么做“意图编译器”，而不是“AI 荐股”

| 选择 | 理由 | 代价 / 边界 |
|---|---|---|
| **自然语言 → DSL → 确定性引擎** | 选股结论必须可复现、可审计。同一份 DSL + 同一份数据，结果必须一致 | 需要先定义字段字典与校验器；模糊语义会被显式假设化 |
| **AI 不选股、不算数** | LLM 只做翻译和解释，避免“看起来合理但算错”的名单 | 复杂意图需要多轮澄清；不支持的能力必须明说 |
| **三态：通过 / 不通过 / 未知** | 缺失数据、负 PE、未披露报告期不能静默当通过 | 会出现“数据不足”Tab，入选数看起来更少 |
| **逐条证据 + 来源 + 时点** | 每个数字能回到字段、数据集、报告期或行情时点 | 对数据口径和缓存一致性要求更高 |
| **按需取财务 + 两阶段漏斗** | 2C2G 机器也能跑全 A：先便宜条件剔除，再对候选按需取财务 | 首次筛选较慢；候选默认上限 500，按成交额截断 |
| **SQLite + 单 worker + 无 Docker** | 部署简单、内存占用小，适合 2C2G 演示环境 | 不适合高并发；多实例需要换数据库/队列 |
| **Vue 3 单页 step 切换** | 主链路只有“意图 → 条件 → 结果”三步，无需 Router | 深链接/多标签页能力弱 |

**一句话：** 让用户看到“AI 理解成了什么”，并且能改；而不是让 AI 直接给一个无法解释的名单。

---

## 2. 快速开始

### 2.1 环境

- Python 3.11+（开发与验收环境为 3.13.13）
- Node.js 18+（**仅在修改前端时需要**；仓库已包含构建产物 `web/dist`）
- 不需要 Docker

### 2.2 本地启动（零 Key 可完整演示）

```bash
cd "D:/2026/智能体开发/金融智能体2"

python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

打开 <http://127.0.0.1:8000/>。

首次启动会自动创建 `data/mingxuan.db`（SQLite）。  
未配置 `FUYAO_API_KEY` 时，页面显示“演示数据 · 构造样本”，使用 43 只构造样本完整走通主链路。

### 2.3 环境变量

在项目根目录创建 `.env`（已被 `.gitignore` 忽略）：

```dotenv
# 数据源：扶摇
FUYAO_API_KEY=你的扶摇Key
FUYAO_BASE_URL=https://fuyao.aicubes.cn

# LLM：DeepSeek
DEEPSEEK_API_KEY=你的DeepSeekKey
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 运行参数
DATA_DIR=./data
MAX_CANDIDATES=500
FETCH_CONCURRENCY=5
FINANCIAL_REPORT=2026-2
ADMIN_TOKEN=
```

| 变量 | 默认值 | 作用 |
|---|---|---|
| `FUYAO_API_KEY` | 空 | 为空 → mock 模式；配置后 → 真实数据模式，需先初始化 |
| `FUYAO_BASE_URL` | `https://fuyao.aicubes.cn` | 扶摇 API 地址 |
| `DEEPSEEK_API_KEY` | 空 | 为空 → 规则解析 + 模板解读；配置后 → DeepSeek 解析/解释 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek 兼容接口地址 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 可改为 `deepseek-flash`；reasoning 模型首次解析约 10–20 秒 |
| `DATA_DIR` | `./data` | SQLite 与 Parquet dump 目录 |
| `MAX_CANDIDATES` | `500` | 完整评估的候选上限；超出按成交额截断，并在结果页提示 |
| `FETCH_CONCURRENCY` | `5` | 按需取财务的并发数；2C2G 建议 4–5 |
| `FINANCIAL_REPORT` | `2026-2` | 财务报告期；未披露时回退上一期并在证据中标注 |
| `ADMIN_TOKEN` | 空 | `/api/admin/ingest` 的 `X-Admin-Token`；不配置则接口禁用 |

> **Key 只在服务端使用。** 前端 bundle、日志和仓库中不出现 Key；`.env` 已 gitignore。

### 2.4 初始化真实数据（只做一次，之后每天可选更新）

```bash
# 全量：代码表 + 行情 + 估值 + 行业成分 + 全市场日 K dump + 技术因子 + 股息
python -m app.data.ingest --all

# 2 核 2G 服务器：跳过全市场 Parquet dump，只加载行情/估值/行业
python -m app.data.ingest --all --skip-dump
```

说明：

- `--all` 会下载全市场日 K Parquet（本次约 181 MB），并计算 20/60/120 日波动率、最大回撤、涨跌幅。
- `--skip-dump` 更快、更省内存；跳过后“走势稳定”等技术条件会显示为“数据不足”，数据说明里能看到原因。
- 初始化幂等，可重复运行；完成后重启 uvicorn。

### 2.5 前端开发 / 构建（可选）

```bash
cd web
npm install
npm run dev      # http://127.0.0.1:5173，/api 代理到 8000
npm run build    # 产物在 web/dist，FastAPI 直接托管
```

> Windows 提示：如果 `npm run build` 在 “transforming...” 后异常退出，通常是 `web/dist` 被正在运行的 uvicorn 占用。先停止服务或 `rm -rf web/dist` 再构建。

---

## 3. 产品主链路

```text
自然语言
  → DeepSeek / 规则解析
  → DSL（条件组 + 字段 + 算子 + 阈值 + 时间窗）
  → 校验与冲突检测（字段白名单 / 算子 / 单位 / ID 唯一）
  → 确定性筛选（三态：通过 / 不通过 / 未知）
  → 逐条证据（值、阈值、来源、时点、缺口）
  → 入选 / 近邻 / 未入选 / 数据不足
  → 单股诊断、敏感性、保存、监控
```

### 已实现

- 自然语言输入 → DSL → 条件卡
- 条件可编辑：阈值、算子、口径、增删
- AI 假设、澄清问题、冲突检查、数据能力提示
- 缺失数据策略：不计入 / 计入但标记 / 直接失败
- 实时影响预览：相对初始条件的入选/近邻/数据不足变化
- 两阶段漏斗：便宜条件 → 候选（默认 ≤500，按成交额截断）→ 完整评估
- 入选 / 近邻 / 未入选 / 数据不足 / 敏感性五个 Tab
- 单股证据抽屉：逐条件值、阈值、来源、时点、原始响应
- 任意股票“为什么没入选”诊断
- 敏感性分析：阈值扫描 + 最卡条件
- 股票对比（最多 3 只）
- 策略保存、策略库、每日 18:30 监控任务、新进/退出 diff
- AI 解读（DeepSeek 生成 + 数字校验；未配置时模板）
- 数据说明弹窗：数据集覆盖、财务口径、技术因子口径

### 未实现 / 已知边界

详见第 10 节。

---

## 4. AI 的角色与边界

| 层 | 负责 | 明确不做 |
|---|---|---|
| **DeepSeek** | 听懂模糊语言、生成 DSL、提出假设/澄清/冲突、写有依据的解释 | 不选股、不算数、不预测涨跌、不承诺收益 |
| **校验器** `validator.py` | 字段白名单、算子、单位、ID 唯一、缺失策略枚举 | 不猜字段、不修复语义 |
| **确定性引擎** `engine.py` | 执行 DSL、三态判定、证据、排除分布、敏感性 | 不生成自然语言、不调用 LLM |
| **数据层** `providers/` + `data/` | 扶摇取数、SQLite 缓存、时点记录、失败重试 | 不做业务结论 |
| **前端** | 展示与编辑、预览、结果、证据抽屉 | 不自己计算名单或数字 |

**产品内 AI 的两个窄任务：**

1. **解析 / 修复**：自然语言 → DSL JSON；校验失败时最多重试 3 次，把错误回传给模型修复；仍失败则回退规则解析。
2. **解释**：把结构化证据包（行情、估值、技术、全部财务指标、近 4 期趋势、筛选条件）改写成中文分析；输出后做**数字校验**，解释中出现的数字必须能回到证据包，否则回退模板。

**关键约束：**

- 股票代码、ISO 日期/时间、字段名中的数字（20/60/120 日）在数字校验前会被剥离，避免误判。
- `deepseek-flash` 在 JSON mode 下可能返回空 content；`_chat` 会自动去掉 `response_format` 重试，并把 `max_tokens` 设为 4096。
- DeepSeek 与扶摇客户端显式 `trust_env=False`，避免 Windows 注册表代理未运行时 `WinError 10061`。

---

## 5. 数据来源与口径

**数据源：扶摇（Fuyao）**，不使用 iFinD。

| 数据 | 用途 | 口径 / 限制 |
|---|---|---|
| 代码表 | 全 A universe | 剔除 ST、停牌、上市不足 250 天、北交所 |
| 行情快照 | 最新价、成交额 | 原始货币；成交额换算为亿元 |
| 估值快照 | PE/PB/PS/PCF | 批量 100 个代码/次；负值保留 |
| PE/PB 行业分位 | 估值条件 | 当前截面、同花顺行业成分内正 PE/PB 样本；行业少于 5 只不计算 |
| 财务指标 | 成长/盈利/偿债/现金流 | 默认报告期 `2026-2`（中报）；未披露回退上一期并在证据标注 |
| 全市场日 K dump | 技术因子 | **未复权**口径；波动率 = 日收益标准差 × √252；最大回撤 = 相对累计最高点最大跌幅 |
| 复权因子 dump | 股息率 | 近 365 天每股现金分红（税前）之和 / 最新价 |

### 截至 2026-10-25 的真实数据状态（本机验收）

| 数据集 | 行数 | 说明 |
|---|---:|---|
| tickers | 5,578 | 全 A 代码表 |
| snapshot | 5,578 | 行情快照 |
| valuation | 5,578 | 估值快照 |
| tech_factors | 5,575 | 未复权日 K 计算 |
| industry | 5,577 | 同花顺行业映射 |
| dividend | 3,738 | 近 365 天股息率 |
| financials | 1,382 | 按需取数缓存，覆盖率 24.78%，会随使用增长 |

> 经过 ST/停牌/上市天数/北交所过滤后，可筛选 universe 约 4,970 只（以当次快照为准）。  
> 财务数据**不在启动时全量预热**；首次带财务条件的筛选会按需取数，之后命中 SQLite 缓存。

更细的字段定义见页面“数据说明”与 [`docs/API.md`](docs/API.md)。

---

## 6. 架构与关键文件

```text
Vue 3 (web/)
  │ 只看 DSL / 结果 / 证据，不计算任何选股结论
  ▼
FastAPI (app/)
  ├─ llm.py          DeepSeek：自然语言 → DSL；解释 + 数字校验
  ├─ intent.py       规则解析兜底（未配置/调用失败时）
  ├─ validator.py    DSL 校验、字段白名单、算子/单位、ID 唯一
  ├─ engine.py       确定性筛选、三态、证据、排除分布、敏感性
  ├─ facts.py        解释用事实包（全量指标 + 近 4 期 + 筛选证据）
  ├─ providers/      mock / 扶摇真实数据（SQLite + 按需取数）
  ├─ data/           扶摇 REST 客户端、数据初始化 CLI
  ├─ api/routes.py   API 路由
  ├─ api/jobs.py     筛选任务 + 进度轮询
  └─ monitor.py      策略保存 + 每日 18:30 监控
```

| 文件 | 作用 |
|---|---|
| `app/field_registry.py` | 字段字典，LLM/校验/引擎/前端的唯一真相 |
| `app/validator.py` | DSL 校验（字段、算子、单位、ID 唯一） |
| `app/engine.py` | 三态筛选、证据、排除分布、敏感性 |
| `app/intent.py` | 规则解析兜底 |
| `app/llm.py` | DeepSeek 解析 + 修复 + 解释 + 数字校验 |
| `app/facts.py` | 解释事实包与模板解释 |
| `app/providers/mock.py` | 43 只演示样本 |
| `app/providers/fuyao.py` | 真实 universe + 按需财务 |
| `app/data/fuyao_client.py` | 扶摇 REST 客户端（重试/限流/request_id） |
| `app/data/ingest.py` | 数据初始化 CLI（含 Polars 技术因子） |
| `app/api/routes.py` | API 路由 |
| `app/api/jobs.py` | 筛选任务 + 进度轮询 |
| `app/monitor.py` | 策略保存 + 每日 18:30 监控 |
| `web/src/stores/screening.ts` | 前端状态与动作 |
| `docs/API.md` | API 契约 |
| `docs/AI_USAGE.md` | AI 使用与验证记录 |
| `docs/TESTING.md` | 测试矩阵与已验证结果 |

完整目录：

```text
.
├─ app/                       # FastAPI 后端
├─ web/                       # Vue 3 + Vite + TS + Pinia
│  ├─ src/
│  └─ dist/                   # 已构建产物（FastAPI 直接托管）
├─ data/                      # SQLite + Parquet（gitignored）
├─ deploy/                    # systemd / nginx 示例（不使用 Docker）
├─ docs/                      # API / AI 使用 / 测试
├─ diagrams/                  # 架构图 JSON（agent-panel）
├─ scripts/                   # probe / smoke / ui smoke
├─ requirements.txt
├─ .env.example
└─ README.md
```

---

## 7. API

Base URL：`/api`。完整契约见 [`docs/API.md`](docs/API.md)。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 健康检查、当前模式、LLM 是否启用 |
| GET | `/api/status` | 数据集覆盖、时点、财务覆盖率、口径定义 |
| POST | `/api/parse` | 自然语言 → DSL + 假设/澄清/冲突/不支持能力 |
| POST | `/api/preview` | 只用已缓存财务数据做实时预览，不触发取数 |
| POST | `/api/screen` | 同步筛选（会按需取数，可能 20–40 秒） |
| POST | `/api/screen/jobs` | 创建筛选任务 |
| GET | `/api/screen/jobs/{id}` | 轮询进度 / 结果 |
| POST | `/api/diagnose` | 单股诊断：为什么入选/没入选 |
| POST | `/api/explain` | 单股 AI 解读（带数字校验） |
| GET/POST | `/api/strategies` | 策略列表 / 保存策略 |
| POST | `/api/strategies/{id}/run` | 立即执行一次监控 |
| GET | `/api/strategies/{id}/runs` | 监控运行记录 |
| POST | `/api/admin/ingest` | 后台数据初始化（需 `X-Admin-Token`） |

常见错误码：`INVALID_DSL`(400)、`DATA_NOT_READY`(503)、`STOCK_NOT_FOUND`(404)、`JOB_NOT_FOUND`(404)、`FUYAO_ERROR`(502)、`LLM_ERROR`(502)。

---

## 8. 部署（不使用 Docker）

### 8.1 本地 / 单机

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.data.ingest --all --skip-dump
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

### 8.2 阿里云 ECS（实际部署目标）

目标环境：Alibaba Cloud Linux 3，2C2G，Miniconda 环境 `mingxuan`（Python 3.13），运行账号 `www`，目录 `/opt/mingxuan`。**不使用 Docker，也不使用 venv 作为主环境。**

```bash
# 1. 上传项目到 /opt/mingxuan
cd /opt/mingxuan

# 2. 安装依赖（conda 环境内）
/opt/miniconda3/envs/mingxuan/bin/pip install -r requirements.txt

# 3. 配置 .env 后初始化数据（2C2G 建议先跳过 dump）
/opt/miniconda3/envs/mingxuan/bin/python -m app.data.ingest --all --skip-dump

# 4. systemd
sudo cp deploy/mingxuan.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mingxuan

# 5. nginx（见 deploy/nginx.conf）
sudo cp deploy/nginx.conf /etc/nginx/conf.d/mingxuan.conf
sudo nginx -t && sudo systemctl enable --now nginx
```

> `deploy/mingxuan.service` 和 `deploy/nginx.conf` 是**通用示例**：示例里用的是 `www-data` + `.venv`，实际 ECS 环境应改为 `User=www`、`ExecStart=/opt/miniconda3/envs/mingxuan/bin/uvicorn ...`。按实际路径/账号修改后再启用。

2C2G 建议：`--workers 1`、`MAX_CANDIDATES=300~500`、`FETCH_CONCURRENCY=4~5`。

### 8.3 公网入口检查

如果 `http://47.111.78.141/` 打不开，按顺序检查：

1. ECS 安全组是否放行 80/443；
2. `systemctl status mingxuan` 是否 active；
3. `ss -ltnp | grep :8000` 是否有 uvicorn；
4. `nginx -t` 与 `systemctl status nginx`；
5. nginx 的 `root` 是否指向 `/opt/mingxuan/web/dist`。

---

## 9. 测试与验证

```bash
# 终端 1：启动服务
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1

# 终端 2：API 冒烟
python scripts/smoke_test.py
python scripts/ui_smoke.py        # 可选，需要 Playwright
```

**Mock 模式预期（43 只构造样本）：**

- `/api/status`：`mode=mock`, `ready=true`, 43 只
- 默认 query：3 组条件
- summary：`included=11, near_miss=13, excluded=16, unknown=3, returned=43`
- `cheap_excluded=16`, `evaluated=27`, `data_completeness=96%`

**真实数据 smoke（2026-10-25 本机验收）：**

- `parser=deepseek`，默认 query 3 组条件
- `universe=4,970`（过滤后），`cheap_excluded=3,839`，`after_cheap=1,131`
- `evaluated=500`，`truncated=631`
- `included=198`, `near_miss=82`, `excluded=4,040`, `unknown=19`, `returned=4,339`
- `data_completeness=99%`
- 单股诊断 `600036` 返回 `excluded`；AI 解读 `mode=llm`、数字校验通过
- 假 Key → 扶摇 `code=2003`；无效 DSL → 400；未知股票/任务 → 404

完整矩阵、失败路径与合规边界见 [`docs/TESTING.md`](docs/TESTING.md)。

---

## 10. 已知边界与未做事项

| 项目 | 状态 | 说明 |
|---|---|---|
| **导出 CSV** | 已实现 | 结果页一键导出全部四类股票，含逐条件证据；UTF-8 BOM，Excel 直接打开 |
| **行业龙头 / 总市值** | 不支持 | 扶摇公开 API 暂无；规则解析会标记“暂不支持”，不静默忽略 |
| **用户体系 / 权限** | 未实现 | 无登录、无多用户隔离；适合单机/内网演示 |
| **高并发 / 多实例** | 未验证 | SQLite + 单 worker；压测与限流未做 |
| **每日 18:30 监控长跑** | 待观察 | 已实现 APScheduler；真实 Key 下未做多日长跑 |
| **2026Q3 披露回退** | 待观察 | 报告期回退逻辑已实现并标注；真实披露期需继续观察 |
| **技术因子口径** | 有已知偏差 | 基于**未复权**日 K；除权除息日附近可能有偏差，界面/文档已标注 |
| **财务覆盖率** | 按需增长 | 首次筛选较慢；覆盖率随使用增长，不是全量预热 |
| **合规硬拒答** | 待加强 | 不输出预测/承诺；“必涨/保证收益”类输入会被改写为可观察条件并说明，当前没有独立拒答页 |
| **LLM 输出字段归一化** | 已知问题 | 少数自由文本字段（如 `unsupported.text`）与前端契约不完全一致，可能导致提示卡空白；验收已记录，下一版统一 |
| **演示数据文案** | 已知不一致 | mock 数据说明里有一处“前复权”旧表述；真实模式与本文档以**未复权**为准 |
| **CORS** | 演示配置 | 当前 `allow_origins=["*"]`；公网部署应收紧到实际域名 |
| **公网 URL** | 依赖运维 | ECS 安全组 / nginx 未放行时公网入口不可用；本地入口不受影响 |
| **自动化测试** | 部分覆盖 | 仓库提供 2 个冒烟脚本；负向/合规模块尚未纳入 pytest CI |

---

## 11. 合规声明

- 不预测涨跌、不承诺收益、不给出直接买卖建议。
- 数据缺失、过期、接口失败时不会静默生成“正常”结论；会进入“数据不足”或显示降级提示。
- 每个数字都带字段、来源、时点；派生指标有口径说明。
- 股票代码、日期、字段名中的数字不会被误当作财务数字。
- 产品仅用于研究与信息整理，不构成投资建议。

---

## 12. 常见问题

### DeepSeek 解析回退到规则解析

- 日志出现 `Connection error` / `WinError 10061`：Windows 注册表代理未运行，但 httpx 读取了系统代理。项目已对 DeepSeek 和扶摇客户端设置 `trust_env=False` 直连；如果网络**必须**走代理，需要显式配置代理。
- `deepseek-flash` 是 reasoning 模型，首次解析约 10–20 秒；想更快可把 `DEEPSEEK_MODEL` 改为 `deepseek-chat`。
- `deepseek-flash` 在 JSON mode 下可能返回空 content；`_chat` 会自动去掉 `response_format` 重试。

### AI 解读显示“模板生成”

- 未配置 DeepSeek，或模型调用失败：回退模板是预期行为。
- 数字校验未通过：解释里的数字必须能回到证据包；股票代码、日期时间、字段名中的“20/60/120 日”已被排除，不会误判。
- 配置了 DeepSeek 且校验通过时，面板显示“DeepSeek 生成 · 已做数字校验”。

### 真实模式提示 `DATA_NOT_READY`

先在 `.env` 配置 `FUYAO_API_KEY`，再运行：

```bash
python -m app.data.ingest --all --skip-dump
```

### 首次筛选很慢

- 财务数据按需取数；首次带财务条件时会逐只拉取并缓存。
- 缩小范围（沪深 300 / 中证 500）或先加便宜条件，可显著减少取数。
- 2C2G 建议 `MAX_CANDIDATES=300~500`、`FETCH_CONCURRENCY=4~5`。
