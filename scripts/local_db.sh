#!/usr/bin/env bash
# Create the local application database when it does not exist.
# Works with a system Postgres, Homebrew Postgres, or the workspace build in
# ../../.toolchain/pg16/bin (set PG_BIN).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_BIN="${PG_BIN:-}"
export PATH="$PG_BIN:$PATH"

DSN="${DATABASE_URL:-postgresql://127.0.0.1:55432/rag_api}"
DB_NAME="${DSN##*/}"
DB_NAME="${DB_NAME%%\?*}"
HOSTPORT="${DSN#postgresql://}"
HOSTPORT="${HOSTPORT%%/*}"
HOST="${HOSTPORT%%:*}"
PORT="${HOSTPORT##*:}"
[ "$HOST" = "localhost" ] && HOST=127.0.0.1

command -v psql >/dev/null || {
  echo "psql not found. Install postgresql@16 and pgvector, then set PG_BIN." >&2
  exit 1
}

if ! psql -h "$HOST" -p "$PORT" -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
  createdb -h "$HOST" -p "$PORT" "$DB_NAME"
  echo "created database $DB_NAME"
else
  echo "database $DB_NAME exists"
fi

psql -h "$HOST" -p "$PORT" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
echo "pgvector ready in $DB_NAME"
