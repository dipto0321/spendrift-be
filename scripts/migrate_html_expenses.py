#!/usr/bin/env python3
"""One-time migration: parse Google-Sheets monthly expense HTML exports into the
local Postgres ``expenses`` table.

Source
------
``/Users/dipto/My_Works/Projects/FinTracker/Monthly Expense/*.html`` — files
covering Dec 2021 → Mar 2026. Each monthly file is a "Download as webpage"
export of a Google Sheet titled "Monthly Expense <Month YYYY>" with the
layout:

    A = Date (e.g. "Sunday, May 1, 2022")
    B = Spent Detail (free text, sometimes wrapped in <div class="softmerge-inner">)
    C = Amount ("৳1,234.56", can be negative "-৳500.00", or "৳0.00" / "None")
    D-G = empty in data rows
    H-J = sidebar columns (Total Income / Savings / Provide loan / Return) — out of scope.

Only files matching the strict pattern ``<Month name> <year>.html`` are
processed — both the full month name (``January 2022.html``) and the
three-letter abbreviation used for the most recent months (``Jan 2026.html``,
``Feb 2026.html``, ``Mar 2026.html``). Files with different names
(notably ``Name.html`` and ``summery of costs.html``) are skipped. The typo'd
``Setember, 2021.html`` is **also** included by an explicit exception — it
holds the September 2021 ledger despite the misspelling and stray comma in
the filename.

The first <tbody> row is the data header "Date | Spent Detail | Amount" and is
dropped. The "Grand Total" row at the bottom of each sheet is also skipped.

Target
------
- One ``Category`` per bucket under the target tracker. 10 buckets reuse the
  categories already in ``modules/categories/service.py:DEFAULT_CATEGORIES``;
  2 are new (``Education``, ``Family Support``).
- One ``Expense`` per surviving data row. ``type="need"`` for all imported rows
  (no source signal). ``id`` and ``created_at`` default to model values.

Idempotency
-----------
Dedupe key on insert: (tracker_id, date, description, amount). The script is
safe to re-run. Negative-amount rows are skipped + logged, not inserted.

Usage
-----
::

    cd backend
    uv run python scripts/migrate_html_expenses.py --dry-run
    uv run python scripts/migrate_html_expenses.py
"""

from __future__ import annotations

import argparse
import html as html_lib
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from uuid import UUID

# Mirror seed.py's import trick.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from modules.categories.model import Category  # noqa: E402
from modules.expenses.model import Expense  # noqa: E402
from modules.trackers.model import Tracker  # noqa: E402
from modules.users.model import User  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Match the pinned IDs used by seed.py so we hit the same personal workspace.
DEFAULT_USER_ID = UUID("fa2796f0-0598-4b59-933f-51f10310b24b")
DEFAULT_TRACKER_ID = UUID("7a865e4b-cc23-4e9d-a4b9-8a28f49c9e8d")

# Override with environment variables if needed.
USER_ID = UUID(os.environ.get("MIGRATION_USER_ID", str(DEFAULT_USER_ID)))
TRACKER_ID = UUID(os.environ.get("MIGRATION_TRACKER_ID", str(DEFAULT_TRACKER_ID)))

# Source: sibling directory of "backend" → ../../Monthly Expense.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML_DIR = BACKEND_ROOT.parent / "Monthly Expense"
HTML_DIR = Path(
    os.environ.get("MIGRATION_HTML_DIR", str(DEFAULT_HTML_DIR))
).expanduser()

SKIPPED_LOG = BACKEND_ROOT / "scripts" / "migration_skipped.log"

# ---------------------------------------------------------------------------
# Filename filter
# ---------------------------------------------------------------------------
# Accept files matching "<Month name> <year>.html" with either the full month
# name or the standard 3-letter abbreviation, plus one explicit exception for
# the typo'd "Setember, 2021.html" (missing 'p' and stray comma) — that file
# holds the September 2021 ledger and is included by special-case.
MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTH_PATTERN = "|".join(MONTH_NAMES + MONTH_ABBR)
MONTHLY_FILE_RE = re.compile(
    rf"^(?:{MONTH_PATTERN})\s+\d{{4}}\.html$",
    re.IGNORECASE,
)
# Explicit allow-list for files that don't match the regex but should still be
# treated as monthly ledgers (typos, historical anomalies, etc.).
EXTRA_MONTHLY_FILES = frozenset({"Setember, 2021.html"})


