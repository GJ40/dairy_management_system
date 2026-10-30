from __future__ import annotations

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
    expenses,
    health,
    invoices,
    production,
    reports,
    sales,
    stock,
    users,
    wastage,
)


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=None if settings.is_production else ".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(docs.router)
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
