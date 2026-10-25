"""Data provider interface shared by mock and live modes."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]


class DataNotReady(Exception):
    """Raised when the live database has not been initialized."""

    code = "DATA_NOT_READY"

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class ProviderError(Exception):
    code = "PROVIDER_ERROR"


class DataProvider:
    mode = "base"

    async def get_universe(self, dsl: dict) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_financials(
        self,
        codes: list[str],
        fields: set[str],
        progress: ProgressCallback | None = None,
    ) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    async def get_cached_financials(
        self,
        codes: list[str],
        fields: set[str],
    ) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    async def get_financial_history(
        self,
        code: str,
        periods: int = 4,
    ) -> list[dict[str, Any]]:
        """Return raw indicator snapshots for the latest N report periods."""
        raise NotImplementedError

    async def get_stock(self, query: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def get_status(self) -> dict[str, Any]:
        raise NotImplementedError

    async def close(self) -> None:
        return None
