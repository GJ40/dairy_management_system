from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.main import app


class MiddlewareApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def _health(self, connected: bool = True) -> httpx.Response:
        with patch(
            "app.db.session.check_database",
            new=AsyncMock(return_value=connected),
        ):
            return await self.client.get("/health")

    async def test_unknown_route_error_envelope(self) -> None:
        response = await self.client.get("/api/v1/missing?x=1")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Cannot GET /api/v1/missing?x=1",
                }
            },
        )

    async def test_wrong_method_maps_to_404(self) -> None:
        response = await self.client.post("/health")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")
        self.assertEqual(response.json()["error"]["message"], "Cannot POST /health")

    async def test_cors_preflight(self) -> None:
        origin = "http://localhost:5173"
        response = await self.client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], origin)
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")

    async def test_security_headers(self) -> None:
        response = await self._health(True)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "SAMEORIGIN")

    async def test_body_limit(self) -> None:
        response = await self.client.post(
            "/health",
            content=b"x" * (1024 * 1024 + 1),
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": "request entity too large",
                }
            },
        )

    async def test_chunked_body_limit_without_content_length(self) -> None:
        async def chunks():
            for _ in range(17):
                yield b"x" * 65536

        response = await self.client.post("/health", content=chunks())
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "PAYLOAD_TOO_LARGE")

    async def test_chunked_body_under_limit_is_replayed(self) -> None:
        async def chunks():
            yield b'{"hello":'
            yield b'"world"}'

        response = await self.client.post("/health", content=chunks())
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
