"""Tests for the reports module."""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session

from modules.categories import repo as category_repo
from modules.trackers.model import Tracker


def _reports_url(tracker_id, endpoint: str) -> str:
    return f"/api/v1/trackers/{tracker_id}/reports/{endpoint}"


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
        f"/api/v1/trackers/{tracker_id}/expenses",
        json={
            "amount": amount,
            "category_id": category_id,
            "date": date,
            "type": type_,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def _get(client, tracker_id, endpoint, headers, **params) -> dict | list:
    response = client.get(
        _reports_url(tracker_id, endpoint), params=params, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #


def test_summary_empty(client: TestClient, tracker: Tracker, auth_headers):
    body = _get(client, tracker.id, "summary", auth_headers)
    assert body["count"] == 0
    for field in ("total", "min", "max", "avg"):
        assert Decimal(str(body[field])) == Decimal("0")


def test_summary_statistics(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    for amount, day in [
        ("10.00", "2026-06-01"),
        ("20.00", "2026-06-02"),
        ("45.50", "2026-06-03"),
    ]:
        _add_expense(client, tracker.id, auth_headers, category_id, amount, day)

    body = _get(client, tracker.id, "summary", auth_headers)
    assert body["count"] == 3
    assert Decimal(str(body["total"])) == Decimal("75.50")
    assert Decimal(str(body["min"])) == Decimal("10.00")
    assert Decimal(str(body["max"])) == Decimal("45.50")
    assert Decimal(str(body["avg"])) == Decimal("25.17")  # 75.50/3 rounded


def test_summary_respects_date_range(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    _add_expense(client, tracker.id, auth_headers, category_id, "10.00", "2026-06-01")
    _add_expense(client, tracker.id, auth_headers, category_id, "99.00", "2026-07-01")

    body = _get(
        client,
        tracker.id,
        "summary",
        auth_headers,
        start_date="2026-06-01",
        end_date="2026-06-30",
    )
    assert body["count"] == 1
    assert Decimal(str(body["total"])) == Decimal("10.00")


def test_summary_invalid_range_rejected(
    client: TestClient, tracker: Tracker, auth_headers
):
    response = client.get(
        _reports_url(tracker.id, "summary"),
        params={"start_date": "2026-06-30", "end_date": "2026-06-01"},
        headers=auth_headers,
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Spending over time
# --------------------------------------------------------------------------- #


def test_spending_monthly_buckets(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    _add_expense(client, tracker.id, auth_headers, category_id, "10.00", "2026-05-15")
    _add_expense(client, tracker.id, auth_headers, category_id, "20.00", "2026-06-01")
    _add_expense(client, tracker.id, auth_headers, category_id, "30.00", "2026-06-20")

    body = _get(client, tracker.id, "spending", auth_headers, period="monthly")
    assert [b["label"] for b in body] == ["2026-05", "2026-06"]
    assert Decimal(str(body[1]["total"])) == Decimal("50.00")
    assert body[1]["count"] == 2


def test_spending_weekly_buckets_use_monday(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    # 2026-06-10 is a Wednesday; its ISO week starts Monday 2026-06-08
    _add_expense(client, tracker.id, auth_headers, category_id, "10.00", "2026-06-10")
    _add_expense(client, tracker.id, auth_headers, category_id, "15.00", "2026-06-12")
    # next ISO week
    _add_expense(client, tracker.id, auth_headers, category_id, "99.00", "2026-06-15")

    body = _get(client, tracker.id, "spending", auth_headers, period="weekly")
    assert [b["label"] for b in body] == ["2026-06-08", "2026-06-15"]
    assert Decimal(str(body[0]["total"])) == Decimal("25.00")


def test_spending_yearly_buckets(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    _add_expense(client, tracker.id, auth_headers, category_id, "10.00", "2025-03-01")
    _add_expense(client, tracker.id, auth_headers, category_id, "20.00", "2026-03-01")

    body = _get(client, tracker.id, "spending", auth_headers, period="yearly")
    assert [b["label"] for b in body] == ["2025", "2026"]


def test_spending_daily_buckets(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    _add_expense(client, tracker.id, auth_headers, category_id, "10.00", "2026-06-01")
    _add_expense(client, tracker.id, auth_headers, category_id, "20.00", "2026-06-01")
    _add_expense(client, tracker.id, auth_headers, category_id, "30.00", "2026-06-03")

    body = _get(client, tracker.id, "spending", auth_headers, period="daily")
    assert [b["label"] for b in body] == ["2026-06-01", "2026-06-03"]
    assert Decimal(str(body[0]["total"])) == Decimal("30.00")
    assert body[0]["count"] == 2
    assert Decimal(str(body[1]["total"])) == Decimal("30.00")


def test_spending_invalid_period_rejected(
    client: TestClient, tracker: Tracker, auth_headers
):
    response = client.get(
        _reports_url(tracker.id, "spending"),
        params={"period": "hourly"},
        headers=auth_headers,
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Category breakdown
# --------------------------------------------------------------------------- #


def test_category_breakdown(
    client: TestClient, session: Session, tracker: Tracker, auth_headers
):
    categories = category_repo.list_categories_by_tracker(session, tracker.id)
    groceries, transport = categories[1], categories[2]

    _add_expense(
        client, tracker.id, auth_headers, str(groceries.id), "75.00", "2026-06-01"
    )
    _add_expense(
        client, tracker.id, auth_headers, str(groceries.id), "5.00", "2026-06-02"
    )
    _add_expense(
        client, tracker.id, auth_headers, str(transport.id), "20.00", "2026-06-03"
    )

    body = _get(client, tracker.id, "category-breakdown", auth_headers)
    assert len(body) == 2  # only categories with spend
    first, second = body
    assert first["category_name"] == groceries.name
    assert Decimal(str(first["total"])) == Decimal("80.00")
    assert first["percentage"] == 80
    assert first["count"] == 2
    assert first["category_color"] == groceries.color
    assert second["category_name"] == transport.name
    assert second["percentage"] == 20


def test_category_breakdown_empty(client: TestClient, tracker: Tracker, auth_headers):
    assert _get(client, tracker.id, "category-breakdown", auth_headers) == []


# --------------------------------------------------------------------------- #
# Needs vs wants
# --------------------------------------------------------------------------- #


def test_needs_vs_wants(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    _add_expense(
        client, tracker.id, auth_headers, category_id, "60.00", "2026-06-01", "need"
    )
    _add_expense(
        client, tracker.id, auth_headers, category_id, "40.00", "2026-06-02", "want"
    )

    body = _get(client, tracker.id, "needs-vs-wants", auth_headers)
    assert Decimal(str(body["needs_total"])) == Decimal("60.00")
    assert Decimal(str(body["wants_total"])) == Decimal("40.00")
    assert body["needs_percentage"] == 60
    assert body["wants_percentage"] == 40


def test_needs_vs_wants_empty(client: TestClient, tracker: Tracker, auth_headers):
    body = _get(client, tracker.id, "needs-vs-wants", auth_headers)
    assert body["needs_percentage"] == 0
    assert body["wants_percentage"] == 0


# --------------------------------------------------------------------------- #
# Year comparison
# --------------------------------------------------------------------------- #


def test_year_comparison(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    _add_expense(client, tracker.id, auth_headers, category_id, "120.00", "2025-01-15")
    _add_expense(client, tracker.id, auth_headers, category_id, "60.00", "2025-07-15")
    _add_expense(client, tracker.id, auth_headers, category_id, "240.00", "2026-02-15")

    body = _get(client, tracker.id, "year-comparison", auth_headers)
    assert [item["year"] for item in body] == [2025, 2026]

    y2025, y2026 = body
    assert Decimal(str(y2025["total"])) == Decimal("180.00")
    assert Decimal(str(y2025["avg"])) == Decimal("15.00")  # 180/12
    assert y2025["count"] == 2
    assert Decimal(str(y2026["avg"])) == Decimal("20.00")  # 240/12


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #


def test_reports_require_auth(client: TestClient, tracker: Tracker):
    for endpoint in (
        "summary",
        "spending",
        "category-breakdown",
        "needs-vs-wants",
        "year-comparison",
    ):
        response = client.get(_reports_url(tracker.id, endpoint))
        assert response.status_code == 401, endpoint


def test_reports_other_user_gets_404(
    client: TestClient, tracker: Tracker, other_auth_headers
):
    for endpoint in (
        "summary",
        "spending",
        "category-breakdown",
        "needs-vs-wants",
        "year-comparison",
    ):
        response = client.get(
            _reports_url(tracker.id, endpoint), headers=other_auth_headers
        )
        assert response.status_code == 404, endpoint


# --------------------------------------------------------------------------- #
# Monthly insights snapshot (Smart Report)
# --------------------------------------------------------------------------- #


def _post_monthly_insights(
    client: TestClient,
    tracker_id,
    headers,
    month: str,
    top_n_categories: int = 5,
    top_n_expenses: int = 3,
) -> dict:
    response = client.post(
        _reports_url(tracker_id, "monthly-insights"),
        json={
            "month": month,
            "top_n_categories": top_n_categories,
            "top_n_expenses": top_n_expenses,
        },
        headers=headers,
    )
    return response


def test_monthly_insights_snapshot_basic(
    client: TestClient, session: Session, tracker: Tracker, auth_headers, category_id
):
    """Returns the requested month with totals, needs/wants, and top expenses."""
    used_category_name = next(
        c.name
        for c in category_repo.list_categories_by_tracker(session, tracker.id)
        if str(c.id) == category_id
    )

    _add_expense(client, tracker.id, auth_headers, category_id, "10.00", "2026-06-01")
    _add_expense(client, tracker.id, auth_headers, category_id, "20.00", "2026-06-15")
    _add_expense(
        client,
        tracker.id,
        auth_headers,
        category_id,
        "5.00",
        "2026-06-30",
        type_="want",
    )

    response = _post_monthly_insights(client, tracker.id, auth_headers, "2026-06")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["month"] == "2026-06"
    assert body["currency"] == "USD"
    assert Decimal(str(body["total"])) == Decimal("35.00")
    assert Decimal(str(body["prior_total"])) == Decimal("0")
    assert body["delta_pct"] == 0  # prior is zero → no comparison
    assert len(body["top_categories"]) == 1  # only one category used
    assert Decimal(str(body["top_categories"][0]["current_total"])) == Decimal("35.00")
    assert body["top_categories"][0]["count"] == 3
    assert len(body["largest_expenses"]) == 3
    # Largest expense first
    assert Decimal(str(body["largest_expenses"][0]["amount"])) == Decimal("20.00")
    assert body["largest_expenses"][0]["category_name"] == used_category_name
    # Needs vs wants
    nw = body["needs_wants"]
    assert Decimal(str(nw["needs_total"])) == Decimal("30.00")
    assert Decimal(str(nw["wants_total"])) == Decimal("5.00")


def test_monthly_insights_snapshot_includes_deltas(
    client: TestClient, session: Session, tracker: Tracker, auth_headers
):
    """Categories from the prior month carry the right delta against the current."""
    categories = category_repo.list_categories_by_tracker(session, tracker.id)
    cat_a = str(next(c for c in categories if c.name == "Groceries").id)
    cat_b = str(next(c for c in categories if c.name == "Dining").id)

    # Prior month — May 2026
    _add_expense(client, tracker.id, auth_headers, cat_a, "100.00", "2026-05-10")
    # Current month — June 2026: Groceries up 50%, Dining new
    _add_expense(client, tracker.id, auth_headers, cat_a, "150.00", "2026-06-10")
    _add_expense(client, tracker.id, auth_headers, cat_b, "80.00", "2026-06-15")

    response = _post_monthly_insights(client, tracker.id, auth_headers, "2026-06")
    assert response.status_code == 200, response.text
    body = response.json()

    # Top categories ordered by current_total descending: Groceries 150, Dining 80.
    assert len(body["top_categories"]) == 2
    groceries, dining = body["top_categories"]
    assert groceries["category_name"] == "Groceries"
    assert Decimal(str(groceries["current_total"])) == Decimal("150.00")
    assert Decimal(str(groceries["prior_total"])) == Decimal("100.00")
    assert groceries["delta_pct"] == 50
    assert dining["category_name"] == "Dining"
    assert Decimal(str(dining["current_total"])) == Decimal("80.00")
    assert Decimal(str(dining["prior_total"])) == Decimal("0")
    assert dining["delta_pct"] == 0  # no prior → no delta

    # Totals: current 230, prior 100, +130%
    assert Decimal(str(body["total"])) == Decimal("230.00")
    assert Decimal(str(body["prior_total"])) == Decimal("100.00")
    assert body["delta_pct"] == 130


def test_monthly_insights_snapshot_year_boundary(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    """December → November correctly rolls the year back."""
    _add_expense(client, tracker.id, auth_headers, category_id, "40.00", "2026-11-30")
    _add_expense(client, tracker.id, auth_headers, category_id, "60.00", "2026-12-15")

    response = _post_monthly_insights(client, tracker.id, auth_headers, "2026-12")
    assert response.status_code == 200, response.text
    body = response.json()

    assert Decimal(str(body["total"])) == Decimal("60.00")
    assert Decimal(str(body["prior_total"])) == Decimal("40.00")
    assert body["delta_pct"] == 50


def test_monthly_insights_snapshot_ownership_404(
    client: TestClient, tracker: Tracker, other_auth_headers
):
    """Other-user requests get 404 (don't reveal existence)."""
    response = _post_monthly_insights(client, tracker.id, other_auth_headers, "2026-06")
    assert response.status_code == 404


def test_monthly_insights_snapshot_invalid_month_format(
    client: TestClient, tracker: Tracker, auth_headers
):
    """Bad `month` strings are rejected by Pydantic (422)."""
    for bad in ["2026-6", "2026/06", "26-06", "2026-13", "2026-00", "202606"]:
        response = _post_monthly_insights(client, tracker.id, auth_headers, bad)
        assert response.status_code == 422, bad


def test_monthly_insights_snapshot_requires_auth(client: TestClient, tracker: Tracker):
    response = _post_monthly_insights(client, tracker.id, {}, "2026-06")
    assert response.status_code == 401
