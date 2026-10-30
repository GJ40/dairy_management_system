from __future__ import annotations

from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.models.customer_portal_account import CustomerPortalAccount
from app.repositories.customer_repository import CustomerRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.schemas.customer_invoices import (
    INVOICE_STATUSES,
    PortalInvoiceQuery,
    serialize_portal_balance,
    serialize_portal_invoice,
    serialize_portal_invoice_detail,
)
from app.utils.pdf import build_invoice_pdf


class CustomerInvoiceService:
    def __init__(
        self,
        repository: InvoiceRepository,
        customer_repository: CustomerRepository,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository

    async def list_invoices(
        self,
        account: CustomerPortalAccount,
        query: PortalInvoiceQuery,
    ) -> dict[str, Any]:
        if query.status is not None and query.status not in INVOICE_STATUSES:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "status: Invalid invoice status",
            )
        if (
            query.from_date is not None
            and query.to_date is not None
            and query.from_date > query.to_date
        ):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "from: must be on or before to",
            )

        rows, total = await self.repository.list_and_count(
            page=query.page,
            page_size=query.page_size,
            customer_id=account.customer_id,
            status=query.status,
            from_date=query.from_date,
            to_date=query.to_date,
        )
        return {
            "items": [serialize_portal_invoice(row) for row in rows],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": max(1, (total + query.page_size - 1) // query.page_size),
        }

    async def get_invoice(
        self,
        account: CustomerPortalAccount,
        invoice_id: int,
    ) -> dict[str, Any]:
        invoice = await self._get_owned(account, invoice_id)
        return {"invoice": serialize_portal_invoice_detail(invoice)}

    async def generate_invoice_pdf(
        self,
        account: CustomerPortalAccount,
        invoice_id: int,
    ) -> tuple[bytes, str]:
        invoice = await self._get_owned(account, invoice_id)
        sales = [
            link.sale
            for link in (invoice.sale_links or [])
            if link.sale is not None
        ]
        sales.sort(key=lambda sale: (sale.sale_date, sale.id))
        content = build_invoice_pdf(
            invoice=invoice,
            customer=invoice.customer,
            sales=sales,
        )
        return content, f"invoice-{invoice.invoice_no}.pdf"

    async def get_balance(
        self,
        account: CustomerPortalAccount,
    ) -> dict[str, Any]:
        total_sales, total_paid, outstanding = (
            await self.customer_repository.financials(account.customer_id)
        )
        return {"balance": serialize_portal_balance(total_sales, total_paid, outstanding)}

    async def _get_owned(
        self,
        account: CustomerPortalAccount,
        invoice_id: int,
    ):
        invoice = await self.repository.get_owned(
            invoice_id,
            account.customer_id,
        )
        if invoice is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Invoice with id {invoice_id} not found",
            )
        return invoice
