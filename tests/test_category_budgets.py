"""Tests for the category_budgets module (per-category budget allocation)."""

from decimal import Decimal

from fastapi.testclient import TestClient

from modules.categories import repo as category_repo
from modules.trackers.model import Tracker


def _budgets_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/budgets"


def _allocations_url(tracker_id, budget_id) -> str:
    return f"{_budgets_url(tracker_id)}/{budget_id}/category-allocations"


def _categories_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/categories"


def _expenses_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/expenses"


def _create_budget(client: TestClient, tracker_id, headers, **overrides) -> dict:
    payload = {
        "name": "June budget",
        "monthly_limit": "1000.00",
        "savings_target": "200.00",
        "month": "2026-06",
    }
    payload.update(overrides)
    response = client.post(_budgets_url(tracker_id), json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


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


def _two_category_ids(session, tracker: Tracker) -> tuple[str, str]:
    categories = category_repo.list_categories_by_tracker(session, tracker.id)
    return str(categories[0].id), str(categories[1].id)


# --------------------------------------------------------------------------- #
# List (empty) / replace (create)
# --------------------------------------------------------------------------- #


def test_list_allocations_empty(client: TestClient, tracker: Tracker, auth_headers):
    budget = _create_budget(client, tracker.id, auth_headers)
    response = client.get(
        _allocations_url(tracker.id, budget["id"]), headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == []


def test_replace_allocations_creates_and_returns(
    client: TestClient, tracker: Tracker, auth_headers, session
):
    budget = _create_budget(client, tracker.id, auth_headers)
    cat_a, cat_b = _two_category_ids(session, tracker)

    response = client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[
            {"category_id": cat_a, "allocated_amount": "600.00"},
            {"category_id": cat_b, "allocated_amount": "400.00"},
        ],
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 2
    by_category = {row["category_id"]: row for row in body}
    assert Decimal(str(by_category[cat_a]["allocated_amount"])) == Decimal("600.00")
    assert Decimal(str(by_category[cat_a]["actual_amount"])) == Decimal("0")
    assert by_category[cat_a]["percentage_used"] == 0
    assert by_category[cat_a]["category_name"]
    assert by_category[cat_a]["category_color"]


def test_replace_allocations_is_a_full_replace(
    client: TestClient, tracker: Tracker, auth_headers, session
):
    budget = _create_budget(client, tracker.id, auth_headers)
    cat_a, cat_b = _two_category_ids(session, tracker)

    client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[{"category_id": cat_a, "allocated_amount": "600.00"}],
        headers=auth_headers,
    )

    # Second PUT replaces the first set entirely — cat_a should be gone.
    response = client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[{"category_id": cat_b, "allocated_amount": "250.00"}],
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["category_id"] == cat_b

    listed = client.get(
        _allocations_url(tracker.id, budget["id"]), headers=auth_headers
    ).json()
    assert len(listed) == 1
    assert listed[0]["category_id"] == cat_b


def test_replace_allocations_reflects_actual_spend_and_percentage(
    client: TestClient, tracker: Tracker, auth_headers, session, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    _add_expense(client, tracker.id, auth_headers, category_id, "300.00", "2026-06-10")

    response = client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[{"category_id": category_id, "allocated_amount": "600.00"}],
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert Decimal(str(row["actual_amount"])) == Decimal("300.00")
    assert row["percentage_used"] == 50


def test_replace_allocations_percentage_can_exceed_100_when_overspent(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    _add_expense(client, tracker.id, auth_headers, category_id, "900.00", "2026-06-10")

    response = client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[{"category_id": category_id, "allocated_amount": "600.00"}],
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()[0]["percentage_used"] == 150


def test_replace_allocations_rejects_duplicate_category(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    response = client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[
            {"category_id": category_id, "allocated_amount": "100.00"},
            {"category_id": category_id, "allocated_amount": "200.00"},
        ],
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "duplicate" in response.json()["detail"].lower()


def test_replace_allocations_rejects_category_from_other_tracker(
    client: TestClient, tracker: Tracker, auth_headers
):
    budget = _create_budget(client, tracker.id, auth_headers)

    other = client.post(
        "/api/v1/trackers",
        json={"name": "Travel", "currency": "EUR"},
        headers=auth_headers,
    ).json()
    foreign_category_id = client.get(
        _categories_url(other["id"]), headers=auth_headers
    ).json()[0]["id"]

    response = client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[{"category_id": foreign_category_id, "allocated_amount": "100.00"}],
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "does not belong" in response.json()["detail"].lower()


def test_replace_allocations_rejects_nonpositive_amount(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    response = client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[{"category_id": category_id, "allocated_amount": "0.00"}],
        headers=auth_headers,
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #


def test_allocations_require_auth(client: TestClient, tracker: Tracker, auth_headers):
    budget = _create_budget(client, tracker.id, auth_headers)
    response = client.get(_allocations_url(tracker.id, budget["id"]))
    assert response.status_code == 401


def test_other_user_cannot_access_allocations(
    client: TestClient, tracker: Tracker, auth_headers, other_auth_headers
):
    budget = _create_budget(client, tracker.id, auth_headers)
    response = client.get(
        _allocations_url(tracker.id, budget["id"]), headers=other_auth_headers
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Cross-module: category deletion must respect existing allocations
# --------------------------------------------------------------------------- #


def test_delete_category_blocked_while_allocated(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    client.put(
        _allocations_url(tracker.id, budget["id"]),
        json=[{"category_id": category_id, "allocated_amount": "100.00"}],
        headers=auth_headers,
    )

    response = client.delete(
        f"{_categories_url(tracker.id)}/{category_id}", headers=auth_headers
    )
    assert response.status_code == 409
    assert "allocation" in response.json()["detail"].lower()
