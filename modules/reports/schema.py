"""Report schemas."""

from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from modules.dashboard.schema import NeedsWantsSplit  # noqa: F401  (re-exported)


class ReportPeriod(str, Enum):
    """Granularity for spending-over-time grouping."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class AnalyticsSummary(BaseModel):
    """Aggregate statistics over a set of expenses."""

    total: Decimal
    min: Decimal
    max: Decimal
    avg: Decimal
    count: int


class PeriodSpend(BaseModel):
    """Spending total for one period bucket.

    Label format depends on the period: daily -> YYYY-MM-DD,
    weekly -> ISO date of the week's Monday, monthly -> YYYY-MM,
    yearly -> YYYY.
    """

    label: str
    total: Decimal
    count: int


class CategoryBreakdownItem(BaseModel):
    """Spending total for one category, sorted by total descending."""

    category_id: UUID
    category_name: str
    category_color: str
    total: Decimal
    percentage: int = Field(description="Share of the range's spend, 0-100")
    count: int


class YearComparisonItem(BaseModel):
    """Yearly totals for the comparison chart, sorted by year ascending."""

    year: int
    total: Decimal
    avg: Decimal = Field(description="total / 12, rounded to 2 decimal places")
    count: int
