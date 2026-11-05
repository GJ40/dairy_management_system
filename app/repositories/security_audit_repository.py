from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.security_audit_event import SecurityAuditEvent
from app.models.user import User


class SecurityAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, event: SecurityAuditEvent) -> None:
        self.session.add(event)

    async def get_by_id(self, event_id: int) -> SecurityAuditEvent | None:
        return await self.session.get(SecurityAuditEvent, event_id)

    async def resolve_actor_labels(
        self, events: list[SecurityAuditEvent]
    ) -> dict[tuple[str, int], tuple[str | None, str | None]]:
        """Map staff and portal actors to a readable name and email.

        Soft-deleted users and customers are included on purpose: an audit row
        must keep naming its actor long after the account itself is gone, and
        portal account ids are not exposed anywhere in the staff UI.
        """
        user_ids = {
            event.actor_user_id
            for event in events
            if event.actor_type == "staff" and event.actor_user_id is not None
        }
        account_ids = {
            event.actor_account_id
            for event in events
            if event.actor_type == "customer" and event.actor_account_id is not None
        }

        labels: dict[tuple[str, int], tuple[str | None, str | None]] = {}
        if user_ids:
            user_rows = await self.session.execute(
                select(User.id, User.full_name, User.email).where(
                    User.id.in_(user_ids)
                )
            )
            for user_id, full_name, email in user_rows:
                labels[("staff", int(user_id))] = (full_name, email)
        if account_ids:
            account_rows = await self.session.execute(
                select(
                    CustomerPortalAccount.id,
                    CustomerPortalAccount.email,
                    Customer.name,
                )
                .join(
                    Customer,
                    Customer.id == CustomerPortalAccount.customer_id,
                    isouter=True,
                )
                .where(CustomerPortalAccount.id.in_(account_ids))
            )
            for account_id, email, customer_name in account_rows:
                labels[("customer", int(account_id))] = (
                    customer_name or email,
                    email,
                )
        return labels

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        event_type: str | None = None,
        category: str | None = None,
        search: str | None = None,
        ip_address: str | None = None,
        outcome: str | None = None,
        severity: str | None = None,
        actor_type: str | None = None,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
        request_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        from_created_at: datetime | None = None,
        to_created_at: datetime | None = None,
    ) -> tuple[list[SecurityAuditEvent], int]:
        conditions: list[Any] = []
        if event_type is not None:
            conditions.append(SecurityAuditEvent.event_type == event_type)
        if category is not None:
            conditions.append(
                SecurityAuditEvent.event_type.startswith(f"{category}.")
            )
        if search is not None:
            term = search.strip()
            if term:
                conditions.append(
                    or_(
                        SecurityAuditEvent.event_type.contains(term, autoescape=True),
                        SecurityAuditEvent.path.contains(term, autoescape=True),
                        SecurityAuditEvent.resource_type.contains(
                            term, autoescape=True
                        ),
                        SecurityAuditEvent.resource_id.contains(
                            term, autoescape=True
                        ),
                        SecurityAuditEvent.request_id.contains(
                            term, autoescape=True
                        ),
                        SecurityAuditEvent.ip_address.contains(
                            term, autoescape=True
                        ),
                    )
                )
        if ip_address is not None:
            conditions.append(SecurityAuditEvent.ip_address == ip_address)
        if outcome is not None:
            conditions.append(SecurityAuditEvent.outcome == outcome)
        if severity is not None:
            conditions.append(SecurityAuditEvent.severity == severity)
        if actor_type is not None:
            conditions.append(SecurityAuditEvent.actor_type == actor_type)
        if actor_user_id is not None:
            conditions.append(SecurityAuditEvent.actor_user_id == actor_user_id)
        if actor_account_id is not None:
            conditions.append(SecurityAuditEvent.actor_account_id == actor_account_id)
        if request_id is not None:
            conditions.append(SecurityAuditEvent.request_id == request_id)
        if resource_type is not None:
            conditions.append(SecurityAuditEvent.resource_type == resource_type)
        if resource_id is not None:
            conditions.append(SecurityAuditEvent.resource_id == resource_id)
        if from_created_at is not None:
            conditions.append(SecurityAuditEvent.created_at >= from_created_at)
        if to_created_at is not None:
            conditions.append(SecurityAuditEvent.created_at <= to_created_at)

        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(SecurityAuditEvent)
                .where(*conditions)
            )
            or 0
        )
        rows = list(
            await self.session.scalars(
                select(SecurityAuditEvent)
                .where(*conditions)
                .order_by(
                    SecurityAuditEvent.created_at.desc(),
                    SecurityAuditEvent.id.desc(),
                )
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        return rows, total

    async def count_recent(
        self,
        *,
        event_type: str,
        since: datetime,
        actor_user_id: int | None = None,
        actor_account_id: int | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> int:
        conditions: list[Any] = [
            SecurityAuditEvent.event_type == event_type,
            SecurityAuditEvent.created_at >= since,
        ]
        if actor_user_id is not None:
            conditions.append(SecurityAuditEvent.actor_user_id == actor_user_id)
        if actor_account_id is not None:
            conditions.append(SecurityAuditEvent.actor_account_id == actor_account_id)
        if resource_type is not None:
            conditions.append(SecurityAuditEvent.resource_type == resource_type)
        if resource_id is not None:
            conditions.append(SecurityAuditEvent.resource_id == resource_id)
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(SecurityAuditEvent)
                .where(*conditions)
            )
            or 0
        )

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
