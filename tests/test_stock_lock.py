from __future__ import annotations

import unittest
from typing import Any

from app.services.stock_lock import StockLockService


class FakeConnection:
    def __init__(self, acquire_result: int = 1) -> None:
        self.acquire_result = acquire_result
        self.acquires: list[tuple[str, dict[str, Any]]] = []
        self.releases: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def scalar(self, statement: Any, params: dict[str, Any] | None = None):
        self.acquires.append((str(statement), dict(params or {})))
        return self.acquire_result

    async def execute(self, statement: Any, params: dict[str, Any] | None = None):
        self.releases.append((str(statement), dict(params or {})))
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.connects = 0

    def connect(self) -> FakeConnection:
        self.connects += 1
        return self.connection


class StockLockServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_acquires_and_releases_around_the_block(self) -> None:
        connection = FakeConnection()
        service = StockLockService(FakeEngine(connection))  # type: ignore[arg-type]

        entered = False
        async with service.lock():
            entered = True
            self.assertEqual(connection.releases, [])

        self.assertTrue(entered)
        self.assertEqual(len(connection.acquires), 1)
        self.assertIn("GET_LOCK", connection.acquires[0][0])
        self.assertEqual(
            connection.acquires[0][1],
            {"name": "dairy:stock", "timeout": 10},
        )
        self.assertEqual(len(connection.releases), 1)
        self.assertIn("RELEASE_LOCK", connection.releases[0][0])
        self.assertEqual(connection.releases[0][1], {"name": "dairy:stock"})

    async def test_contention_raises_busy_and_does_not_release(self) -> None:
        connection = FakeConnection(acquire_result=0)
        service = StockLockService(FakeEngine(connection))  # type: ignore[arg-type]

        entered = False
        with self.assertRaises(Exception) as caught:
            async with service.lock():
                entered = True
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail["code"], "STOCK_BUSY")
        self.assertFalse(entered)
        self.assertEqual(connection.releases, [])

    async def test_releases_when_the_body_raises(self) -> None:
        connection = FakeConnection()
        service = StockLockService(FakeEngine(connection))  # type: ignore[arg-type]

        with self.assertRaises(RuntimeError):
            async with service.lock():
                raise RuntimeError("boom")

        self.assertEqual(len(connection.releases), 1)
        self.assertIn("RELEASE_LOCK", connection.releases[0][0])

    async def test_custom_name_and_timeout_are_forwarded(self) -> None:
        connection = FakeConnection()
        service = StockLockService(
            FakeEngine(connection),  # type: ignore[arg-type]
            lock_name="dairy:test",
            timeout_seconds=3,
        )

        async with service.lock():
            pass

        self.assertEqual(
            connection.acquires[0][1],
            {"name": "dairy:test", "timeout": 3},
        )
        self.assertEqual(connection.releases[0][1], {"name": "dairy:test"})


if __name__ == "__main__":
    unittest.main()
