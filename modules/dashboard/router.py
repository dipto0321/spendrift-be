"""Dashboard router."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import get_current_user
from modules.budgets.schema import MONTH_PATTERN
from modules.dashboard import service as dashboard_service
from modules.dashboard.schema import DashboardResponse
from modules.users.model import User

router = APIRouter(prefix="/trackers/{tracker_id}/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: str | None = Query(
        default=None,
        pattern=MONTH_PATTERN,
        description="Month to summarize (YYYY-MM); defaults to the current month",
    ),
):
    """Get the spending summary dashboard for a tracker month."""
    return dashboard_service.get_dashboard(
        session, tracker_id, current_user.id, month=month
    )
