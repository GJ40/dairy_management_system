from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class SeedStore:
    """Minimal persistence surface used by the seeders.

    Lookups intentionally ignore ``is_deleted``, matching the Node seeders, which
    use ``findOrCreate`` on the natural key only.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find(self, model: Any, **conditions: Any) -> Any | None:
        statement = select(model).filter_by(**conditions).limit(1)
        return await self.session.scalar(statement)

    async def find_all(self, model: Any) -> list[Any]:
        statement = select(model)
        return list(await self.session.scalars(statement))

    async def create(self, model: Any, **values: Any) -> Any:
        instance = model(**values)
        self.session.add(instance)
        return instance

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
