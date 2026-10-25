"""SQLite storage for the on-demand screening cache and app state.

The server is expected to run on a small 2C2G box: SQLite in WAL mode keeps
memory low, and all heavy data is stored on disk.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterable

import aiosqlite

from .config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
  thscode TEXT PRIMARY KEY,
  ticker TEXT,
  name TEXT,
  exchange TEXT,
  asset_type TEXT,
  list_date TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tickers_name ON tickers(name);

CREATE TABLE IF NOT EXISTS snapshot (
  thscode TEXT PRIMARY KEY,
  as_of TEXT,
  last_price REAL,
  price_change REAL,
  pct_chg REAL,
  open_price REAL,
  high_price REAL,
  low_price REAL,
  prev_price REAL,
  volume REAL,
  turnover REAL
);

CREATE TABLE IF NOT EXISTS valuation (
  thscode TEXT PRIMARY KEY,
  as_of TEXT,
  pe_ttm REAL,
  pe_mrq REAL,
  pb_mrq REAL,
  ps_ttm REAL,
  pcf_ttm REAL,
  pe_industry_pct REAL,
  pb_industry_pct REAL
);

CREATE TABLE IF NOT EXISTS tech_factors (
  thscode TEXT PRIMARY KEY,
  as_of TEXT,
  return_20d REAL,
  return_60d REAL,
  return_120d REAL,
  volatility_20d REAL,
  volatility_60d REAL,
  volatility_120d REAL,
  max_drawdown_60d REAL,
  max_drawdown_120d REAL,
  ma20 REAL,
  ma60 REAL,
  above_ma60 INTEGER,
  avg_turnover_20d REAL
);

CREATE TABLE IF NOT EXISTS industry_map (
  thscode TEXT PRIMARY KEY,
  industry_code TEXT,
  industry_name TEXT,
  as_of TEXT
);

CREATE TABLE IF NOT EXISTS dividend (
  thscode TEXT PRIMARY KEY,
  as_of TEXT,
  dividend_yield_ttm REAL
);

CREATE TABLE IF NOT EXISTS index_members (
  index_code TEXT,
  thscode TEXT,
  as_of TEXT,
  PRIMARY KEY (index_code, thscode)
);
CREATE INDEX IF NOT EXISTS idx_index_members_stock ON index_members(thscode);

CREATE TABLE IF NOT EXISTS financial_indicators (
  thscode TEXT,
  report TEXT,
  index_id TEXT,
  value REAL,
  period_end TEXT,
  fetched_at TEXT,
  PRIMARY KEY (thscode, report, index_id)
);
CREATE INDEX IF NOT EXISTS idx_financial_stock ON financial_indicators(thscode);

CREATE TABLE IF NOT EXISTS data_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset TEXT,
  as_of TEXT,
  row_count INTEGER,
  status TEXT,
  error TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS strategies (
  id TEXT PRIMARY KEY,
  name TEXT,
  query TEXT,
  dsl_json TEXT,
  data_version TEXT,
  created_at TEXT,
  monitor_enabled INTEGER DEFAULT 0,
  last_run_at TEXT
);

CREATE TABLE IF NOT EXISTS monitor_runs (
  id TEXT PRIMARY KEY,
  strategy_id TEXT,
  run_at TEXT,
  status TEXT,
  summary_json TEXT,
  diff_json TEXT,
  error TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
  id TEXT PRIMARY KEY,
  purpose TEXT,
  model TEXT,
  prompt_version TEXT,
  input_digest TEXT,
  output_json TEXT,
  validation TEXT,
  retries INTEGER,
  latency_ms INTEGER,
  created_at TEXT
);

CREATE VIEW IF NOT EXISTS universe_view AS
SELECT
  t.thscode, t.ticker, t.name, t.exchange, t.list_date,
  s.as_of AS quote_as_of, s.last_price, s.pct_chg, s.turnover, s.volume,
  v.as_of AS valuation_as_of, v.pe_ttm, v.pe_mrq, v.pb_mrq, v.ps_ttm, v.pcf_ttm,
  v.pe_industry_pct, v.pb_industry_pct,
  f.as_of AS tech_as_of, f.return_20d, f.return_60d, f.return_120d,
  f.volatility_20d, f.volatility_60d, f.volatility_120d,
  f.max_drawdown_60d, f.max_drawdown_120d, f.ma20, f.ma60, f.above_ma60,
  f.avg_turnover_20d,
  i.industry_code, i.industry_name,
  d.dividend_yield_ttm
FROM tickers t
LEFT JOIN snapshot s ON s.thscode = t.thscode
LEFT JOIN valuation v ON v.thscode = t.thscode
LEFT JOIN tech_factors f ON f.thscode = t.thscode
LEFT JOIN industry_map i ON i.thscode = t.thscode
LEFT JOIN dividend d ON d.thscode = t.thscode
WHERE t.asset_type = 'a-share';
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        await db.close()


async def init_db() -> None:
    async with get_db() as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def upsert_many(db: aiosqlite.Connection, sql: str, rows: Iterable[tuple]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    await db.executemany(sql, rows)
    await db.commit()
    return len(rows)


async def record_version(
    dataset: str,
    as_of: str,
    row_count: int,
    status: str = "ok",
    error: str | None = None,
) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO data_versions(dataset, as_of, row_count, status, error, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (dataset, as_of, row_count, status, error, now_iso()),
        )
        await db.commit()


async def table_count(table: str) -> int:
    async with get_db() as db:
        cursor = await db.execute(f"SELECT COUNT(*) AS n FROM {table}")
        row = await cursor.fetchone()
        return int(row["n"] if row else 0)


async def latest_version(dataset: str) -> dict[str, Any] | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT dataset, as_of, row_count, status, error, created_at "
            "FROM data_versions WHERE dataset = ? ORDER BY id DESC LIMIT 1",
            (dataset,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
