"""Tests for the tax report module (Bangladesh IT-10BB).

The LLM call is stubbed via the `get_llm` dependency override, so these tests
exercise ownership, get-or-create idempotency, exact server-side summation,
LLM output salvage, and error mapping — never a real Gemini call.
"""

from collections.abc import Generator
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.llm import get_llm
from app.core.llm.base import LLMError, LLMNotConfiguredError
from app.main import app
from modules.categories import repo as category_repo
from modules.expenses.repo import create_expense
from modules.expenses.schema import ExpenseCreate, ExpenseType
from modules.trackers.model import Tracker


def _url(tracker_id: Any, fiscal_year: str | None = None) -> str:
    base = f"/api/v1/trackers/{tracker_id}/tax-reports"
    if fiscal_year is None:
        return base
    return f"{base}/{fiscal_year}"


def _category_id_by_name(session: Session, tracker: Tracker, name: str) -> UUID:
    categories = category_repo.list_categories_by_tracker(session, tracker.id)
    return next(c.id for c in categories if c.name == name)


def _create_expense(
    session: Session,
    tracker: Tracker,
    category_name: str,
    amount: Decimal,
    expense_date: date,
    description: str,
    expense_type: ExpenseType = ExpenseType.NEED,
) -> None:
    category_id = _category_id_by_name(session, tracker, category_name)
    create_expense(
        session,
        tracker.id,
        ExpenseCreate(
            amount=amount,
            category_id=category_id,
            date=expense_date,
            description=description,
            type=expense_type,
        ),
    )


class _StubLLM:
    """Returns a canned payload (or raises) instead of calling Gemini."""

    def __init__(
        self,
        payload: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.error = error
        self.prompts: list[str] = []

    def generate_structured(self, prompt: str, response_schema: dict[str, Any]) -> Any:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.fixture(name="stub_llm")
def stub_llm_fixture() -> Generator[_StubLLM, None, None]:
    stub = _StubLLM()
    app.dependency_overrides[get_llm] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_llm, None)


def test_create_requires_auth(client: TestClient, tracker: Tracker):
    response = client.post(_url(tracker.id), json={"fiscal_year": "2025-26"})
    assert response.status_code == 401


def test_unknown_tracker_is_404(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        _url(uuid4()), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert response.status_code == 404


def test_other_users_tracker_is_404(
    client: TestClient,
    tracker: Tracker,
    other_auth_headers: dict[str, str],
    stub_llm: _StubLLM,
):
    stub_llm.payload = []
    response = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=other_auth_headers
    )
    assert response.status_code == 404


def test_get_or_create_is_idempotent(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    session: Session,
    stub_llm: _StubLLM,
):
    _create_expense(
        session, tracker, "Groceries", Decimal("10.00"), date(2025, 8, 1), "items"
    )
    stub_llm.payload = [
        {"category": "Groceries", "head": "food_clothing_essentials"},
    ]

    first = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert first.status_code == 200
    first_id = first.json()["id"]

    second = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert second.status_code == 200
    assert second.json()["id"] == first_id

    # LLM was called exactly once because the second request reused the saved report.
    assert len(stub_llm.prompts) == 1


def test_happy_path_maps_categories_and_sums_exactly(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    session: Session,
    stub_llm: _StubLLM,
):
    _create_expense(
        session, tracker, "Groceries", Decimal("120.50"), date(2025, 8, 1), "big bazar"
    )
    _create_expense(
        session, tracker, "Groceries", Decimal("30.00"), date(2026, 3, 15), "tea stall"
    )
    _create_expense(
        session, tracker, "Transport", Decimal("45.00"), date(2025, 9, 10), "bus"
    )

    stub_llm.payload = [
        {"category": "Groceries", "head": "food_clothing_essentials"},
        {"category": "Transport", "head": "auto_transportation"},
    ]

    response = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert response.status_code == 200

    data = response.json()
    heads = {h["head_code"]: h for h in data["heads"]}
    assert data["fiscal_year"] == "2025-26"
    assert data["total_amount"] == "195.50"
    assert heads["food_clothing_essentials"]["amount"] == "150.50"
    assert heads["auto_transportation"]["amount"] == "45.00"

    # Category-level evidence is preserved.
    food_allocs = heads["food_clothing_essentials"]["category_allocations"]
    assert len(food_allocs) == 1
    assert food_allocs[0]["category_name"] == "Groceries"
    assert food_allocs[0]["amount"] == "150.50"


