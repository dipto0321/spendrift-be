"""Tests for the AI module (smart-paste expense parsing).

The LLM call is stubbed via the `get_llm` dependency override, so these
tests exercise ownership, prompt-output salvage rules, category name→id
mapping (against the tracker's seeded categories), and error mapping —
never a real Gemini call.
"""

from collections.abc import Generator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.llm import get_llm
from app.core.llm.base import LLMError, LLMNotConfiguredError
from app.main import app
from modules.trackers.model import Tracker


def _url(tracker_id: Any) -> str:
    return f"/api/v1/trackers/{tracker_id}/ai/parse-expenses"


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


def _request_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "text": "coffee 120, bus 40",
        "default_date": "2026-07-18",
    }
    body.update(overrides)
    return body


def _category_id_by_name(
    client: TestClient, auth_headers: dict[str, str], tracker: Tracker, name: str
) -> str:
    categories = client.get(
        f"/api/v1/trackers/{tracker.id}/categories", headers=auth_headers
    ).json()
    return next(c["id"] for c in categories if c["name"] == name)


def test_parse_requires_auth(client: TestClient, tracker: Tracker, stub_llm: _StubLLM):
    response = client.post(_url(tracker.id), json=_request_body())
    assert response.status_code == 401


def test_parse_unknown_tracker_is_404(
    client: TestClient, auth_headers, stub_llm: _StubLLM
):
    response = client.post(_url(uuid4()), json=_request_body(), headers=auth_headers)
    assert response.status_code == 404


def test_parse_happy_path_maps_seeded_categories_and_money(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    groceries_id = _category_id_by_name(client, auth_headers, tracker, "Groceries")
    stub_llm.payload = [
        {
            "amount": "120.50",
            "description": "bigbazar items",
            "category": "Groceries",
            "type": "need",
            "date": "2026-07-18",
        },
        {
            "amount": "40",
            "description": "bus",
            "category": None,
            "type": "need",
            "date": "2026-07-18",
        },
    ]

    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 200, response.text
    expenses = response.json()["expenses"]
    assert len(expenses) == 2

    first, second = expenses
    # Money stays a decimal string on the wire; the category name the model
    # returned is mapped to the tracker's real category id server-side.
    assert first["amount"] == "120.50"
    assert first["category_id"] == groceries_id
    assert first["date"] == "2026-07-18"
    # Unmapped category comes back as null for the review grid to resolve.
    assert second["category_id"] is None
    assert second["amount"] == "40.00"


def test_parse_maps_category_names_case_insensitively(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    transport_id = _category_id_by_name(client, auth_headers, tracker, "Transport")
    stub_llm.payload = [
        {
            "amount": "40",
            "description": "bus",
            "category": "tRANSPORT",
            "type": "need",
            "date": "2026-07-18",
        }
    ]

    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["expenses"][0]["category_id"] == transport_id


def test_parse_hallucinated_category_name_becomes_null(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    stub_llm.payload = [
        {
            "amount": "10",
            "description": "mystery",
            "category": "No Such Category",
            "type": "need",
            "date": "2026-07-18",
        }
    ]

    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["expenses"][0]["category_id"] is None


def test_parse_salvages_bad_dates_and_types(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    stub_llm.payload = [
        {
            "amount": "15",
            "description": "snack",
            "category": None,
            "type": "impulse",  # not need/want → defaults to need
            "date": "not-a-date",  # unparseable → default_date
        }
    ]

    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 200
    row = response.json()["expenses"][0]
    assert row["type"] == "need"
    assert row["date"] == "2026-07-18"


def test_parse_drops_unsalvageable_rows(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    stub_llm.payload = [
        {
            "amount": "not-money",
            "description": "broken",
            "category": None,
            "type": "need",
            "date": "2026-07-18",
        },
        {
            "amount": "-5",
            "description": "negative",
            "category": None,
            "type": "need",
            "date": "2026-07-18",
        },
        {
            "amount": "120",
            "description": "coffee",
            "category": None,
            "type": "want",
            "date": "2026-07-18",
        },
    ]

    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 200
    expenses = response.json()["expenses"]
    assert len(expenses) == 1
    assert expenses[0]["description"] == "coffee"


def test_parse_nothing_usable_is_422(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    stub_llm.payload = []
    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 422


def test_parse_non_list_llm_payload_is_502(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    stub_llm.payload = {"unexpected": "shape"}
    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 502


def test_parse_empty_text_is_422(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    response = client.post(
        _url(tracker.id), json=_request_body(text=""), headers=auth_headers
    )
    assert response.status_code == 422


def test_parse_provider_failure_is_502(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    stub_llm.error = LLMError("gemini exploded")
    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 502


def test_parse_missing_api_key_is_503(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    stub_llm.error = LLMNotConfiguredError("GEMINI_API_KEY not set")
    response = client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert response.status_code == 503


def test_prompt_includes_tracker_categories_and_default_date(
    client: TestClient, auth_headers, tracker: Tracker, stub_llm: _StubLLM
):
    stub_llm.payload = [
        {
            "amount": "1",
            "description": "x",
            "category": None,
            "type": "need",
            "date": "2026-07-18",
        }
    ]
    client.post(_url(tracker.id), json=_request_body(), headers=auth_headers)
    assert len(stub_llm.prompts) == 1
    prompt = stub_llm.prompts[0]
    # Category names come from the tracker's seeded categories, not the body.
    assert "Groceries" in prompt
    assert "Transport" in prompt
    assert "2026-07-18" in prompt
    assert "coffee 120, bus 40" in prompt
