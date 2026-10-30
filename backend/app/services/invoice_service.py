from __future__ import annotations

import math
import secrets
import time
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.models.invoice import Invoice
from app.repositories.customer_repository import CustomerRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.sale_repository import SaleRepository
from app.schemas.invoice import (
    CreateInvoiceRequest,
    InvoiceQuery,
    RecordPaymentRequest,
    serialize_invoice,
)
from app.utils.pdf import build_invoice_pdf

CENT = Decimal("0.01")


def parse_invoice_id(raw_id: str) -> int:
    if not raw_id.isdigit():
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Invoice with id {raw_id} not found",
        )
    return int(raw_id)


class InvoiceService:
    def __init__(
        self,
        repository: InvoiceRepository,
        customer_repository: CustomerRepository,
        sale_repository: SaleRepository,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository
        self.sale_repository = sale_repository

    async def _generate_unique_invoice_number(self, date_str: str) -> str:
        clean_date = date_str.replace("-", "")
        candidate = ""
        for _ in range(5):
            suffix = secrets.token_hex(2).upper()
            candidate = f"INV-{clean_date}-{suffix}"
            if await self.repository.find_by_invoice_no(candidate) is None:
                return candidate
        return f"INV-{clean_date}-{str(int(time.time() * 1000))[-4:]}"

    async def create_invoice_for_sale(
        self,
        *,
        customer_id: int,
        sale_id: int,
        period_start: date,
        period_end: date,
        total_amount: Decimal,
    ) -> Invoice:
        """Create one invoice linked to one sale without committing.

        Used by order fulfilment so the sale, invoice, link, order state and
        event commit or roll back together (D-012).
        """
        invoice_no = await self._generate_unique_invoice_number(
            period_start.isoformat()
        )
        invoice = await self.repository.create(
            invoice_no=invoice_no,
            customer_id=customer_id,
            period_start=period_start,
            period_end=period_end,
            total_amount=total_amount,
        )
        await self.repository.flush()
        await self.repository.create_invoice_sales(invoice.id, [sale_id])
        return invoice

    async def create_invoice(
        self,
        payload: CreateInvoiceRequest,
    ) -> dict[str, Any]:
        customer = await self.customer_repository.get_by_id(payload.customer_id)
        if customer is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Customer with id {payload.customer_id} not found",
            )

        period_start = date.fromisoformat(payload.period_start)
        period_end = date.fromisoformat(payload.period_end)

        try:
            if payload.sale_ids:
                sales = await self.sale_repository.find_by_ids_for_customer(
                    payload.customer_id,
                    payload.sale_ids,
                )
                if len(sales) != len(payload.sale_ids):
                    raise api_error(
                        status.HTTP_400_BAD_REQUEST,
                        "INVALID_SALES_SELECTION",
                        "One or more selected sales do not exist or do not "
                        "belong to this customer",
                    )
            else:
                sales = await self.sale_repository.find_for_period(
                    customer_id=payload.customer_id,
                    period_start=period_start,
                    period_end=period_end,
                )

            if not sales:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "NO_SALES_TO_INVOICE",
                    f"No sales found for customer '{customer.name}' between "
                    f"{payload.period_start} and {payload.period_end}",
                )

            sale_ids = [sale.id for sale in sales]
            already_invoiced = (
                await self.repository.find_invoice_sales_by_sale_ids(sale_ids)
            )
            if already_invoiced:
                conflicting = ", ".join(
                    str(row.sale_id) for row in already_invoiced
                )
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "SALE_ALREADY_INVOICED",
                    f"One or more sales (IDs: {conflicting}) have already "
                    "been invoiced",
                )

            total_amount = sum(
                (Decimal(str(sale.amount)) for sale in sales),
                Decimal("0.00"),
            ).quantize(CENT, rounding=ROUND_HALF_UP)
            invoice_no = await self._generate_unique_invoice_number(
                payload.period_end
            )

            invoice = await self.repository.create(
                invoice_no=invoice_no,
                customer_id=payload.customer_id,
                period_start=period_start,
                period_end=period_end,
                total_amount=total_amount,
            )
            await self.repository.flush()
            await self.repository.create_invoice_sales(invoice.id, sale_ids)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return await self.get_invoice_by_id(str(invoice.id))

    async def get_invoice_by_id(self, raw_id: str) -> dict[str, Any]:
        invoice = await self.repository.get_by_id(parse_invoice_id(raw_id))
        if invoice is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Invoice with id {raw_id} not found",
            )
        return serialize_invoice(invoice, detail=True)

    async def list_invoices(self, query: InvoiceQuery) -> dict[str, Any]:
        rows, total = await self.repository.list_and_count(
            page=query.page,
            page_size=query.page_size,
            customer_id=query.customer_id,
            status=query.status,
            from_date=(
                date.fromisoformat(query.from_date)
                if query.from_date is not None
                else None
            ),
            to_date=(
                date.fromisoformat(query.to_date)
                if query.to_date is not None
                else None
            ),
        )
        return {
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": math.ceil(total / query.page_size) or 1,
            "items": [
                serialize_invoice(invoice, detail=False) for invoice in rows
            ],
        }

    async def record_payment(
        self,
        raw_id: str,
        payload: RecordPaymentRequest,
    ) -> dict[str, Any]:
        payment_amount = Decimal(str(payload.amount))
        if not payment_amount.is_finite() or payment_amount <= 0:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "BAD_REQUEST",
                "Payment amount must be greater than zero",
            )

        try:
            invoice = await self.repository.get_by_id(
                parse_invoice_id(raw_id)
            )
            if invoice is None:
                raise api_error(
                    status.HTTP_404_NOT_FOUND,
                    "NOT_FOUND",
                    f"Invoice with id {raw_id} not found",
                )

            current_total = Decimal(str(invoice.total_amount))
            current_paid = Decimal(str(invoice.paid_amount))
            new_paid = current_paid + payment_amount
            new_status = "partial"
            if new_paid >= current_total:
                new_status = "paid"
            elif new_paid <= 0:
                new_status = "unpaid"

            invoice.paid_amount = new_paid.quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )
            invoice.status = new_status

            if new_status == "paid" and invoice.sale_links:
                sale_ids = [
                    link.sale.id
                    for link in invoice.sale_links
                    if link.sale is not None
                ]
                for link in invoice.sale_links:
                    if link.sale is not None:
                        link.sale.payment_status = "paid"
                await self.repository.mark_sales_paid(sale_ids)

            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return await self.get_invoice_by_id(raw_id)

    async def generate_invoice_pdf(
        self,
        raw_id: str,
    ) -> tuple[bytes, str]:
        invoice = await self.get_invoice_by_id(raw_id)
        buffer = build_invoice_pdf(
            invoice=invoice,
            customer=invoice["customer"],
            sales=invoice["sales"],
        )
        return buffer, f"invoice-{invoice['invoice_no']}.pdf"
