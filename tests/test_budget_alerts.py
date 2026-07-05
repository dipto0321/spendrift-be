"""Tests for the budget_alerts module (per-category threshold status)."""

from fastapi.testclient import TestClient

from modules.trackers.model import Tracker


def _alerts_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/budget-alerts"


def _budgets_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/budgets"


def _allocations_url(tracker_id, budget_id) -> str:
    return f"{_budgets_url(tracker_id)}/{budget_id}/category-allocations"


def _expenses_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/expenses"


def _create_budget(client: TestClient, tracker_id, headers, **overrides) -> dict:
    payload = {
        "name": "July budget",
        "monthly_limit": "1000.00",
        "savings_target": "200.00",
        "month": "2026-07",
    }
    payload.update(overrides)
    response = client.post(_budgets_url(tracker_id), json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _allocate(client: TestClient, tracker_id, budget_id, headers, category_id, amount: str):
    response = client.put(
        _allocations_url(tracker_id, budget_id),
        json=[{"category_id": category_id, "allocated_amount": amount}],
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _add_expense(
    client: TestClient, tracker_id, headers, category_id, amount: str, date: str
) -> None:
    response = client.post(
        _expenses_url(tracker_id),
        json={
            "amount": amount,
            "category_id": category_id,
            "date": date,
            "type": "need",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def test_no_budget_for_month_returns_empty(
    client: TestClient, tracker: Tracker, auth_headers
):
    response = client.get(
        _alerts_url(tracker.id), params={"month": "2026-07"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == []


def test_budget_with_no_allocations_returns_empty(
    client: TestClient, tracker: Tracker, auth_headers
):
    _create_budget(client, tracker.id, auth_headers)
    response = client.get(
        _alerts_url(tracker.id), params={"month": "2026-07"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == []


def test_under_80_percent_is_ok(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    _allocate(client, tracker.id, budget["id"], auth_headers, category_id, "600.00")
    _add_expense(client, tracker.id, auth_headers, category_id, "300.00", "2026-07-10")

    response = client.get(
        _alerts_url(tracker.id), params={"month": "2026-07"}, headers=auth_headers
    )
    assert response.status_code == 200
    item = response.json()[0]
    assert item["percentage"] == 50
    assert item["level"] == "ok"


def test_between_80_and_100_percent_is_warning(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    _allocate(client, tracker.id, budget["id"], auth_headers, category_id, "500.00")
    _add_expense(client, tracker.id, auth_headers, category_id, "450.00", "2026-07-10")

    response = client.get(
        _alerts_url(tracker.id), params={"month": "2026-07"}, headers=auth_headers
    )
    assert response.status_code == 200
    item = response.json()[0]
    assert item["percentage"] == 90
    assert item["level"] == "warning"


def test_over_100_percent_is_exceeded(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    _allocate(client, tracker.id, budget["id"], auth_headers, category_id, "400.00")
    _add_expense(client, tracker.id, auth_headers, category_id, "500.00", "2026-07-10")

    response = client.get(
        _alerts_url(tracker.id), params={"month": "2026-07"}, headers=auth_headers
    )
    assert response.status_code == 200
    item = response.json()[0]
    assert item["percentage"] == 125
    assert item["level"] == "exceeded"


def test_exactly_80_percent_is_warning_boundary(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    _allocate(client, tracker.id, budget["id"], auth_headers, category_id, "500.00")
    _add_expense(client, tracker.id, auth_headers, category_id, "400.00", "2026-07-10")

    response = client.get(
        _alerts_url(tracker.id), params={"month": "2026-07"}, headers=auth_headers
    )
    item = response.json()[0]
    assert item["percentage"] == 80
    assert item["level"] == "warning"


def test_alerts_require_auth(client: TestClient, tracker: Tracker):
    response = client.get(_alerts_url(tracker.id), params={"month": "2026-07"})
    assert response.status_code == 401


def test_other_user_cannot_access_alerts(
    client: TestClient, tracker: Tracker, auth_headers, other_auth_headers
):
    _create_budget(client, tracker.id, auth_headers)
    response = client.get(
        _alerts_url(tracker.id),
        params={"month": "2026-07"},
        headers=other_auth_headers,
    )
    assert response.status_code == 404
