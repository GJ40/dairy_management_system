from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.main import app


class HealthAndDocsApiTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_health_connected(self) -> None:
        response = await self._health(True)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "connected")
        self.assertIsInstance(body["uptime_seconds"], int)
        self.assertGreaterEqual(body["uptime_seconds"], 0)
        self.assertIsInstance(body["environment"], str)
        self.assertIsInstance(body["timezone"], str)
        self.assertTrue(body["timestamp"].endswith("Z"))

    async def test_health_disconnected_still_200(self) -> None:
        response = await self._health(False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "disconnected")

    async def test_api_v1_health(self) -> None:
        with patch(
            "app.db.session.check_database",
            new=AsyncMock(return_value=True),
        ):
            response = await self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    async def test_docs_routes(self) -> None:
        for path in ("/docs", "/api/v1/docs"):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
                self.assertIn("swagger-ui", response.text)
                self.assertIn("/api/v1/docs/openapi.json", response.text)

    async def test_openapi_spec(self) -> None:
        response = await self.client.get("/api/v1/docs/openapi.json")
        self.assertEqual(response.status_code, 200)
        spec = response.json()
        self.assertIn("/health", spec["paths"])
        self.assertIn("/api/v1/health", spec["paths"])

    async def test_openapi_documents_bearer_auth(self) -> None:
        spec = (
            await self.client.get("/api/v1/docs/openapi.json")
        ).json()
        scheme = spec["components"]["securitySchemes"]["BearerAuth"]
        self.assertEqual(scheme["type"], "http")
        self.assertEqual(scheme["scheme"], "bearer")

        protected = spec["paths"]["/api/v1/customers"]["get"]
        self.assertEqual(protected["security"], [{"BearerAuth": []}])

        public = spec["paths"]["/health"]["get"]
        self.assertNotIn("security", public)


if __name__ == "__main__":
    unittest.main()
