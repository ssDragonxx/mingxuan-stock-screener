"""Application settings loaded from .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    base_dir: Path = BASE_DIR

    # Fuyao
    fuyao_api_key: str = (os.getenv("FUYAO_API_KEY") or "").strip()
    fuyao_base_url: str = (os.getenv("FUYAO_BASE_URL") or "https://fuyao.aicubes.cn").rstrip("/")

    # DeepSeek
    deepseek_api_key: str = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    deepseek_base_url: str = (os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    deepseek_model: str = (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()

    # Runtime
    data_dir: Path = Path(os.getenv("DATA_DIR") or (BASE_DIR / "data")).resolve()
    max_candidates: int = _int("MAX_CANDIDATES", 500)
    fetch_concurrency: int = _int("FETCH_CONCURRENCY", 5)
    financial_report: str = (os.getenv("FINANCIAL_REPORT") or "2026-2").strip()
    admin_token: str = (os.getenv("ADMIN_TOKEN") or "").strip()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mingxuan.db"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def live_data(self) -> bool:
        return bool(self.fuyao_api_key)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.deepseek_api_key)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
