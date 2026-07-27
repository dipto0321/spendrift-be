"""Report service - aggregation queries.

Aggregations live here (not in a repo) per the project convention for
report-style queries. Spending-over-time first aggregates per day in SQL
(portable across PostgreSQL and the SQLite test engine), then folds the
small per-day result into week/month/year buckets in Python.
"""

import logging
from datetime import date as date_type
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session, func, select

from modules.budgets.service import month_bounds
from modules.categories.model import Category
from modules.dashboard.schema import NeedsWantsSplit
from modules.expenses.model import Expense
from modules.expenses.schema import ExpenseType
from modules.reports.schema import (
    AnalyticsSummary,
    CategoryBreakdownItem,
    CategoryWithDelta,
    LargestExpenseItem,
    MonthlyInsightsSnapshot,
    PeriodSpend,
    ReportPeriod,
    YearComparisonItem,
)
from modules.trackers import service as tracker_service

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def _validate_range(start_date: date_type | None, end_date: date_type | None) -> None:
    if start_date and end_date and end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must not be before start_date",
        )


def _expense_filter(statement, tracker_id: UUID, start_date, end_date):
    statement = statement.where(Expense.tracker_id == tracker_id)
    if start_date is not None:
        statement = statement.where(Expense.date >= start_date)
    if end_date is not None:
        statement = statement.where(Expense.date <= end_date)
    return statement


def _prior_month(month: str) -> str:
    """Return the `YYYY-MM` immediately before `month` (handles year rollover)."""
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def _delta_pct(current: Decimal, prior: Decimal) -> int:
    """Integer percent change; positive means `current` is larger.

    Returns 0 when prior is 0 (no comparison possible).
    """
    if prior <= 0:
        return 0
    raw = (current - prior) / prior * 100
    return int(raw.to_integral_value(rounding=ROUND_HALF_UP))


def _month_inclusive_bounds(month: str) -> tuple[date_type, date_type]:
    """`[first_of_month, last_of_month]` — the inclusive shape expected by
    `_expense_filter` (which uses `<= end_date`).
    """
    start, exclusive_end = month_bounds(month)
    return start, exclusive_end - timedelta(days=1)


