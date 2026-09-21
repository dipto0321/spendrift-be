"""Tax report service - aggregation, LLM classification, and persistence.

The LLM only maps category names to IT-10BB head codes; every amount is
summed server-side from the real expense rows. Untrusted LLM output is
salvaged the same way as the smart-paste AI feature.
"""

import logging
from datetime import date as date_type
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session, func, select

from app.core.llm.base import LLMClient, LLMError, LLMNotConfiguredError
from modules.categories.model import Category
from modules.expenses.model import Expense
from modules.tax.model import TaxReport, TaxReportHead
from modules.tax import repo as tax_repo
from modules.tax.schema import (
    TAX_HEADS,
    TaxCategoryAllocation,
    TaxHeadCode,
    TaxHeadResponse,
    TaxReportCreateRequest,
    TaxReportResponse,
    TaxReportSummaryResponse,
    TaxReportUpdateRequest,
)
from modules.trackers import service as tracker_service

logger = logging.getLogger(__name__)

_HEAD_BY_CODE = {h["code"]: h for h in TAX_HEADS}
_OTHER_HEAD = TaxHeadCode.OTHER_EXPENSES.value

# Gemini structured-output schema: the model answers with an array of
# category → head mappings. It returns the head *code*, not a name, so a
# hallucinated head can never map onto a real bucket.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "category": {"type": "STRING"},
            "head": {"type": "STRING", "enum": [h["code"] for h in TAX_HEADS]},
        },
        "required": ["category", "head"],
    },
}

_PROMPT_TEMPLATE = """\
You categorize personal expenses into the 9 heads of the Bangladesh IT-10BB income-tax expense statement.

Available heads (use the exact "code" value for each mapping):
{heads}

Rules:
- Map every listed category below to EXACTLY ONE head by its "code".
- Use "other_expenses" when nothing else fits or you are unsure.
- Keep "personal_loan_interest" and "environmental_surcharge" only if a category clearly matches them; normally both should receive no categories.
- Respect the currency: {currency}.

Categories (name | total | expense count | sample descriptions):
{categories}

Reply with a JSON array of {{"category": <name>, "head": <code>}} covering every category listed above.
"""


def _fiscal_year_bounds(fiscal_year: str) -> tuple[date_type, date_type]:
    """Income year YYYY-YY → [Jul 1 YYYY, Jun 30 YYYY+1]."""
    start_year = int(fiscal_year[:4])
    return date_type(start_year, 7, 1), date_type(start_year + 1, 6, 30)


def _aggregate_by_category(
    session: Session, tracker_id: UUID, start: date_type, end: date_type
) -> list[dict[str, Any]]:
    """Sum/count expenses per category over the inclusive date range."""
    rows = session.exec(
        select(Category.name, func.sum(Expense.amount), func.count())
        .join(Expense, Expense.category_id == Category.id)  # type: ignore[arg-type]
        .where(Expense.tracker_id == tracker_id)
        .where(Expense.date >= start)
        .where(Expense.date <= end)
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
    ).all()

    aggregates = []
    for name, total, count in rows:
        aggregates.append(
            {
                "category_name": name,
                "total": Decimal(total),
                "count": count,
                "samples": _sample_descriptions(session, tracker_id, name, start, end),
            }
        )
    return aggregates


def _sample_descriptions(
    session: Session,
    tracker_id: UUID,
    category_name: str,
    start: date_type,
    end: date_type,
) -> list[str]:
    """Up to 5 sample descriptions for a category to help classification."""
    rows = session.exec(
        select(Expense.description)
        .join(Category, Category.id == Expense.category_id)  # type: ignore[arg-type]
        .where(Expense.tracker_id == tracker_id)
        .where(Category.name == category_name)
        .where(Expense.date >= start)
        .where(Expense.date <= end)
        .where(Expense.description.is_not(None))  # type: ignore[union-attr]
        .order_by(Expense.amount.desc())  # type: ignore[attr-defined]
        .limit(5)
    ).all()
    return [str(r) for r in rows if r]


