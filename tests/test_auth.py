"""Tests for the auth module: register, login, refresh rotation, sign-out."""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.security import hash_token
from modules.refresh_tokens.model import RefreshToken
from modules.users.model import User

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
SIGN_OUT_URL = "/api/v1/auth/sign-out"
ME_URL = "/api/v1/users/me"


def _register(client: TestClient, **overrides) -> dict:
    payload = {
        "name": "Carol",
        "email": "carol@example.com",
        "password": "password123",
    }
    payload.update(overrides)
    response = client.post(REGISTER_URL, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Register
# --------------------------------------------------------------------------- #


def test_register_returns_token_pair(client: TestClient):
    body = _register(client)
    assert body["token_type"] == "bearer"
    assert body["access_token"] != body["refresh_token"]


def test_register_duplicate_email(client: TestClient):
    _register(client)
    response = client.post(
        REGISTER_URL,
        json={"name": "Other", "email": "carol@example.com", "password": "password123"},
    )
    assert response.status_code == 400


def test_register_validation(client: TestClient):
    cases = [
        {"name": "C", "email": "carol@example.com", "password": "short"},  # < 8
        {"name": "C", "email": "carol@example.com", "password": "x" * 129},  # > 128
        {"name": "C", "email": "not-an-email", "password": "password123"},
        {"name": "", "email": "carol@example.com", "password": "password123"},
    ]
    for payload in cases:
        response = client.post(REGISTER_URL, json=payload)
        assert response.status_code == 422, payload


def test_register_persists_refresh_token_hash(client: TestClient, session: Session):
    body = _register(client)
    stored = session.exec(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_token(body["refresh_token"])
        )
    ).first()
    assert stored is not None
    assert stored.revoked is False


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #


def test_login_success(client: TestClient, user: User):
    response = client.post(
        LOGIN_URL, json={"email": user.email, "password": "password123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["refresh_token"]


def test_login_wrong_password(client: TestClient, user: User):
    response = client.post(
        LOGIN_URL, json={"email": user.email, "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_unknown_email(client: TestClient):
    response = client.post(
        LOGIN_URL, json={"email": "ghost@example.com", "password": "password123"}
    )
    assert response.status_code == 401


def test_login_inactive_user(client: TestClient, session: Session, user: User):
    user.is_active = False
    session.add(user)
    session.commit()

    response = client.post(
        LOGIN_URL, json={"email": user.email, "password": "password123"}
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Token semantics
# --------------------------------------------------------------------------- #


def test_refresh_token_rejected_as_access_token(client: TestClient):
    body = _register(client)
    response = client.get(
        ME_URL, headers={"Authorization": f"Bearer {body['refresh_token']}"}
    )
    assert response.status_code == 401


def test_access_token_rejected_at_refresh(client: TestClient):
    body = _register(client)
    response = client.post(REFRESH_URL, json={"refresh_token": body["access_token"]})
    assert response.status_code == 401


def test_garbage_refresh_token_rejected(client: TestClient):
    response = client.post(REFRESH_URL, json={"refresh_token": "garbage"})
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Refresh rotation
# --------------------------------------------------------------------------- #


def test_refresh_rotates_token_pair(client: TestClient, session: Session):
    body = _register(client)
    response = client.post(REFRESH_URL, json={"refresh_token": body["refresh_token"]})
    assert response.status_code == 200
    new_body = response.json()
    assert new_body["refresh_token"] != body["refresh_token"]

    # old token is revoked and linked to its replacement
    old = session.exec(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_token(body["refresh_token"])
        )
    ).first()
    assert old.revoked is True
    assert old.replaced_by_id is not None

    # new access token works
    response = client.get(
        ME_URL, headers={"Authorization": f"Bearer {new_body['access_token']}"}
    )
    assert response.status_code == 200


def test_rotated_token_reuse_rejected(client: TestClient):
    body = _register(client)
    first = client.post(REFRESH_URL, json={"refresh_token": body["refresh_token"]})
    assert first.status_code == 200
    second = client.post(REFRESH_URL, json={"refresh_token": body["refresh_token"]})
    assert second.status_code == 401


def test_refresh_rejected_for_inactive_user(client: TestClient, session: Session):
    body = _register(client)
    user = session.exec(
        select(User).where(User.email == "carol@example.com")
    ).first()
    user.is_active = False
    session.add(user)
    session.commit()

    response = client.post(REFRESH_URL, json={"refresh_token": body["refresh_token"]})
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Sign-out
# --------------------------------------------------------------------------- #


def test_sign_out_revokes_refresh_token(client: TestClient):
    body = _register(client)
    response = client.post(SIGN_OUT_URL, json={"refresh_token": body["refresh_token"]})
    assert response.status_code == 204

    response = client.post(REFRESH_URL, json={"refresh_token": body["refresh_token"]})
    assert response.status_code == 401


def test_sign_out_unknown_token_still_204(client: TestClient):
    response = client.post(SIGN_OUT_URL, json={"refresh_token": "unknown-token"})
    assert response.status_code == 204
