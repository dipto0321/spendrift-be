"""AI service: turn free text into candidate expense rows via the LLM.

Salvage philosophy: the model's output is untrusted input. Every row is
coerced field-by-field — recoverable problems (bad type, bad date) fall
back to safe defaults, unrecoverable ones (no positive amount, no
description) drop the row. The client's review grid is the real gate;
this layer only guarantees the rows it returns are well-formed.
"""

import logging
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.core.llm.base import LLMClient, LLMError, LLMNotConfiguredError
from modules.ai.schema import (
    ParsedExpense,
    ParseExpensesRequest,
    ParseExpensesResponse,
)
from modules.expenses.schema import ExpenseType

logger = logging.getLogger(__name__)

# Gemini structured-output schema: the model answers with a JSON array of
# rows. It returns the category *name* (from the list in the prompt) — not
# an id — so a hallucinated category can never map onto a real UUID.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "amount": {"type": "STRING"},
            "description": {"type": "STRING"},
            "category": {"type": "STRING", "nullable": True},
            "type": {"type": "STRING", "enum": ["need", "want"]},
            "date": {"type": "STRING"},
        },
        "required": ["amount", "description", "type", "date"],
    },
}

_PROMPT_TEMPLATE = """\
You extract personal expenses from informal notes.

Parse every expense in the text below into a JSON array. For each expense:
- "amount": the number as a plain decimal string, no currency symbols.
- "description": short label taken from the text, lowercase.
- "category": the best-matching name from this exact list, or null if none \
fits: {category_names}
- "type": "need" for essentials (food, transport, bills, health), "want" \
for discretionary spending — respect an explicit need/want written in the \
text.
- "date": ISO date (YYYY-MM-DD). Use {default_date} unless the text names \
another date.

Do not invent expenses that are not in the text. If the text contains no
expenses, return an empty array.

Text:
{text}
"""


def _build_prompt(payload: ParseExpensesRequest) -> str:
    names = ", ".join(c.name for c in payload.categories) or "(no categories)"
    return _PROMPT_TEMPLATE.format(
        category_names=names,
        default_date=payload.default_date.isoformat(),
        text=payload.text,
    )


def _coerce_amount(raw: Any) -> Decimal | None:
    try:
        amount = Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return amount if amount > 0 else None


def _coerce_date(raw: Any, fallback: date_type) -> date_type:
    try:
        return date_type.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return fallback


def _coerce_type(raw: Any) -> ExpenseType:
    try:
        return ExpenseType(str(raw).lower())
    except ValueError:
        return ExpenseType.NEED


def _salvage_row(
    row: Any,
    category_ids_by_name: dict[str, UUID],
    default_date: date_type,
) -> ParsedExpense | None:
    if not isinstance(row, dict):
        return None

    amount = _coerce_amount(row.get("amount"))
    description = str(row.get("description") or "").strip()
    if amount is None or not description:
        return None

    category_name = str(row.get("category") or "").strip().lower()
    return ParsedExpense(
        amount=amount,
        description=description[:255],
        category_id=category_ids_by_name.get(category_name),
        type=_coerce_type(row.get("type")),
        date=_coerce_date(row.get("date"), default_date),
    )


def parse_expenses(
    llm: LLMClient, payload: ParseExpensesRequest
) -> ParseExpensesResponse:
    """Ask the LLM for candidate rows and salvage its output."""
    try:
        raw = llm.generate_structured(_build_prompt(payload), _RESPONSE_SCHEMA)
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI parsing is not configured on this server",
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider could not process the request",
        ) from exc

    if not isinstance(raw, list):
        logger.warning("llm returned non-list payload: %r", type(raw))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider returned an unexpected response",
        )

    category_ids_by_name = {c.name.strip().lower(): c.id for c in payload.categories}
    expenses = [
        parsed
        for row in raw
        if (parsed := _salvage_row(row, category_ids_by_name, payload.default_date))
        is not None
    ]

    if not expenses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not find any expenses in the text",
        )

    return ParseExpensesResponse(expenses=expenses)