def is_monthly_file(name: str) -> bool:
    """Return True if ``name`` is a monthly-ledger HTML filename."""
    return bool(MONTHLY_FILE_RE.match(name)) or name in EXTRA_MONTHLY_FILES

DATE_RE = re.compile(
    r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December) "
    r"\d{1,2}, \d{4}$"
)

# ---------------------------------------------------------------------------
# Category taxonomy (first-match-wins)
# ---------------------------------------------------------------------------
# Order matters — earlier entries beat later ones on description keyword overlap.
# 10 entries reused from modules/categories/service.py:DEFAULT_CATEGORIES plus
# 2 new ones (Education, Family Support). The last entry, "Uncategorized", is
# the fallback and is always present (mirrors seed.py:122-130).
CATEGORY_TAXONOMY: list[dict] = [
    {
        "name": "Health",
        "color": "#14B8A6",
        "keywords": [
            "doctor", "medicine", "arogga", "med ", "med.", "hospital",
            "pharmacy", "mom med", "check up", "checkup", "dental",
            "eye doctor", "follow up", "followup", "medic",
            "multivitamin", "vicks", "ibn sina",
        ],
    },
    {
        "name": "Education",
        "color": "#0EA5E9",
        "keywords": [
            "tution", "tuition", "book ", "books", "course fee", "course",
            "boitoi", "ielts", "class fee", "webener", "exam fee", "study",
            "learning", "school admission", "admission fee", "arpita's sir",
            "arpita's practical", "document printing charge",
            "passport",
        ],
    },
    {
        "name": "Subscriptions",
        "color": "#8B5CF6",
        "keywords": [
            "chorki", "hoichoi", "progga", "metlife", "doctime", "netflix",
            "spotify", "youtube premium", "prime", "subscription",
            "monthly plan", "pay premium", "premium ",
        ],
    },
    {
        "name": "Utilities",
        "color": "#06B6D4",
        "keywords": [
            "net bill", "recharge", "rent", "dish bill", "electricity",
            "electric bill", "gas bill", "water", "wifi", "moila", "internet",
            "broadband", "bl recharge", "flexiload", "flexi", "gas point",
            "electric point", "deposit machine", "trial deposit",
            "pureit", "saloon bill",  # deposit/trial rows live here in the source
            "sim ", "dpdc", "bank transfer fee", "house rent",
        ],
    },
    {
        "name": "Transport",
        "color": "#3B82F6",
        "keywords": [
            "uber", "pathao", "cng", "rickshaw", "fare", "ticket", "bus",
            "train", "ola", "petrol", "gas (vehicle)", "launch", "vat",
            "transport", "auto", "taxi", "metro", "riksha", "rikshaw",
            "fair", "updown", "up down",
        ],
    },
    {
        "name": "Coffee",
        "color": "#A855F7",
        "keywords": [
            "coffee", "starbucks", "cold brew", "espresso", "cappuccino",
        ],
    },
    {
        "name": "Dining",
        "color": "#F97316",
        "keywords": [
            "lunch", "dinner", "breakfast", "pizza", "burger", "fuchka",
            "sweets", "restaurant", "kitchen", "chai", "snacks", "khichuri",
            "biryani", "kacchi", "tea", "nasta", "muri", "maggie",
            "nimki", "momo", "foodpanda", "street food", "chocklet",
            "chocolate", "icecream", "kunafa", "singara", "samosa",
            "rooti", "ruti", "paratha", "pauruti", "kabab",
            "bakery", "bekary", "lipbum", "biscuite", "biscuit",
            "puri", "sandwich", "chinese", "evening snaks",
            "snaks", "snack", "evening snack", "evening snaks",
            "dinner", "matha",
        ],
    },
    {
        "name": "Groceries",
        "color": "#22C55E",
        "keywords": [
            "bazar", "unimart", "meat", "fish", "milk", "egg ", "eggs",
            "vegetable", "fruit", "rice", "মুরগি", "ডিম", "হাঁসের ডিম",
            "মাছ", "সবজি", "doi", "ghee", "semai", "khejur", "gur",
            "ata", "flour", "onion", "potato", "দুধ",
            "khassfood", "khaasfood", "khaassfood", "groceries",
            "grocerries", "grocceries", "egg", "molom", "oil",
            "suger", "soigner", "toothpaste", "vim", "savloon",
            "soap", "pollishwad", "rishoi", "boiled egg",
            "duck", "hilsha", "daab", "sorbot", "chilli",
            "turmeric", "curd", "bread",
        ],
    },
    {
        "name": "Shopping",
        "color": "#EAB308",
        "keywords": [
            "hoodie", "daraz", "sandal", "mr. diy", "saloon", "clothes",
            "shirt", "pant", "shoe", "t-shirt", "tshirt", "phone stand",
            "phone cover", "dress", "bag", "watch", "earphone", "ear buds",
            "winter", "winter products", "grid furniture", "gadget",
            "parlour", "parlor", "darz", "bracelet", "guiter", "guitar",
            "rfl ", "sanitary",
            "magic pipe", "ceiling fan", "ciling fan", "fan cover",
            "ups ", "battery",
        ],
    },
    {
        "name": "Family Support",
        "color": "#EF4444",
        "keywords": [
            "give mom", "give dad", "give baba", "provide mom", "provide dad",
            "bokshish", "tip", "tips", "baksheesh", "loan to", "give shamim",
            "loan from", "loan return", "eid bonus", "gift for family",
            "family gift", "nayan", "joynal", "give ", "provide ", "dad",
            "mom", "baba", "arpita ", "arpi ", "installment",
            "puja chanda", "chanda", "given mom", "for marketing",
            "arpita's", "arpita di", "arpita sir", "given arpita",
            "deposite arpita", "house helping", "house help", "mashi",
            "kajer mashi", "buy bread", "needy",
            "police ghush", "baksheesh",
        ],
    },
    {
        "name": "Entertainment",
        "color": "#EC4899",
        "keywords": [
            "outing", "movie", "cinema", "puja gift", "marriage gift",
            "wedding", "party", "concert", "trip", "tour", "outing plan",
            "hangout", "biye bari", "wed car", "photography", "protography",
            "reception", "babay shower", "baby shower", "iftar",
            "puja marketing", "puja visiting", "puja ghuraghuri",
            "durga puja", "newspaper order",
        ],
    },
    # FALLBACK — always last.
    {
        "name": "Uncategorized",
        "color": "#78716C",
        "keywords": [],
    },
]

