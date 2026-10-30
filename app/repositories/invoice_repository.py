from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.invoice import Invoice
from app.models.invoice_sale import InvoiceSale
from app.models.sale import Sale


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, invoice_id: int) -> Invoice | None:
        statement = (
            select(Invoice)
            .options(
                joinedload(Invoice.customer),
                selectinload(Invoice.sale_links).joinedload(InvoiceSale.sale),
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.is_deleted.is_(False),
            )
        )
        result = await self.session.scalars(statement)
        return result.unique().one_or_none()

    async def find_by_invoice_no(self, invoice_no: str) -> Invoice | None:
        statement = select(Invoice).where(Invoice.invoice_no == invoice_no)
        return await self.session.scalar(statement)

    async def get_owned(
        self,
        invoice_id: int,
        customer_id: int,
    ) -> Invoice | None:
        statement = (
            select(Invoice)
            .options(
                joinedload(Invoice.customer),
                selectinload(Invoice.sale_links).joinedload(InvoiceSale.sale),
            )
            .where(
                Invoice.id == invoice_id,
                Invoice.customer_id == customer_id,
                Invoice.is_deleted.is_(False),
            )
        )
        result = await self.session.scalars(statement)
        return result.unique().one_or_none()

    async def list_and_count(
        self,
        *,
        page: int,
        page_size: int,
        customer_id: int | None = None,
        status: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[Invoice], int]:
        conditions = [Invoice.is_deleted.is_(False)]
        if customer_id is not None:
            conditions.append(Invoice.customer_id == customer_id)
        if status is not None:
            conditions.append(Invoice.status == status)
        if from_date is not None and to_date is not None:
            conditions.append(Invoice.period_start >= from_date)
            conditions.append(Invoice.period_end <= to_date)
        elif from_date is not None:
            conditions.append(Invoice.period_start >= from_date)
        elif to_date is not None:
            conditions.append(Invoice.period_end <= to_date)

        count_statement = select(func.count()).select_from(Invoice).where(
            *conditions
        )
        total = int(await self.session.scalar(count_statement) or 0)

        statement = (
            select(Invoice)
            .options(joinedload(Invoice.customer))
            .where(*conditions)
            .order_by(Invoice.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = list((await self.session.scalars(statement)).unique().all())
        return rows, total

    async def create(
        self,
        *,
        invoice_no: str,
        customer_id: int,
        period_start: date,
        period_end: date,
        total_amount: Decimal,
    ) -> Invoice:
        invoice = Invoice(
            invoice_no=invoice_no,
            customer_id=customer_id,
            period_start=period_start,
            period_end=period_end,
            total_amount=total_amount,
            paid_amount=Decimal("0.00"),
            status="unpaid",
            is_deleted=False,
        )
        self.session.add(invoice)
        return invoice

    async def create_invoice_sales(
        self,
        invoice_id: int,
        sale_ids: list[int],
    ) -> None:
        self.session.add_all(
            [
                InvoiceSale(invoice_id=invoice_id, sale_id=sale_id)
                for sale_id in sale_ids
            ]
        )

    async def find_invoice_sales_by_sale_ids(
        self,
        sale_ids: list[int],
    ) -> list[InvoiceSale]:
        statement = select(InvoiceSale).where(InvoiceSale.sale_id.in_(sale_ids))
        return list(await self.session.scalars(statement))

    async def mark_sales_paid(self, sale_ids: list[int]) -> None:
        if not sale_ids:
            return
        await self.session.execute(
            update(Sale)
            .where(Sale.id.in_(sale_ids))
            .values(payment_status="paid")
        )

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
