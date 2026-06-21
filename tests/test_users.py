"""Tests for the users module."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from modules.users.model import User

ME_URL = "/api/v1/users/me"


def test_me_returns_current_user(client: TestClient, user: User, auth_headers):
    response = client.get(ME_URL, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["name"] == user.name
    assert body["id"] == str(user.id)
    assert "hashed_password" not in body


def test_me_requires_auth(client: TestClient):
    assert client.get(ME_URL).status_code == 401


def test_me_invalid_token(client: TestClient):
    response = client.get(ME_URL, headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_me_malformed_header(client: TestClient):
    response = client.get(ME_URL, headers={"Authorization": "Token abc"})
    assert response.status_code == 401


def test_me_inactive_user_403(
    client: TestClient, session: Session, user: User, auth_headers
):
    user.is_active = False
    session.add(user)
    session.commit()

    response = client.get(ME_URL, headers=auth_headers)
    assert response.status_code == 403


def test_me_deleted_user_401(
    client: TestClient, session: Session, user: User, auth_headers
):
    session.delete(user)
    session.commit()

    response = client.get(ME_URL, headers=auth_headers)
    assert response.status_code == 401
