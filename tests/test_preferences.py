"""Tests for the preferences module (Settings > Preferences toggles)."""

from fastapi.testclient import TestClient

from modules.users.model import User

_URL = "/api/v1/preferences"


def test_get_preferences_creates_default_row(
    client: TestClient, user: User, auth_headers
):
    response = client.get(_URL, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["budget_alerts_enabled"] is True
    assert body["weekly_summary_enabled"] is True
    assert body["round_amounts_enabled"] is False


def test_get_preferences_is_idempotent(client: TestClient, auth_headers):
    first = client.get(_URL, headers=auth_headers).json()
    second = client.get(_URL, headers=auth_headers).json()
    assert first["id"] == second["id"]


def test_put_preferences_partial_update(client: TestClient, auth_headers):
    client.get(_URL, headers=auth_headers)

    response = client.put(
        _URL, json={"round_amounts_enabled": True}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["round_amounts_enabled"] is True
    # Untouched fields keep their defaults.
    assert body["budget_alerts_enabled"] is True
    assert body["weekly_summary_enabled"] is True


def test_put_preferences_without_prior_get_creates_default_first(
    client: TestClient, auth_headers
):
    response = client.put(
        _URL, json={"weekly_summary_enabled": False}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["weekly_summary_enabled"] is False


def test_preferences_require_auth(client: TestClient):
    response = client.get(_URL)
    assert response.status_code == 401


def test_preferences_are_per_user(
    client: TestClient, auth_headers, other_auth_headers
):
    client.put(_URL, json={"round_amounts_enabled": True}, headers=auth_headers)

    other = client.get(_URL, headers=other_auth_headers).json()
    assert other["round_amounts_enabled"] is False
