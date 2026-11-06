from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.request_context import RequestContextMiddleware
from app.db.session import dispose_engine
from app.routers import (
    auth,
    buffaloes,
    customer_auth,
    customer_orders,
    customer_portal,
    customer_portal_accounts,
    customer_queries,
    customers,
    delete,
    docs,
    email_settings,
    expenses,
    health,
    invoices,
    production,
    reports,
    sales,
    security_audit,
    stock,
    users,
    wastage,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Dairy Management System API",
        version="1.0.0",
        description="FastAPI migration of the Dairy Management System backend.",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/docs/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.body_limit_bytes)
    app.add_middleware(SecurityHeadersMiddleware)

    cors_origins = settings.cors_origin_list
    is_development = settings.node_env.strip().lower() == "development"
    # `Access-Control-Allow-Origin: *` is rejected by the browser on every
    # request that carries credentials, and every frontend call sets
    # `withCredentials`. A wildcard is therefore never forwarded to the
    # middleware: it becomes "mirror whatever Origin asked" instead, which is
    # the only form the browser accepts. Any other origin (development, or a
    # configured `*`) is handled the same way for the same reason, so staging
    # and production must still list their origins in CORS_ORIGINS.
    allowed_origins = [origin for origin in cors_origins if origin != "*"]
    allow_any_origin = "*" in cors_origins or is_development
    if "*" in cors_origins and not is_development:
        logger.warning(
            "CORS_ORIGINS contains '*'; any origin can call the API with "
            "credentials. List the real frontend origins instead."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=".*" if allow_any_origin else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        RequestContextMiddleware,
        trust_proxy=settings.trust_proxy,
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(docs.router)
    app.include_router(email_settings.router, prefix=settings.api_v1_prefix)
    app.include_router(auth.router, prefix=settings.api_v1_prefix)
    app.include_router(users.router, prefix=settings.api_v1_prefix)
    app.include_router(buffaloes.router, prefix=settings.api_v1_prefix)
    app.include_router(production.router, prefix=settings.api_v1_prefix)
    app.include_router(stock.router, prefix=settings.api_v1_prefix)
    app.include_router(wastage.router, prefix=settings.api_v1_prefix)
    app.include_router(customers.router, prefix=settings.api_v1_prefix)
    app.include_router(sales.router, prefix=settings.api_v1_prefix)
    app.include_router(invoices.router, prefix=settings.api_v1_prefix)
    app.include_router(delete.router, prefix=settings.api_v1_prefix)
    app.include_router(expenses.router, prefix=settings.api_v1_prefix)
    app.include_router(expenses.alias_router, prefix=settings.api_v1_prefix)
    app.include_router(reports.router, prefix=settings.api_v1_prefix)
    app.include_router(security_audit.router, prefix=settings.api_v1_prefix)
    app.include_router(customer_auth.router, prefix=settings.api_v1_prefix)
    app.include_router(customer_orders.router, prefix=settings.api_v1_prefix)
    app.include_router(customer_portal.router, prefix=settings.api_v1_prefix)
    app.include_router(customer_queries.router, prefix=settings.api_v1_prefix)
    app.include_router(
        customer_portal_accounts.router,
        prefix=settings.api_v1_prefix,
    )

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=False)
