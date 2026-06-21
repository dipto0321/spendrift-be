"""Dashboard schemas."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from modules.budgets.schema import SavingsHealth


class CategorySpend(BaseModel):
    """Spending total for a single category within the month."""

    category_id: UUID
    name: str
    color: str
    total: Decimal
    percentage: int = Field(description="Share of the month's spend, 0-100")


class NeedsWantsSplit(BaseModel):
    """Needs vs wants totals and percentages for the month."""

    needs_total: Decimal
    wants_total: Decimal
    needs_percentage: int
    wants_percentage: int


class BudgetSnapshot(BaseModel):
    """Status of the month's budget, if one exists."""

    budget_id: UUID
    name: str
    monthly_limit: Decimal
    savings_target: Decimal
    spent: Decimal
    remaining: Decimal
    savings_progress: int
    savings_health: SavingsHealth
    is_over_budget: bool


class DashboardResponse(BaseModel):
    """Tracker dashboard summary for one month."""

    month: str
    total_spent: Decimal
    expense_count: int
    needs_wants: NeedsWantsSplit
    top_categories: list[CategorySpend]
    budget: BudgetSnapshot | None
