"""Budget threshold alerts router."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import get_current_user
from modules.budgets.schema import MONTH_PATTERN
from modules.budget_alerts import service as budget_alerts_service
from modules.budget_alerts.schema import BudgetAlertItem
from modules.users.model import User

router = APIRouter(prefix="/trackers/{tracker_id}/budget-alerts", tags=["Budget Alerts"])


@router.get("", response_model=list[BudgetAlertItem])
def get_budget_alerts(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: str | None = Query(
        default=None,
        pattern=MONTH_PATTERN,
        description="Month to check (YYYY-MM); defaults to the current month",
    ),
):
    """Per-category budget threshold status (ok/warning/exceeded) for a month."""
    return budget_alerts_service.get_budget_alerts(
        session, tracker_id, current_user.id, month=month
    )
