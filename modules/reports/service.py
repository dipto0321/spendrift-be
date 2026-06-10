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

from modules.categories.model import Category
from modules.dashboard.schema import NeedsWantsSplit
from modules.expenses.model import Expense
from modules.reports.schema import (
    AnalyticsSummary,
    CategoryBreakdownItem,
    PeriodSpend,
    ReportPeriod,
    YearComparisonItem,
)
from modules.trackers import service as tracker_service

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


def _validate_range(
    start_date: date_type | None, end_date: date_type | None
) -> None:
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
    """Spending totals bucketed by week, month, or year, sorted ascending.

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
