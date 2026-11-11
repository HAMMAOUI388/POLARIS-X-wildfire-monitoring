"""Tests for Phase 11 monitoring subscriptions API and alert integration."""
from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from polaris_x.app import create_app
from polaris_x.db.models import (
    DataSource,
    LocationAccess,
    MonitoringLocation,
    MonitoringSubscription,
    Role,
    SatelliteFireObservation,
    Severity,
    User,
)
from polaris_x.db.session import make_engine, make_session_factory
from polaris_x.extensions import db_session
from polaris_x.intelligence.alerts import AlertContext, generate_alert_for_match
from polaris_x.intelligence.detection import find_matches_for_observation


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
        "JWT_SECRET_KEY": "phase11-test-secret-with-32-bytes-minimum-length",
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


def register(client, email):
    return client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Correct-Horse-Battery-1",
        "display_name": "Test User",
    })


def login(client, email):
    response = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "Correct-Horse-Battery-1",
    })
    return response.json["access_token"]


def create_test_location(client, token, name="Test Farm", lon=-6.8, lat=33.9):
    res = client.post(
        "/api/v1/locations",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "location_type": "farm", "longitude": lon, "latitude": lat},
    )
    assert res.status_code == 201
    return res.json["location"]["id"]


def test_subscription_crud_lifecycle(client):
    email = f"test-{uuid4()}@example.com"
    register(client, email)
    token = login(client, email)
    location_id = create_test_location(client, token, "Olive Grove")

    # 1. Create subscription
    res = client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "location_id": location_id,
            "radius_m": 7500,
            "minimum_severity": "moderate",
            "enabled": True,
        },
    )
    assert res.status_code == 201
    sub_data = res.json["subscription"]
    sub_id = sub_data["id"]
    assert sub_data["location_id"] == location_id
    assert sub_data["radius_m"] == 7500.0
    assert sub_data["minimum_severity"] == "moderate"
    assert sub_data["enabled"] is True

    # 2. List subscriptions
    list_res = client.get("/api/v1/subscriptions", headers={"Authorization": f"Bearer {token}"})
    assert list_res.status_code == 200
    subs = list_res.json["subscriptions"]
    assert len(subs) == 1
    assert subs[0]["id"] == sub_id

    # 3. Get subscription details
    get_res = client.get(f"/api/v1/subscriptions/{sub_id}", headers={"Authorization": f"Bearer {token}"})
    assert get_res.status_code == 200
    assert get_res.json["subscription"]["id"] == sub_id

    # 4. Update subscription (radius, severity, enabled)
    patch_res = client.patch(
        f"/api/v1/subscriptions/{sub_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"radius_m": 12000, "minimum_severity": "high", "enabled": False},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json["subscription"]
    assert updated["radius_m"] == 12000.0
    assert updated["minimum_severity"] == "high"
    assert updated["enabled"] is False

    # 5. Delete subscription
    del_res = client.delete(f"/api/v1/subscriptions/{sub_id}", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 204

    # 6. Verify deleted
    assert client.get(f"/api/v1/subscriptions/{sub_id}", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert len(client.get("/api/v1/subscriptions", headers={"Authorization": f"Bearer {token}"}).json["subscriptions"]) == 0


def test_duplicate_subscription_rejected(client):
    email = f"test-{uuid4()}@example.com"
    register(client, email)
    token = login(client, email)
    loc_id = create_test_location(client, token)

    # First subscription: OK
    res1 = client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": loc_id, "radius_m": 5000},
    )
    assert res1.status_code == 201

    # Second subscription for same user & location: 409 Conflict
    res2 = client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": loc_id, "radius_m": 8000},
    )
    assert res2.status_code == 409
    assert res2.json["error"]["code"] == "conflict"


def test_unauthorized_location_and_idor_protection(client):
    owner_email = f"test-{uuid4()}@example.com"
    attacker_email = f"test-{uuid4()}@example.com"
    register(client, owner_email)
    register(client, attacker_email)
    owner_token = login(client, owner_email)
    attacker_token = login(client, attacker_email)

    loc_id = create_test_location(client, owner_token, "Owner Secret Farm")

    # Attacker tries to subscribe to owner's location -> 404 Not Found (private-resource 404)
    res = client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {attacker_token}"},
        json={"location_id": loc_id, "radius_m": 5000},
    )
    assert res.status_code == 404
    assert res.json["error"]["code"] == "not_found"

    # Owner creates subscription
    sub_res = client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"location_id": loc_id, "radius_m": 5000},
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json["subscription"]["id"]

    # Attacker tries to GET owner's subscription -> 404
    assert client.get(f"/api/v1/subscriptions/{sub_id}", headers={"Authorization": f"Bearer {attacker_token}"}).status_code == 404

    # Attacker tries to PATCH owner's subscription -> 404
    assert client.patch(
        f"/api/v1/subscriptions/{sub_id}",
        headers={"Authorization": f"Bearer {attacker_token}"},
        json={"radius_m": 100},
    ).status_code == 404

    # Attacker tries to DELETE owner's subscription -> 404
    assert client.delete(f"/api/v1/subscriptions/{sub_id}", headers={"Authorization": f"Bearer {attacker_token}"}).status_code == 404