def _build_prompt(aggregates: list[dict[str, Any]], currency: str) -> str:
    head_lines = [f"- {h['code']}: {h['name']} — {h['description']}" for h in TAX_HEADS]
    category_lines = []
    for agg in aggregates:
        samples = ", ".join(agg["samples"]) or "(no descriptions)"
        category_lines.append(
            f"- {agg['category_name']} | {agg['total']} | {agg['count']} | {samples}"
        )
    return _PROMPT_TEMPLATE.format(
        heads="\n".join(head_lines),
        currency=currency,
        categories="\n".join(category_lines),
    )


def _classify_categories(
    llm: LLMClient, aggregates: list[dict[str, Any]], currency: str
) -> dict[str, str]:
    """Ask the LLM to map each category to an IT-10BB head code."""
    raw = llm.generate_structured(_build_prompt(aggregates, currency), _RESPONSE_SCHEMA)

    if not isinstance(raw, list):
        logger.warning("llm returned non-list payload: %r", type(raw))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider returned an unexpected response",
        )

    valid_names = {a["category_name"] for a in aggregates}
    mapping: dict[str, str] = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        category = str(row.get("category") or "").strip()
        head = str(row.get("head") or "").strip()
        if category not in valid_names:
            continue
        if category in mapping:
            # Already have a valid mapping for this category; ignore later rows.
            continue
        if head in _HEAD_BY_CODE:
            mapping[category] = head
        else:
            mapping[category] = _OTHER_HEAD

    # Any category the LLM omitted defaults to "other_expenses".
    for name in valid_names:
        mapping.setdefault(name, _OTHER_HEAD)
    return mapping


def _sum_by_head(
    aggregates: list[dict[str, Any]], mapping: dict[str, str]
) -> dict[str, list[dict[str, Decimal]]]:
    """Group category totals per IT-10BB head for exact server-side summation."""
    allocations: dict[str, list[dict[str, Decimal]]] = {
        h["code"]: [] for h in TAX_HEADS
    }
    for agg in aggregates:
        head = mapping.get(agg["category_name"], _OTHER_HEAD)
        allocations[head].append(
            {"category_name": agg["category_name"], "amount": agg["total"]}
        )
    return allocations


def _to_head_rows(
    report_id: UUID, allocations: dict[str, list[dict[str, Decimal]]]
) -> list[TaxReportHead]:
    """Build TaxReportHead rows (unsaved) for all 9 heads, including zeros."""
    heads = []
    for h in TAX_HEADS:
        code = h["code"]
        allocs = allocations.get(code, [])
        amount = sum((a["amount"] for a in allocs), Decimal("0"))
        heads.append(
            TaxReportHead(
                report_id=report_id,
                head_code=code,
                amount=amount,
                category_allocations=[
                    {"category_name": a["category_name"], "amount": str(a["amount"])}
                    for a in allocs
                ],
            )
        )
    return heads


def _sort_heads(heads: list[TaxReportHead]) -> list[TaxReportHead]:
    """Return heads in the canonical IT-10BB order."""
    order = {h["code"]: i for i, h in enumerate(TAX_HEADS)}
    return sorted(heads, key=lambda h: order.get(h.head_code, 999))


