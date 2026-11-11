"""Tests for Phase 11 role-based authorization foundation."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from polaris_x.app import create_app
from polaris_x.db.models import LocationAccess, MonitoringLocation, MonitoringSubscription, Role, User
from polaris_x.db.session import make_engine, make_session_factory
from polaris_x.extensions import db_session


@pytest.fixture(scope="module")
def database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = make_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT PostGIS_Version()"))
    except Exception as exc:
        pytest.skip(f"PostGIS database unavailable: {exc}")
    engine.dispose()
    Session = make_session_factory(url)
    with Session.begin() as session:
        for name in ("user", "farm_owner", "authority", "admin"):
            if session.query(Role).filter_by(name=name).one_or_none() is None:
                session.add(Role(name=name))
    return url


@pytest.fixture
def client(database_url):
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": database_url,
        "JWT_SECRET_KEY": "phase11-authz-test-secret-with-32-bytes-minimum",
    })
    with app.test_client() as client:
        yield client
    with app.app_context():
        session = db_session()
        test_user_ids = session.query(User.id).filter(User.email.like("test-%@example.com"))
        session.query(MonitoringSubscription).filter(MonitoringSubscription.user_id.in_(test_user_ids)).delete(synchronize_session=False)
        session.query(LocationAccess).filter(LocationAccess.user_id.in_(test_user_ids)).delete(synchronize_session=False)
        session.query(MonitoringLocation).filter(MonitoringLocation.owner_id.in_(test_user_ids)).delete(synchronize_session=False)
        session.query(User).filter(User.email.like("test-%@example.com")).delete(synchronize_session=False)
        session.commit()


def create_user_with_roles(client, email, role_names: list[str]) -> str:
    """Helper to create a user with specific roles in the test DB and log in."""
    client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Correct-Horse-Battery-1",
        "display_name": f"User {','.join(role_names)}",
    })
    with client.application.app_context():
        session = db_session()
        u = session.query(User).filter_by(email=email).one()
        for r_name in role_names:
            role = session.query(Role).filter_by(name=r_name).one()
            if role not in u.roles:
                u.roles.append(role)
        session.commit()
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-1"})
    return res.json["access_token"]


def test_ordinary_user_cannot_self_assign_roles(client):
    """Registration rejects roles parameter (mass assignment / privilege escalation prevention)."""
    email = f"test-{uuid4()}@example.com"
    res1 = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Correct-Horse-Battery-1",
        "display_name": "Attacker",
        "roles": ["admin"],
    })
    assert res1.status_code == 422

    res2 = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Correct-Horse-Battery-1",
        "display_name": "Attacker",
        "roles": ["authority"],
    })
    assert res2.status_code == 422


def test_ordinary_user_role_boundaries(client):
    """Ordinary user has public portal access, but 403 on authority and admin endpoints."""
    token = create_user_with_roles(client, f"test-{uuid4()}@example.com", ["user"])

    # Public portal endpoints: 200 OK
    assert client.get("/api/v1/locations", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/subscriptions", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Professional portal endpoints: 403 Forbidden
    auth_res = client.get("/api/v1/authority/events", headers={"Authorization": f"Bearer {token}"})
    assert auth_res.status_code == 403
    assert auth_res.json["error"]["code"] == "forbidden"

    admin_res = client.get("/api/v1/admin/system", headers={"Authorization": f"Bearer {token}"})
    assert admin_res.status_code == 403
    assert admin_res.json["error"]["code"] == "forbidden"


def test_farm_owner_cannot_access_authority_or_admin(client):
    """Farm owner is restricted to public portal capabilities."""
    token = create_user_with_roles(client, f"test-{uuid4()}@example.com", ["user", "farm_owner"])

    # Public portal access: 200 OK
    assert client.get("/api/v1/locations", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Cannot access authority endpoint: 403
    assert client.get("/api/v1/authority/events", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.get("/api/v1/authority/operational-summary", headers={"Authorization": f"Bearer {token}"}).status_code == 403

    # Cannot access admin endpoint: 403
    assert client.get("/api/v1/admin/system", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_authority_cannot_access_admin_or_private_locations(client):
    """Authority can access operational events, but cannot access admin system, and cannot view private user locations."""
    authority_token = create_user_with_roles(client, f"test-{uuid4()}@example.com", ["user", "authority"])
    owner_token = create_user_with_roles(client, f"test-{uuid4()}@example.com", ["user"])

    # Authority CAN access operational authority endpoints
    auth_events = client.get("/api/v1/authority/events", headers={"Authorization": f"Bearer {authority_token}"})
    assert auth_events.status_code == 200
    assert "events" in auth_events.json

    auth_summary = client.get("/api/v1/authority/operational-summary", headers={"Authorization": f"Bearer {authority_token}"})
    assert auth_summary.status_code == 200
    assert auth_summary.json["mode"] == "professional_monitoring"

    # Authority CANNOT access admin-only endpoints (must not automatically become administrator)
    admin_res = client.get("/api/v1/admin/system", headers={"Authorization": f"Bearer {authority_token}"})
    assert admin_res.status_code == 403
    assert admin_res.json["error"]["code"] == "forbidden"

    # Authority CANNOT read other users' private locations without grant
    loc_res = client.post(
        "/api/v1/locations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Private Farm", "location_type": "farm", "longitude": -6.8, "latitude": 33.9},
    )
    loc_id = loc_res.json["location"]["id"]
    assert client.get(f"/api/v1/locations/{loc_id}", headers={"Authorization": f"Bearer {authority_token}"}).status_code == 404


def test_admin_full_professional_access(client):
    """Admin has access to both authority and admin endpoints, plus location ownership overrides."""
    admin_token = create_user_with_roles(client, f"test-{uuid4()}@example.com", ["user", "admin"])
    owner_token = create_user_with_roles(client, f"test-{uuid4()}@example.com", ["user"])

    # Admin CAN access authority endpoints
    assert client.get("/api/v1/authority/events", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200

    # Admin CAN access admin endpoints
    admin_sys = client.get("/api/v1/admin/system", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_sys.status_code == 200
    assert "total_users" in admin_sys.json

    # Admin CAN read private user locations (admin override)
    loc_res = client.post(
        "/api/v1/locations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Owner Property", "location_type": "point", "longitude": -6.8, "latitude": 33.9},
    )
    loc_id = loc_res.json["location"]["id"]
    assert client.get(f"/api/v1/locations/{loc_id}", headers={"Authorization": f"Bearer {admin_token}"}).status_code == 200
