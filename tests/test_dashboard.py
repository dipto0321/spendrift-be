"""Tests for the dashboard module."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session

from modules.categories import repo as category_repo
from modules.trackers.model import Tracker


def _dashboard_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/dashboard"


def _expenses_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/expenses"


def _add_expense(
    client: TestClient,
    tracker_id,
    headers,
    category_id,
    amount: str,
    date: str,
    type_: str = "need",
) -> None:
    response = client.post(
        _expenses_url(tracker_id),
        json={
            "amount": amount,
            "category_id": category_id,
            "date": date,
            "type": type_,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _get_dashboard(client, tracker_id, headers, month: str | None = "2026-06") -> dict:
    params = {"month": month} if month else {}
    response = client.get(_dashboard_url(tracker_id), params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_dashboard_empty_month(client: TestClient, tracker: Tracker, auth_headers):
    body = _get_dashboard(client, tracker.id, auth_headers)
    assert body["month"] == "2026-06"
    assert Decimal(str(body["total_spent"])) == Decimal("0")
    assert body["expense_count"] == 0
    assert body["needs_wants"]["needs_percentage"] == 0
    assert body["needs_wants"]["wants_percentage"] == 0
    assert body["top_categories"] == []
    assert body["budget"] is None


def test_dashboard_defaults_to_current_month(
    client: TestClient, tracker: Tracker, auth_headers
):
    body = _get_dashboard(client, tracker.id, auth_headers, month=None)
    assert body["month"] == datetime.now(timezone.utc).strftime("%Y-%m")


def test_dashboard_invalid_month_rejected(
    client: TestClient, tracker: Tracker, auth_headers
):
    response = client.get(
        _dashboard_url(tracker.id), params={"month": "2026-13"}, headers=auth_headers
    )
    assert response.status_code == 422


def test_dashboard_totals_and_needs_wants_split(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    _add_expense(client, tracker.id, auth_headers, category_id, "75.00", "2026-06-05", "need")
    _add_expense(client, tracker.id, auth_headers, category_id, "25.00", "2026-06-10", "want")
    # outside month - excluded
    _add_expense(client, tracker.id, auth_headers, category_id, "500.00", "2026-05-31")

    body = _get_dashboard(client, tracker.id, auth_headers)
    assert Decimal(str(body["total_spent"])) == Decimal("100.00")
    assert body["expense_count"] == 2
    split = body["needs_wants"]
    assert Decimal(str(split["needs_total"])) == Decimal("75.00")
    assert Decimal(str(split["wants_total"])) == Decimal("25.00")
    assert split["needs_percentage"] == 75
    assert split["wants_percentage"] == 25


def test_dashboard_top_categories_ordered_and_limited(
    client: TestClient, session: Session, tracker: Tracker, auth_headers
):
    categories = category_repo.list_categories_by_tracker(session, tracker.id)
    # 6 categories with increasing spend; top 5 returned, biggest first
    for i, category in enumerate(categories[:6]):
        _add_expense(
            client,
            tracker.id,
            auth_headers,
            str(category.id),
            f"{(i + 1) * 10}.00",
            "2026-06-15",
        )

    body = _get_dashboard(client, tracker.id, auth_headers)
    top = body["top_categories"]
    assert len(top) == 5
    totals = [Decimal(str(c["total"])) for c in top]
    assert totals == sorted(totals, reverse=True)
    assert totals[0] == Decimal("60.00")
    # smallest spender (10.00) fell out of the top 5
    assert Decimal("10.00") not in totals
    # percentage of total spend (210): 60/210 -> 29%
    assert top[0]["percentage"] == 29
    assert {"category_id", "name", "color", "total", "percentage"} <= top[0].keys()


def test_dashboard_includes_budget_snapshot(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    response = client.post(
        f"/api/v1/trackers/{tracker.id}/budgets",
        json={
            "name": "June",
            "monthly_limit": "1000.00",
            "savings_target": "200.00",
            "month": "2026-06",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    _add_expense(client, tracker.id, auth_headers, category_id, "850.00", "2026-06-10")

    body = _get_dashboard(client, tracker.id, auth_headers)
    budget = body["budget"]
    assert budget is not None
    assert budget["name"] == "June"
    assert Decimal(str(budget["spent"])) == Decimal("850.00")
    assert Decimal(str(budget["remaining"])) == Decimal("150.00")
    assert budget["savings_health"] == "yellow"
    assert budget["is_over_budget"] is False


def test_dashboard_budget_only_for_matching_month(
    client: TestClient, tracker: Tracker, auth_headers
):
    response = client.post(
        f"/api/v1/trackers/{tracker.id}/budgets",
        json={
            "name": "May",
            "monthly_limit": "500.00",
            "savings_target": "0.00",
            "month": "2026-05",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    assert _get_dashboard(client, tracker.id, auth_headers, "2026-06")["budget"] is None
    assert _get_dashboard(client, tracker.id, auth_headers, "2026-05")["budget"] is not None


def test_dashboard_requires_auth(client: TestClient, tracker: Tracker):
    response = client.get(_dashboard_url(tracker.id))
    assert response.status_code == 401


def test_dashboard_other_user_gets_404(
    client: TestClient, tracker: Tracker, other_auth_headers
):
    response = client.get(_dashboard_url(tracker.id), headers=other_auth_headers)
    assert response.status_code == 404
