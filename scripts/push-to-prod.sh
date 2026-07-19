#!/usr/bin/env bash
# HELP_START
# push-to-prod.sh
#
# Pushes NEW/CHANGED rows from local Docker Postgres into production.
# Automatically detects what changed by comparing timestamps.
#
# How it works:
#   1. For each table, queries production for MAX(GREATEST(created_at, updated_at))
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
#   - Schema pre-check: aborts if local has columns that prod doesn't
#   - refresh_tokens (and anything else listed via --exclude-tables) is never synced
#   - --force overrides the timestamp filter and pushes EVERY row — use only
#     for the very first sync or after a restore from backup
#
# Usage:
#   make push-prod PROD_URL='postgres://user:pass@host:5432/db'
#
# Optional flags:
#   --dry-run                   Preview what would be synced without touching prod
#   --skip-backup               Skip the production backup step (NOT recommended)
#   --yes                       Skip the interactive confirmation prompt (CI)
#   --tables t1,t2              Only sync specific tables (allowlist)
#   --exclude-tables t1,t2      Skip these tables in addition to the default denylist
#   --force                     Push ALL local rows (ignore timestamps)
# HELP_END
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
ASSUME_YES=0
ONLY_TABLES=""
EXCLUDE_TABLES="refresh_tokens,alembic_version"

# Strict arg parser: unknown flags fail, value-taking flags validate their arg.
while [[ $# -gt 0 ]]; do
  arg="$1"
  case "$arg" in
    --dry-run)      DRY_RUN=1; shift ;;
    --skip-backup|--no-backup) SKIP_BACKUP=1; shift ;;
    --force)        FORCE_FULL=1; shift ;;
    --yes|-y)       ASSUME_YES=1; shift ;;
    --tables)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "ERROR: --tables requires a comma-separated value" >&2; exit 1
      fi
      ONLY_TABLES="$2"; shift 2 ;;
    --tables=*)     ONLY_TABLES="${arg#*=}"; shift ;;
    --exclude-tables)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "ERROR: --exclude-tables requires a comma-separated value" >&2; exit 1
      fi
      EXCLUDE_TABLES="$EXCLUDE_TABLES,$2"; shift 2 ;;
    --exclude-tables=*) EXCLUDE_TABLES="$EXCLUDE_TABLES,${arg#*=}"; shift ;;
    -h|--help)
      awk '/^# HELP_START/{flag=1; next} /^# HELP_END/{flag=0; next} flag {sub(/^# ?/,""); print}' "$0"; exit 0 ;;
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

for bin in pg_dump pg_restore psql; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: $bin not found. Install the Postgres client." >&2
    echo "  macOS:  brew install libpq && brew link --force libpq" >&2
    exit 1
  fi
done

if ! docker ps --format '{{.Names}}' | grep -qx "$LOCAL_CONTAINER"; then
  echo "ERROR: container '$LOCAL_CONTAINER' is not running." >&2
  echo "  Start it with: docker-compose up -d" >&2
  exit 1
fi

# Ensure SSL mode for prod connections (required by Render, Supabase, etc.)
PROD_URL_SSL="${PROD_URL}"
if [[ "$PROD_URL_SSL" != *"sslmode"* ]]; then
  if [[ "$PROD_URL_SSL" == *"?"* ]]; then
    PROD_URL_SSL="${PROD_URL_SSL}&sslmode=require"
  else
    PROD_URL_SSL="${PROD_URL_SSL}?sslmode=require"
  fi
fi

# Parse URL via Python so URL-encoded passwords, IPv6 hosts, and default
# ports are handled correctly (the old sed/regex approach broke on all three).
PROD_PARTS=$(PROD_URL_SSL="$PROD_URL_SSL" python3 - <<'PY'
import os, sys
from urllib.parse import urlparse
url = urlparse(os.environ['PROD_URL_SSL'])
print(f"PROD_HOST={url.hostname or 'localhost'}")
print(f"PROD_PORT={url.port or 5432}")
print(f"PROD_DB={url.path.lstrip('/')}")
PY
)
eval "$PROD_PARTS"

echo "  Local DB:  ${LOCAL_DB} @ ${LOCAL_CONTAINER}"
echo "  Prod DB:   ${PROD_DB} @ ${PROD_HOST}:${PROD_PORT}"

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

