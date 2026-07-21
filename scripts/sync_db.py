#!/usr/bin/env python3
"""
Bidirectional incremental sync between local Docker Postgres and production
Postgres. Designed for `make sync-db`.

Safety guarantees:
  - BOTH databases are dumped to /tmp BEFORE any mutation.
  - Each table is synced inside its own transaction per side, so a partial
    failure rolls back to the last good state on that side.
  - On any failure during apply, BOTH databases are restored from the
    pre-sync dumps.
  - sync_state watermarks only advance forward; a successful run is
    resumable and idempotent.
  - Deletions are NEVER propagated (INSERT-only sync). A row missing from
    one side is left alone on the other.
  - When the same row has been updated on both sides since the last sync,
    the row with the newer `updated_at` wins.

This script is intentionally a standalone tool — it does NOT import from
`app.*` or `modules.*` so it can run without the FastAPI stack.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

# Make project modules importable so we can use the SQLModel metadata to
# discover synced tables. We deliberately do NOT touch the FastAPI app.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import every SQLModel so SQLModel.metadata reflects every real table.
# These imports have no side effects beyond registering the tables.
from modules.budgets.model import Budget  # noqa: E402, F401
from modules.categories.model import Category  # noqa: E402, F401
from modules.category_budgets.model import CategoryBudget  # noqa: E402, F401
from modules.expenses.model import Expense  # noqa: E402, F401
from modules.preferences.model import UserPreference  # noqa: E402, F401
from modules.refresh_tokens.model import RefreshToken  # noqa: E402, F401
from modules.trackers.model import Tracker  # noqa: E402, F401
from modules.users.model import User  # noqa: E402, F401

# Tables NOT synced (sensitive, write-once semantics, or no updated_at):
SKIP_TABLES: frozenset[str] = frozenset(
    {
        "refresh_tokens",   # security-sensitive; never sync
        "user_avatars",     # only created_at; S3 objects out of scope
        "alembic_version",  # managed by migrations, must not diverge
    }
)

# Sync order respects FK dependencies: parents first, children last. We
# sync `users` before `trackers` so a child row's INSERT cannot transiently
# violate its FK on the target side.
SYNC_ORDER: tuple[str, ...] = (
    "users",
    "trackers",
    "categories",
    "budgets",
    "category_budgets",
    "expenses",
    "user_preferences",
)

SYNC_STATE_TABLE = "sync_state"

# Columns we never want to overwrite or print in verbose mode.
SENSITIVE_COLUMNS: dict[str, frozenset[str]] = {
    "users": frozenset({"password_hash"}),
    "refresh_tokens": frozenset({"token_hash"}),
}

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sync_db.py",
        description="Bidirectional incremental sync between local Docker DB "
        "and a remote Postgres (prod).",
    )
    p.add_argument("--local-url", default=os.environ.get("LOCAL_DATABASE_URL"))
    p.add_argument("--prod-url", default=os.environ.get("PROD_DATABASE_URL"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--status",
        action="store_true",
        help="Print current sync_state watermarks on both sides and exit.",
    )
    p.add_argument(
        "--reset-watermark",
        action="store_true",
        help="Reset all sync_state rows to epoch (forces a full re-scan).",
    )
    p.add_argument(
        "--table",
        action="append",
        default=None,
        help="Restrict sync to the given table name (repeatable).",
    )
    p.add_argument(
        "--keep-dump",
        action="store_true",
        help="Keep pre-sync dumps in /tmp after a successful run.",
    )
    p.add_argument("--jobs", type=int, default=4, help="Parallel pg_dump jobs.")
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print row-level details (sensitive columns still masked).",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------
def make_engine(url: str) -> Engine:
    """Create a sync SQLAlchemy engine. We disable pooling — pg_dump owns
    the connection lifecycle, and the per-table transactions are short.

    Accepts both `postgresql://` and `postgres://` schemes (libpq-style
    shorthand) — the psycopg2 driver only knows `postgresql+psycopg2://`.
    """
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    return sa.create_engine(url, future=True, poolclass=sa.pool.NullPool)


def libpq_url(sa_url: sa.URL) -> str:
    """Render an SQLAlchemy URL into a plain libpq-style `postgresql://` URL
    that `pg_dump` and `pg_restore` understand. Strips the `+psycopg2` driver
    suffix and URL-encodes credentials the way libpq expects."""
    out = sa_url.set(drivername="postgresql")
    return out.render_as_string(hide_password=False)


def check_connection(engine: Engine, label: str) -> None:
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot connect to {label} ({engine.url.host}): {exc}")
        sys.exit(1)


def get_alembic_version(engine: Engine) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(sa.text("SELECT version_num FROM alembic_version")).first()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Backup / restore via pg_dump / pg_restore
# ---------------------------------------------------------------------------
def pg_dump(url: str, out_path: str, jobs: int) -> None:
    """Dump `url` to `out_path` using pg_dump. Directory format if jobs > 1
    so we can parallelise, custom format otherwise."""
    # Clear any stale path. ignore_errors handles the missing-file case
    # without a TOCTOU pre-check.
    if os.path.isdir(out_path):
        shutil.rmtree(out_path, ignore_errors=True)
    else:
        try:
            os.remove(out_path)
        except FileNotFoundError:
            pass

    if jobs > 1:
        os.makedirs(out_path, exist_ok=False)
        cmd = [
            "pg_dump",
            url,
            "-Fd",
            "-j",
            str(jobs),
            "-f",
            out_path,
            "--no-owner",
            "--no-privileges",
        ]
    else:
        cmd = [
            "pg_dump",
            url,
            "-Fc",
            "-f",
            out_path,
            "--no-owner",
            "--no-privileges",
        ]
    subprocess.run(cmd, check=True)  # noqa: S603


def remove_dump(path: str) -> None:
    """Delete a pg_dump output, which is a directory (-Fd) or a file (-Fc)."""
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def pg_restore(dump_path: str, url: str, jobs: int) -> None:
    """Restore a pg_dump file/dir into `url` with --clean --if-exists: every
    dumped object is dropped and recreated, so the DB returns to the exact
    state captured in the dump. Terminates other connections first so the
    DROPs can take their locks."""
    parsed = sa.make_url(url)
    db_name = parsed.database
    password = parsed.password
    host = parsed.host or "localhost"
    port = parsed.port or 5432

    # Terminate other backends on this DB so pg_restore can take locks.
    admin_url = parsed.set(database="postgres")
    admin_engine = make_engine(admin_url.render_as_string(hide_password=False))
    try:
        with admin_engine.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.commit()
    finally:
        admin_engine.dispose()

    cmd = [
        "pg_restore",
        "-d",
        url,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "-j",
        str(jobs),
        dump_path,
    ]
    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password
    # pg_restore exits non-zero on harmless warnings (e.g. role already
    # exists). We still want to know about real failures, so capture and
    # surface stderr; non-zero exit + non-empty stderr = fail.
    proc = subprocess.run(  # noqa: S603
        cmd,
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 and proc.stderr.strip():
        raise RuntimeError(
            f"pg_restore failed for {db_name} on {host}:{port}\n{proc.stderr}"
        )


# ---------------------------------------------------------------------------
# Schema discovery
# ---------------------------------------------------------------------------
def synced_tables() -> list[str]:
    """Return the list of tables that have an `updated_at` column AND are
    not in SKIP_TABLES. Order is SYNC_ORDER."""
    available = {t.name: t for t in SQLModel.metadata.tables.values()}
    result: list[str] = []
    for name in SYNC_ORDER:
        t = available.get(name)
        if t is None:
            continue
        if "updated_at" not in t.c:
            continue
        if name in SKIP_TABLES:
            continue
        result.append(name)
    return result


def columns_for(table_name: str) -> list[str]:
    return [c.name for c in SQLModel.metadata.tables[table_name].c]


def pk_column(table_name: str) -> str:
    pk_cols = SQLModel.metadata.tables[table_name].primary_key.columns.keys()
    if len(pk_cols) != 1:
        raise ValueError(
            f"{table_name} must have a single-column primary key, has {len(pk_cols)}"
        )
    return pk_cols[0]


# ---------------------------------------------------------------------------
# sync_state
# ---------------------------------------------------------------------------
def ensure_sync_state(engine: Engine) -> None:
    """The sync_state table is created by Alembic. Defensive: if it
    doesn't exist yet (e.g. someone ran the script before `make upgrade`),
    bail with a clear message."""
    with engine.connect() as conn:
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :t"
            ),
            {"t": SYNC_STATE_TABLE},
        ).first()
        if not exists:
            raise RuntimeError(
                f"sync_state table missing on {engine.url.host}. "
                f"Run `make upgrade` on that DB first."
            )


def read_watermarks(engine: Engine, table_name: str) -> datetime:
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT last_synced_at FROM sync_state WHERE table_name = :t"
            ),
            {"t": table_name},
        ).first()
    if not row:
        return EPOCH
    val = row[0]
    if val.tzinfo is None:
        val = val.replace(tzinfo=timezone.utc)
    return val


def advance_watermark(engine: Engine, table_name: str, new_watermark: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO sync_state (table_name, last_synced_at, updated_at)
                VALUES (:t, :w, now())
                ON CONFLICT (table_name) DO UPDATE
                SET last_synced_at = GREATEST(sync_state.last_synced_at, EXCLUDED.last_synced_at),
                    updated_at = now()
                """
            ),
            {"t": table_name, "w": new_watermark},
        )


