from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_portal_account import CustomerPortalAccount
from app.models.customer_portal_account_event import CustomerPortalAccountEvent
from app.schemas.customer_portal_auth import PortalAccountQuery


class CustomerPortalAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        account_id: int,
        *,
        include_deleted: bool = False,
    ) -> CustomerPortalAccount | None:
        statement = select(CustomerPortalAccount).where(
            CustomerPortalAccount.id == account_id
        )
        if not include_deleted:
            statement = statement.where(CustomerPortalAccount.is_deleted.is_(False))
        return await self.session.scalar(statement)

    async def get_by_email(
        self,
        email: str,
        *,
        include_deleted: bool = False,
    ) -> CustomerPortalAccount | None:
        statement = select(CustomerPortalAccount).where(
            CustomerPortalAccount.email == email.strip().lower()
        )
        if not include_deleted:
            statement = statement.where(CustomerPortalAccount.is_deleted.is_(False))
        return await self.session.scalar(statement)

    async def get_by_customer_id(
        self,
        customer_id: int,
        *,
        include_deleted: bool = False,
    ) -> CustomerPortalAccount | None:
        statement = select(CustomerPortalAccount).where(
            CustomerPortalAccount.customer_id == customer_id
        )
        if not include_deleted:
            statement = statement.where(CustomerPortalAccount.is_deleted.is_(False))
        return await self.session.scalar(statement)

    async def get_by_activation_hash(
        self,
        token_hash: str,
    ) -> CustomerPortalAccount | None:
        statement = select(CustomerPortalAccount).where(
            CustomerPortalAccount.activation_token_hash == token_hash,
            CustomerPortalAccount.is_deleted.is_(False),
        )
        return await self.session.scalar(statement)

    async def list_and_count(
        self,
        query: PortalAccountQuery,
    ) -> tuple[list[CustomerPortalAccount], int]:
        conditions = [CustomerPortalAccount.is_deleted.is_(False)]
        if query.customer_id is not None:
            conditions.append(CustomerPortalAccount.customer_id == query.customer_id)
        if query.is_active is not None:
            conditions.append(CustomerPortalAccount.is_active.is_(query.is_active))
        if query.is_locked is not None:
            conditions.append(
                CustomerPortalAccount.locked_at.is_not(None)
                if query.is_locked
                else CustomerPortalAccount.locked_at.is_(None)
            )

        count_statement = select(func.count()).select_from(CustomerPortalAccount).where(
            *conditions
        )
        total = int(await self.session.scalar(count_statement) or 0)

        offset = (query.page - 1) * query.page_size
        statement = (
            select(CustomerPortalAccount)
            .where(*conditions)
            .order_by(CustomerPortalAccount.created_at.desc())
            .offset(offset)
            .limit(query.page_size)
        )
        rows = list(await self.session.scalars(statement))
        return rows, total

    async def create(
        self,
        *,
        customer_id: int,
        email: str,
        activation_token_hash: str,
        activation_expires_at: datetime,
    ) -> CustomerPortalAccount:
        account = CustomerPortalAccount(
            customer_id=customer_id,
            email=email.strip().lower(),
            password_hash=None,
            is_active=True,
            activation_token_hash=activation_token_hash,
            activation_expires_at=activation_expires_at,
            activated_at=None,
            is_deleted=False,
        )
        self.session.add(account)
        await self.session.flush()
        return account

    async def list_events(
        self,
        account_id: int,
    ) -> list[CustomerPortalAccountEvent]:
        statement = (
            select(CustomerPortalAccountEvent)
            .where(CustomerPortalAccountEvent.account_id == account_id)
            .order_by(
                CustomerPortalAccountEvent.created_at.asc(),
                CustomerPortalAccountEvent.id.asc(),
            )
        )
        return list(await self.session.scalars(statement))

    async def add_event(
        self,
        *,
        account_id: int,
        action: str,
        actor_user_id: int | None,
        note: str | None = None,
    ) -> CustomerPortalAccountEvent:
        event = CustomerPortalAccountEvent(
            account_id=account_id,
            action=action,
            actor_user_id=actor_user_id,
            note=note,
        )
        self.session.add(event)
        return event

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, account: CustomerPortalAccount) -> None:
        await self.session.refresh(account)
