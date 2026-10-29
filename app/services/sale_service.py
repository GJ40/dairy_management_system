from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.models.customer import Customer
from app.models.user import User
from app.repositories.customer_repository import CustomerRepository
from app.repositories.sale_repository import SaleRepository
from app.schemas.sale import (
    UNSET,
    CreateSaleRequest,
    SaleQuery,
    UpdateSaleRequest,
    _date_string,
    serialize_sale_detail,
)
from app.services.stock_service import StockService
from app.utils.time import is_future_date, is_today

CENT = Decimal("0.01")


def parse_sale_id(raw_id: str) -> int:
    if not raw_id.isdigit():
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            f"Sale with id {raw_id} not found",
        )
    return int(raw_id)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class SaleService:
    def __init__(
        self,
        repository: SaleRepository,
        customer_repository: CustomerRepository,
        stock_service: StockService,
    ) -> None:
        self.repository = repository
        self.customer_repository = customer_repository
        self.stock_service = stock_service

    def _assert_date_permission(self, sale_date: str, user: User) -> None:
        if is_future_date(sale_date):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_SALE_DATE",
                "Sale date cannot be in the future",
            )
        if user.role == "operator" and not is_today(sale_date):
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "OPERATOR_DATE_RESTRICTION",
                "Operators may only record sales for the current business day",
            )

    async def _assert_active_customer(self, customer_id: int) -> Customer:
        customer = await self.customer_repository.get_by_id(customer_id)
        if customer is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Customer with id {customer_id} not found",
            )
        if not customer.is_active:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "CUSTOMER_NOT_ACTIVE",
                f"Customer '{customer.name}' is currently deactivated and "
                "cannot make new purchases. Historical records remain "
                "preserved.",
            )
        return customer

    async def record_sale(
        self,
        payload: CreateSaleRequest,
        user: User,
    ) -> dict[str, Any]:
        self._assert_date_permission(payload.sale_date, user)

        try:
            customer = await self._assert_active_customer(payload.customer_id)
            captured_rate = (
                _decimal(payload.rate)
                if payload.rate is not UNSET
                else _decimal(customer.rate_per_litre)
            )
            if not captured_rate.is_finite() or captured_rate <= 0:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_RATE",
                    "Captured sale rate must be greater than zero",
                )

            litres = _decimal(payload.litres)
            if not litres.is_finite() or litres <= 0:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "INVALID_QUANTITY",
                    "Litres sold must be greater than zero",
                )

            amount = (litres * captured_rate).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )
            await self.stock_service.assert_available_stock(
                payload.sale_date,
                litres,
            )

            sale = await self.repository.create(
                customer_id=customer.id,
                sale_date=date.fromisoformat(payload.sale_date),
                litres=litres.quantize(CENT, rounding=ROUND_HALF_UP),
                rate=captured_rate.quantize(CENT, rounding=ROUND_HALF_UP),
                amount=amount,
                recorded_by=user.id,
            )
            await self.repository.flush()
            updated_stock = await self.stock_service.get_stock_for_date(
                payload.sale_date
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return {
            "id": sale.id,
            "customer_id": sale.customer_id,
            "sale_date": _date_string(sale.sale_date),
            "litres": f"{sale.litres:.2f}",
            "rate": f"{sale.rate:.2f}",
            "amount": f"{sale.amount:.2f}",
            "payment_status": sale.payment_status,
            "stock_remaining": updated_stock["closing_stock"],
        }

    async def list_sales(self, query: SaleQuery) -> dict[str, Any]:
        if (
            query.sale_date is None
            and query.from_date is not None
            and query.to_date is not None
            and query.from_date > query.to_date
        ):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_DATE_RANGE",
                "'from' date cannot be after 'to' date",
            )

        rows, total = await self.repository.list_and_count(
            page=query.page,
            page_size=query.page_size,
            customer_id=query.customer_id,
            sale_date=(
                date.fromisoformat(query.sale_date)
                if query.sale_date is not None
                else None
            ),
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
            payment_status=query.payment_status,
        )
        return {
            "items": [
                serialize_sale_detail(row, include_address=False) for row in rows
            ],
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
        }

    async def get_sale(self, raw_id: str) -> dict[str, Any]:
        sale = await self.repository.get_by_id(parse_sale_id(raw_id))
        if sale is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Sale with id {raw_id} not found",
            )
        return serialize_sale_detail(sale, include_address=True)

    async def update_sale(
        self,
        raw_id: str,
        payload: UpdateSaleRequest,
        user: User,
    ) -> dict[str, Any]:
        sale = await self.repository.get_by_id(parse_sale_id(raw_id))
        if sale is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "NOT_FOUND",
                f"Sale with id {raw_id} not found",
            )

        try:
            current_date = _date_string(sale.sale_date) or ""
            new_date = (
                payload.sale_date
                if payload.sale_date is not UNSET
                else current_date
            )
            self._assert_date_permission(new_date, user)

            current_litres = _decimal(sale.litres)
            current_rate = _decimal(sale.rate)
            new_litres = (
                _decimal(payload.litres)
                if payload.litres is not UNSET
                else current_litres
            )
            new_rate = (
                _decimal(payload.rate)
                if payload.rate is not UNSET
                else current_rate
            )

            if new_litres > current_litres or new_date != current_date:
                additional_litres = (
                    new_litres - current_litres
                    if new_date == current_date
                    else new_litres
                )
                await self.stock_service.assert_available_stock(
                    new_date,
                    additional_litres,
                )

            new_amount = (new_litres * new_rate).quantize(
                CENT,
                rounding=ROUND_HALF_UP,
            )
            sale.sale_date = date.fromisoformat(new_date)
            sale.litres = new_litres.quantize(CENT, rounding=ROUND_HALF_UP)
            sale.rate = new_rate.quantize(CENT, rounding=ROUND_HALF_UP)
            sale.amount = new_amount
            sale.recorded_by = user.id

            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        return serialize_sale_detail(sale, include_address=True)
