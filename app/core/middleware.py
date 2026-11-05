from __future__ import annotations

import logging
import time
from urllib.parse import parse_qsl, urlencode

from fastapi import status
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.request")

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "SAMEORIGIN",
    "x-dns-prefetch-control": "off",
    "x-download-options": "noopen",
    "x-permitted-cross-domain-policies": "none",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "origin-agent-cluster": "?1",
    "x-xss-protection": "0",
}

# Query parameters that carry credentials. Reset/activation links put a live
# token in the URL, so logging the raw query string would write it to the log
# file for the whole lifetime of the link.
SENSITIVE_QUERY_MARKERS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
)
REDACTED = "REDACTED"


def _redact_query_string(query: str) -> str:
    """Rebuild a query string with credential-like values masked."""
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    if not pairs:
        return ""
    return urlencode(
        [
            (
                key,
                REDACTED
                if any(marker in key.lower() for marker in SENSITIVE_QUERY_MARKERS)
                else value,
            )
            for key, value in pairs
        ]
    )


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": "request entity too large",
                }
            },
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
            except ValueError:
                length = None
            if length is not None and length > self.max_bytes:
                await self._too_large(scope, receive, send)
                return

        # A declared Content-Length can be absent (chunked bodies) or lie, so
        # the actual stream is capped too. The body is buffered up to the limit
        # and then replayed to the app; every route here accepts small JSON.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._too_large(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {
                    "type": "http.request",
                    "body": bytes(body),
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        except Exception:
            logger.exception(
                "Unhandled exception during %s %s",
                scope.get("method"),
                scope.get("path"),
            )
            raise
        finally:
            path = scope.get("path", "")
            query = _redact_query_string(
                scope.get("query_string", b"").decode("latin-1")
            )
            if query:
                path = f"{path}?{query}"
            duration_ms = (time.perf_counter() - started) * 1000
            request_id = scope.get("state", {}).get("request_id", "-")
            logger.info(
                "%s %s %s %.3f ms rid=%s",
                scope.get("method"),
                path,
                status_code,
                duration_ms,
                request_id,
            )