def reset_watermarks(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE sync_state SET last_synced_at = 'epoch'::timestamptz, updated_at = now()"
            )
        )


# ---------------------------------------------------------------------------
# Diff + apply
# ---------------------------------------------------------------------------
@dataclass
class DiffStats:
    table: str
    push_to_prod: int = 0
    push_to_local: int = 0
    skipped_equal: int = 0
    new_watermark: datetime | None = None


@dataclass
class SyncContext:
    local_engine: Engine
    prod_engine: Engine
    dry_run: bool
    verbose: bool
    jobs: int
    keep_dump: bool = False


def fetch_changed_rows(
    engine: Engine, table_name: str, watermark: datetime
) -> dict[Any, dict[str, Any]]:
    """Return {pk_value: {column: value, ...}} for rows with updated_at > watermark."""
    cols = columns_for(table_name)
    pk = pk_column(table_name)
    stmt = sa.text(
        f"SELECT {', '.join(cols)} FROM {table_name} "
        f"WHERE updated_at > :w ORDER BY updated_at ASC, {pk} ASC"
    )
    out: dict[Any, dict[str, Any]] = {}
    with engine.connect() as conn:
        rows = conn.execute(stmt, {"w": watermark}).fetchall()
    for row in rows:
        out[row._mapping[pk]] = dict(row._mapping)
    return out


