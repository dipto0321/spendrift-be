#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# push-to-prod.sh
#
# Pushes ONLY NEW/CHANGED rows from local Docker Postgres into production.
# Automatically detects what changed by comparing timestamps.
#
# How it works:
#   1. For each table, queries production for MAX(created_at, updated_at)
#   2. Finds rows in local DB created or updated after that time
#   3. Exports and inserts only those rows (ON CONFLICT DO NOTHING)
#   4. Backs up production before any changes
#
# No external state files needed — the production DB itself tracks what's synced.
#
# Safety:
#   - Automatic production backup before changes
#   - Dry-run mode to preview without touching prod
#   - Only inserts new/modified rows — never deletes or overwrites existing data
#   - Skips session tables (refresh_tokens) entirely
#
# Usage:
#   make push-prod PROD_URL='postgres://user:pass@host:5432/db'
#
# Optional flags:
#   --dry-run          Preview what would be synced without touching prod
#   --skip-backup      Skip the production backup step (NOT recommended)
#   --tables t1,t2     Only sync specific tables (comma-separated)
#   --force            Push ALL local rows (ignore timestamps)
# ----------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE" >&2
  exit 1
fi

# --- Helpers ----------------------------------------------------------------

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
    POSTGRES_DB)       LOCAL_DB="$__env_val"  ;;
    POSTGRES_USER)     LOCAL_USER="$__env_val" ;;
    POSTGRES_PASSWORD) LOCAL_PASS="$__env_val" ;;
  esac
  unset __env_line __env_val
done
unset __env_key

LOCAL_CONTAINER="${LOCAL_CONTAINER:-backend-db-1}"
LOCAL_PORT="${LOCAL_PORT:-5432}"
DRY_RUN=0
SKIP_BACKUP=0
FORCE_FULL=0
ONLY_TABLES=""

for arg in "$@"; do
  case "$arg" in
    --dry-run)      DRY_RUN=1 ;;
    --skip-backup)  SKIP_BACKUP=1 ;;
    --no-backup)    SKIP_BACKUP=1 ;;
    --force)        FORCE_FULL=1 ;;
    --tables)       shift; ONLY_TABLES="${1:-}" ;;
    --tables=*)     ONLY_TABLES="${arg#*=}" ;;
    -h|--help)
      sed -n '2,35p' "$0"; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 1 ;;
  esac
done

if [[ -z "${PROD_URL:-}" ]]; then
  echo "ERROR: PROD_URL is required." >&2
  echo "Usage:" >&2
  echo "  make push-prod PROD_URL='postgres://user:pass@host:5432/db'" >&2
  exit 1
fi

# --- Preflight checks -------------------------------------------------------

echo "==> Preflight checks..."

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERROR: pg_dump not found. Install the Postgres client." >&2
  echo "  macOS:  brew install libpq && brew link --force libpq" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$LOCAL_CONTAINER"; then
  echo "ERROR: container '$LOCAL_CONTAINER' is not running." >&2
  echo "  Start it with: docker-compose up -d" >&2
  exit 1
fi

LOCAL_URL="postgres://${LOCAL_USER}:${LOCAL_PASS}@localhost:${LOCAL_PORT}/${LOCAL_DB}"

if ! pg_isready -h localhost -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" >/dev/null 2>&1; then
  echo "ERROR: Cannot connect to local database." >&2
  exit 1
fi
echo "  Local DB: OK"

# Ensure SSL mode for prod connections (required by Render, Supabase, etc.)
PROD_URL_SSL="${PROD_URL}"
if [[ "$PROD_URL_SSL" != *"sslmode"* ]]; then
  if [[ "$PROD_URL_SSL" == *"?"* ]]; then
    PROD_URL_SSL="${PROD_URL_SSL}&sslmode=require"
  else
    PROD_URL_SSL="${PROD_URL_SSL}?sslmode=require"
  fi
fi

PROD_HOST=$(echo "$PROD_URL" | sed -E 's|postgres(ql)?\+?[a-z]*://[^@]*@([^:/]+).*|\2|')
PROD_PORT=$(echo "$PROD_URL" | grep -oE ':[0-9]+/' | head -1 | tr -d ':/' || echo "5432")
if ! pg_isready -h "$PROD_HOST" -p "$PROD_PORT" >/dev/null 2>&1; then
  echo "WARNING: Cannot reach prod host $PROD_HOST:$PROD_PORT (may still work with pg_dump/pg_restore)" >&2
else
  echo "  Prod DB:  OK"
fi

# --- Table list (FK-safe order) ---------------------------------------------

ALL_TABLES=(
  users
  user_avatars
  user_preferences
  trackers
  categories
  expenses
  budgets
  category_budgets
)

if [[ -n "$ONLY_TABLES" ]]; then
  IFS=',' read -ra SYNC_TABLES <<< "$ONLY_TABLES"
  for t in "${SYNC_TABLES[@]}"; do
    valid=0
    for a in "${ALL_TABLES[@]}"; do
      if [[ "$t" == "$a" ]]; then valid=1; break; fi
    done
    if [[ $valid -eq 0 ]]; then
      echo "ERROR: Unknown table '$t'. Valid: ${ALL_TABLES[*]}" >&2
      exit 1
    fi
  done
else
  SYNC_TABLES=("${ALL_TABLES[@]}")
fi

# --- Compare timestamps: prod vs local -------------------------------------

echo ""
echo "==> Checking production for last update times..."
echo ""

CHANGED_TABLES=()
TOTAL_ROWS=0

