"""Tests for the expenses module."""

from decimal import Decimal

from fastapi.testclient import TestClient

from modules.trackers.model import Tracker


def _expenses_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/expenses"


def _categories_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/categories"


def _make_payload(category_id: str, **overrides) -> dict:
    payload = {
        "amount": "12.50",
        "category_id": category_id,
        "date": "2026-05-15",
        "description": "Lunch",
        "type": "need",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def test_create_expense_requires_auth(
    client: TestClient, tracker: Tracker, category_id: str
):
    resp = client.post(
        _expenses_url(tracker.id), json=_make_payload(category_id)
    )
    assert resp.status_code == 401


def test_list_expenses_requires_auth(client: TestClient, tracker: Tracker):
    resp = client.get(_expenses_url(tracker.id))
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
def test_create_expense(
    client: TestClient,
    tracker: Tracker,
    category_id: str,
    auth_headers: dict,
):
    resp = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(category_id, amount="42.00", description="Books"),
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"]
    assert body["tracker_id"] == str(tracker.id)
    assert body["category_id"] == category_id
    assert Decimal(str(body["amount"])) == Decimal("42.00")
    assert body["date"] == "2026-05-15"
    assert body["description"] == "Books"
    assert body["type"] == "need"


def test_create_expense_rejects_non_positive_amount(
    client: TestClient, tracker: Tracker, category_id: str, auth_headers: dict
):
    resp = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(category_id, amount="0"),
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_expense_rejects_invalid_type(
    client: TestClient, tracker: Tracker, category_id: str, auth_headers: dict
):
    resp = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(category_id, type="luxury"),
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_create_expense_rejects_category_from_other_tracker(
    client: TestClient, tracker: Tracker, auth_headers: dict
):
    # Create a second tracker (owned by the same user) and use ITS category.
    other = client.post(
        "/api/v1/trackers",
        json={"name": "Travel", "currency": "EUR"},
        headers=auth_headers,
    ).json()
    other_categories = client.get(
        _categories_url(other["id"]), headers=auth_headers
    ).json()
    foreign_category_id = other_categories[0]["id"]

    resp = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(foreign_category_id),
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "category" in resp.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# List + filtering
# --------------------------------------------------------------------------- #
def test_list_expenses_empty(
    client: TestClient, tracker: Tracker, auth_headers: dict
):
    resp = client.get(_expenses_url(tracker.id), headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_and_filter_expenses(
    client: TestClient, tracker: Tracker, auth_headers: dict
):
    categories = client.get(
        _categories_url(tracker.id), headers=auth_headers
    ).json()
    cat_a, cat_b = categories[0]["id"], categories[1]["id"]

    def create(**kwargs):
        cid = kwargs.pop("category_id", cat_a)
        resp = client.post(
            _expenses_url(tracker.id),
            json=_make_payload(cid, **kwargs),
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    create(amount="10.00", date="2026-05-01", type="need", description="Rice")
    create(amount="20.00", date="2026-05-10", type="want", description="Movie")
    create(
        amount="30.00",
        date="2026-06-01",
        type="need",
        description="Train ticket",
        category_id=cat_b,
    )

    url = _expenses_url(tracker.id)

    # No filter -> all three, default sort date_desc
    all_items = client.get(url, headers=auth_headers).json()
    assert len(all_items) == 3
    assert all_items[0]["date"] == "2026-06-01"
    assert all_items[-1]["date"] == "2026-05-01"

    # Sort ascending
    asc = client.get(f"{url}?sort=date_asc", headers=auth_headers).json()
    assert asc[0]["date"] == "2026-05-01"

    # Filter by type
    needs = client.get(f"{url}?type=need", headers=auth_headers).json()
    assert {e["description"] for e in needs} == {"Rice", "Train ticket"}

    # Date range (inclusive)
    in_may = client.get(
        f"{url}?start_date=2026-05-01&end_date=2026-05-31", headers=auth_headers
    ).json()
    assert len(in_may) == 2

    # Category filter
    by_cat_b = client.get(
        f"{url}?category_ids={cat_b}", headers=auth_headers
    ).json()
    assert len(by_cat_b) == 1
    assert by_cat_b[0]["description"] == "Train ticket"

    # Description search (case-insensitive)
    found = client.get(f"{url}?search=movie", headers=auth_headers).json()
    assert len(found) == 1
    assert found[0]["description"] == "Movie"


# --------------------------------------------------------------------------- #
# Get / not found
# --------------------------------------------------------------------------- #
def test_get_expense(
    client: TestClient, tracker: Tracker, category_id: str, auth_headers: dict
):
    created = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(category_id),
        headers=auth_headers,
    ).json()
    resp = client.get(
        f"{_expenses_url(tracker.id)}/{created['id']}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_expense_not_found(
    client: TestClient, tracker: Tracker, auth_headers: dict
):
    missing = "00000000-0000-0000-0000-000000000000"
    resp = client.get(
        f"{_expenses_url(tracker.id)}/{missing}", headers=auth_headers
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# Ownership isolation
# --------------------------------------------------------------------------- #
def test_other_user_cannot_access_tracker_expenses(
    client: TestClient,
    tracker: Tracker,
    category_id: str,
    auth_headers: dict,
    other_auth_headers: dict,
):
    created = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(category_id),
        headers=auth_headers,
    ).json()

    # Listing someone else's tracker -> 404 (don't reveal existence)
    assert (
        client.get(_expenses_url(tracker.id), headers=other_auth_headers).status_code
        == 404
    )
    # Reading a specific expense -> 404
    assert (
        client.get(
            f"{_expenses_url(tracker.id)}/{created['id']}",
            headers=other_auth_headers,
        ).status_code
        == 404
    )
    # Creating in someone else's tracker -> 404
    assert (
        client.post(
            _expenses_url(tracker.id),
            json=_make_payload(category_id),
            headers=other_auth_headers,
        ).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #
def test_update_expense(
    client: TestClient, tracker: Tracker, category_id: str, auth_headers: dict
):
    created = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(category_id, amount="10.00", type="need"),
        headers=auth_headers,
    ).json()

    resp = client.patch(
        f"{_expenses_url(tracker.id)}/{created['id']}",
        json={"amount": "99.99", "type": "want"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(str(body["amount"])) == Decimal("99.99")
    assert body["type"] == "want"
    # Unchanged fields preserved
    assert body["category_id"] == category_id
    assert body["date"] == "2026-05-15"


def test_update_expense_rejects_category_from_other_tracker(
    client: TestClient, tracker: Tracker, category_id: str, auth_headers: dict
):
    created = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(category_id),
        headers=auth_headers,
    ).json()

    other = client.post(
        "/api/v1/trackers",
        json={"name": "Travel", "currency": "EUR"},
        headers=auth_headers,
    ).json()
    foreign_category_id = client.get(
        _categories_url(other["id"]), headers=auth_headers
    ).json()[0]["id"]

    resp = client.patch(
        f"{_expenses_url(tracker.id)}/{created['id']}",
        json={"category_id": foreign_category_id},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Delete
# --------------------------------------------------------------------------- #
def test_delete_expense(
    client: TestClient, tracker: Tracker, category_id: str, auth_headers: dict
):
    created = client.post(
        _expenses_url(tracker.id),
        json=_make_payload(category_id),
        headers=auth_headers,
    ).json()

    resp = client.delete(
        f"{_expenses_url(tracker.id)}/{created['id']}", headers=auth_headers
    )
    assert resp.status_code == 204

    # Now gone
    assert (
        client.get(
            f"{_expenses_url(tracker.id)}/{created['id']}", headers=auth_headers
        ).status_code
        == 404
    )
