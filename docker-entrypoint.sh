#!/bin/sh
# ==============================================================================
# Backend container startup
#
# Order matters on a first `docker compose up`: MySQL reports itself healthy
# only after InnoDB is up, but a slow first-run initialisation can still accept
# the TCP connection a moment later than the app starts. Retrying the
# connectivity probe (instead of crashing on the first `alembic upgrade head`)
# removes the "Can't connect to MySQL server on 'db'" failure.
#
# Migrations are idempotent (see app/db/migration_helpers.py), so re-running
# this script on an existing volume is safe.
# ==============================================================================
set -e

DB_HOST_LABEL="${DB_HOST:-db}"
DB_PORT_LABEL="${DB_PORT:-3306}"
MAX_ATTEMPTS="${DB_WAIT_ATTEMPTS:-60}"
SLEEP_SECONDS="${DB_WAIT_INTERVAL:-2}"

echo "[entrypoint] Waiting for MySQL at ${DB_HOST_LABEL}:${DB_PORT_LABEL} ..."
attempt=1
while ! python - <<'PY'
import asyncio
import sys

from app.db.session import check_database, dispose_engine


async def main() -> int:
    ready = await check_database()
    await dispose_engine()
    return 0 if ready else 1


sys.exit(asyncio.run(main()))
PY
do
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "[entrypoint] Database unreachable after ${attempt} attempts; giving up." >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep "$SLEEP_SECONDS"
done
echo "[entrypoint] Database is ready."

if [ "${RUN_MIGRATIONS:-true}" != "false" ]; then
  echo "[entrypoint] Applying migrations: alembic upgrade head"
  alembic upgrade head
  echo "[entrypoint] Schema is at $(alembic current 2>/dev/null | tail -n 1)"
else
  echo "[entrypoint] RUN_MIGRATIONS=false - skipping migrations."
fi

if [ "${RUN_SEED:-true}" != "false" ]; then
  echo "[entrypoint] Ensuring base seed data (admin user, expense categories)"
  python -m app.seeders.base_seed
else
  echo "[entrypoint] RUN_SEED=false - skipping seed."
fi

echo "[entrypoint] Starting: $*"
exec "$@"
