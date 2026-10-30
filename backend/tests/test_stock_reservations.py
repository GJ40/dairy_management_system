from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal

import app.models  # noqa: F401
from app.services.stock_service import StockService

TODAY = date(2026, 10, 30)


class FakeStockRepository:
    def __init__(
        self,
        produced: dict[date, Decimal],
        future_dates: list[date] | None = None,
        sold: dict[date, Decimal] | None = None,
    ) -> None:
        self.produced = produced
        self.future_dates = list(future_dates or [])
        self.sold = sold or {}

    async def sum_prior_quantities(self, day: date):
        return (
            sum(
                (value for key, value in self.produced.items() if key < day),
                Decimal("0"),
            ),
            sum(
                (value for key, value in self.sold.items() if key < day),
                Decimal("0"),
            ),
            Decimal("0"),
        )

    async def sum_current_quantities(self, day: date):
        return (
            self.produced.get(day, Decimal("0")),
            self.sold.get(day, Decimal("0")),
            Decimal("0"),
        )

    async def get_future_active_dates(self, day: date):
        return [value for value in self.future_dates if value > day]


class ReservationAvailabilityTests(unittest.IsolatedAsyncioTestCase):
    def _service(self, **kwargs) -> StockService:
        return StockService(FakeStockRepository(**kwargs))  # type: ignore[arg-type]

    async def test_approved_reservations_reduce_availability(self) -> None:
        service = self._service(produced={TODAY: Decimal("100.00")})
        reserved = {TODAY: Decimal("95.00")}

        async def lookup(day: date) -> Decimal:
            return reserved.get(day, Decimal("0"))

        await service.assert_available_stock(
            TODAY.isoformat(),
            Decimal("5.00"),
            reserved_lookup=lookup,
        )

        with self.assertRaises(Exception) as caught:
            await service.assert_available_stock(
                TODAY.isoformat(),
                Decimal("10.00"),
                reserved_lookup=lookup,
            )
        self.assertEqual(caught.exception.detail["code"], "STOCK_INSUFFICIENT")
        self.assertIn("5.00", caught.exception.detail["message"])

    async def test_forward_propagation_checks_later_active_dates(self) -> None:
        tomorrow = TODAY + timedelta(days=1)
        service = self._service(
            produced={TODAY: Decimal("100.00"), tomorrow: Decimal("5.00")},
            future_dates=[tomorrow],
            sold={tomorrow: Decimal("100.00")},
        )

        with self.assertRaises(Exception) as caught:
            await service.assert_available_stock(
                TODAY.isoformat(),
                Decimal("10.00"),
            )
        self.assertEqual(caught.exception.detail["code"], "STOCK_INSUFFICIENT")
        self.assertIn(tomorrow.isoformat(), caught.exception.detail["message"])

    async def test_later_date_reservations_also_reduce_availability(self) -> None:
        tomorrow = TODAY + timedelta(days=1)
        service = self._service(
            produced={TODAY: Decimal("100.00"), tomorrow: Decimal("20.00")},
            future_dates=[tomorrow],
            sold={tomorrow: Decimal("100.00")},
        )

        async def lookup(day: date) -> Decimal:
            return Decimal("15.00") if day == tomorrow else Decimal("0")

        with self.assertRaises(Exception) as caught:
            await service.assert_available_stock(
                TODAY.isoformat(),
                Decimal("10.00"),
                reserved_lookup=lookup,
            )
        self.assertEqual(caught.exception.detail["code"], "STOCK_INSUFFICIENT")
        self.assertIn("5.00", caught.exception.detail["message"])

    async def test_availability_without_reservations_is_unchanged(self) -> None:
        service = self._service(produced={TODAY: Decimal("100.00")})

        stock = await service.assert_available_stock(
            TODAY.isoformat(),
            Decimal("100.00"),
        )
        self.assertEqual(stock["closing_stock"], "100.00")

        with self.assertRaises(Exception) as caught:
            await service.assert_available_stock(
                TODAY.isoformat(),
                Decimal("100.01"),
            )
        self.assertEqual(caught.exception.detail["code"], "STOCK_INSUFFICIENT")
