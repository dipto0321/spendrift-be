#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# sync-db.sh
#
# Bidirectional incremental sync between the local Docker Postgres and a
# remote production Postgres. Backs up BOTH databases to /tmp before any
# mutation; restores both on any failure.
#
# Local settings come from .env (POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD).
# The prod URL must be supplied at runtime and is NEVER stored on disk:
#
#   PROD_URL='postgres://USER:PASS@host:5432/DBNAME' ./scripts/sync-db.sh
#
# Optional flags (passed through to sync_db.py):
#   --dry-run             Print what would change without writing
#   --status              Print current watermarks and exit
#   --reset-watermark     Reset sync_state to epoch (forces full re-scan)
#   --table NAME          Sync only the named table (repeatable)
#   --keep-dump           Keep pre-sync dumps in /tmp after success
#   --jobs N              Parallel pg_dump / pg_restore jobs (default 4)
#   --verbose             Print row-level diff details (sensitive cols masked)
# ----------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE" >&2
  exit 1
fi

# Handle --help up front so callers can invoke it without PROD_URL.
for arg in "$@"; do
  case "$arg" in
    -h|--help)
      sed -n '2,21p' "$0"; exit 0 ;;
  esac
done

# Pull only the keys we need from .env (avoids sourcing commented values
# or unrelated keys like STAGGING_DATABASE_URL into the environment).
get_env() {
  python3 - "$1" "$ENV_FILE" <<'PY'
import sys
key, env_path = sys.argv[1], sys.argv[2]
target = {key}
with open(env_path) as f:
    for raw in f:
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        if k in target:
            v = v.strip().strip('"').strip("'")
            print(f"__ENV__{k}={v}")
PY
}

for __env_key in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD; do
  __env_line="$(get_env "$__env_key" | tail -n 1)"
  if [[ -z "$__env_line" ]]; then
    echo "ERROR: $__env_key missing from $ENV_FILE" >&2
    exit 1
  fi
  __env_val="${__env_line#__ENV__${__env_key}=}"
  case "$__env_key" in
    POSTGRES_DB)       LOCAL_DB="$__env_val" ;;
    POSTGRES_USER)     LOCAL_USER="$__env_val" ;;
    POSTGRES_PASSWORD) LOCAL_PASS="$__env_val" ;;
  esac
  unset __env_line __env_val
done
unset __env_key

LOCAL_PORT="${LOCAL_PORT:-5432}"
LOCAL_URL="postgres://${LOCAL_USER}:${LOCAL_PASS}@localhost:${LOCAL_PORT}/${LOCAL_DB}"

if [[ -z "${PROD_URL:-}" ]]; then
  echo "ERROR: PROD_URL is required." >&2
  echo "Example:" >&2
  echo "  PROD_URL='postgres://USER:PASS@host:5432/DBNAME' $0 --dry-run" >&2
  exit 1
fi

if ! command -v pg_dump >/dev/null; then
  echo "ERROR: pg_dump not found. Install the Postgres client." >&2
  exit 1
fi

export LOCAL_DATABASE_URL="$LOCAL_URL"
export PROD_DATABASE_URL="$PROD_URL"

exec python3 "$SCRIPT_DIR/sync_db.py" "$@"
