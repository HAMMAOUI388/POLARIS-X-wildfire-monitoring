"""Tests covering CORS headers, Private Network Access preflights, and registration validation."""
from __future__ import annotations

import pytest
from polaris_x.app import create_app


@pytest.fixture
def test_app():
    return create_app({
        "TESTING": True,
        "CORS_ORIGINS": ["http://localhost:3000", "http://127.0.0.1:3000"],
        "CORS_ALLOW_PRIVATE_NETWORK": True,
        "JWT_SECRET_KEY": "unit-test-secret-with-at-least-32-chars",
    })


def test_cors_preflight_for_localhost(test_app):
    with test_app.test_client() as client:
        res = client.options(
            "/api/v1/auth/register",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
        assert "POST" in res.headers.get("Access-Control-Allow-Methods", "")


def test_cors_preflight_private_network_access(test_app):
    with test_app.test_client() as client:
        res = client.options(
            "/api/v1/auth/register",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
                "Access-Control-Request-Private-Network": "true",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
        assert res.headers.get("Access-Control-Allow-Private-Network") == "true"


def test_cors_disallows_unrecognized_origin(test_app):
    with test_app.test_client() as client:
        res = client.options(
            "/api/v1/auth/register",
            headers={
                "Origin": "http://malicious-site.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert res.headers.get("Access-Control-Allow-Origin") is None


def test_registration_validation_short_password(test_app):
    with test_app.test_client() as client:
        res = client.post(
            "/api/v1/auth/register",
            headers={"Origin": "http://localhost:3000"},
            json={
                "email": "valid.user@example.com",
                "password": "short",
                "display_name": "Valid Name",
            },
        )
        assert res.status_code == 422
        body = res.get_json()
        assert body["error"]["code"] == "validation_error"


def test_registration_validation_invalid_email(test_app):
    with test_app.test_client() as client:
        res = client.post(
            "/api/v1/auth/register",
            headers={"Origin": "http://localhost:3000"},
            json={
                "email": "not-an-email",
                "password": "Correct-Horse-Battery-1",
                "display_name": "Valid Name",
            },
        )
        assert res.status_code == 422
        body = res.get_json()
        assert body["error"]["code"] == "validation_error"
