from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_order import CustomerOrder
from app.models.customer_order_event import CustomerOrderEvent
from app.models.customer_portal_account import CustomerPortalAccount
from app.models.invoice import Invoice
from app.models.invoice_sale import InvoiceSale
from app.models.sale import Sale


class CustomerOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(
        self,
        order_id: int,
        *,
        include_deleted: bool = False,
    ) -> CustomerOrder | None:
        conditions = [CustomerOrder.id == order_id]
        if not include_deleted:
            conditions.append(CustomerOrder.is_deleted.is_(False))
        result = await self.session.scalars(
            select(CustomerOrder).where(*conditions)
        )
        return result.one_or_none()

    async def get_owned(
        self,
        order_id: int,
        customer_id: int,
    ) -> CustomerOrder | None:
        result = await self.session.scalars(
            select(CustomerOrder).where(
                CustomerOrder.id == order_id,
                CustomerOrder.customer_id == customer_id,
                CustomerOrder.is_deleted.is_(False),
            )
        )
        return result.one_or_none()

    async def find_by_order_no(self, order_no: str) -> CustomerOrder | None:
        result = await self.session.scalars(
            select(CustomerOrder).where(CustomerOrder.order_no == order_no)
        )
        return result.one_or_none()

    async def list_and_count(
        self,
        *,
        customer_id: int,
        page: int,
        page_size: int,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[CustomerOrder], int]:
        conditions: list[Any] = [
            CustomerOrder.customer_id == customer_id,
            CustomerOrder.is_deleted.is_(False),
        ]
        if status is not None:
            conditions.append(CustomerOrder.status == status)
        if from_date is not None:
            conditions.append(CustomerOrder.requested_date >= from_date)
        if to_date is not None:
            conditions.append(CustomerOrder.requested_date <= to_date)

        total = int(
            await self.session.scalar(
                select(func.count()).select_from(CustomerOrder).where(*conditions)
            )
            or 0
        )
        rows = list(
            await self.session.scalars(
                select(CustomerOrder)
                .where(*conditions)
                .order_by(
                    CustomerOrder.created_at.desc(),
                    CustomerOrder.id.desc(),
                )
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        return rows, total

    async def reserved_litres(
        self,
        *,
        customer_id: int,
        requested_date: date,
    ) -> Decimal:
        total = await self.session.scalar(
            select(func.sum(CustomerOrder.quantity_litres)).where(
                CustomerOrder.customer_id == customer_id,
                CustomerOrder.requested_date == requested_date,
                CustomerOrder.status.in_(("submitted", "approved")),
                CustomerOrder.is_deleted.is_(False),
            )
        )
        return Decimal(total or 0)

    async def total_approved_litres(self, requested_date: date) -> Decimal:
        total = await self.session.scalar(
            select(func.sum(CustomerOrder.quantity_litres)).where(
                CustomerOrder.requested_date == requested_date,
                CustomerOrder.status == "approved",
                CustomerOrder.is_deleted.is_(False),
            )
        )
        return Decimal(total or 0)

    async def list_all_and_count(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        customer_id: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        search: str | None = None,
    ) -> tuple[list[CustomerOrder], int]:
        conditions: list[Any] = [CustomerOrder.is_deleted.is_(False)]
        if status is not None:
            conditions.append(CustomerOrder.status == status)
        if customer_id is not None:
            conditions.append(CustomerOrder.customer_id == customer_id)
        if from_date is not None:
            conditions.append(CustomerOrder.requested_date >= from_date)
        if to_date is not None:
            conditions.append(CustomerOrder.requested_date <= to_date)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                or_(
                    CustomerOrder.order_no.like(pattern),
                    Customer.name.like(pattern),
                    Customer.phone.like(pattern),
                )
            )

        base = (
            select(CustomerOrder)
            .join(Customer, Customer.id == CustomerOrder.customer_id)
            .where(*conditions)
        )
        total = int(
            await self.session.scalar(
                select(func.count())
                .select_from(CustomerOrder)
                .join(Customer, Customer.id == CustomerOrder.customer_id)
                .where(*conditions)
            )
            or 0
        )
        rows = list(
            await self.session.scalars(
                base.order_by(
                    CustomerOrder.created_at.desc(),
                    CustomerOrder.id.desc(),
                )
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        return rows, total

    async def get_account(self, account_id: int) -> CustomerPortalAccount | None:
        return await self.session.get(CustomerPortalAccount, account_id)

    async def create(
        self,
        *,
        order_no: str,
        customer_id: int,
        account_id: int,
        requested_date: date,
        quantity_litres: Decimal,
        rate_snapshot: Decimal,
        estimated_total: Decimal,
        note: str | None,
    ) -> CustomerOrder:
        order = CustomerOrder(
            order_no=order_no,
            customer_id=customer_id,
            account_id=account_id,
            requested_date=requested_date,
            quantity_litres=quantity_litres,
            rate_snapshot=rate_snapshot,
            estimated_total=estimated_total,
            note=note,
            status="submitted",
            is_deleted=False,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def add_event(
        self,
        *,
        order_id: int,
        from_status: str | None,
        to_status: str,
        actor_type: str,
        actor_account_id: int | None = None,
        actor_user_id: int | None = None,
        reason: str | None = None,
    ) -> CustomerOrderEvent:
        event = CustomerOrderEvent(
            order_id=order_id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor_type,
            actor_account_id=actor_account_id,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        self.session.add(event)
        return event

    async def list_events(self, order_id: int) -> list[CustomerOrderEvent]:
        return list(
            await self.session.scalars(
                select(CustomerOrderEvent)
                .where(CustomerOrderEvent.order_id == order_id)
                .order_by(
                    CustomerOrderEvent.created_at.asc(),
                    CustomerOrderEvent.id.asc(),
                )
            )
        )

    async def get_sale_by_order_id(self, order_id: int) -> Sale | None:
        result = await self.session.scalars(
            select(Sale).where(
                Sale.source_order_id == order_id,
                Sale.is_deleted.is_(False),
            )
        )
        return result.one_or_none()

    async def get_invoice_for_sale(self, sale_id: int) -> Invoice | None:
        result = await self.session.scalars(
            select(Invoice)
            .join(InvoiceSale, InvoiceSale.invoice_id == Invoice.id)
            .where(
                InvoiceSale.sale_id == sale_id,
                Invoice.is_deleted.is_(False),
            )
        )
        return result.one_or_none()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, order: CustomerOrder) -> None:
        await self.session.refresh(order)