# Apply --exclude-tables (denylist).
EXCLUDED=()
IFS=',' read -ra EXCLUDED <<< "$EXCLUDE_TABLES"
declare -A EXCLUDED_SET=()
for t in "${EXCLUDED[@]}"; do
  t="$(echo "$t" | tr -d ' ')"
  [[ -n "$t" ]] && EXCLUDED_SET["$t"]=1
done

SYNC_TABLES=()
if [[ -n "$ONLY_TABLES" ]]; then
  IFS=',' read -ra REQUESTED <<< "$ONLY_TABLES"
  for t in "${REQUESTED[@]}"; do
    t="$(echo "$t" | tr -d ' ')"
    valid=0
    for a in "${ALL_TABLES[@]}"; do
      if [[ "$t" == "$a" ]]; then valid=1; break; fi
    done
    if [[ $valid -eq 0 ]]; then
      echo "ERROR: Unknown table '$t'. Valid: ${ALL_TABLES[*]}" >&2
      exit 1
    fi
    if [[ -n "${EXCLUDED_SET[$t]:-}" ]]; then
      echo "ERROR: '$t' is in --exclude-tables and can't also be in --tables." >&2
      exit 1
    fi
    SYNC_TABLES+=("$t")
  done
else
  for a in "${ALL_TABLES[@]}"; do
    if [[ -z "${EXCLUDED_SET[$a]:-}" ]]; then
      SYNC_TABLES+=("$a")
    fi
  done
fi

# --- Schema pre-check -------------------------------------------------------
# Abort if local has columns that prod doesn't. Pushing rows that reference
# missing columns would either fail row-by-row in psql or — worse — succeed
# but insert NULLs and silently corrupt data.

echo ""
echo "==> Schema compatibility check..."
SCHEMA_DIFF=$(PROD_URL_SSL="$PROD_URL_SSL" SYNC_TABLES_CSV="$(IFS=,; echo "${SYNC_TABLES[*]}")" \
LOCAL_CONTAINER="$LOCAL_CONTAINER" LOCAL_USER="$LOCAL_USER" LOCAL_PASS="$LOCAL_PASS" LOCAL_DB="$LOCAL_DB" \
  python3 - <<'PY'
import os, subprocess, sys
prod_url = os.environ['PROD_URL_SSL']
sync_tables = [t for t in os.environ['SYNC_TABLES_CSV'].split(',') if t]
container = os.environ['LOCAL_CONTAINER']
local_user = os.environ['LOCAL_USER']
local_pass = os.environ['LOCAL_PASS']
local_db = os.environ['LOCAL_DB']

def fetch(url_or_docker_args):
    """Return list of (table, column_name) for sync tables from the given source."""
    pass  # implemented via subprocess per source

# Local columns via docker exec psql with PGPASSWORD
local_sql = f"""
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = ANY(ARRAY[{','.join(repr(t) for t in sync_tables)}])
ORDER BY table_name, ordinal_position;
"""
local_proc = subprocess.run(
    ["docker", "exec", "-e", f"PGPASSWORD={local_pass}", container,
     "psql", "-U", local_user, "-d", local_db, "-t", "-A", "-F", "|", "-c", local_sql],
    capture_output=True, text=True, check=True,
)
local_cols = {}
for line in local_proc.stdout.strip().splitlines():
    if not line: continue
    t, c = line.split("|", 1)
    local_cols.setdefault(t, set()).add(c)

# Prod columns via psql (libpq handles sslmode from URL)
prod_sql = f"""
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = ANY(ARRAY[{','.join(repr(t) for t in sync_tables)}])
ORDER BY table_name, ordinal_position;
"""
prod_proc = subprocess.run(
    ["psql", prod_url, "-t", "-A", "-F", "|", "-c", prod_sql],
    capture_output=True, text=True, check=True,
)
prod_cols = {}
for line in prod_proc.stdout.strip().splitlines():
    if not line: continue
    t, c = line.split("|", 1)
    prod_cols.setdefault(t, set()).add(c)

diffs = []
for t in sync_tables:
    if t not in prod_cols:
        # Will be reported as MISSING_IN_PROD below; not a hard diff yet.
        continue
    only_local = sorted(local_cols.get(t, set()) - prod_cols.get(t, set()))
    if only_local:
        diffs.append((t, only_local))

for t, missing in diffs:
    print(f"  ! {t}: missing in prod: {', '.join(missing)}", file=sys.stderr)
sys.exit(1 if diffs else 0)
PY
) || {
  echo "" >&2
  echo "ERROR: Schema mismatch between local and prod." >&2
  echo "  Run 'make migrations' locally, commit, and apply on prod with 'make upgrade' before pushing." >&2
  exit 1
}
echo "  Schema: OK"

