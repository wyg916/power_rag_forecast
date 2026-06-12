#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required for database initialization." >&2
  exit 1
fi

python - <<'PY'
import os
import sys
import time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
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

alembic upgrade head
