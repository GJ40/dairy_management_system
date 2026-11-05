from __future__ import annotations

import re
import unittest

import httpx
from fastapi import FastAPI, Request

from app.core.request_context import (
    RequestContextMiddleware,
    sanitize_user_agent,
)

REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def build_app(*, trust_proxy: bool) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware, trust_proxy=trust_proxy)

    @app.get("/echo")
    async def echo(request: Request) -> dict[str, object]:
        context = request.state.request_context
        return {
            "request_id": context.request_id,
            "ip_address": context.ip_address,
            "user_agent": context.user_agent,
            "http_method": context.http_method,
            "path": context.path,
        }

    return app


class RequestContextTests(unittest.IsolatedAsyncioTestCase):
    async def _get(
        self,
        *,
        trust_proxy: bool = False,
        path: str = "/echo",
        headers: dict[str, str] | None = None,
    ) -> tuple[httpx.Response, dict[str, object]]:
        app = build_app(trust_proxy=trust_proxy)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get(path, headers=headers)
        return response, response.json()

    async def test_request_id_is_generated_and_echoed(self) -> None:
        response, body = await self._get()
        request_id = response.headers["x-request-id"]
        self.assertRegex(request_id, REQUEST_ID_PATTERN)
        self.assertEqual(body["request_id"], request_id)

    async def test_client_request_id_is_not_trusted(self) -> None:
        response, body = await self._get(
            headers={"X-Request-ID": "client-supplied"}
        )
        self.assertRegex(response.headers["x-request-id"], REQUEST_ID_PATTERN)
        self.assertNotEqual(body["request_id"], "client-supplied")

    async def test_forwarded_for_is_ignored_by_default(self) -> None:
        _, body = await self._get(headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(body["ip_address"], "127.0.0.1")

    async def test_trusted_proxy_uses_first_valid_forwarded_address(self) -> None:
        _, body = await self._get(
            trust_proxy=True,
            headers={"X-Forwarded-For": "garbage, 203.0.113.9, 10.0.0.1"},
        )
        self.assertEqual(body["ip_address"], "203.0.113.9")

    async def test_malformed_forwarded_for_falls_back_to_client(self) -> None:
        _, body = await self._get(
            trust_proxy=True,
            headers={"X-Forwarded-For": "not-an-ip, also-not-an-ip"},
        )
        self.assertEqual(body["ip_address"], "127.0.0.1")

    async def test_query_string_is_not_stored_in_path(self) -> None:
        _, body = await self._get(path="/echo?token=super-secret")
        self.assertEqual(body["path"], "/echo")
        self.assertNotIn("super-secret", str(body))

    async def test_user_agent_is_sanitized_and_capped(self) -> None:
        _, body = await self._get(headers={"User-Agent": "  dairy\u0000agent  "})
        self.assertEqual(body["user_agent"], "dairy agent")

    def test_sanitize_user_agent_strips_controls_and_caps(self) -> None:
        cleaned = sanitize_user_agent("bad\nagent\t" + "x" * 600)
        self.assertIsNotNone(cleaned)
        assert cleaned is not None
        self.assertEqual(len(cleaned), 512)
        self.assertNotIn("\n", cleaned)
        self.assertNotIn("\t", cleaned)
        self.assertTrue(cleaned.startswith("bad agent"))

    def test_sanitize_user_agent_returns_none_when_empty(self) -> None:
        self.assertIsNone(sanitize_user_agent(None))
        self.assertIsNone(sanitize_user_agent(" \t"))


if __name__ == "__main__":
    unittest.main()