CATEGORY_KEYWORD_INDEX: dict[str, list[str]] = {
    c["name"]: [k.lower() for k in c["keywords"]] for c in CATEGORY_TAXONOMY
}

# ---------------------------------------------------------------------------
# HTML parser — minimal stdlib-only walker for Google Sheets "Download as
# webpage" exports. Records each <tr>'s first 3 <td> text contents.
# ---------------------------------------------------------------------------


class WaffleParser(HTMLParser):
    """Collect ``(date_text, desc_text, amount_text)`` tuples from every row in a
    Google Sheets ``<table class="waffle">``. Only the first three data cells of
    each row are captured (columns A/B/C)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in_tr = False
        self._in_td = False
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    # Tag handlers ------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._in_tr = True
            self._current_row = []
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._current_cell = []

    def handle_startendtag(self, tag, attrs):
        # Treat self-closing <td ... /> same as open+close.
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "td" and self._current_row is not None and self._current_cell is not None:
            self._current_row.append("".join(self._current_cell).strip())
            self._in_td = False
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            self.rows.append(self._current_row)
            self._in_tr = False
            self._current_row = None

    # Text handler — only inside <td>, ignore <style>/<meta> etc.
    def handle_data(self, data):
        if self._in_td and self._current_cell is not None:
            self._current_cell.append(data)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _normalize_desc(raw: str) -> str:
    """Decode HTML entities, collapse whitespace, strip."""
    decoded = html_lib.unescape(raw)
    return re.sub(r"\s+", " ", decoded).strip()


def parse_month_html(path: Path) -> tuple[list[tuple[date, str, Decimal]], Decimal | None]:
    """Return (rows, grand_total) for one monthly HTML file.

    ``rows`` is a list of ``(date, description, amount)`` tuples with positive
    amounts only; header / "Grand Total" / placeholder / empty rows are
    excluded. ``grand_total`` is the parsed value of the sheet's "Grand Total"
    cell (column C of the totals row), or ``None`` if not found. Useful for
    verification in the summary.
    """
    parser = WaffleParser()
    parser.feed(path.read_text(encoding="utf-8"))

    rows: list[tuple[date, str, Decimal]] = []
    grand_total: Decimal | None = None

    for tr in parser.rows:
        if len(tr) < 3:
            continue
        date_text, desc_raw, amount_raw = tr[0], tr[1], tr[2]
        desc = _normalize_desc(desc_raw)

        if desc.lower() == "grand total" and not date_text:
            try:
                amt = _strip_amount(amount_raw)
                if amt is not None:
                    grand_total = amt
            except InvalidOperation:
                pass
            continue

        if not desc or desc.lower() in {"none", "nothing", "nope", "-"}:
            continue

        date_text = _normalize_desc(date_text)
        if not DATE_RE.match(date_text):
            continue
        try:
            d = datetime.strptime(date_text, "%A, %B %d, %Y").date()
        except ValueError:
            continue

        try:
            amt = _strip_amount(amount_raw)
        except InvalidOperation:
            continue
        if amt is None or amt == 0:
            continue

        rows.append((d, desc, amt))

    return rows, grand_total


def _strip_amount(raw: str) -> Decimal | None:
    """Strip ``৳``, thousands commas, whitespace, ``-`` prefix.

    Returns ``None`` if the cleaned value doesn't parse as a number.
    """
    cleaned = raw.replace("৳", "").replace(",", "").strip()
    if not cleaned:
        return None
    return Decimal(cleaned)


def classify(description: str) -> str:
    """Return the matching CATEGORY_TAXONOMY name, or 'Uncategorized'."""
    desc_lc = description.lower()
    for entry in CATEGORY_TAXONOMY:
        name = entry["name"]
        if name == "Uncategorized":
            continue
        for kw in CATEGORY_KEYWORD_INDEX[name]:
            if kw in desc_lc:
                return name
    return "Uncategorized"


# Database column limit — match modules/expenses/model.py:max_length=255.
DESCRIPTION_MAX_LEN = 255


def truncate_description(description: str) -> tuple[str, bool]:
    """Return (description, was_truncated). Trims to 255 chars with an
    ellipsis-free plain trim (matches the existing model constraint exactly).
    """
    if len(description) <= DESCRIPTION_MAX_LEN:
        return description, False
    return description[:DESCRIPTION_MAX_LEN], True


def log_truncated(filename: str, d: date, original: str, stored: str) -> None:
    """Append one row to the truncation log so we can find any descriptions
    that lost content during insert.
    """
    SKIPPED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SKIPPED_LOG.open("a", encoding="utf-8") as fh:
        fh.write(
            f"[TRUNCATED {len(original)}→{len(stored)}] {filename} | "
            f"{d.isoformat()} | {stored!r}\n"
        )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_or_create_category(
    session: Session, tracker_id: UUID, name: str, color: str
) -> Category:
    existing = session.exec(
        select(Category).where(
            Category.tracker_id == tracker_id, Category.name == name
        )
    ).first()
    if existing is not None:
        return existing
    cat = Category(tracker_id=tracker_id, name=name, color=color)
    session.add(cat)
    session.flush()  # populate cat.id before being referenced by Expense
    return cat


def _truncate(s: str, n: int = 30) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def log_skip(filename: str, d: date, amount: Decimal, description: str) -> None:
    """Append one skipped (refund) row to the skipped-log file."""
    line = (
        f"{filename} | {d.isoformat()} | {amount} | "
        f"\"{_truncate(html_lib.unescape(description), 60)}\"\n"
    )
    SKIPPED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SKIPPED_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _monthly_files(html_dir: Path) -> list[Path]:
    """Return monthly-ledger HTML files in deterministic order.

    Filters via :func:`is_monthly_file`: strict regex on
    "<Month name> <year>.html" (case-insensitive month, full or 3-letter
    abbreviation) plus an explicit allow-list for known-good historical files
    that don't match the regex (e.g. the typo'd ``Setember, 2021.html``).
    Excludes ``Name.html``, ``summery of costs.html``, and any other HTML file
    that is not a month ledger.
    """
    files: list[Path] = []
    for p in sorted(html_dir.glob("*.html")):
        if is_monthly_file(p.name):
            files.append(p)
    return files


def _print_summary(
    by_month: dict[str, dict[str, tuple[int, Decimal]]],
    grand_totals: dict[str, Decimal],
    parsed_totals: dict[str, Decimal],
) -> None:
    print("\n=== PER-MONTH SUMMARY ===")
    print(
        f"{'file':<32} {'parsed_total':>14} {'grand_total':>14} {'#rows':>6}"
    )
    print("-" * 72)
    for fname, by_cat in sorted(by_month.items()):
        rows = sum(n for n, _ in by_cat.values())
        gt = grand_totals.get(fname)
        pt = parsed_totals.get(fname)
        print(
            f"{_truncate(fname, 32):<32} "
            f"{(pt if pt is not None else Decimal(0)):>14} "
            f"{(gt if gt is not None else Decimal('NaN')):>14} "
            f"{rows:>6}"
        )

    print("\n=== PER-CATEGORY TOTALS ===")
    cat_totals: dict[str, tuple[int, Decimal]] = defaultdict(lambda: (0, Decimal(0)))
    for by_cat in by_month.values():
        for cat, (n, amt) in by_cat.items():
            existing_n, existing_amt = cat_totals[cat]
            cat_totals[cat] = (existing_n + n, existing_amt + amt)
    grand_n = sum(n for n, _ in cat_totals.values())
    grand_amt = sum(amt for _, amt in cat_totals.values())
    print(
        f"{'category':<22} {'count':>6} {'amount (BDT)':>16}   {'share':>7}"
    )
    for cat in [c["name"] for c in CATEGORY_TAXONOMY]:
        if cat in cat_totals:
            n, amt = cat_totals[cat]
            pct = (n / grand_n * 100) if grand_n else 0
            print(
                f"{cat:<22} {n:>6} {str(amt):>16}   {pct:>6.1f}%"
            )
    print(f"{'TOTAL':<22} {grand_n:>6} {str(grand_amt):>16}   100.0%")


def run(dry_run: bool) -> int:
    if not HTML_DIR.is_dir():
        print(f"ERROR: HTML_DIR does not exist: {HTML_DIR}")
        return 2

    engine = None
    if not dry_run:
        engine = create_engine(
            settings.database_url, echo=False, pool_pre_ping=True
        )

    by_month: dict[str, dict[str, tuple[int, Decimal]]] = {}
    grand_totals: dict[str, Decimal] = {}
    parsed_totals: dict[str, Decimal] = {}
    total_kept = total_dup = total_skipped = total_truncated = total_grand_mismatch = 0

    print(f"HTML_DIR  : {HTML_DIR}")
    print(f"USER_ID   : {USER_ID}")
    print(f"TRACKER_ID: {TRACKER_ID}")
    print(f"DRY RUN   : {dry_run}")
    print()

    # Sanity-check the filter: warn about any non-monthly files encountered.
    all_html = sorted(HTML_DIR.glob("*.html"))
    non_monthly = [p.name for p in all_html if not is_monthly_file(p.name)]
    if non_monthly:
        print(f"Skipping {len(non_monthly)} non-monthly file(s):")
        for n in non_monthly:
            print(f"  - {n}")
        print()

    files = _monthly_files(HTML_DIR)
    if not files:
        print("ERROR: no monthly HTML files matched the filter.")
        return 2
    print(f"Processing {len(files)} monthly file(s).")
    print()

    if dry_run:
        for fp in files:
            rows, grand_total = parse_month_html(fp)
            parsed_total = sum((amt for _, _, amt in rows), Decimal(0))
            positive = [r for r in rows if r[2] > 0]
            negative = [r for r in rows if r[2] < 0]
            grand_totals[fp.name] = (
                grand_total if grand_total is not None else Decimal(0)
            )
            parsed_totals[fp.name] = parsed_total
            per_cat: dict[str, tuple[int, Decimal]] = defaultdict(
                lambda: (0, Decimal(0))
            )
            for _, desc, amt in positive:
                cat = classify(desc)
                n, amt_existing = per_cat[cat]
                per_cat[cat] = (n + 1, amt_existing + amt)
            by_month[fp.name] = per_cat
            print(
                f"[dry-run] {fp.name}: rows={len(rows)} "
                f"positive={len(positive)} negative={len(negative)} "
                f"grand_total={grand_total}"
            )
        _print_summary(by_month, grand_totals, parsed_totals)
        return 0

    # Real run.
    with Session(engine) as session:
        user = session.get(User, USER_ID)
        if not user:
            print(f"ERROR: user {USER_ID} not found in DB.")
            return 2
        tracker = session.get(Tracker, TRACKER_ID)
        if not tracker:
            print(f"ERROR: tracker {TRACKER_ID} not found in DB.")
            return 2
        if tracker.user_id != USER_ID:
            print("ERROR: tracker does not belong to this user.")
            return 2
        print(f"User   : {user.name} ({user.email})")
        print(f"Tracker: {tracker.name} ({tracker.currency}) — {tracker.id}")
        print()

        cats: dict[str, Category] = {}
        for entry in CATEGORY_TAXONOMY:
            cat = get_or_create_category(
                session, tracker.id, entry["name"], entry["color"]
            )
            cats[entry["name"]] = cat
        print(f"Categories: {len(cats)} resolved")
        print()

        if SKIPPED_LOG.exists():
            SKIPPED_LOG.unlink()

        for fp in files:
            rows, grand_total = parse_month_html(fp)
            parsed_total = sum((amt for _, _, amt in rows), Decimal(0))
            per_cat: dict[str, tuple[int, Decimal]] = defaultdict(
                lambda: (0, Decimal(0))
            )
            kept = dup = skipped = truncated = 0
            for d, desc, amt in rows:
                if amt < 0:
                    skipped += 1
                    log_skip(fp.name, d, amt, desc)
                    continue
                # Truncate to the schema's max_length=255. Use the truncated
                # form for both the dedupe lookup AND the insert so re-runs
                # are idempotent.
                stored_desc, was_truncated = truncate_description(desc)
                if was_truncated:
                    truncated += 1
                    log_truncated(fp.name, d, desc, stored_desc)
                cat = cats[classify(desc)]
                already = session.exec(
                    select(Expense).where(
                        Expense.tracker_id == tracker.id,
                        Expense.date == d,
                        Expense.description == stored_desc,
                        Expense.amount == amt,
                    )
                ).first()
                if already is not None:
                    dup += 1
                    continue
                session.add(
                    Expense(
                        tracker_id=tracker.id,
                        category_id=cat.id,
                        amount=amt,
                        date=d,
                        description=stored_desc,
                        type="need",
                    )
                )
                kept += 1
                n, amt_existing = per_cat[cat.name]
                per_cat[cat.name] = (n + 1, amt_existing + amt)
            by_month[fp.name] = per_cat
            grand_totals[fp.name] = (
                grand_total if grand_total is not None else Decimal(0)
            )
            parsed_totals[fp.name] = parsed_total
            if grand_total is not None and parsed_total != grand_total:
                total_grand_mismatch += 1
                diff = parsed_total - grand_total
                print(
                    f"[mismatch] {fp.name}: parsed={parsed_total} "
                    f"grand={grand_total} diff={diff}"
                )
            total_kept += kept
            total_dup += dup
            total_skipped += skipped
            total_truncated += truncated
            print(
                f"[{fp.name}] parsed={len(rows)} "
                f"kept={kept} skipped={skipped} dup={dup} "
                f"truncated={truncated}"
            )
        session.commit()

    print()
    print(
        f"Done — kept={total_kept} dup={total_dup} skipped={total_skipped} "
        f"truncated={total_truncated} grand_mismatches={total_grand_mismatch}"
    )
    if SKIPPED_LOG.exists():
        print(f"Skipped (negative-amount) rows: {SKIPPED_LOG}")
    _print_summary(by_month, grand_totals, parsed_totals)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse all files and print per-month + per-category summary. "
        "Does NOT connect to the database or insert anything.",
    )
    args = parser.parse_args(argv)
    return run(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
