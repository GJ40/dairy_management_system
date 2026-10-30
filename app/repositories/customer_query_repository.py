from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.models.customer_query import CustomerQuery
from app.models.customer_query_message import CustomerQueryMessage


class CustomerQueryRepository:
    def __init__(self, session: Any) -> None:
        self.session = session

    async def get_by_id(self, query_id: int) -> CustomerQuery | None:
        return await self.session.get(CustomerQuery, query_id)

    async def get_owned(
        self,
        query_id: int,
        customer_id: int,
    ) -> CustomerQuery | None:
        statement = select(CustomerQuery).where(
            CustomerQuery.id == query_id,
            CustomerQuery.customer_id == customer_id,
            CustomerQuery.is_deleted.is_(False),
        )
        return await self.session.scalar(statement)

    async def find_by_query_no(self, query_no: str) -> CustomerQuery | None:
        statement = select(CustomerQuery).where(
            CustomerQuery.query_no == query_no
        )
        return await self.session.scalar(statement)

    async def list_own_and_count(
        self,
        *,
        customer_id: int,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[CustomerQuery], int]:
        conditions = [
            CustomerQuery.is_deleted.is_(False),
            CustomerQuery.customer_id == customer_id,
        ]
        if status is not None:
            conditions.append(CustomerQuery.status == status)

        count_statement = select(func.count()).select_from(CustomerQuery).where(
            *conditions
        )
        total = int(await self.session.scalar(count_statement) or 0)

        statement = (
            select(CustomerQuery)
            .where(*conditions)
            .order_by(CustomerQuery.updated_at.desc(), CustomerQuery.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        result = await self.session.scalars(statement)
        return list(result.all()), total

    async def count_open_owned(self, customer_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(CustomerQuery)
            .where(
                CustomerQuery.is_deleted.is_(False),
                CustomerQuery.customer_id == customer_id,
                CustomerQuery.status != "closed",
            )
        )
        return int(await self.session.scalar(statement) or 0)

    async def list_all_and_count(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        assigned_to: int | None = None,
        customer_id: int | None = None,
        category: str | None = None,
    ) -> tuple[list[CustomerQuery], int]:
        conditions = [CustomerQuery.is_deleted.is_(False)]
        if status is not None:
            conditions.append(CustomerQuery.status == status)
        if assigned_to is not None:
            conditions.append(CustomerQuery.assigned_to == assigned_to)
        if customer_id is not None:
            conditions.append(CustomerQuery.customer_id == customer_id)
        if category is not None:
            conditions.append(CustomerQuery.category == category)

        count_statement = select(func.count()).select_from(CustomerQuery).where(
            *conditions
        )
        total = int(await self.session.scalar(count_statement) or 0)

        statement = (
            select(CustomerQuery)
            .where(*conditions)
            .order_by(CustomerQuery.updated_at.desc(), CustomerQuery.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        result = await self.session.scalars(statement)
        return list(result.all()), total

    async def create(
        self,
        *,
        query_no: str,
        customer_id: int,
        account_id: int,
        category: str,
        subject: str,
        last_message_at: datetime,
    ) -> CustomerQuery:
        query = CustomerQuery(
            query_no=query_no,
            customer_id=customer_id,
            account_id=account_id,
            category=category,
            subject=subject,
            status="open",
            last_message_at=last_message_at,
            is_deleted=False,
        )
        self.session.add(query)
        await self.session.flush()
        return query

    async def add_message(
        self,
        *,
        query_id: int,
        body: str,
        sender_type: str,
        sender_account_id: int | None = None,
        sender_user_id: int | None = None,
        is_internal: bool = False,
    ) -> CustomerQueryMessage:
        message = CustomerQueryMessage(
            query_id=query_id,
            body=body,
            sender_type=sender_type,
            sender_account_id=sender_account_id,
            sender_user_id=sender_user_id,
            is_internal=is_internal,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_messages(
        self,
        query_id: int,
        *,
        include_internal: bool,
    ) -> list[CustomerQueryMessage]:
        statement = select(CustomerQueryMessage).where(
            CustomerQueryMessage.query_id == query_id
        )
        if not include_internal:
            statement = statement.where(
                CustomerQueryMessage.is_internal.is_(False)
            )
        statement = statement.order_by(
            CustomerQueryMessage.created_at.asc(),
            CustomerQueryMessage.id.asc(),
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, row: Any) -> None:
        await self.session.refresh(row)