def test_shared_location_allows_subscription(client):
    owner_email = f"test-{uuid4()}@example.com"
    viewer_email = f"test-{uuid4()}@example.com"
    register(client, owner_email)
    register(client, viewer_email)
    owner_token = login(client, owner_email)
    viewer_token = login(client, viewer_email)

    loc_id = create_test_location(client, owner_token, "Shared Property")

    with client.application.app_context():
        viewer_user = db_session().query(User).filter_by(email=viewer_email).one()
    # Share location with viewer
    share_res = client.post(
        f"/api/v1/locations/{loc_id}/shares",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"user_id": str(viewer_user.id), "permission": "view"},
    )
    assert share_res.status_code == 201

    # Viewer can now create their own subscription for the shared location
    sub_res = client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"location_id": loc_id, "radius_m": 6000, "minimum_severity": "low"},
    )
    assert sub_res.status_code == 201
    assert sub_res.json["subscription"]["user_id"] == str(viewer_user.id)


def test_jwt_enforcement_and_mass_assignment_protection(client):
    email = f"test-{uuid4()}@example.com"
    register(client, email)
    token = login(client, email)
    loc_id = create_test_location(client, token)

    # Missing token -> 401
    assert client.get("/api/v1/subscriptions").status_code == 401
    assert client.post("/api/v1/subscriptions", json={"location_id": loc_id}).status_code == 401

    # Mass assignment / arbitrary user_id in body must be rejected (extra="forbid")
    fake_user_id = str(uuid4())
    res = client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": loc_id, "user_id": fake_user_id},
    )
    assert res.status_code == 422


def test_validation_rules_for_subscriptions(client):
    email = f"test-{uuid4()}@example.com"
    register(client, email)
    token = login(client, email)
    loc_id = create_test_location(client, token)

    # Negative radius
    assert client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": loc_id, "radius_m": -100},
    ).status_code == 422

    # Zero radius
    assert client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": loc_id, "radius_m": 0},
    ).status_code == 422

    # Excessive radius (> 100 km)
    assert client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": loc_id, "radius_m": 150000},
    ).status_code == 422

    # Invalid severity string
    assert client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": loc_id, "minimum_severity": "catastrophic"},
    ).status_code == 422


def test_alert_matching_regression_with_api_subscription(client):
    """Verify that a subscription created via the API matches real observations in the alert engine."""
    from datetime import datetime, timezone

    email = f"test-{uuid4()}@example.com"
    register(client, email)
    token = login(client, email)

    # Create location at (lon=-6.84, lat=33.97)
    loc_id = create_test_location(client, token, "Monitored Vineyard", lon=-6.84, lat=33.97)

    # Create subscription with 10 km radius via API
    sub_res = client.post(
        "/api/v1/subscriptions",
        headers={"Authorization": f"Bearer {token}"},
        json={"location_id": loc_id, "radius_m": 10000, "minimum_severity": "low"},
    )
    assert sub_res.status_code == 201

    with client.application.app_context():
        session = db_session()
        suffix = uuid4().hex
        source = DataSource(name=f"test-source-{suffix}", source_type="satellite", provider="NASA FIRMS", metadata_json={})
        session.add(source)
        session.flush()

        # Observation ~2 km away from Vineyard (lon=-6.82, lat=33.98)
        obs = SatelliteFireObservation(
            source_id=source.id,
            external_id=f"firms-{suffix}",
            product="viirs",
            observed_at=datetime.now(timezone.utc),
            point=WKTElement("POINT(-6.82 33.98)", srid=4326),
            raw_payload={},
        )
        session.add(obs)
        session.flush()

        # Run alert matching engine
        matches = find_matches_for_observation(session, obs.id)
        test_user = session.query(User).filter_by(email=email).one()
        assert any(m.user_id == test_user.id for m in matches)

        match = next(m for m in matches if m.user_id == test_user.id)
        alert = generate_alert_for_match(session, AlertContext(match))
        assert alert is not None
        assert "not a confirmed wildfire" in alert.message
        session.commit()

    # Now verify user can retrieve the generated alert via API
    alerts_res = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {token}"})
    assert alerts_res.status_code == 200
    user_alerts = alerts_res.json["alerts"]
    assert len(user_alerts) >= 1
    assert user_alerts[0]["title"] == alert.title

    # Mark as read
    read_res = client.post(f"/api/v1/alerts/{user_alerts[0]['id']}/read", headers={"Authorization": f"Bearer {token}"})
    assert read_res.status_code == 200
    assert read_res.json["alert"]["status"] == "read"
