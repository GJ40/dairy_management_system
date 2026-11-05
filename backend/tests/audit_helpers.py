from __future__ import annotations

from typing import Any


class FakeAuditService:
    """Record audit calls without touching a database session."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.standalone_records: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> object:
        self.records.append(kwargs)
        return object()

    async def record_standalone(self, **kwargs: Any) -> bool:
        self.standalone_records.append(kwargs)
        return True
