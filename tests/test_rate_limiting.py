"""Tests for the global default rate limit (gh#14).

The `client` fixture disables the limiter as the last step of its own
setup (every other test module relies on that), so re-enabling it in a
fixture would run too early and get silently undone. Instead each test
re-enables it as its first statement, after `client` is already built.
"""

from app.main import app
from app.middleware.rate_limit import limiter


def _enable_and_reset_limiter() -> None:
    limiter.reset()
    app.state.limiter.enabled = True


def test_default_limit_applies_to_a_route_without_its_own_decorator(
    client, auth_headers
):
    _enable_and_reset_limiter()
    responses = [
        client.get("/api/v1/trackers", headers=auth_headers) for _ in range(61)
    ]
    assert all(r.status_code == 200 for r in responses[:60])
    assert responses[-1].status_code == 429


def test_sign_out_is_exempt_from_the_default_limit(client):
    _enable_and_reset_limiter()
    responses = [
        client.post(
            "/api/v1/auth/sign-out", json={"refresh_token": "not-a-real-token"}
        )
        for _ in range(65)
    ]
    assert all(r.status_code == 204 for r in responses)