def test_salvage_unknown_category_dropped_and_unknown_head_becomes_other(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    session: Session,
    stub_llm: _StubLLM,
):
    _create_expense(
        session, tracker, "Groceries", Decimal("100.00"), date(2025, 8, 1), "items"
    )

    # "Rent" is not in the tracker's aggregates → dropped.
    # The duplicate "Groceries" row with an invalid head is ignored because a
    # valid mapping was already seen first.
    stub_llm.payload = [
        {"category": "Groceries", "head": "food_clothing_essentials"},
        {"category": "Rent", "head": "accommodation"},
        {"category": "Groceries", "head": "no_such_head"},
    ]

    response = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert response.status_code == 200

    heads = {h["head_code"]: h for h in response.json()["heads"]}
    assert heads["food_clothing_essentials"]["amount"] == "100.00"
    assert heads["accommodation"]["amount"] == "0.00"
    assert heads["other_expenses"]["amount"] == "0.00"


def test_no_expenses_returns_all_zero_and_skips_llm(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    stub_llm: _StubLLM,
):
    response = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert len(stub_llm.prompts) == 0

    data = response.json()
    assert data["total_amount"] == "0.00"
    assert len(data["heads"]) == 9
    for head in data["heads"]:
        assert head["amount"] == "0.00"
        assert head["category_allocations"] == []


def test_invalid_fiscal_year_is_422(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    stub_llm: _StubLLM,
):
    stub_llm.payload = []

    for bad in ["25-26", "2025-27", "2025-2026", "abc"]:
        response = client.post(
            _url(tracker.id), json={"fiscal_year": bad}, headers=auth_headers
        )
        assert response.status_code == 422, bad


def test_get_existing_report(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    stub_llm: _StubLLM,
):
    stub_llm.payload = [
        {"category": "Groceries", "head": "food_clothing_essentials"},
    ]
    created = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert created.status_code == 200

    fetched = client.get(_url(tracker.id, "2025-26"), headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created.json()["id"]


def test_update_heads_persists_manual_override_and_recomputes_total(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    stub_llm: _StubLLM,
):
    stub_llm.payload = []
    response = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert response.status_code == 200

    patch = client.patch(
        _url(tracker.id, "2025-26"),
        json={
            "heads": [
                {"head_code": "personal_loan_interest", "amount": "1250.00"},
                {"head_code": "environmental_surcharge", "amount": "500.00"},
            ]
        },
        headers=auth_headers,
    )
    assert patch.status_code == 200

    data = patch.json()
    heads = {h["head_code"]: h for h in data["heads"]}
    assert heads["personal_loan_interest"]["amount"] == "1250.00"
    assert heads["environmental_surcharge"]["amount"] == "500.00"
    assert data["total_amount"] == "1750.00"

    # Re-fetch confirms persistence.
    fetched = client.get(_url(tracker.id, "2025-26"), headers=auth_headers)
    assert fetched.json()["total_amount"] == "1750.00"


def test_update_heads_rejects_negative_amount_and_unknown_code(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    stub_llm: _StubLLM,
):
    stub_llm.payload = []
    client.post(_url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers)

    bad_amount = client.patch(
        _url(tracker.id, "2025-26"),
        json={"heads": [{"head_code": "food_clothing_essentials", "amount": "-10"}]},
        headers=auth_headers,
    )
    assert bad_amount.status_code == 422

    bad_code = client.patch(
        _url(tracker.id, "2025-26"),
        json={"heads": [{"head_code": "no_such_head", "amount": "10"}]},
        headers=auth_headers,
    )
    assert bad_code.status_code == 422


def test_regenerate_calls_llm_again(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    session: Session,
    stub_llm: _StubLLM,
):
    _create_expense(
        session, tracker, "Groceries", Decimal("80.00"), date(2025, 8, 1), "items"
    )

    stub_llm.payload = [
        {"category": "Groceries", "head": "food_clothing_essentials"},
    ]
    first = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert first.status_code == 200
    assert len(stub_llm.prompts) == 1

    stub_llm.payload = [
        {"category": "Groceries", "head": "other_expenses"},
    ]
    regenerated = client.post(
        _url(tracker.id, "2025-26") + "/regenerate", headers=auth_headers
    )
    assert regenerated.status_code == 200
    assert len(stub_llm.prompts) == 2

    heads = {h["head_code"]: h for h in regenerated.json()["heads"]}
    assert heads["other_expenses"]["amount"] == "80.00"
    assert heads["food_clothing_essentials"]["amount"] == "0.00"


def test_provider_error_is_502(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    session: Session,
    stub_llm: _StubLLM,
):
    _create_expense(
        session, tracker, "Groceries", Decimal("10.00"), date(2025, 8, 1), "items"
    )
    stub_llm.error = LLMError("gemini exploded")
    response = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert response.status_code == 502


def test_missing_api_key_is_503(
    client: TestClient,
    auth_headers: dict[str, str],
    tracker: Tracker,
    session: Session,
    stub_llm: _StubLLM,
):
    _create_expense(
        session, tracker, "Groceries", Decimal("10.00"), date(2025, 8, 1), "items"
    )
    stub_llm.error = LLMNotConfiguredError("GEMINI_API_KEY not set")
    response = client.post(
        _url(tracker.id), json={"fiscal_year": "2025-26"}, headers=auth_headers
    )
    assert response.status_code == 503
