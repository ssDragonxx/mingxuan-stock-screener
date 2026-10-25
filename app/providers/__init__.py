"""Provider factory."""

from __future__ import annotations

from ..config import settings
from .base import DataNotReady, DataProvider, ProviderError

_provider: DataProvider | None = None


def get_provider() -> DataProvider:
    global _provider
    if _provider is None:
        if settings.live_data:
            from .fuyao import FuyaoProvider

            _provider = FuyaoProvider()
        else:
            from .mock import MockProvider

            _provider = MockProvider()
    return _provider


async def close_provider() -> None:
    global _provider
    if _provider is not None:
        await _provider.close()
        _provider = None


__all__ = ["DataProvider", "DataNotReady", "ProviderError", "get_provider", "close_provider"]
