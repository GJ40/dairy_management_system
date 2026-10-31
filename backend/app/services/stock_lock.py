from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import api_error

DEFAULT_LOCK_NAME = "dairy:stock"
DEFAULT_TIMEOUT_SECONDS = 10


class StockLockService:
    """Serialises stock-mutating operations with a MySQL advisory lock (D-005 option B).

    A dedicated connection owns the named lock for the whole unit of work, so the
    work session may commit while the lock is still held. A single global key is
    used instead of per-date keys because a sale on one date changes the derived
    opening stock of every later date; a narrower key would leave that race open.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        lock_name: str = DEFAULT_LOCK_NAME,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.engine = engine
        self.lock_name = lock_name
        self.timeout_seconds = timeout_seconds

    @asynccontextmanager
    async def lock(self) -> AsyncIterator[None]:
        async with self.engine.connect() as connection:
            acquired = await connection.scalar(
                text("SELECT GET_LOCK(:name, :timeout)"),
                {"name": self.lock_name, "timeout": self.timeout_seconds},
            )
            if acquired != 1:
                raise api_error(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "STOCK_BUSY",
                    "Stock is being updated by another request; try again",
                )
            try:
                yield
            finally:
                await connection.execute(
                    text("SELECT RELEASE_LOCK(:name)"),
                    {"name": self.lock_name},
                )
