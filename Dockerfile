# ==============================================================================
# Multi-stage Dockerfile for Dairy Management System FastAPI Backend
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build virtual environment with uv
# ------------------------------------------------------------------------------
FROM python:3.11-alpine AS builder

# Copy uv binary directly from official Astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install Alpine build dependencies required for compiling Python C-extensions
# (e.g., bcrypt, greenlet, asyncmy, reportlab)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    freetype-dev \
    libjpeg-turbo-dev \
    zlib-dev

WORKDIR /app

# Enable bytecode compilation and standalone copy mode for uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy dependency specifications first for optimal Docker layer caching
COPY pyproject.toml uv.lock ./

# Install project dependencies into /app/.venv without development dependencies
RUN uv sync --frozen --no-dev --no-install-project

# ------------------------------------------------------------------------------
# Stage 2: Minimal runtime image
# ------------------------------------------------------------------------------
FROM python:3.11-alpine AS runner

# Install runtime shared libraries required by ReportLab and timezone handling
RUN apk add --no-cache \
    freetype \
    libjpeg-turbo \
    libpng \
    tzdata

# Copy uv binary into runtime stage to support CLI execution of migrations and seeders
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Create a non-privileged user and group for runtime security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Copy pre-built virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Set environment variables for runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Kolkata \
    PORT=8000

# Copy application codebase, database migrations, and project configuration
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/
COPY pyproject.toml ./
COPY docker-entrypoint.sh ./

# Tolerate a CRLF checkout of the entrypoint (see .gitattributes): a stray \r
# would make the shell fail with "\r: not found" on the first line.
RUN sed -i 's/\r$//' docker-entrypoint.sh

# Ensure correct file ownership for the non-root application user
RUN chown -R appuser:appgroup /app

USER appuser

# Expose FastAPI application port
EXPOSE 8000

# Startup is owned by docker-entrypoint.sh: wait for MySQL, run the idempotent
# migrations, ensure the base seed data, then exec the command below.
CMD ["sh", "./docker-entrypoint.sh", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

