"""Tests for the categories module."""

from fastapi.testclient import TestClient

from modules.trackers.model import Tracker


def _categories_url(tracker_id) -> str:
    return f"/api/v1/trackers/{tracker_id}/categories"


def test_list_seeded_categories(client: TestClient, tracker: Tracker, auth_headers):
    response = client.get(_categories_url(tracker.id), headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 10
    assert {"id", "tracker_id", "name", "color", "created_at"} <= body[0].keys()


def test_create_category(client: TestClient, tracker: Tracker, auth_headers):
    response = client.post(
        _categories_url(tracker.id),
        json={"name": "Travel", "color": "#6366F1"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Travel"


def test_create_duplicate_name_fails(
    client: TestClient, tracker: Tracker, auth_headers
):
    response = client.post(
        _categories_url(tracker.id),
        json={"name": "Groceries", "color": "#6366F1"},  # seeded name
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_color_validation(client: TestClient, tracker: Tracker, auth_headers):
    for bad in ["red", "#FFF", "#GGGGGG", "22C55E", "#22C55E00"]:
        response = client.post(
            _categories_url(tracker.id),
            json={"name": "Bad", "color": bad},
            headers=auth_headers,
        )
        assert response.status_code == 422, bad


def test_update_category(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    response = client.patch(
        f"{_categories_url(tracker.id)}/{category_id}",
        json={"name": "Renamed", "color": "#EF4444"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["color"] == "#EF4444"


def test_update_to_existing_name_fails(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    # pick a seeded name that is NOT the category being renamed
    categories = client.get(_categories_url(tracker.id), headers=auth_headers).json()
    taken_name = next(c["name"] for c in categories if c["id"] != category_id)

    response = client.patch(
        f"{_categories_url(tracker.id)}/{category_id}",
        json={"name": taken_name},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_delete_unused_category(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    url = f"{_categories_url(tracker.id)}/{category_id}"
    assert client.delete(url, headers=auth_headers).status_code == 204
    assert client.get(url, headers=auth_headers).status_code == 404


def test_delete_category_in_use_409(
    client: TestClient, tracker: Tracker, auth_headers, category_id
):
    response = client.post(
        f"/api/v1/trackers/{tracker.id}/expenses",
        json={
            "amount": "5.00",
            "category_id": category_id,
            "date": "2026-06-01",
            "type": "want",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201

    response = client.delete(
        f"{_categories_url(tracker.id)}/{category_id}", headers=auth_headers
    )
    assert response.status_code == 409
    assert "expense" in response.json()["detail"].lower()


def test_other_user_gets_404(
    client: TestClient, tracker: Tracker, other_auth_headers, category_id
):
    assert (
        client.get(_categories_url(tracker.id), headers=other_auth_headers).status_code
        == 404
    )
    assert (
        client.get(
            f"{_categories_url(tracker.id)}/{category_id}", headers=other_auth_headers
        ).status_code
        == 404
    )


def test_categories_require_auth(client: TestClient, tracker: Tracker):
    assert client.get(_categories_url(tracker.id)).status_code == 401
