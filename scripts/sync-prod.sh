#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# sync-prod.sh
#
# Dumps the production Postgres database and restores it into the local Docker
# Postgres container, fully replacing the local DB.
#
# Local settings are sourced from .env (DB name / user / password / container).
# The prod URL must be provided at runtime and is NEVER stored on disk:
#
#   PROD_URL='postgres://USER:PASS@host:5432/DBNAME' ./scripts/sync-prod.sh
#
# Optional flags:
#   --keep-dump     Keep the dump file after restore (default: delete it)
#   --jobs N        Parallel jobs for pg_dump/pg_restore (default: 4)
#   --dry-run       Print commands without running them
# ----------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE" >&2
  exit 1
fi

# Load only the keys we need from .env (avoid sourcing the whole file blindly,
# which would also pick up commented values, STAGGING_DATABASE_URL, etc).
# Output format: key=value per line, values are NOT quoted (callers decide).
get_env() {
  python3 - "$1" "$ENV_FILE" <<'PY'
import sys, os
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
            # Use a sentinel prefix so callers can prefix the local var name
            # without ambiguity. Format: __ENV__<KEY>=<VALUE>
            print(f"__ENV__{k}={v}")
PY
}

# Read each value into a temporary __ENV__ prefixed name, then assign to the
# LOCAL_* alias only if the value is non-empty. This avoids the previous bug
# where sed-prefixing POSTGRES_DB=fintrack produced LOCAL_DB=POSTGRES_DB=...
# which bash parsed as nested assignment.
for __env_key in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD; do
  __env_line="$(get_env "$__env_key" | tail -n 1)"
  if [[ -z "$__env_line" ]]; then
    echo "ERROR: $__env_key missing from $ENV_FILE" >&2
    exit 1
  fi
  __env_val="${__env_line#__ENV__${__env_key}=}"
  case "$__env_key" in
    POSTGRES_DB)       LOCAL_DB="$__env_val"  ;;
    POSTGRES_USER)     LOCAL_USER="$__env_val" ;;
    POSTGRES_PASSWORD) LOCAL_PASS="$__env_val" ;;
  esac
  unset __env_line __env_val
done
unset __env_key

LOCAL_CONTAINER="${LOCAL_CONTAINER:-backend-db-1}"
LOCAL_PORT="${LOCAL_PORT:-5432}"
JOBS=4
KEEP_DUMP=0
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --keep-dump) KEEP_DUMP=1 ;;
    --jobs)      shift; JOBS="${1:-4}" ;;
    --jobs=*)    JOBS="${arg#*=}" ;;
    --dry-run)   DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 1 ;;
  esac
done

if [[ -z "${PROD_URL:-}" ]]; then
  echo "ERROR: PROD_URL is required." >&2
  echo "Example:" >&2
  echo "  PROD_URL='postgres://user:pass@prod-host:5432/db' $0" >&2
  exit 1
fi

if ! command -v pg_dump >/dev/null; then
  echo "ERROR: pg_dump not found. Install the Postgres client." >&2
  echo "  macOS:  brew install libpq && brew link --force libpq" >&2
  echo "  Ubuntu: sudo apt install postgresql-client" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$LOCAL_CONTAINER"; then
  echo "ERROR: container '$LOCAL_CONTAINER' is not running." >&2
  exit 1
fi

LOCAL_URL="postgres://${LOCAL_USER}:${LOCAL_PASS}@localhost:${LOCAL_PORT}/${LOCAL_DB}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DUMP="/tmp/fintrack-prod-${TIMESTAMP}.dump"

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '\033[2m%s\033[0m\n' "$*"
  else
    "$@"
  fi
}

# Always clean up the dump on exit — success or failure — unless --keep-dump.
# This guards against the script bailing out mid-restore and leaving the dump
# file behind (which is exactly what happened on the previous failed run).
cleanup_dump() {
  if [[ ${KEEP_DUMP:-0} -eq 1 ]]; then
    return
  fi
  if [[ -n "${DUMP:-}" ]]; then
    if [[ -d "$DUMP" ]]; then
      rm -rf "$DUMP" 2>/dev/null || true
    elif [[ -e "$DUMP" ]]; then
      rm -f "$DUMP" 2>/dev/null || true
    fi
  fi
}
trap cleanup_dump EXIT

# Use directory format (-Fd) so we can parallel-dump with -j. Job count of 1
# falls back to a single-threaded custom-format dump (the only mode pg_dump
# supports with -Fc).
if [[ "$JOBS" -gt 1 ]]; then
  DUMP_DIR="/tmp/fintrack-prod-${TIMESTAMP}"
  DUMP="$DUMP_DIR"
  echo "==> Dumping production to $DUMP_DIR (directory, $JOBS jobs)"
  run pg_dump "$PROD_URL" -Fd -j "$JOBS" -f "$DUMP_DIR" --no-owner --no-privileges -v
else
  echo "==> Dumping production to $DUMP (custom, single-threaded)"
  run pg_dump "$PROD_URL" -Fc -f "$DUMP" --no-owner --no-privileges -v
fi

echo "==> Terminating connections on local DB '${LOCAL_DB}'"
run docker exec -e PGPASSWORD="$LOCAL_PASS" "$LOCAL_CONTAINER" \
  psql -U "$LOCAL_USER" -d postgres -v ON_ERROR_STOP=1 -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${LOCAL_DB}' AND pid <> pg_backend_pid();"

echo "==> Recreating local DB '${LOCAL_DB}'"
run docker exec "$LOCAL_CONTAINER" dropdb -U "$LOCAL_USER" "$LOCAL_DB" --if-exists
run docker exec "$LOCAL_CONTAINER" createdb -U "$LOCAL_USER" "$LOCAL_DB"

echo "==> Restoring dump into local DB"
# pg_restore auto-detects format: -Fc files pass directly, -Fd directories pass directly.
run pg_restore -d "$LOCAL_URL" --no-owner --no-privileges -j "$JOBS" -v "$DUMP"

echo "==> Done. Local DB '${LOCAL_DB}' is now in sync with prod."
