"""Verify the Fuyao key and common capabilities before running ingestion.

    python scripts/probe_fuyao.py

It checks:
- ticker list
- a snapshot for 600519.SH
- a valuation for 600519.SH
- financial indicators for the configured report
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running as `python scripts/probe_fuyao.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.data.fuyao_client import FuyaoClient, FuyaoError


async def main() -> int:
    if not settings.fuyao_api_key:
        print("FUYAO_API_KEY is empty. Put it in .env first.")
        return 2
    client = FuyaoClient(settings.fuyao_api_key, settings.fuyao_base_url)
    try:
        result = await client.probe()
        print("probe:", result)
        snapshot = await client.snapshot_by_codes(["600519.SH"])
        print("snapshot:", snapshot[:1])
        valuation = await client.valuations(["600519.SH"])
        print("valuation:", valuation[:1])
        indicators = await client.financial_indicators("600519.SH", settings.financial_report)
        values = {k: v for k, v in (indicators.get("indicators") or {}).items() if v is not None}
        print("financial report:", settings.financial_report, "non-null indicators:", len(values))
        print("probe ok")
        return 0
    except FuyaoError as exc:
        print("FuyaoError:", exc.code, "|", exc.message, "| request_id:", exc.request_id)
        if exc.code == 2003:
            print("Hint: the key is valid but lacks capability permission; check the Fuyao console.")
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
