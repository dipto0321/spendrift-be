"""Tests for the trackers module."""

from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from modules.categories.model import Category
from modules.expenses.model import Expense

TRACKERS_URL = "/api/v1/trackers"


def _create(client: TestClient, headers, name="Main", currency="USD") -> dict:
    response = client.post(
        TRACKERS_URL, json={"name": name, "currency": currency}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_tracker_seeds_default_categories(
    client: TestClient, session: Session, auth_headers
):
    body = _create(client, auth_headers)
    assert body["name"] == "Main"
    assert body["currency"] == "USD"

    categories = session.exec(
        select(Category).where(Category.tracker_id == UUID(body["id"]))
    ).all()
    assert len(categories) == 10
    assert {c.name for c in categories} >= {"Uncategorized", "Groceries", "Coffee"}


def test_currency_normalized_to_uppercase(client: TestClient, auth_headers):
    body = _create(client, auth_headers, currency="usd")
    assert body["currency"] == "USD"


def test_currency_validation(client: TestClient, auth_headers):
    for bad in ["US", "USDT", "U1D", "$$$"]:
        response = client.post(
            TRACKERS_URL, json={"name": "X", "currency": bad}, headers=auth_headers
        )
        assert response.status_code == 422, bad


def test_list_only_own_trackers(
    client: TestClient, auth_headers, other_auth_headers
):
    _create(client, auth_headers, name="Mine")
    _create(client, other_auth_headers, name="Theirs")

    body = client.get(TRACKERS_URL, headers=auth_headers).json()
    assert [t["name"] for t in body] == ["Mine"]


def test_get_update_delete_tracker(client: TestClient, auth_headers):
    created = _create(client, auth_headers)
    url = f"{TRACKERS_URL}/{created['id']}"

    assert client.get(url, headers=auth_headers).status_code == 200

    response = client.patch(url, json={"name": "Renamed"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert response.json()["currency"] == "USD"  # unchanged

    assert client.delete(url, headers=auth_headers).status_code == 204
    assert client.get(url, headers=auth_headers).status_code == 404


def test_other_user_cannot_access_tracker(
    client: TestClient, auth_headers, other_auth_headers
):
    created = _create(client, auth_headers)
    url = f"{TRACKERS_URL}/{created['id']}"

    assert client.get(url, headers=other_auth_headers).status_code == 404
    assert (
        client.patch(url, json={"name": "Hacked"}, headers=other_auth_headers).status_code
        == 404
    )
    assert client.delete(url, headers=other_auth_headers).status_code == 404


def test_delete_tracker_cascades_categories_and_expenses(
    client: TestClient, session: Session, auth_headers
):
    created = _create(client, auth_headers)
    tracker_id = created["id"]

    categories = session.exec(
        select(Category).where(Category.tracker_id == UUID(tracker_id))
    ).all()
    response = client.post(
        f"{TRACKERS_URL}/{tracker_id}/expenses",
        json={
            "amount": "10.00",
            "category_id": str(categories[0].id),
            "date": "2026-06-01",
            "type": "need",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    assert client.delete(
        f"{TRACKERS_URL}/{tracker_id}", headers=auth_headers
    ).status_code == 204

    session.expire_all()
    assert (
        session.exec(
            select(Category).where(Category.tracker_id == UUID(tracker_id))
        ).all()
        == []
    )
    assert (
        session.exec(
            select(Expense).where(Expense.tracker_id == UUID(tracker_id))
        ).all()
        == []
    )


def test_trackers_require_auth(client: TestClient):
    assert client.get(TRACKERS_URL).status_code == 401
