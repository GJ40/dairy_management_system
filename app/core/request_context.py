from __future__ import annotations

import ipaddress
import uuid
from dataclasses import dataclass

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

USER_AGENT_MAX_LENGTH = 512
PATH_MAX_LENGTH = 255
METHOD_MAX_LENGTH = 10


def sanitize_user_agent(value: str | None) -> str | None:
    """Strip control characters and cap the stored User-Agent."""
    if not value:
        return None
    cleaned = "".join(character if character.isprintable() else " " for character in value)
    cleaned = cleaned.strip()[:USER_AGENT_MAX_LENGTH].strip()
    return cleaned or None


def resolve_client_ip(request: Request, *, trust_proxy: bool) -> str | None:
    """Return a validated client address, never a raw forwarding chain."""
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            for candidate in forwarded.split(","):
                try:
                    return str(ipaddress.ip_address(candidate.strip()))
                except ValueError:
                    continue

    if request.client is not None:
        try:
            return str(ipaddress.ip_address(request.client.host))
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    ip_address: str | None
    user_agent: str | None
    http_method: str
    path: str

    @classmethod
    def from_request(cls, request: Request, *, trust_proxy: bool) -> "RequestContext":
        return cls(
            request_id=uuid.uuid4().hex,
            ip_address=resolve_client_ip(request, trust_proxy=trust_proxy),
            user_agent=sanitize_user_agent(request.headers.get("user-agent")),
            http_method=request.method[:METHOD_MAX_LENGTH].upper(),
            path=request.url.path[:PATH_MAX_LENGTH],
        )


def get_request_context(request: Request) -> RequestContext:
    """Return the context installed by middleware, or build a safe fallback."""
    context = getattr(request.state, "request_context", None)
    if isinstance(context, RequestContext):
        return context
    return RequestContext.from_request(request, trust_proxy=settings.trust_proxy)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, trust_proxy: bool = False) -> None:
        self.app = app
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        context = RequestContext.from_request(request, trust_proxy=self.trust_proxy)
        request.state.request_context = context
        request.state.request_id = context.request_id
        request.state.client_ip = context.ip_address

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = context.request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)
