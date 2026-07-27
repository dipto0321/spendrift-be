"""Report schemas."""

import re
from datetime import date as date_type
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

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


# --------------------------------------------------------------------------- #
# Monthly insights snapshot (powers the Smart Report feature in the FE).
#
# Pure aggregation — no LLM work. The FE constructs the prompt locally
# (browser → provider directly using the user's own key, see front-end
# /ai settings) and asks the model to narrate this structured snapshot.
# --------------------------------------------------------------------------- #


_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class MonthlyInsightsRequest(BaseModel):
    """Body for `POST /trackers/{id}/reports/monthly-insights`.

    `month` is calendar month in `YYYY-MM` form. The endpoint returns a
    snapshot for that month plus deltas against the prior month.
    """

    month: str = Field(description="Calendar month, YYYY-MM")
    top_n_categories: int = Field(default=5, ge=1, le=20)
    top_n_expenses: int = Field(default=3, ge=1, le=10)

    @field_validator("month")
    @classmethod
    def _validate_month(cls, v: str) -> str:
        if not _MONTH_PATTERN.match(v):
            raise ValueError("month must be in YYYY-MM format")
        return v


class CategoryWithDelta(BaseModel):
    """One category's spend in the requested month plus its prior-month delta.

    `delta_pct` is rounded to the nearest integer percent; positive means
    spend went up vs the prior month.
    """

    category_id: UUID
    category_name: str
    category_color: str
    current_total: Decimal
    prior_total: Decimal
    delta_pct: int = Field(description="Prior-month delta, percent, rounded")
    count: int


class LargestExpenseItem(BaseModel):
    """One of the largest individual expenses in the requested month."""

    id: UUID
    amount: Decimal
    date: date_type
    description: str | None
    category_name: str
    type: str


class MonthlyInsightsSnapshot(BaseModel):
    """Structured numeric snapshot of a single calendar month for a tracker.

    The FE feeds this into the LLM prompt. Numbers are exact (sourced from
    real aggregation queries) — the model only writes the narrative.
    """

    tracker_id: UUID
    month: str
    currency: str
    total: Decimal
    prior_total: Decimal
    delta_pct: int = Field(description="Prior-month delta for the total, percent")
    top_categories: list[CategoryWithDelta]
    needs_wants: NeedsWantsSplit
    largest_expenses: list[LargestExpenseItem]
