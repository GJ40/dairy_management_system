from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.core.request_context import RequestContext
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import (
    UNSET,
    CreateCustomerRequest,
    CustomerQuery,
    UpdateCustomerRequest,
    _decimal_string,
    serialize_customer,
)
from app.services.security_audit_service import SecurityAuditService


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
    def __init__(
        self,
        repository: CustomerRepository,
        audit: SecurityAuditService | None = None,
    ) -> None:
        self.repository = repository
        self.audit = audit

    async def _record(
        self,
        *,
        event_type: str,
        actor_user_id: int | None,
        context: RequestContext | None,
        customer_id: int,
        metadata: dict[str, object],
    ) -> None:
        if self.audit is None or actor_user_id is None:
            return
        await self.audit.record(
            event_type=event_type,
            context=context,
            actor_user_id=actor_user_id,
            resource_type="customer",
            resource_id=customer_id,
            metadata=metadata,
        )

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
        *,
        actor_user_id: int | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        customer = await self.repository.create(
            name=payload.name,
            phone=_optional_text(payload.phone),
            address=_optional_text(payload.address),
            rate_per_litre=Decimal(f"{payload.rate_per_litre:.2f}"),
            is_active=payload.is_active,
        )
        try:
            await self.repository.flush()
            await self._record(
                event_type="customer.created",
                actor_user_id=actor_user_id,
                context=context,
                customer_id=customer.id,
                metadata={"customer_id": customer.id},
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return serialize_customer(customer)

    async def update_customer(
        self,
        raw_id: str,
        payload: UpdateCustomerRequest,
        *,
        actor_user_id: int | None = None,
        context: RequestContext | None = None,
    ) -> dict[str, Any]:
        customer = await self.repository.get_by_id(parse_customer_id(raw_id))
        if customer is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Customer with id {raw_id} not found",
            )

        changed_fields: list[str] = []
        if payload.name is not UNSET and customer.name != payload.name:
            customer.name = payload.name
            changed_fields.append("name")
        if payload.phone is not UNSET:
            phone = _optional_text(payload.phone)
            if customer.phone != phone:
                customer.phone = phone
                changed_fields.append("phone")
        if payload.address is not UNSET:
            address = _optional_text(payload.address)
            if customer.address != address:
                customer.address = address
                changed_fields.append("address")
        if payload.rate_per_litre is not UNSET:
            rate = Decimal(f"{payload.rate_per_litre:.2f}")
            if customer.rate_per_litre != rate:
                customer.rate_per_litre = rate
                changed_fields.append("rate_per_litre")
        if payload.is_active is not UNSET:
            if customer.is_active != payload.is_active:
                customer.is_active = payload.is_active
                changed_fields.append("is_active")

        try:
            if changed_fields:
                await self._record(
                    event_type="customer.updated",
                    actor_user_id=actor_user_id,
                    context=context,
                    customer_id=customer.id,
                    metadata={
                        "customer_id": customer.id,
                        "changed_fields": changed_fields,
                    },
                )
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
