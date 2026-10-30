from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import (
    UNSET,
    CreateCustomerRequest,
    CustomerQuery,
    UpdateCustomerRequest,
    _decimal_string,
    serialize_customer,
)


def parse_customer_id(raw_id: str) -> int:
    if not raw_id.isdigit():
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Customer with id {raw_id} not found",
        )
    return int(raw_id)


def _optional_text(value: Any) -> str | None:
    if value is None or value is UNSET:
        return None
    return value or None


class CustomerService:
    def __init__(self, repository: CustomerRepository) -> None:
        self.repository = repository

    async def list_customers(self, query: CustomerQuery) -> dict[str, Any]:
        rows, total = await self.repository.list_and_count(
            page=query.page,
            page_size=query.page_size,
            search=query.search,
            is_active=query.is_active,
        )
        return {
            "items": [serialize_customer(customer) for customer in rows],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
        }

    async def get_customer(self, raw_id: str) -> dict[str, Any]:
        customer = await self.repository.get_by_id(parse_customer_id(raw_id))
        if customer is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Customer with id {raw_id} not found",
            )
        return serialize_customer(customer)

    async def create_customer(
        self,
        payload: CreateCustomerRequest,
    ) -> dict[str, Any]:
        customer = await self.repository.create(
            name=payload.name,
            phone=_optional_text(payload.phone),
            address=_optional_text(payload.address),
            rate_per_litre=Decimal(f"{payload.rate_per_litre:.2f}"),
            is_active=payload.is_active,
        )
        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return serialize_customer(customer)

    async def update_customer(
        self,
        raw_id: str,
        payload: UpdateCustomerRequest,
    ) -> dict[str, Any]:
        customer = await self.repository.get_by_id(parse_customer_id(raw_id))
        if customer is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Customer with id {raw_id} not found",
            )

        if payload.name is not UNSET:
            customer.name = payload.name
        if payload.phone is not UNSET:
            customer.phone = _optional_text(payload.phone)
        if payload.address is not UNSET:
            customer.address = _optional_text(payload.address)
        if payload.rate_per_litre is not UNSET:
            customer.rate_per_litre = Decimal(
                f"{payload.rate_per_litre:.2f}"
            )
        if payload.is_active is not UNSET:
            customer.is_active = payload.is_active

        try:
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return serialize_customer(customer)

    async def get_customer_balance(self, raw_id: str) -> dict[str, Any]:
        customer = await self.repository.get_by_id(parse_customer_id(raw_id))
        if customer is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Customer with id {raw_id} not found",
            )

        total_sales, total_paid, outstanding = (
            await self.repository.financials(customer.id)
        )
        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "rate_per_litre": _decimal_string(customer.rate_per_litre),
            "is_active": bool(customer.is_active),
            "total_sales_amount": f"{total_sales:.2f}",
            "total_paid_amount": f"{total_paid:.2f}",
            "outstanding_balance": f"{outstanding:.2f}",
        }
