#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is not set; cannot run Alembic migrations." >&2
  exit 1
fi

alembic upgrade head
alembic current