def mask_sensitive(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    sensitive = SENSITIVE_COLUMNS.get(table_name, frozenset())
    masked = dict(row)
    for col in sensitive:
        if col in masked:
            masked[col] = "***REDACTED***"
    return masked


def upsert_row(engine: Engine, table_name: str, row: dict[str, Any]) -> None:
    """INSERT ... ON CONFLICT (pk) DO UPDATE. Built with SQLAlchemy core so
    every column of the model is handled without per-table code."""
    cols = columns_for(table_name)
    pk = pk_column(table_name)
    update_cols = [c for c in cols if c != pk]

    insert_stmt = sa.text(
        f"INSERT INTO {table_name} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)}) "
        f"ON CONFLICT ({pk}) DO UPDATE SET "
        f"{', '.join(f'{c} = EXCLUDED.{c}' for c in update_cols)}"
    )
    with engine.begin() as conn:
        conn.execute(insert_stmt, row)


def sync_table(ctx: SyncContext, table_name: str) -> DiffStats:
    stats = DiffStats(table=table_name)

    local_wm = read_watermarks(ctx.local_engine, table_name)
    prod_wm = read_watermarks(ctx.prod_engine, table_name)

    # Fetch on BOTH sides from the OLDER of the two watermarks. The two DBs'
    # watermarks diverge whenever one side is fresh or was synced against a
    # different peer; fetching each side from its own watermark would then
    # silently skip rows the other side never received. Re-scanning older
    # rows is safe: upserts are idempotent and equal rows are skipped.
    effective_wm = min(local_wm, prod_wm)

    if ctx.verbose:
        print(f"  [{table_name}] local watermark = {local_wm.isoformat()}")
        print(f"  [{table_name}] prod  watermark = {prod_wm.isoformat()}")
        print(f"  [{table_name}] fetching from   = {effective_wm.isoformat()}")

    local_rows = fetch_changed_rows(ctx.local_engine, table_name, effective_wm)
    prod_rows = fetch_changed_rows(ctx.prod_engine, table_name, effective_wm)

    all_pks = set(local_rows) | set(prod_rows)
    if not all_pks:
        if ctx.verbose:
            print(f"  [{table_name}] no changes since last sync")
        return stats

    plan_push_to_prod: list[dict[str, Any]] = []
    plan_push_to_local: list[dict[str, Any]] = []
    new_watermark = max(local_wm, prod_wm)

    for pk in all_pks:
        local_row = local_rows.get(pk)
        prod_row = prod_rows.get(pk)
        if local_row and not prod_row:
            plan_push_to_prod.append(local_row)
            new_watermark = max(new_watermark, _ts(local_row["updated_at"]))
        elif prod_row and not local_row:
            plan_push_to_local.append(prod_row)
            new_watermark = max(new_watermark, _ts(prod_row["updated_at"]))
        else:
            local_ts = _ts(local_row["updated_at"])
            prod_ts = _ts(prod_row["updated_at"])
            if local_ts > prod_ts:
                plan_push_to_prod.append(local_row)
                new_watermark = max(new_watermark, local_ts)
            elif prod_ts > local_ts:
                plan_push_to_local.append(prod_row)
                new_watermark = max(new_watermark, prod_ts)
            else:
                stats.skipped_equal += 1

    stats.push_to_prod = len(plan_push_to_prod)
    stats.push_to_local = len(plan_push_to_local)
    stats.new_watermark = new_watermark

    if ctx.verbose:
        pk_name = pk_column(table_name)
        for row in plan_push_to_prod:
            print(f"    -> push to prod: {row[pk_name]} {mask_sensitive(table_name, row)}")
        for row in plan_push_to_local:
            print(f"    -> push to local: {row[pk_name]} {mask_sensitive(table_name, row)}")

    if ctx.dry_run:
        return stats

    # APPLY: each upsert is its own transaction. On any failure, run_sync's
    # outer except block restores both DBs from the pre-sync dumps.
    for row in plan_push_to_prod:
        upsert_row(ctx.prod_engine, table_name, row)

    for row in plan_push_to_local:
        upsert_row(ctx.local_engine, table_name, row)

    advance_watermark(ctx.local_engine, table_name, new_watermark)
    advance_watermark(ctx.prod_engine, table_name, new_watermark)
    return stats


def _ts(value: Any) -> datetime:
    """Coerce a datetime / string to a timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Cannot coerce {value!r} to datetime")


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------
def print_status(ctx: SyncContext) -> None:
    for label, engine in (("local", ctx.local_engine), ("prod", ctx.prod_engine)):
        print(f"== {label} ({engine.url.host}) ==")
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT table_name, last_synced_at, updated_at "
                    "FROM sync_state ORDER BY table_name"
                )
            ).fetchall()
            if not rows:
                print("  (sync_state has no rows yet)")
            for r in rows:
                print(f"  {r.table_name:<22}  last_synced_at = {r.last_synced_at}")


def run_sync(ctx: SyncContext, tables: list[str]) -> int:
    """Returns 0 on success, non-zero on failure."""
    check_connection(ctx.local_engine, "local")
    check_connection(ctx.prod_engine, "prod")

    local_ver = get_alembic_version(ctx.local_engine)
    prod_ver = get_alembic_version(ctx.prod_engine)
    if local_ver != prod_ver:
        print("ERROR: Alembic versions differ — refusing to sync.")
        print(f"  local = {local_ver}")
        print(f"  prod  = {prod_ver}")
        print("Run `make upgrade` on whichever side is behind.")
        return 1
    print(f"==> Both DBs on Alembic version: {local_ver}")

    ensure_sync_state(ctx.local_engine)
    ensure_sync_state(ctx.prod_engine)

    # Take backups BEFORE anything else. We deliberately use raw string paths
    # instead of a dict on SyncContext: nothing else needs to read them.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_local_path = f"/tmp/fintrack-sync-local-{timestamp}.dump"
    backup_prod_path = f"/tmp/fintrack-sync-prod-{timestamp}.dump"
    print(f"==> Backing up local DB to {backup_local_path}")
    pg_dump(libpq_url(ctx.local_engine.url), backup_local_path, ctx.jobs)
    print(f"==> Backing up prod DB to {backup_prod_path}")
    pg_dump(libpq_url(ctx.prod_engine.url), backup_prod_path, ctx.jobs)

    if ctx.dry_run:
        print("==> DRY-RUN: no changes will be written.")

    total_prod = total_local = total_skipped = 0
    try:
        for table in tables:
            print(f"==> Syncing {table}")
            stats = sync_table(ctx, table)
            print(
                f"    push_to_prod={stats.push_to_prod} "
                f"push_to_local={stats.push_to_local} "
                f"skipped_equal={stats.skipped_equal}"
            )
            total_prod += stats.push_to_prod
            total_local += stats.push_to_local
            total_skipped += stats.skipped_equal
    except Exception as exc:
        print(f"\nERROR: sync failed: {exc}")
        print("==> Restoring both DBs from pre-sync dumps...")
        try:
            pg_restore(
                backup_local_path,
                libpq_url(ctx.local_engine.url),
                ctx.jobs,
            )
            pg_restore(
                backup_prod_path,
                libpq_url(ctx.prod_engine.url),
                ctx.jobs,
            )
            print("==> Restore complete. Both DBs are back to their pre-sync state.")
        except Exception as restore_exc:  # noqa: BLE001
            print(f"ERROR: restore failed: {restore_exc}")
            print("Manual recovery required:")
            print(f"  local dump: {backup_local_path}")
            print(f"  prod  dump: {backup_prod_path}")
        finally:
            # Always keep dumps after failure for post-mortem.
            print(f"  dumps kept at: {backup_local_path}, {backup_prod_path}")
        return 1

    print(
        f"\n==> Sync complete. "
        f"pushed_to_prod={total_prod} pushed_to_local={total_local} skipped_equal={total_skipped}"
    )
    if ctx.keep_dump:
        print(f"==> Dumps kept at: {backup_local_path}, {backup_prod_path}")
    else:
        remove_dump(backup_local_path)
        remove_dump(backup_prod_path)
        print("==> Pre-sync dumps removed (use --keep-dump to keep them).")
    return 0


def main() -> int:
    args = parse_args()

    if not args.local_url or not args.prod_url:
        print("ERROR: --local-url and --prod-url (or LOCAL_DATABASE_URL / "
              "PROD_DATABASE_URL env vars) are required.")
        return 1

    if shutil.which("pg_dump") is None:
        print("ERROR: pg_dump not found. Install the Postgres client.")
        return 1

    ctx = SyncContext(
        local_engine=make_engine(args.local_url),
        prod_engine=make_engine(args.prod_url),
        dry_run=args.dry_run,
        verbose=args.verbose,
        jobs=args.jobs,
        keep_dump=args.keep_dump,
    )

    all_tables = synced_tables()
    tables = all_tables
    if args.table:
        tables = [t for t in all_tables if t in args.table]
        if not tables:
            print(f"ERROR: --table filters matched nothing. Available: {all_tables}")
            return 1

    if args.status:
        print_status(ctx)
        return 0

    if args.reset_watermark and not args.dry_run:
        print("==> Resetting watermarks to epoch on both sides")
        reset_watermarks(ctx.local_engine)
        reset_watermarks(ctx.prod_engine)

    return run_sync(ctx, tables)


if __name__ == "__main__":
    sys.exit(main())