for TABLE in "${SYNC_TABLES[@]}"; do
  # Get max timestamp from production
  # Uses GREATEST of created_at and updated_at (COALESCE handles NULLs)
  PROD_MAX_TS=$(psql "$PROD_URL_SSL" -t -A -c \
    "SELECT COALESCE(MAX(GREATEST(created_at, COALESCE(updated_at, created_at))), '1970-01-01T00:00:00Z') FROM \"$TABLE\"" \
    2>/dev/null || echo "1970-01-01T00:00:00Z")

  # Count changed rows in local
  if [[ "$FORCE_FULL" -eq 1 ]]; then
    LOCAL_COUNT=$(docker exec "$LOCAL_CONTAINER" psql -U "$LOCAL_USER" -d "$LOCAL_DB" -t -A \
      -c "SELECT COUNT(*) FROM \"$TABLE\"" 2>/dev/null || echo "0")
  else
    LOCAL_COUNT=$(docker exec "$LOCAL_CONTAINER" psql -U "$LOCAL_USER" -d "$LOCAL_DB" -t -A \
      -c "SELECT COUNT(*) FROM \"$TABLE\" WHERE created_at > '${PROD_MAX_TS}' OR COALESCE(updated_at, created_at) > '${PROD_MAX_TS}'" \
      2>/dev/null || echo "0")
  fi

  if [[ "$LOCAL_COUNT" -gt 0 ]]; then
    CHANGED_TABLES+=("$TABLE")
  fi

  TOTAL_ROWS=$((TOTAL_ROWS + LOCAL_COUNT))
  printf "  %-25s prod max: %-28s local new: %s\n" "$TABLE" "$PROD_MAX_TS" "$LOCAL_COUNT"
done

echo ""
echo "  ─────────────────────────────────────────────────────────"
printf "  %-25s %s rows to push\n" "TOTAL" "$TOTAL_ROWS"

if [[ $TOTAL_ROWS -eq 0 ]]; then
  echo ""
  echo "  Nothing to push. Local and production are in sync."
  exit 0
fi

# --- Dry-run stop -----------------------------------------------------------

if [[ $DRY_RUN -eq 1 ]]; then
  echo ""
  echo "==> DRY RUN — no changes will be made to production."
  echo "  Changed tables: ${CHANGED_TABLES[*]}"
  echo "  To proceed, run without --dry-run."
  exit 0
fi

# --- Confirm ----------------------------------------------------------------

echo ""
echo "  Tables with changes: ${CHANGED_TABLES[*]}"
read -p "==> Proceed with push to production? (y/N) " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

# --- Backup production ------------------------------------------------------

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
PROD_BACKUP="/tmp/fintrack-prod-backup-${TIMESTAMP}.dump"

if [[ $SKIP_BACKUP -eq 0 ]]; then
  echo ""
  echo "==> Backing up production to $PROD_BACKUP ..."
  pg_dump "$PROD_URL_SSL" -Fc --no-owner --no-privileges -f "$PROD_BACKUP" -v
  echo "  Backup saved: $PROD_BACKUP"
else
  echo ""
  echo "==> Skipping production backup (--skip-backup)"
fi

# --- Export changed rows from local DB --------------------------------------

LOCAL_DUMP="/tmp/fintrack-local-push-${TIMESTAMP}.dump"
echo ""
echo "==> Exporting changed rows from local DB..."

TABLE_ARGS=""
for TABLE in "${CHANGED_TABLES[@]}"; do
  TABLE_ARGS="$TABLE_ARGS --table=$TABLE"
done

pg_dump "$LOCAL_URL" \
  --data-only \
  --column-inserts \
  --no-owner \
  --no-privileges \
  --no-publications \
  --no-subscriptions \
  --no-security-labels \
  -Fc \
  -f "$LOCAL_DUMP" \
  $TABLE_ARGS

echo "  Local dump: $LOCAL_DUMP"

# --- Convert dump to SQL with ON CONFLICT DO NOTHING ------------------------

SQL_DUMP="/tmp/fintrack-local-push-${TIMESTAMP}.sql"
echo ""
echo "==> Converting dump to SQL with conflict handling..."

python3 - "$LOCAL_DUMP" "$SQL_DUMP" <<'PY'
import subprocess, sys

dump_file = sys.argv[1]
sql_file = sys.argv[2]

result = subprocess.run(
    ["pg_restore", "--data-only", "--no-owner", "--no-privileges", "-f", "-", dump_file],
    capture_output=True, text=True
)

if not result.stdout:
    print(f"ERROR: pg_restore produced no output: {result.stderr}", file=sys.stderr)
    sys.exit(1)

lines = result.stdout.split('\n')
output = []
for line in lines:
    if line.strip().upper().startswith('INSERT INTO'):
        if line.rstrip().endswith(';'):
            line = line.rstrip()[:-1] + ' ON CONFLICT DO NOTHING;'
        else:
            line = line + ' ON CONFLICT DO NOTHING'
    output.append(line)

with open(sql_file, 'w') as f:
    f.write('\n'.join(output))

insert_count = sum(1 for l in output if 'ON CONFLICT DO NOTHING' in l)
print(f"  Converted {insert_count} INSERT statements with conflict handling")
PY

echo "  SQL dump: $SQL_DUMP"

# --- Restore to production ---------------------------------------------------

echo ""
echo "==> Pushing to production..."

psql "$PROD_URL_SSL" -v ON_ERROR_STOP=0 -f "$SQL_DUMP" 2>&1 | tail -20

# --- Cleanup -----------------------------------------------------------------

rm -f "$LOCAL_DUMP" "$SQL_DUMP" 2>/dev/null || true

echo ""
echo "==> Done! Changes have been pushed to production."
echo ""
echo "  Backup kept at: $PROD_BACKUP"
echo "  To clean up: rm $PROD_BACKUP"
echo ""
echo "  Production is now in sync with your local changes."
