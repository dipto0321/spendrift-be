"""Report router."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import get_current_user
from modules.dashboard.schema import NeedsWantsSplit
from modules.reports import service as report_service
from modules.reports.schema import (
    AnalyticsSummary,
    CategoryBreakdownItem,
    PeriodSpend,
    ReportPeriod,
    YearComparisonItem,
)
from modules.users.model import User

router = APIRouter(prefix="/trackers/{tracker_id}/reports", tags=["Reports"])


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """Aggregate statistics (total/min/max/avg/count) over a date range."""
    return report_service.get_summary(
        session, tracker_id, current_user.id, start_date, end_date
    )


@router.get("/spending", response_model=list[PeriodSpend])
def get_spending_over_time(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    period: ReportPeriod = Query(default=ReportPeriod.MONTHLY),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """Spending totals bucketed by day, week, month, or year."""
    return report_service.get_spending_over_time(
        session, tracker_id, current_user.id, period, start_date, end_date
    )


@router.get("/category-breakdown", response_model=list[CategoryBreakdownItem])
def get_category_breakdown(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """Per-category spending totals over a date range, largest first."""
    return report_service.get_category_breakdown(
        session, tracker_id, current_user.id, start_date, end_date
    )


@router.get("/needs-vs-wants", response_model=NeedsWantsSplit)
def get_needs_vs_wants(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    """Needs vs wants split over a date range."""
    return report_service.get_needs_vs_wants(
        session, tracker_id, current_user.id, start_date, end_date
    )


@router.get("/year-comparison", response_model=list[YearComparisonItem])
def get_year_comparison(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Yearly spending totals across the tracker's history."""
    return report_service.get_year_comparison(session, tracker_id, current_user.id)
