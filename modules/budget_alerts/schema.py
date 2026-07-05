"""Budget threshold alert schemas."""

from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class BudgetAlertLevel(str, Enum):
    """Threshold status of a category's spend against its allocation."""

    OK = "ok"
    WARNING = "warning"
    EXCEEDED = "exceeded"


class BudgetAlertItem(BaseModel):
    """One category allocation's threshold status for the current month."""

    category_id: UUID
    category_name: str
    spent: Decimal
    limit: Decimal
    percentage: int
    level: BudgetAlertLevel
