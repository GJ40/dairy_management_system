from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.sale import Sale


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, customer_id: int) -> Customer | None:
        statement = select(Customer).where(
            Customer.id == customer_id,
            Customer.is_deleted.is_(False),
        )
        return await self.session.scalar(statement)

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[Customer], int]:
        conditions = [Customer.is_deleted.is_(False)]
        if is_active is not None:
            conditions.append(Customer.is_active.is_(is_active))
        if search:
            term = f"%{search}%"
            conditions.append(
                or_(
                    Customer.name.like(term),
                    Customer.phone.like(term),
                )
            )

        count_statement = select(func.count()).select_from(Customer).where(
            *conditions
        )
        total = int(await self.session.scalar(count_statement) or 0)

        statement = (
            select(Customer)
            .where(*conditions)
            .order_by(Customer.name.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = list(await self.session.scalars(statement))
        return rows, total

    async def create(
        self,
        *,
        name: str,
        phone: str | None,
        address: str | None,
        rate_per_litre: Decimal,
        is_active: bool,
    ) -> Customer:
        customer = Customer(
            name=name,
            phone=phone,
            address=address,
            rate_per_litre=rate_per_litre,
            is_active=is_active,
            is_deleted=False,
        )
        self.session.add(customer)
        return customer

    async def financials(self, customer_id: int) -> tuple[Decimal, Decimal, Decimal]:
        sales_statement = select(func.sum(Sale.amount)).where(
            Sale.customer_id == customer_id,
            Sale.is_deleted.is_(False),
        )
        invoices_statement = select(func.sum(Invoice.paid_amount)).where(
            Invoice.customer_id == customer_id,
            Invoice.is_deleted.is_(False),
        )
        total_sales = await self.session.scalar(sales_statement)
        total_paid = await self.session.scalar(invoices_statement)
        sales_value = Decimal(str(total_sales or 0))
        paid_value = Decimal(str(total_paid or 0))
        outstanding = max(Decimal("0"), sales_value - paid_value)
        return sales_value, paid_value, outstanding

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
