"""Tax report schemas (Bangladesh IT-10BB)."""

import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TaxHeadCode(str, Enum):
    """The 9 fixed heads of the Bangladesh IT-10BB expense statement."""

    FOOD_CLOTHING_ESSENTIALS = "food_clothing_essentials"
    ACCOMMODATION = "accommodation"
    AUTO_TRANSPORTATION = "auto_transportation"
    HOUSEHOLD_UTILITY = "household_utility"
    EDUCATION = "education"
    FESTIVAL_SPECIAL = "festival_special"
    OTHER_EXPENSES = "other_expenses"
    PERSONAL_LOAN_INTEREST = "personal_loan_interest"
    ENVIRONMENTAL_SURCHARGE = "environmental_surcharge"


TAX_HEADS: list[dict[str, str]] = [
    {
        "code": TaxHeadCode.FOOD_CLOTHING_ESSENTIALS.value,
        "name": "Food, Clothing & Other Essentials",
        "description": "Daily food and meals, family clothing, and essential household/grocery purchases for the year.",
    },
    {
        "code": TaxHeadCode.ACCOMMODATION.value,
        "name": "Accommodation Expense",
        "description": "House rent, or repair and maintenance of the residence (enter 0 for an owned home).",
    },
    {
        "code": TaxHeadCode.AUTO_TRANSPORTATION.value,
        "name": "Auto & Transportation",
        "description": "Fuel and maintenance for your own vehicle, or bus, train, rideshare and daily commuting costs.",
    },
    {
        "code": TaxHeadCode.HOUSEHOLD_UTILITY.value,
        "name": "Household & Utility",
        "description": "Dish, internet, water, gas and electricity bills, plus wages for household help.",
    },
    {
        "code": TaxHeadCode.EDUCATION.value,
        "name": "Education Expenses",
        "description": "Books, stationery, and tuition/school/college/university fees for yourself or family.",
    },
    {
        "code": TaxHeadCode.FESTIVAL_SPECIAL.value,
        "name": "Festival & Special Expenses",
        "description": "Religious festivals (Eid/Puja etc.), family travel/vacations, and gifts to close relatives.",
    },
    {
        "code": TaxHeadCode.OTHER_EXPENSES.value,
        "name": "Any Other Expenses",
        "description": "Other costs not listed above, such as doctor/medical expenses or life-insurance premiums.",
    },
    {
        "code": TaxHeadCode.PERSONAL_LOAN_INTEREST.value,
        "name": "Interest on Personal Loan",
        "description": "Interest paid during the year on a personal loan (0 if none).",
    },
    {
        "code": TaxHeadCode.ENVIRONMENTAL_SURCHARGE.value,
        "name": "Environmental Surcharge",
        "description": "Surcharge on multiple personal vehicles/assets (normally 0).",
    },
]


_FISCAL_YEAR_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")


class TaxReportCreateRequest(BaseModel):
    """Request body for creating or fetching a tax report."""

    fiscal_year: str = Field(description="Bangladesh income year, YYYY-YY")

    @field_validator("fiscal_year")
    @classmethod
    def _validate_fiscal_year(cls, v: str) -> str:
        match = _FISCAL_YEAR_PATTERN.match(v)
        if not match:
            raise ValueError("fiscal_year must be in YYYY-YY format")
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        if end_year != (start_year + 1) % 100:
            raise ValueError("fiscal_year end year must equal start year + 1")
        return v


class TaxCategoryAllocation(BaseModel):
    """One category's contribution to a single IT-10BB head."""

    category_name: str
    amount: Decimal


class TaxHeadResponse(BaseModel):
    """One IT-10BB head with its total and supporting category breakdown."""

    head_code: str
    head_name: str
    description: str
    amount: Decimal
    category_allocations: list[TaxCategoryAllocation]


class TaxReportResponse(BaseModel):
    """Full IT-10BB report response."""

    id: UUID
    tracker_id: UUID
    fiscal_year: str
    start_date: date
    end_date: date
    currency: str
    total_amount: Decimal
    heads: list[TaxHeadResponse]
    created_at: datetime
    updated_at: datetime


class TaxReportSummaryResponse(BaseModel):
    """Lightweight summary for listing a tracker's saved tax reports."""

    id: UUID
    fiscal_year: str
    start_date: date
    end_date: date
    total_amount: Decimal
    created_at: datetime


class TaxHeadUpdate(BaseModel):
    """Manual amount override for one head."""

    head_code: TaxHeadCode
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class TaxReportUpdateRequest(BaseModel):
    """Request body for updating head amounts."""

    heads: list[TaxHeadUpdate]
