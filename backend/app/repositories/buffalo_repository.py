from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.buffalo import Buffalo
from app.schemas.buffalo import BuffaloQuery


class BuffaloRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        buffalo_id: int,
        *,
        include_deleted: bool = False,
    ) -> Buffalo | None:
        statement = select(Buffalo).where(Buffalo.id == buffalo_id)
        if not include_deleted:
            statement = statement.where(Buffalo.is_deleted.is_(False))
        return await self.session.scalar(statement)

    async def get_by_tag_no(
        self,
        tag_no: str,
        *,
        exclude_id: int | None = None,
        include_deleted: bool = False,
    ) -> Buffalo | None:
        statement = select(Buffalo).where(Buffalo.tag_no == tag_no.strip().upper())
        if not include_deleted:
            statement = statement.where(Buffalo.is_deleted.is_(False))
        if exclude_id is not None:
            statement = statement.where(Buffalo.id != exclude_id)
        return await self.session.scalar(statement)

    async def list_buffaloes(self, query: BuffaloQuery) -> tuple[list[Buffalo], int]:
        conditions = [Buffalo.is_deleted.is_(False)]
        if query.status:
            conditions.append(Buffalo.status == query.status)
        if query.search:
            term = f"%{query.search}%"
            conditions.append(
                or_(
                    Buffalo.name.like(term),
                    Buffalo.tag_no.like(term),
                    Buffalo.breed.like(term),
                )
            )

        count_statement = select(func.count()).select_from(Buffalo).where(*conditions)
        total = int(await self.session.scalar(count_statement) or 0)

        offset = (query.page - 1) * query.page_size
        statement = (
            select(Buffalo)
            .where(*conditions)
            .order_by(Buffalo.created_at.desc())
            .offset(offset)
            .limit(query.page_size)
        )
        rows = list(await self.session.scalars(statement))
        return rows, total

    async def list_active(self) -> list[Buffalo]:
        statement = (
            select(Buffalo)
            .where(
                Buffalo.is_deleted.is_(False),
                Buffalo.status == "active",
            )
            .order_by(Buffalo.tag_no.asc())
        )
        return list(await self.session.scalars(statement))

    async def count_by_status(self) -> list[tuple[str, int]]:
        statement = (
            select(Buffalo.status, func.count(Buffalo.id))
            .where(Buffalo.is_deleted.is_(False))
            .group_by(Buffalo.status)
        )
        return [(str(status), int(count)) for status, count in (await self.session.execute(statement)).all()]

    async def create(
        self,
        *,
        tag_no: str,
        name: str,
        breed: str,
        dob: date | None,
        purchase_date: date | None,
        status: str,
    ) -> Buffalo:
        buffalo = Buffalo(
            tag_no=tag_no,
            name=name,
            breed=breed,
            dob=dob,
            purchase_date=purchase_date,
            status=status,
            is_deleted=False,
        )
        self.session.add(buffalo)
        return buffalo

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, buffalo: Buffalo) -> None:
        await self.session.refresh(buffalo)
