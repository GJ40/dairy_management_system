from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DeleteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def soft_delete(self, model: type[Any], record_id: int) -> Any | None:
        record = await self.session.scalar(
            select(model).where(
                model.id == record_id,
                model.is_deleted.is_(False),
            )
        )
        if record is None:
            return None
        record.is_deleted = True
        await self.session.commit()
        return record
