#!/bin/sh
set -eu

wait_for_postgres() {
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "DATABASE_URL is empty; skip PostgreSQL wait."
    return 0
  fi
  python - <<'PY'
import os
import sys
import time
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL", "")
last_error = None
for _ in range(int(os.environ.get("POSTGRES_WAIT_RETRIES", "60"))):
    try:
        engine = create_engine(url, pool_pre_ping=True, future=True)
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        print("PostgreSQL is ready.")
        sys.exit(0)
    except Exception as exc:
        last_error = exc
        time.sleep(2)
print(f"PostgreSQL is not ready: {type(last_error).__name__}: {last_error}", file=sys.stderr)
sys.exit(1)
PY
}

wait_for_redis() {
  if [ -z "${REDIS_URL:-}" ]; then
    echo "REDIS_URL is empty; skip Redis wait."
    return 0
  fi
  python - <<'PY'
import os
import sys
import time

import redis

url = os.environ.get("REDIS_URL", "")
last_error = None
for _ in range(int(os.environ.get("REDIS_WAIT_RETRIES", "60"))):
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        if client.ping():
            print("Redis is ready.")
            sys.exit(0)
    except Exception as exc:
        last_error = exc
        time.sleep(2)
print(f"Redis is not ready: {type(last_error).__name__}: {last_error}", file=sys.stderr)
sys.exit(1)
PY
}

wait_for_postgres
wait_for_redis

if [ "${AUTO_MIGRATE:-1}" = "1" ] && [ -n "${DATABASE_URL:-}" ]; then
  echo "Running Alembic migrations..."
  alembic upgrade head
else
  echo "AUTO_MIGRATE is disabled or DATABASE_URL is empty; skip Alembic migration."
fi

exec "$@"