def _to_response(report: TaxReport, heads: list[TaxReportHead]) -> TaxReportResponse:
    """Build the wire response from a report and its heads."""
    head_responses = []
    for head in _sort_heads(heads):
        meta = _HEAD_BY_CODE.get(head.head_code)
        if meta is None:
            continue
        allocations = [
            TaxCategoryAllocation(
                category_name=a["category_name"], amount=Decimal(a["amount"])
            )
            for a in (head.category_allocations or [])
        ]
        head_responses.append(
            TaxHeadResponse(
                head_code=head.head_code,
                head_name=meta["name"],
                description=meta["description"],
                amount=head.amount,
                category_allocations=allocations,
            )
        )

    return TaxReportResponse(
        id=report.id,
        tracker_id=report.tracker_id,
        fiscal_year=report.fiscal_year,
        start_date=report.start_date,
        end_date=report.end_date,
        currency=report.currency,
        total_amount=report.total_amount,
        heads=head_responses,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def _generate(
    session: Session,
    llm: LLMClient,
    tracker_id: UUID,
    currency: str,
    fiscal_year: str,
) -> tuple[TaxReport, list[TaxReportHead]]:
    """Aggregate, classify, and persist a brand-new tax report."""
    start, end = _fiscal_year_bounds(fiscal_year)
    aggregates = _aggregate_by_category(session, tracker_id, start, end)

    mapping: dict[str, str] = {}
    if aggregates:
        mapping = _classify_categories(llm, aggregates, currency)

    allocations = _sum_by_head(aggregates, mapping)
    total = sum(
        (a["amount"] for allocs in allocations.values() for a in allocs),
        Decimal("0"),
    )

    report = tax_repo.create_report(
        session,
        tracker_id=tracker_id,
        fiscal_year=fiscal_year,
        start_date=start,
        end_date=end,
        currency=currency,
        total_amount=total,
    )
    heads = _to_head_rows(report.id, allocations)
    tax_repo.add_heads(session, heads)
    return report, heads


def get_or_create(
    session: Session,
    llm: LLMClient,
    tracker_id: UUID,
    user_id: UUID,
    payload: TaxReportCreateRequest,
) -> TaxReportResponse:
    """Return an existing report or generate and persist a new one."""
    tracker = tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    existing = tax_repo.get_report_by_fiscal_year(
        session, tracker_id, payload.fiscal_year
    )
    if existing:
        heads = tax_repo.list_heads_by_report(session, existing.id)
        return _to_response(existing, heads)

    try:
        report, heads = _generate(
            session, llm, tracker_id, tracker.currency, payload.fiscal_year
        )
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI classification is not configured on this server",
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider could not process the request",
        ) from exc

    return _to_response(report, heads)


def get_report(
    session: Session, tracker_id: UUID, user_id: UUID, fiscal_year: str
) -> TaxReportResponse:
    """Fetch an existing report by fiscal year."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    report = tax_repo.get_report_by_fiscal_year(session, tracker_id, fiscal_year)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tax report not found"
        )
    heads = tax_repo.list_heads_by_report(session, report.id)
    return _to_response(report, heads)


def list_reports(
    session: Session, tracker_id: UUID, user_id: UUID
) -> list[TaxReportSummaryResponse]:
    """List summaries of a tracker's saved tax reports."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    reports = tax_repo.list_reports_by_tracker(session, tracker_id)
    return [
        TaxReportSummaryResponse(
            id=r.id,
            fiscal_year=r.fiscal_year,
            start_date=r.start_date,
            end_date=r.end_date,
            total_amount=r.total_amount,
            created_at=r.created_at,
        )
        for r in reports
    ]


def update_heads(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    fiscal_year: str,
    payload: TaxReportUpdateRequest,
) -> TaxReportResponse:
    """Apply manual amount overrides to selected heads."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    report = tax_repo.get_report_by_fiscal_year(session, tracker_id, fiscal_year)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tax report not found"
        )

    for update in payload.heads:
        head = tax_repo.get_head_by_code(session, report.id, update.head_code.value)
        if head is None:
            continue
        head.amount = update.amount
        session.add(head)
    session.commit()

    heads = tax_repo.list_heads_by_report(session, report.id)
    total = sum((h.amount for h in heads), Decimal("0"))
    tax_repo.update_report_total(session, report, total)
    return _to_response(report, heads)


def regenerate(
    session: Session,
    llm: LLMClient,
    tracker_id: UUID,
    user_id: UUID,
    fiscal_year: str,
) -> TaxReportResponse:
    """Force re-aggregation and re-classification of an existing report."""
    tracker = tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    report = tax_repo.get_report_by_fiscal_year(session, tracker_id, fiscal_year)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tax report not found"
        )

    try:
        tax_repo.delete_heads_by_report(session, report.id)
        aggregates = _aggregate_by_category(
            session, tracker_id, report.start_date, report.end_date
        )
        mapping = (
            _classify_categories(llm, aggregates, tracker.currency)
            if aggregates
            else {}
        )
        allocations = _sum_by_head(aggregates, mapping)
        total = sum(
            (a["amount"] for allocs in allocations.values() for a in allocs),
            Decimal("0"),
        )
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI classification is not configured on this server",
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider could not process the request",
        ) from exc

    heads = _to_head_rows(report.id, allocations)
    tax_repo.add_heads(session, heads)
    tax_repo.update_report_total(session, report, total)
    return _to_response(report, heads)
