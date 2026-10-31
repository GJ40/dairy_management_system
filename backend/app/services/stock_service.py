from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fastapi import status

from app.core.errors import api_error
from app.repositories.stock_repository import StockRepository
from app.utils.time import get_business_date

ZERO = Decimal("0")
CENT = Decimal("0.01")

ReservedLookup = Callable[[date], Awaitable[Decimal]]


def _decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round2(value: Any) -> Decimal:
    rounded = _decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    if rounded == 0:
        return Decimal("0.00")
    return rounded


class StockService:
    def __init__(self, repository: StockRepository) -> None:
        self.repository = repository

    async def get_stock_for_date(
        self,
        raw_date: str | None = None,
    ) -> dict[str, str]:
        stock_date = raw_date or get_business_date()
        parsed_date = date.fromisoformat(stock_date)

        prior_production, prior_sales, prior_wastage = (
            await self.repository.sum_prior_quantities(parsed_date)
        )
        opening = _round2(prior_production - prior_sales - prior_wastage)

        current_production, current_sales, current_wastage = (
            await self.repository.sum_current_quantities(parsed_date)
        )
        produced = _round2(current_production)
        sold = _round2(current_sales)
        wasted = _round2(current_wastage)
        closing = _round2(opening + produced - sold - wasted)

        return {
            "date": stock_date,
            "opening_stock": f"{opening:.2f}",
            "produced": f"{produced:.2f}",
            "sold": f"{sold:.2f}",
            "wasted": f"{wasted:.2f}",
            "closing_stock": f"{closing:.2f}",
        }

    async def assert_available_stock(
        self,
        raw_date: str,
        requested_litres: Any,
        *,
        reserved_lookup: ReservedLookup | None = None,
    ) -> dict[str, str]:
        try:
            requested = _decimal(requested_litres)
        except (InvalidOperation, ValueError) as exc:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_QUANTITY",
                "Requested litres must be a positive number",
            ) from exc

        if not requested.is_finite() or requested <= 0:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_QUANTITY",
                "Requested litres must be a positive number",
            )

        stock = await self.get_stock_for_date(raw_date)
        stock_day = date.fromisoformat(raw_date)
        current_closing = _decimal(stock["closing_stock"])
        current_reserved = (
            _decimal(await reserved_lookup(stock_day))
            if reserved_lookup is not None
            else ZERO
        )
        available = current_closing - current_reserved
        if available < requested:
            available = max(ZERO, available)
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "STOCK_INSUFFICIENT",
                f"Only {available:.2f} L available",
            )

        future_dates = await self.repository.get_future_active_dates(stock_day)
        for future_date in future_dates:
            future_stock = await self.get_stock_for_date(future_date.isoformat())
            future_reserved = (
                _decimal(await reserved_lookup(future_date))
                if reserved_lookup is not None
                else ZERO
            )
            future_available = (
                _decimal(future_stock["closing_stock"]) - future_reserved
            )
            if future_available < requested:
                raise api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "STOCK_INSUFFICIENT",
                    "Insufficient stock: Deducting "
                    f"{requested:.2f} L on {raw_date} would result in negative "
                    f"closing stock on {future_date.isoformat()} (only "
                    f"{max(ZERO, future_available):.2f} L margin)",
                )

        return stock

    async def get_future_active_dates(self, stock_date: date) -> list[date]:
        return await self.repository.get_future_active_dates(stock_date)

    async def get_stock_history(
        self,
        from_date: str,
        to_date: str,
    ) -> dict[str, Any]:
        if from_date > to_date:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_DATE_RANGE",
                "'from' date cannot be after 'to' date",
            )

        history: list[dict[str, str]] = []
        current = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        while current <= end:
            history.append(await self.get_stock_for_date(current.isoformat()))
            current += timedelta(days=1)

        return {
            "period": {"from": from_date, "to": to_date},
            "history": history,
        }