def get_summary(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> AnalyticsSummary:
    """Total/min/max/avg/count over the range."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    _validate_range(start_date, end_date)

    statement = _expense_filter(
        select(
            func.sum(Expense.amount),
            func.min(Expense.amount),
            func.max(Expense.amount),
            func.count(),
        ),
        tracker_id,
        start_date,
        end_date,
    )
    total, min_, max_, count = session.exec(statement).one()

    if not count:
        zero = Decimal("0")
        return AnalyticsSummary(total=zero, min=zero, max=zero, avg=zero, count=0)

    total = Decimal(total)
    avg = (total / count).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return AnalyticsSummary(
        total=total, min=Decimal(min_), max=Decimal(max_), avg=avg, count=count
    )


def _week_start(day: date_type) -> date_type:
    """Monday of the ISO week containing `day`."""
    return day - timedelta(days=day.weekday())


def _bucket_label(day: date_type, period: ReportPeriod) -> str:
    if period == ReportPeriod.DAILY:
        return day.isoformat()
    if period == ReportPeriod.WEEKLY:
        return _week_start(day).isoformat()
    if period == ReportPeriod.MONTHLY:
        return day.strftime("%Y-%m")
    return day.strftime("%Y")


def get_spending_over_time(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    period: ReportPeriod = ReportPeriod.MONTHLY,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> list[PeriodSpend]:
    """Spending totals bucketed by day, week, month, or year, sorted ascending.

    Only buckets containing expenses are returned (matching the frontend
    groupBy* helpers).
    """
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    _validate_range(start_date, end_date)

    statement = _expense_filter(
        select(Expense.date, func.sum(Expense.amount), func.count()).group_by(
            Expense.date
        ),
        tracker_id,
        start_date,
        end_date,
    )
    rows = session.exec(statement).all()

    buckets: dict[str, dict] = {}
    for day, total, count in rows:
        label = _bucket_label(day, period)
        bucket = buckets.setdefault(label, {"total": Decimal("0"), "count": 0})
        bucket["total"] += Decimal(total)
        bucket["count"] += count

    return [
        PeriodSpend(label=label, total=data["total"], count=data["count"])
        for label, data in sorted(buckets.items())
    ]


def get_category_breakdown(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> list[CategoryBreakdownItem]:
    """Per-category totals over the range, sorted by total descending."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    _validate_range(start_date, end_date)

    statement = _expense_filter(
        select(
            Category.id,
            Category.name,
            Category.color,
            func.sum(Expense.amount),
            func.count(),
        )
        .join(Expense, Expense.category_id == Category.id)  # type: ignore[arg-type]
        .group_by(Category.id, Category.name, Category.color)
        .order_by(func.sum(Expense.amount).desc()),
        tracker_id,
        start_date,
        end_date,
    )
    rows = session.exec(statement).all()

    grand_total = sum((Decimal(row[3]) for row in rows), Decimal("0"))

    return [
        CategoryBreakdownItem(
            category_id=row[0],
            category_name=row[1],
            category_color=row[2],
            total=Decimal(row[3]),
            percentage=(
                round(Decimal(row[3]) / grand_total * 100) if grand_total > 0 else 0
            ),
            count=row[4],
        )
        for row in rows
    ]


def get_needs_vs_wants(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
) -> NeedsWantsSplit:
    """Needs vs wants totals and percentages over the range."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    _validate_range(start_date, end_date)

    statement = _expense_filter(
        select(Expense.type, func.sum(Expense.amount)).group_by(Expense.type),
        tracker_id,
        start_date,
        end_date,
    )
    totals = {row[0]: Decimal(row[1]) for row in session.exec(statement).all()}
    needs = totals.get("need", Decimal("0"))
    wants = totals.get("want", Decimal("0"))
    total = needs + wants

    if total > 0:
        needs_pct = round(needs / total * 100)
        wants_pct = 100 - needs_pct
    else:
        needs_pct = wants_pct = 0

    return NeedsWantsSplit(
        needs_total=needs,
        wants_total=wants,
        needs_percentage=needs_pct,
        wants_percentage=wants_pct,
    )


def get_year_comparison(
    session: Session, tracker_id: UUID, user_id: UUID
) -> list[YearComparisonItem]:
    """Yearly totals across the tracker's history, sorted by year ascending.

    avg is total / 12 (monthly average), matching the frontend's
    multiYearComparison.
    """
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    rows = session.exec(
        select(
            func.extract("year", Expense.date),
            func.sum(Expense.amount),
            func.count(),
        )
        .where(Expense.tracker_id == tracker_id)
        .group_by(func.extract("year", Expense.date))
        .order_by(func.extract("year", Expense.date))
    ).all()

    return [
        YearComparisonItem(
            year=int(row[0]),
            total=Decimal(row[1]),
            avg=(Decimal(row[1]) / 12).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            count=row[2],
        )
        for row in rows
    ]


def get_monthly_insights_snapshot(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    month: str,
    top_n_categories: int = 5,
    top_n_expenses: int = 3,
) -> MonthlyInsightsSnapshot:
    """Structured numeric snapshot of a single calendar month for the LLM.

    Returns totals + prior-month deltas, the top N categories with deltas,
    a needs/wants split, and the top N largest individual expenses. Pure
    aggregation — no LLM work. The FE feeds this into a prompt and the
    browser calls the provider directly (see /ai settings).

    `month_bounds` returns `[first_of_month, first_of_next_month)`. The
    helpers here expect an inclusive `[start, end]` shape (they use
    `<= end_date`), so we use `_month_inclusive_bounds` instead.
    """
    tracker = tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    start, end = _month_inclusive_bounds(month)
    prior_month = _prior_month(month)
    prior_start, prior_end = _month_inclusive_bounds(prior_month)

    # Totals — `get_summary` does one round-trip per call.
    current_summary = get_summary(session, tracker_id, user_id, start, end)
    prior_summary = get_summary(session, tracker_id, user_id, prior_start, prior_end)
    needs_wants = get_needs_vs_wants(session, tracker_id, user_id, start, end)

    # Per-category totals for current month.
    current_breakdown = get_category_breakdown(session, tracker_id, user_id, start, end)
    prior_breakdown = get_category_breakdown(
        session, tracker_id, user_id, prior_start, prior_end
    )
    prior_by_category = {item.category_id: item.total for item in prior_breakdown}

    # Top N categories by current-month total, with prior-month delta.
    top_categories = [
        CategoryWithDelta(
            category_id=item.category_id,
            category_name=item.category_name,
            category_color=item.category_color,
            current_total=item.total,
            prior_total=prior_by_category.get(item.category_id, Decimal("0")),
            delta_pct=_delta_pct(
                item.total, prior_by_category.get(item.category_id, Decimal("0"))
            ),
            count=item.count,
        )
        for item in current_breakdown[:top_n_categories]
    ]

    # Top N largest individual expenses in the month.
    expense_rows = session.exec(
        _expense_filter(
            select(
                Expense.id,
                Expense.amount,
                Expense.date,
                Expense.description,
                Category.name,
                Expense.type,
            )
            .join(Category, Category.id == Expense.category_id)  # type: ignore[arg-type]
            .order_by(Expense.amount.desc())
            .limit(top_n_expenses),
            tracker_id,
            start,
            end,
        )
    ).all()
    largest_expenses = [
        LargestExpenseItem(
            id=row[0],
            amount=Decimal(row[1]),
            date=row[2],
            description=row[3],
            category_name=row[4],
            type=row[5] if isinstance(row[5], str) else ExpenseType(row[5]).value,
        )
        for row in expense_rows
    ]

    return MonthlyInsightsSnapshot(
        tracker_id=tracker.id,
        month=month,
        currency=tracker.currency,
        total=current_summary.total,
        prior_total=prior_summary.total,
        delta_pct=_delta_pct(current_summary.total, prior_summary.total),
        top_categories=top_categories,
        needs_wants=needs_wants,
        largest_expenses=largest_expenses,
    )
