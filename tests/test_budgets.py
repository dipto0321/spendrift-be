"""Tests for the budgets module."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session

from modules.trackers.model import Tracker


def _budgets_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/budgets"


def _expenses_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/expenses"


def _make_payload(**overrides) -> dict:
    payload = {
        "name": "June budget",
        "monthly_limit": "1000.00",
        "savings_target": "200.00",
        "month": "2026-06",
    }
    payload.update(overrides)
    return payload


def _create_budget(client: TestClient, tracker_id, headers, **overrides) -> dict:
    response = client.post(
        _budgets_url(tracker_id), json=_make_payload(**overrides), headers=headers
    )
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


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


def test_create_budget(client: TestClient, tracker: Tracker, auth_headers):
    body = _create_budget(client, tracker.id, auth_headers)
    assert body["name"] == "June budget"
    assert Decimal(str(body["monthly_limit"])) == Decimal("1000.00")
    assert Decimal(str(body["savings_target"])) == Decimal("200.00")
    assert body["month"] == "2026-06"
    assert body["tracker_id"] == str(tracker.id)
    assert "id" in body and "created_at" in body


def test_create_budget_duplicate_month_fails(
    client: TestClient, tracker: Tracker, auth_headers
):
    _create_budget(client, tracker.id, auth_headers)
    response = client.post(
        _budgets_url(tracker.id), json=_make_payload(), headers=auth_headers
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_create_budget_invalid_month_format(
    client: TestClient, tracker: Tracker, auth_headers
):
    for bad_month in ["2026-13", "2026-1", "June 2026", "2026/06", "26-06"]:
        response = client.post(
            _budgets_url(tracker.id),
            json=_make_payload(month=bad_month),
            headers=auth_headers,
        )
        assert response.status_code == 422, bad_month


def test_create_budget_rejects_nonpositive_limit(
    client: TestClient, tracker: Tracker, auth_headers
):
    response = client.post(
        _budgets_url(tracker.id),
        json=_make_payload(monthly_limit="0.00"),
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_list_budgets_with_month_filter(
    client: TestClient, tracker: Tracker, auth_headers
):
    _create_budget(client, tracker.id, auth_headers, month="2026-05", name="May")
    _create_budget(client, tracker.id, auth_headers, month="2026-06", name="June")

    response = client.get(_budgets_url(tracker.id), headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = client.get(
        _budgets_url(tracker.id), params={"month": "2026-05"}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "May"


def test_get_budget(client: TestClient, tracker: Tracker, auth_headers):
    created = _create_budget(client, tracker.id, auth_headers)
    response = client.get(
        f"{_budgets_url(tracker.id)}/{created['id']}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_update_budget(client: TestClient, tracker: Tracker, auth_headers):
    created = _create_budget(client, tracker.id, auth_headers)
    response = client.patch(
        f"{_budgets_url(tracker.id)}/{created['id']}",
        json={"name": "Renamed", "monthly_limit": "1500.00"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert Decimal(str(body["monthly_limit"])) == Decimal("1500.00")
    assert body["month"] == "2026-06"  # unchanged


def test_update_budget_to_taken_month_fails(
    client: TestClient, tracker: Tracker, auth_headers
):
    _create_budget(client, tracker.id, auth_headers, month="2026-05")
    other = _create_budget(client, tracker.id, auth_headers, month="2026-06")
    response = client.patch(
        f"{_budgets_url(tracker.id)}/{other['id']}",
        json={"month": "2026-05"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_delete_budget(client: TestClient, tracker: Tracker, auth_headers):
    created = _create_budget(client, tracker.id, auth_headers)
    response = client.delete(
        f"{_budgets_url(tracker.id)}/{created['id']}", headers=auth_headers
    )
    assert response.status_code == 204
    response = client.get(
        f"{_budgets_url(tracker.id)}/{created['id']}", headers=auth_headers
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #


def test_budgets_require_auth(client: TestClient, tracker: Tracker):
    response = client.get(_budgets_url(tracker.id))
    assert response.status_code == 401


def test_other_user_cannot_access_budget(
    client: TestClient, tracker: Tracker, auth_headers, other_auth_headers
):
    created = _create_budget(client, tracker.id, auth_headers)

    # Tracker (and budget) belong to the first user; both list and detail 404.
    response = client.get(_budgets_url(tracker.id), headers=other_auth_headers)
    assert response.status_code == 404

    response = client.get(
        f"{_budgets_url(tracker.id)}/{created['id']}", headers=other_auth_headers
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Status computation (mirrors front-end calculateBudgetStatus semantics)
# --------------------------------------------------------------------------- #


def _get_status(client, tracker_id, budget_id, headers) -> dict:
    response = client.get(
        f"{_budgets_url(tracker_id)}/{budget_id}/status", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_status_no_expenses(client: TestClient, tracker: Tracker, auth_headers):
    budget = _create_budget(client, tracker.id, auth_headers)
    status = _get_status(client, tracker.id, budget["id"], auth_headers)
    assert Decimal(str(status["spent"])) == Decimal("0")
    assert Decimal(str(status["remaining"])) == Decimal("1000.00")
    assert status["savings_progress"] == 100
    assert status["savings_health"] == "green"
    assert status["is_over_budget"] is False


def test_status_sums_only_expenses_in_month(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    _add_expense(client, tracker.id, auth_headers, category_id, "100.00", "2026-06-01")
    _add_expense(client, tracker.id, auth_headers, category_id, "50.00", "2026-06-30")
    # outside the budget month - must be excluded
    _add_expense(client, tracker.id, auth_headers, category_id, "999.00", "2026-05-31")
    _add_expense(client, tracker.id, auth_headers, category_id, "999.00", "2026-07-01")

    status = _get_status(client, tracker.id, budget["id"], auth_headers)
    assert Decimal(str(status["spent"])) == Decimal("150.00")
    assert Decimal(str(status["remaining"])) == Decimal("850.00")
    assert status["is_over_budget"] is False
    # remaining 850 >= target 200 -> green
    assert status["savings_health"] == "green"


def test_status_yellow_when_savings_at_risk(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    # spent 85%: remaining 150 < target 200, spent% between 80 and 95 -> yellow
    budget = _create_budget(client, tracker.id, auth_headers)
    _add_expense(client, tracker.id, auth_headers, category_id, "850.00", "2026-06-10")

    status = _get_status(client, tracker.id, budget["id"], auth_headers)
    assert status["savings_health"] == "yellow"
    # progress = remaining/target = 150/200 -> 75%
    assert status["savings_progress"] == 75
    assert status["is_over_budget"] is False


def test_status_red_near_limit(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    # spent 96%: remaining 40 < target, spent% >= 95 -> red (but not over)
    budget = _create_budget(client, tracker.id, auth_headers)
    _add_expense(client, tracker.id, auth_headers, category_id, "960.00", "2026-06-10")

    status = _get_status(client, tracker.id, budget["id"], auth_headers)
    assert status["savings_health"] == "red"
    assert status["is_over_budget"] is False


def test_status_over_budget(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    budget = _create_budget(client, tracker.id, auth_headers)
    _add_expense(client, tracker.id, auth_headers, category_id, "1100.00", "2026-06-15")

    status = _get_status(client, tracker.id, budget["id"], auth_headers)
    assert Decimal(str(status["spent"])) == Decimal("1100.00")
    assert Decimal(str(status["remaining"])) == Decimal("-100.00")
    assert status["savings_progress"] == 0
    assert status["savings_health"] == "red"
    assert status["is_over_budget"] is True


def test_status_zero_savings_target(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    # No target: staying within budget reports full progress and green health
    budget = _create_budget(client, tracker.id, auth_headers, savings_target="0.00")
    _add_expense(client, tracker.id, auth_headers, category_id, "100.00", "2026-06-10")

    status = _get_status(client, tracker.id, budget["id"], auth_headers)
    assert status["savings_progress"] == 100
    assert status["savings_health"] == "green"


def test_status_december_month_bounds(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    # Year rollover: December window must end at Jan 1 of the next year
    budget = _create_budget(client, tracker.id, auth_headers, month="2026-12")
    _add_expense(client, tracker.id, auth_headers, category_id, "80.00", "2026-12-31")
    _add_expense(client, tracker.id, auth_headers, category_id, "999.00", "2027-01-01")

    status = _get_status(client, tracker.id, budget["id"], auth_headers)
    assert Decimal(str(status["spent"])) == Decimal("80.00")
