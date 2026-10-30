from __future__ import annotations

from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.models.customer_portal_account import CustomerPortalAccount
from app.repositories.customer_order_repository import CustomerOrderRepository
from app.repositories.customer_query_repository import CustomerQueryRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.schemas.customer_dashboard import serialize_dashboard, serialize_profile

RECENT_LIMIT = 5


class CustomerDashboardService:
    def __init__(
        self,
        customer_repository: CustomerRepository,
        order_repository: CustomerOrderRepository,
        invoice_repository: InvoiceRepository,
        query_repository: CustomerQueryRepository,
    ) -> None:
        self.customer_repository = customer_repository
        self.order_repository = order_repository
        self.invoice_repository = invoice_repository
        self.query_repository = query_repository

    async def get_dashboard(
        self,
        account: CustomerPortalAccount,
    ) -> dict[str, Any]:
        customer = await self._customer(account)
        total_sales, total_paid, outstanding = (
            await self.customer_repository.financials(customer.id)
        )
        orders, _ = await self.order_repository.list_and_count(
            customer_id=customer.id,
            page=1,
            page_size=RECENT_LIMIT,
        )
        invoices, _ = await self.invoice_repository.list_and_count(
            customer_id=customer.id,
            page=1,
            page_size=RECENT_LIMIT,
        )
        open_queries = await self.query_repository.count_open_owned(customer.id)
        return serialize_dashboard(
            customer=customer,
            total_sales=total_sales,
            total_paid=total_paid,
            outstanding=outstanding,
            orders=orders,
            invoices=invoices,
            open_queries=open_queries,
        )

    async def get_profile(
        self,
        account: CustomerPortalAccount,
    ) -> dict[str, Any]:
        customer = await self._customer(account)
        return serialize_profile(account, customer)

    async def _customer(self, account: CustomerPortalAccount) -> Any:
        customer = await self.customer_repository.get_by_id(account.customer_id)
        if customer is None or not customer.is_active:
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "ACCOUNT_INACTIVE",
                "The linked customer account is inactive",
            )
        return customer
