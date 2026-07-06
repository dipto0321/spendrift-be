"""One-time cleanup of test/dummy users and their artifacts from prod DB.

Removes:
  - All users whose email matches a known test pattern (phase1test, uitest,
    refresh, trk, crud, probe, exp, reassign, bud, bs, seed, dash, dashui,
    verify, vtog, smoke, s39, s39b, sc, dv, democalc, tip_)
  - Or whose name is a known test fixture name (Phase One, UI Test, Trk,
    Crud, Probe, Exp, R, B, Bud, BS, Seed, D, Dash, Verify, V, Smoke, S,
    SC, DV, Demo Calc, T, P)
  - Cascades: trackers -> categories/expenses/budgets (DB CASCADE),
              then refresh_tokens (manual), then user_avatars + user_preferences
              (DB CASCADE), then the user itself.

KEEPS the real user `diptokmk47@gmail.com` (Dipto Karmakar) and their
`Daily expense` tracker with all migrated historical data.

Usage:
    # Dry-run (preview only, no changes):
    uv run python scripts/cleanup_test_data.py --dry-run

    # Real cleanup:
    uv run python scripts/cleanup_test_data.py

    # Override the "keep" set (comma-separated emails) if needed:
    uv run python scripts/cleanup_test_data.py --keep "diptokmk47@gmail.com"
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

# Mirror migrate_html_expenses.py: ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, delete  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from modules.categories.model import Category  # noqa: E402
from modules.expenses.model import Expense  # noqa: E402
from modules.refresh_tokens.model import RefreshToken  # noqa: E402
from modules.trackers.model import Tracker  # noqa: E402
from modules.users.model import User  # noqa: E402

logger = logging.getLogger("cleanup_test_data")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------
# Emails that indicate a test fixture. The pattern is the substring before @.
TEST_EMAIL_PATTERNS: tuple[str, ...] = (
    "phase1test+",
    "uitest",
    "refresh",  # covers refresh1781465064@
    "trk",      # trk1781576391@  (also collides with trk = "trackers" test)
    "crud",     # crud1781576447@
    "probe",    # probe1781577484@, probe21781577693@, probe1781620947@
    "exp",      # exp1781578026@  (could be ambiguous, but `exp@` is clearly a test prefix)
    "reassign", # reassign1781579496@
    "bud",      # bud1781580454@, bud1781582224@
    "bs",       # bs1781582452@   (test fixture)
    "seed",     # seed1781582528@
    "dash",     # dash1781583258@, dashui1781583473@, dash_1781623702@
    "verify",   # verify1781621325@, verify1781621719@
    "vtog",     # vtog1781621993@
    "smoke",    # smoke1781622380@, smoke1781622405@
    "s39",      # s39_1781623366@, s39_1781623377@, s39b_1781623420@
    "sc_",      # sc_1781623527@
    "dv_",      # dv_1781730914@
    "democalc", # democalc@
    "tip_",     # tip_1781624117@
)

# Test fixture names (single-letter or known test names). Matched case-insensitive.
TEST_NAME_EXACT: frozenset[str] = frozenset(
    {
        "phase one",
        "ui test",
        "trk",
        "crud",
        "exp",
        "r",
        "b",
        "bud",
        "bs",
        "seed",
        "d",
        "dash",
        "verify",
        "v",
        "smoke",
        "s",
        "sc",
        "dv",
        "t",
        "p",
        "demo calc",
    }
)

DEFAULT_KEEP_EMAILS: tuple[str, ...] = ("diptokmk47@gmail.com",)


# ---------------------------------------------------------------------------
def is_test_user(user: User) -> bool:
    """Return True if this user matches any known test pattern."""
    email = (user.email or "").lower()
    local = email.split("@", 1)[0]
    if any(local.startswith(p) for p in TEST_EMAIL_PATTERNS):
        return True
    name = (user.name or "").strip().lower()
    if name in TEST_NAME_EXACT:
        return True
    return False


# ---------------------------------------------------------------------------
def find_test_users(session: Session, keep_emails: Iterable[str]) -> list[User]:
    keep = {e.lower() for e in keep_emails}
    all_users = session.exec(select(User)).all()
    return [u for u in all_users if is_test_user(u) and u.email.lower() not in keep]


# ---------------------------------------------------------------------------
def preview(
    session: Session, test_users: list[User]
) -> dict[str, int]:
    """Count everything that would be removed."""
    test_user_ids = [u.id for u in test_users]
    tracker_count = session.exec(
        select(Tracker).where(Tracker.user_id.in_(test_user_ids))  # type: ignore[union-attr]
    ).all()
    tracker_ids = [t.id for t in tracker_count]
    category_count = session.exec(
        select(Category).where(Category.tracker_id.in_(tracker_ids))  # type: ignore[union-attr]
    ).all()
    expense_count = session.exec(
        select(Expense).where(Expense.tracker_id.in_(tracker_ids))  # type: ignore[union-attr]
    ).all()
    rt_count = session.exec(
        select(RefreshToken).where(RefreshToken.user_id.in_(test_user_ids))  # type: ignore[union-attr]
    ).all()
    return {
        "users": len(test_users),
        "trackers": len(tracker_count),
        "categories": len(category_count),
        "expenses": len(expense_count),
        "refresh_tokens": len(rt_count),
    }


# ---------------------------------------------------------------------------
def print_preview_table(
    test_users: list[User], session: Session
) -> None:
    test_user_ids = [u.id for u in test_users]
    trackers = session.exec(
        select(Tracker).where(Tracker.user_id.in_(test_user_ids))  # type: ignore[union-attr]
    ).all()
    tracker_ids = [t.id for t in trackers]
    expenses = session.exec(
        select(Expense).where(Expense.tracker_id.in_(tracker_ids))  # type: ignore[union-attr]
    ).all()
    refresh = session.exec(
        select(RefreshToken).where(RefreshToken.user_id.in_(test_user_ids))  # type: ignore[union-attr]
    ).all()

    print()
    print("=" * 78)
    print("PREVIEW — the following would be removed")
    print("=" * 78)
    print(f"\nUsers to delete ({len(test_users)}):")
    for u in test_users:
        print(f"  - {u.email:<45s}  name={u.name!r}  id={u.id}")

    print(f"\nTrackers to delete ({len(trackers)}):")
    for t in trackers:
        owner = next((u.email for u in test_users if u.id == t.user_id), "?")
        print(f"  - {t.name!r:<20s} currency={t.currency}  owner={owner}  id={t.id}")

    print(f"\nRefresh tokens to delete: {len(refresh)}")
    print(f"Expenses to delete (cascade): {len(expenses)}")
    categories = session.exec(
        select(Category).where(Category.tracker_id.in_(tracker_ids))  # type: ignore[union-attr]
    ).all()
    print(f"Categories to delete (cascade): {len(categories)}")
    print("=" * 78)


# ---------------------------------------------------------------------------
def execute_cleanup(
    session: Session, test_users: list[User]
) -> dict[str, int]:
    """Hard-delete test users + all their artifacts. Returns deletion counts."""
    test_user_ids = [u.id for u in test_users]
    trackers = session.exec(
        select(Tracker).where(Tracker.user_id.in_(test_user_ids))  # type: ignore[union-attr]
    ).all()
    tracker_ids = [t.id for t in trackers]

    # 1. Trackers first — DB cascades to categories, expenses, budgets.
    logger.info("Step 1/4: deleting %d trackers (cascades to cats/exp/budgets)", len(trackers))
    session.exec(
        delete(Tracker).where(Tracker.id.in_(tracker_ids))  # type: ignore[union-attr]
    )
    session.flush()

    # 2. Refresh tokens (must come before user delete — FK is NO ACTION).
    logger.info("Step 2/4: deleting refresh tokens for %d users", len(test_user_ids))
    rt_result = session.exec(
        delete(RefreshToken).where(RefreshToken.user_id.in_(test_user_ids))  # type: ignore[union-attr]
    )
    session.flush()
    rt_count = rt_result.rowcount or 0

    # 3. Users — DB cascades to user_avatars + user_preferences.
    logger.info("Step 3/4: deleting %d users (cascades to avatars/prefs)", len(test_user_ids))
    session.exec(
        delete(User).where(User.id.in_(test_user_ids))  # type: ignore[union-attr]
    )
    session.flush()

    return {
        "users": len(test_user_ids),
        "trackers": len(trackers),
        "refresh_tokens": rt_count,
    }


# ---------------------------------------------------------------------------
def verify_after(session: Session) -> None:
    """Sanity checks post-cleanup."""
    remaining = session.exec(select(User)).all()
    test_remaining = [u for u in remaining if is_test_user(u)]
    print("\nPost-cleanup state:")
    print(f"  Total users in DB:        {len(remaining)}")
    print(f"  Remaining test users:     {len(test_remaining)}")
    for u in remaining:
        marker = " <- TEST (should not exist!)" if is_test_user(u) else ""
        print(f"    - {u.email:<40s}  name={u.name!r}{marker}")
    if test_remaining:
        raise RuntimeError(
            f"Cleanup incomplete: {len(test_remaining)} test users still present"
        )


# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Hard-delete test users and all their artifacts from the DB.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without modifying the DB.",
    )
    p.add_argument(
        "--keep",
        type=str,
        default=",".join(DEFAULT_KEEP_EMAILS),
        help=(
            "Comma-separated emails of users to ALWAYS KEEP, even if they match "
            f"a test pattern. Default: {','.join(DEFAULT_KEEP_EMAILS)!r}"
        ),
    )
    p.add_argument(
        "--database-url",
        type=str,
        default=None,
        help=(
            "Override the database URL (e.g. for running against prod while the "
            "local .env points elsewhere). If omitted, uses settings.database_url."
        ),
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
def main() -> int:
    args = parse_args()
    keep_emails = [e.strip() for e in args.keep.split(",") if e.strip()]

    engine = create_engine(
        args.database_url or settings.database_url,
        pool_pre_ping=True,
        future=True,
    )
    db_url_for_log = args.database_url or settings.database_url
    logger.info(
        "Connecting to: %s",
        db_url_for_log.split("@")[-1],  # hide credentials
    )

    with Session(engine) as session:
        test_users = find_test_users(session, keep_emails)

        if not test_users:
            print("\nNothing to clean — no test users matched.")
            return 0

        print_preview_table(test_users, session)
        counts = preview(session, test_users)
        print("\nTotals:")
        for k, v in counts.items():
            print(f"  {k:<20s} {v}")

        if args.dry_run:
            print("\n[dry-run] No changes made. Re-run without --dry-run to execute.")
            return 0

        # Require interactive confirmation unless --yes is set
        print("\nThis will HARD-DELETE the above users and all their data.")
        print("This is irreversible. Type 'yes' to continue, anything else to abort.")
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 1
        if answer != "yes":
            print("Aborted.")
            return 1

        result = execute_cleanup(session, test_users)
        session.commit()

        logger.info("Cleanup complete: %s", result)
        verify_after(session)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