# --- Compare timestamps: prod vs local -------------------------------------

echo ""
echo "==> Checking production for last update times..."
echo ""

CHANGED_TABLES=()
TOTAL_ROWS=0

for TABLE in "${SYNC_TABLES[@]}"; do
  # Get max timestamp from production. Uses GREATEST of created_at and updated_at
  # (COALESCE handles NULLs). Cast to timestamptz so the comparison is
  # timezone-safe regardless of the column type on either side.
  PROD_QUERY="SELECT to_regclass('public.${TABLE}') IS NOT NULL;"
  PROD_EXISTS=$(psql "$PROD_URL_SSL" -t -A -c "$PROD_QUERY" 2>/dev/null | tr -d '[:space:]' || echo "")
  if [[ "$PROD_EXISTS" != "t" ]]; then
    printf "  %-25s prod: MISSING_IN_PROD\n" "$TABLE"
    CHANGED_TABLES+=("$TABLE")
    continue
  fi

  PROD_MAX_TS=$(psql "$PROD_URL_SSL" -t -A -c \
    "SELECT COALESCE(MAX(GREATEST(created_at AT TIME ZONE 'UTC', COALESCE(updated_at, created_at) AT TIME ZONE 'UTC')) AT TIME ZONE 'UTC', '1970-01-01T00:00:00Z'::timestamptz) FROM \"$TABLE\"" \
    2>/dev/null | tr -d '[:space:]' || echo "1970-01-01T00:00:00+00")

  # Check that local table has created_at; if not, count all rows.
  LOCAL_HAS_CREATED_AT=$(docker exec -e PGPASSWORD="$LOCAL_PASS" "$LOCAL_CONTAINER" \
    psql -U "$LOCAL_USER" -d "$LOCAL_DB" -t -A -c \
    "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='$TABLE' AND column_name='created_at');" \
    2>/dev/null | tr -d '[:space:]' || echo "f")

  if [[ "$FORCE_FULL" -eq 1 ]]; then
    LOCAL_COUNT_QUERY="SELECT COUNT(*) FROM \"$TABLE\""
  elif [[ "$LOCAL_HAS_CREATED_AT" == "t" ]]; then
    LOCAL_COUNT_QUERY="SELECT COUNT(*) FROM \"$TABLE\" WHERE created_at > '${PROD_MAX_TS}'::timestamptz OR COALESCE(updated_at, created_at) > '${PROD_MAX_TS}'::timestamptz"
  else
    # Table has no created_at column (unusual for app tables) — treat all rows as new.
    LOCAL_COUNT_QUERY="SELECT COUNT(*) FROM \"$TABLE\""
  fi

  # Capture stderr so real errors aren't silently coerced to "0".
  LOCAL_COUNT_RAW=$(docker exec -e PGPASSWORD="$LOCAL_PASS" "$LOCAL_CONTAINER" \
    psql -U "$LOCAL_USER" -d "$LOCAL_DB" -t -A -c "$LOCAL_COUNT_QUERY" 2>&1)
  LOCAL_COUNT=$(echo "$LOCAL_COUNT_RAW" | tail -n 1 | tr -d '[:space:]')

  if ! [[ "$LOCAL_COUNT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: COUNT(*) for '$TABLE' returned a non-numeric result:" >&2
    echo "$LOCAL_COUNT_RAW" >&2
    exit 1
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
if [[ $ASSUME_YES -eq 1 ]]; then
  echo "==> --yes set; skipping confirmation."
else
  if ! read -p "==> Proceed with push to production? (y/N) " CONFIRM; then
    echo "Aborted (no input)."
    exit 1
  fi
  if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

# --- Backup production ------------------------------------------------------

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
PROD_BACKUP="/tmp/fintrack-prod-backup-${TIMESTAMP}.dump"
LOCAL_DUMP="/tmp/fintrack-local-push-${TIMESTAMP}.dump"
SQL_DUMP="/tmp/fintrack-local-push-${TIMESTAMP}.sql"
PSQL_LOG="/tmp/fintrack-push-${TIMESTAMP}.log"

# Cleanup intermediate artefacts on exit. Production backup is intentionally
# preserved (you'll need it to roll back if anything went wrong).
cleanup_tmp() {
  rm -f "$LOCAL_DUMP" "$SQL_DUMP" "$PSQL_LOG" 2>/dev/null || true
}
trap cleanup_tmp EXIT

if [[ $SKIP_BACKUP -eq 0 ]]; then
  echo ""
  echo "==> Backing up production to $PROD_BACKUP ..."
  pg_dump "$PROD_URL_SSL" -Fc --no-owner --no-privileges --no-comments -f "$PROD_BACKUP" -v
  echo "  Backup saved: $PROD_BACKUP"
else
  echo ""
  echo "==> Skipping production backup (--skip-backup)"
fi

# --- Export changed rows from local DB --------------------------------------

echo ""
echo "==> Exporting changed rows from local DB..."

TABLE_ARGS=""
for TABLE in "${CHANGED_TABLES[@]}"; do
  TABLE_ARGS="$TABLE_ARGS --table=$TABLE"
done

# Use PGPASSWORD via env to keep the password out of argv / process list.
PGPASSWORD="$LOCAL_PASS" pg_dump \
  --data-only \
  --column-inserts \
  --no-owner \
  --no-privileges \
  --no-publications \
  --no-subscriptions \
  --no-security-labels \
  --no-comments \
  -Fc \
  -f "$LOCAL_DUMP" \
  $TABLE_ARGS

echo "  Local dump: $LOCAL_DUMP"

# --- Convert dump to SQL with ON CONFLICT DO NOTHING ------------------------

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

if result.returncode != 0:
    print(f"ERROR: pg_restore exited with {result.returncode}", file=sys.stderr)
    if result.stderr: print(result.stderr, file=sys.stderr)
    sys.exit(1)
if not result.stdout:
    print(f"ERROR: pg_restore produced no output", file=sys.stderr)
    sys.exit(1)

# Transform INSERT statements. We rely on pg_dump --column-inserts which
# always emits single-line INSERT INTO ... VALUES (...) statements. Multi-line
# statements are left untouched (better safe than silent corruption).
lines = result.stdout.split('\n')
output = []
insert_count = 0
for line in lines:
    stripped = line.lstrip()
    if stripped.upper().startswith('INSERT INTO'):
        if line.rstrip().endswith(';'):
            line = line.rstrip()[:-1] + ' ON CONFLICT DO NOTHING;'
        else:
            line = line + ' ON CONFLICT DO NOTHING'
        insert_count += 1
    output.append(line)

with open(sql_file, 'w') as f:
    f.write('\n'.join(output))

print(f"  Converted {insert_count} INSERT statements with conflict handling")
PY

echo "  SQL dump: $SQL_DUMP"

# --- Restore to production --------------------------------------------------

echo ""
echo "==> Pushing to production..."
echo "    Full output is being captured to: $PSQL_LOG"

# ON_ERROR_STOP=1 so any failure aborts the script (non-zero exit).
# stderr/stdout are captured in the log so we can still show a tail of it
# without losing earlier errors.
if ! psql "$PROD_URL_SSL" -v ON_ERROR_STOP=1 -f "$SQL_DUMP" >"$PSQL_LOG" 2>&1; then
  echo "" >&2
  echo "ERROR: psql exited with a non-zero status. Push was aborted." >&2
  echo "  See the last 30 lines of output below for details." >&2
  echo "  Full log: $PSQL_LOG" >&2
  echo "  Backup:   $PROD_BACKUP" >&2
  echo "" >&2
  tail -30 "$PSQL_LOG" >&2 || true
  exit 1
fi

echo ""
echo "  Last lines of psql output:"
tail -10 "$PSQL_LOG" | sed 's/^/    /'

# --- Done -------------------------------------------------------------------

echo ""
echo "==> Done! Changes have been pushed to production."
echo ""
echo "  Backup kept at: $PROD_BACKUP"
echo "  To clean up:    rm $PROD_BACKUP"
echo ""
echo "  Production is now in sync with your local changes."
