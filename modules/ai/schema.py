"""AI schemas (smart-paste expense parsing).

No model.py/repo.py in this module: parsing is stateless — candidate
rows are returned to the client for review and persisted (or not)
through the normal expenses endpoints.
"""

from datetime import date as date_type
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from modules.expenses.schema import ExpenseType


class ParseExpensesRequest(BaseModel):
    """Free text to parse. Categories come from the tracker, not the client."""

    text: str = Field(min_length=1, max_length=4000)
    default_date: date_type


class ParsedExpense(BaseModel):
    """One candidate row — never persisted here (review-grid only)."""

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str = Field(min_length=1, max_length=255)
    category_id: UUID | None
    type: ExpenseType
    date: date_type


class ParseExpensesResponse(BaseModel):
    """Candidate rows for the client's review grid."""

    expenses: list[ParsedExpense]
