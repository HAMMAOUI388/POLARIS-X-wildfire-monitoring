"""Comprehensive integration, security, idempotency, and retention tests for IoT Telemetry (Phase 13.1)."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from polaris_x.app import create_app
from polaris_x.db.models import (
    IOTUplink,
    LocationAccess,
    LocationType,
    MonitoringLocation,
    Role,
    Sensor,
    SensorMeasurement,
    SensorNode,
    User,
)
from polaris_x.db.session import make_engine, make_session_factory
from polaris_x.extensions import db_session
from polaris_x.ingestion.iot_schemas import TTSWebhookPayload
from tests.fixtures.tts_v3_fixtures import make_tts_uplink_payload


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
        "JWT_SECRET_KEY": "phase13-iot-test-secret-with-at-least-32-bytes",
        "IOT_WEBHOOK_SECRET": "test-iot-webhook-secret-phase13",
    })
    with app.test_client() as client:
        yield client
    with app.app_context():
        session = db_session()
        # Clean up test nodes, uplinks, and measurements
        test_nodes = session.query(SensorNode.id).filter(SensorNode.node_identifier.like("test-%"))
        uplink_ids = session.query(IOTUplink.id).filter(IOTUplink.node_id.in_(test_nodes))
        session.query(SensorMeasurement).filter(SensorMeasurement.uplink_id.in_(uplink_ids)).delete(synchronize_session=False)
        session.query(IOTUplink).filter(IOTUplink.id.in_(uplink_ids)).delete(synchronize_session=False)
        session.query(Sensor).filter(Sensor.node_id.in_(test_nodes)).delete(synchronize_session=False)
        session.query(SensorNode).filter(SensorNode.id.in_(test_nodes)).delete(synchronize_session=False)

        test_user_ids = session.query(User.id).filter(User.email.like("test-%@example.com"))
        session.query(LocationAccess).filter(LocationAccess.user_id.in_(test_user_ids)).delete(synchronize_session=False)
        session.query(MonitoringLocation).filter(MonitoringLocation.owner_id.in_(test_user_ids)).delete(synchronize_session=False)
        session.query(User).filter(User.id.in_(test_user_ids)).delete(synchronize_session=False)
        session.commit()


def _login_user(client, role_name: str) -> str:
    email = f"test-{uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "Correct-Horse-Battery-1",
        "display_name": f"User {role_name}",
    })
    with client.application.app_context():
        session = db_session()
        u = session.query(User).filter_by(email=email).one()
        role = session.query(Role).filter_by(name=role_name).one()
        if role not in u.roles:
            u.roles.append(role)
        session.commit()
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-1"})
    return res.json["access_token"]


def test_webhook_authentication(client):
    """Webhook requires valid Bearer token."""
    payload = make_tts_uplink_payload()

    # 1. Missing header -> 401
    res1 = client.post("/api/v1/iot/webhook/tts", json=payload)
    assert res1.status_code == 401
    assert res1.json["error"]["code"] == "unauthorized"

    # 2. Bad token -> 401
    res2 = client.post(
        "/api/v1/iot/webhook/tts",
        json=payload,
        headers={"Authorization": "Bearer invalid-secret"}
    )
    assert res2.status_code == 401
    assert res2.json["error"]["code"] == "unauthorized"


def test_webhook_authentication_fail_closed(client):
    """When IOT_WEBHOOK_SECRET is missing or empty, webhook requests fail closed (401)."""
    payload = make_tts_uplink_payload()
    app = client.application

    # Test with None
    original_secret = app.config.get("IOT_WEBHOOK_SECRET")
    try:
        app.config["IOT_WEBHOOK_SECRET"] = None
        res1 = client.post(
            "/api/v1/iot/webhook/tts",
            json=payload,
            headers={"Authorization": "Bearer some-token"}
        )
        assert res1.status_code == 401
        assert res1.json["error"]["code"] == "unauthorized"
        assert "not configured" in res1.json["error"]["message"].lower()

        # Test with empty string
        app.config["IOT_WEBHOOK_SECRET"] = ""
        res2 = client.post(
            "/api/v1/iot/webhook/tts",
            json=payload,
            headers={"Authorization": "Bearer some-token"}
        )
        assert res2.status_code == 401
        assert res2.json["error"]["code"] == "unauthorized"
        assert "not configured" in res2.json["error"]["message"].lower()

        # Test with whitespace string
        app.config["IOT_WEBHOOK_SECRET"] = "   "
        res3 = client.post(
            "/api/v1/iot/webhook/tts",
            json=payload,
            headers={"Authorization": "Bearer some-token"}
        )
        assert res3.status_code == 401
        assert res3.json["error"]["code"] == "unauthorized"
    finally:
        app.config["IOT_WEBHOOK_SECRET"] = original_secret


def test_webhook_rejects_inactive_or_decommissioned_stations(client):
    """Inactive, retired, or decommissioned stations are rejected with 403 Forbidden without persisting telemetry."""
    dev_eui_inactive = f"INA{uuid4().hex[:13].upper()}"
    dev_eui_retired = f"RET{uuid4().hex[:13].upper()}"
    dev_eui_decom = f"DEC{uuid4().hex[:13].upper()}"

    with client.application.app_context():
        session = db_session()
        node_inactive = SensorNode(
            node_identifier=f"test-inactive-{uuid4().hex[:6]}",
            name="Inactive Station",
            dev_eui=dev_eui_inactive,
            active=False,
            status="active",  # active is False
        )
        node_retired = SensorNode(
            node_identifier=f"test-retired-{uuid4().hex[:6]}",
            name="Retired Station",
            dev_eui=dev_eui_retired,
            active=False,
            status="retired",
        )
        node_decom = SensorNode(
            node_identifier=f"test-decom-{uuid4().hex[:6]}",
            name="Decommissioned Station",
            dev_eui=dev_eui_decom,
            active=False,
            status="decommissioned",
        )
        session.add_all([node_inactive, node_retired, node_decom])
        session.commit()

    headers = {"Authorization": "Bearer test-iot-webhook-secret-phase13"}

    # 1. Inactive node (active=False) -> 403
    p1 = make_tts_uplink_payload(dev_eui=dev_eui_inactive, session_key_id="01HINACTIVEKEY", f_cnt=1)
    res1 = client.post("/api/v1/iot/webhook/tts", json=p1, headers=headers)
    assert res1.status_code == 403
    assert res1.json["error"]["code"] == "forbidden"

    # 2. Retired node -> 403
    p2 = make_tts_uplink_payload(dev_eui=dev_eui_retired, session_key_id="01HRETIREDKEY", f_cnt=1)
    res2 = client.post("/api/v1/iot/webhook/tts", json=p2, headers=headers)
    assert res2.status_code == 403
    assert res2.json["error"]["code"] == "forbidden"

    # 3. Decommissioned node -> 403
    p3 = make_tts_uplink_payload(dev_eui=dev_eui_decom, session_key_id="01HDECOMKEY", f_cnt=1)
    res3 = client.post("/api/v1/iot/webhook/tts", json=p3, headers=headers)
    assert res3.status_code == 403
    assert res3.json["error"]["code"] == "forbidden"

    # Verify no uplinks or measurements created, and last_seen_at remains None
    with client.application.app_context():
        session = db_session()
        for eui in (dev_eui_inactive, dev_eui_retired, dev_eui_decom):
            assert session.query(IOTUplink).filter_by(dev_eui=eui).count() == 0
            n = session.query(SensorNode).filter_by(dev_eui=eui).one()
            assert n.last_seen_at is None
            assert n.last_f_cnt is None


def test_admin_lifecycle_synchronization(client):
    """Patching status or active keeps both fields strictly synchronized."""
    admin_token = _login_user(client, "admin")
    dev_eui = f"SYN{uuid4().hex[:13].upper()}"
    node_ident = f"test-sync-node-{uuid4().hex[:6]}"

    # Provision station (defaults to active=True, status='active')
    res = client.post(
        "/api/v1/admin/iot/nodes",
        json={"node_identifier": node_ident, "name": "Sync Test Station", "dev_eui": dev_eui},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 201
    node_id = res.json["id"]
    assert res.json["status"] == "active"

    # 1. Update status to retired -> active becomes False
    res1 = client.patch(
        f"/api/v1/admin/iot/nodes/{node_id}",
        json={"status": "retired"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res1.status_code == 200
    assert res1.json["status"] == "retired"
    assert res1.json["active"] is False

    # 2. Update active to True -> status becomes active
    res2 = client.patch(
        f"/api/v1/admin/iot/nodes/{node_id}",
        json={"active": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res2.status_code == 200
    assert res2.json["status"] == "active"
    assert res2.json["active"] is True

    # 3. Update status to decommissioned -> active becomes False
    res3 = client.patch(
        f"/api/v1/admin/iot/nodes/{node_id}",
        json={"status": "decommissioned"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res3.status_code == 200
    assert res3.json["status"] == "decommissioned"
    assert res3.json["active"] is False

    # 4. Update active to False when status was active -> status becomes retired
    # First re-activate
    client.patch(f"/api/v1/admin/iot/nodes/{node_id}", json={"status": "active"}, headers={"Authorization": f"Bearer {admin_token}"})
    res4 = client.patch(
        f"/api/v1/admin/iot/nodes/{node_id}",
        json={"active": False},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res4.status_code == 200
    assert res4.json["status"] == "retired"
    assert res4.json["active"] is False


def test_webhook_rejects_missing_session_key_id(client):
    """OTAA requirement: Payloads missing session_key_id return 422 Unprocessable Entity."""
    payload = make_tts_uplink_payload()
    del payload["uplink_message"]["session_key_id"]

    res = client.post(
        "/api/v1/iot/webhook/tts",
        json=payload,
        headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"}
    )
    assert res.status_code == 422
    assert res.json["error"]["code"] == "unprocessable_entity"


def test_webhook_unprovisioned_device(client):
    """Payload for an unknown DevEUI returns 404 Not Found."""
    payload = make_tts_uplink_payload(dev_eui="AABBCCDDEEFF0011")

    res = client.post(
        "/api/v1/iot/webhook/tts",
        json=payload,
        headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"}
    )
    assert res.status_code == 404
    assert res.json["error"]["code"] == "not_found"


def test_successful_otaa_uplink_ingestion_and_spatial_snapshot(client):
    """Verifies complete ingestion, timestamp honesty (measured_at=None), and location snapshots."""
    dev_eui = f"TEST{uuid4().hex[:12].upper()}"
    node_id = None
    loc_id = None

    with client.application.app_context():
        session = db_session()
        owner = User(
            email=f"test-{uuid4()}@example.com",
            display_name="Owner",
            password_hash="fakehash"
        )
        session.add(owner)
        session.flush()

        loc = MonitoringLocation(
            owner_id=owner.id,
            name="Ifrane National Park Station",
            location_type=LocationType.point,
            point=WKTElement("POINT(-5.1234 33.5678)", srid=4326),
        )
        session.add(loc)
        session.flush()
        loc_id = loc.id

        node = SensorNode(
            node_identifier=f"test-node-{uuid4().hex[:8]}",
            name="Ifrane Node 01",
            dev_eui=dev_eui,
            location_id=loc.id,
            status="active",
        )
        session.add(node)
        session.commit()
        node_id = node.id

    payload = make_tts_uplink_payload(
        dev_eui=dev_eui,
        session_key_id="01HSESSIONKEYALPHA",
        f_cnt=10,
        temperature=22.4,
        humidity=41.5,
        pressure=1012.3,
        battery=3.92,
    )

    res = client.post(
        "/api/v1/iot/webhook/tts",
        json=payload,
        headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"}
    )
    assert res.status_code == 201
    assert res.json["status"] == "created"
    uplink_id = res.json["uplink_id"]

    with client.application.app_context():
        session = db_session()
        uplink = session.get(IOTUplink, uplink_id)
        assert uplink is not None
        assert uplink.dev_eui == dev_eui
        assert uplink.session_id == "01HSESSIONKEYALPHA"
        assert uplink.f_cnt == 10
        assert uplink.location_name_snapshot == "Ifrane National Park Station"
        assert uplink.location_point is not None

        # Verify timestamp honesty:
        assert uplink.sampled_at is None
        assert uplink.lns_received_at is not None

        # Verify measurements
        measurements = session.query(SensorMeasurement).filter_by(uplink_id=uplink.id).all()
        assert len(measurements) == 4
        for m in measurements:
            assert m.measured_at is None  # Never fabricated!
            assert m.received_at == uplink.lns_received_at
            assert m.quality_flag == "good"

        # Verify node health state updated
        n = session.get(SensorNode, node_id)
        assert n.last_f_cnt == 10
        assert n.last_session_id == "01HSESSIONKEYALPHA"
        assert n.last_seen_at == uplink.lns_received_at
        assert n.battery_voltage == Decimal("3.92")


def test_idempotent_duplicate_delivery(client):
    """Replaying an identical (dev_eui, session_id, f_cnt) returns 200 and inserts ZERO duplicate rows."""
    dev_eui = f"TEST{uuid4().hex[:12].upper()}"

    with client.application.app_context():
        session = db_session()
        node = SensorNode(
            node_identifier=f"test-node-{uuid4().hex[:8]}",
            name="Atlas Station",
            dev_eui=dev_eui,
            status="active",
        )
        session.add(node)
        session.commit()

    payload = make_tts_uplink_payload(
        dev_eui=dev_eui,
        session_key_id="01HSESSIONDUPLICATETEST",
        f_cnt=5,
    )

    # First delivery -> 201 Created
    res1 = client.post(
        "/api/v1/iot/webhook/tts",
        json=payload,
        headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"}
    )
    assert res1.status_code == 201
    assert res1.json["status"] == "created"

    with client.application.app_context():
        session = db_session()
        count_uplinks_1 = session.query(IOTUplink).filter_by(dev_eui=dev_eui).count()
        count_meas_1 = session.query(SensorMeasurement).count()
        assert count_uplinks_1 == 1

    # Second delivery (identical retry) -> 200 duplicate_ignored
    res2 = client.post(
        "/api/v1/iot/webhook/tts",
        json=payload,
        headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"}
    )
    assert res2.status_code == 200
    assert res2.json["status"] == "duplicate_ignored"

    with client.application.app_context():
        session = db_session()
        count_uplinks_2 = session.query(IOTUplink).filter_by(dev_eui=dev_eui).count()
        count_meas_2 = session.query(SensorMeasurement).count()
        assert count_uplinks_2 == count_uplinks_1  # Zero new uplinks
        assert count_meas_2 == count_meas_1        # Zero new measurements


def test_otaa_rejoin_resets_fcnt_successfully(client):
    """Device OTAA rejoin (new session_id with f_cnt=0) is accepted as a new uplink without collision."""
    dev_eui = f"TEST{uuid4().hex[:12].upper()}"

    with client.application.app_context():
        session = db_session()
        node = SensorNode(
            node_identifier=f"test-node-{uuid4().hex[:8]}",
            name="Rejoin Test Node",
            dev_eui=dev_eui,
            status="active",
        )
        session.add(node)
        session.commit()

    # Session 1: f_cnt 0
    p1 = make_tts_uplink_payload(dev_eui=dev_eui, session_key_id="01HSESSIONONE", f_cnt=0)
    res1 = client.post("/api/v1/iot/webhook/tts", json=p1, headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"})
    assert res1.status_code == 201

    # Session 1: f_cnt 1
    p2 = make_tts_uplink_payload(dev_eui=dev_eui, session_key_id="01HSESSIONONE", f_cnt=1)
    res2 = client.post("/api/v1/iot/webhook/tts", json=p2, headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"})
    assert res2.status_code == 201

    # Node reboots / rejoins: Session 2, f_cnt resets to 0!
    p3 = make_tts_uplink_payload(dev_eui=dev_eui, session_key_id="01HSESSIONTWO", f_cnt=0)
    res3 = client.post("/api/v1/iot/webhook/tts", json=p3, headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"})
    assert res3.status_code == 201
    assert res3.json["status"] == "created"

    with client.application.app_context():
        session = db_session()
        uplinks = session.query(IOTUplink).filter_by(dev_eui=dev_eui).order_by(IOTUplink.ingested_at).all()
        assert len(uplinks) == 3
        assert uplinks[0].session_id == "01HSESSIONONE" and uplinks[0].f_cnt == 0
        assert uplinks[1].session_id == "01HSESSIONONE" and uplinks[1].f_cnt == 1
        assert uplinks[2].session_id == "01HSESSIONTWO" and uplinks[2].f_cnt == 0


def test_admin_station_provisioning(client):
    """Admin can provision and update nodes; regular users cannot."""
    admin_token = _login_user(client, "admin")
    user_token = _login_user(client, "user")

    dev_eui = f"ADM{uuid4().hex[:13].upper()}"
    node_ident = f"test-admin-node-{uuid4().hex[:6]}"

    # Non-admin forbidden
    res1 = client.post(
        "/api/v1/admin/iot/nodes",
        json={"node_identifier": node_ident, "name": "Station A", "dev_eui": dev_eui},
        headers={"Authorization": f"Bearer {user_token}"}
    )
    assert res1.status_code == 403

    # Admin provisions station
    res2 = client.post(
        "/api/v1/admin/iot/nodes",
        json={"node_identifier": node_ident, "name": "Station A", "dev_eui": dev_eui},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res2.status_code == 201
    node_id = res2.json["id"]
    assert res2.json["dev_eui"] == dev_eui

    # Admin lists stations
    res3 = client.get("/api/v1/admin/iot/nodes", headers={"Authorization": f"Bearer {admin_token}"})
    assert res3.status_code == 200
    assert any(n["id"] == node_id for n in res3.json["nodes"])

    # Admin patches lifecycle status to retired
    res4 = client.patch(
        f"/api/v1/admin/iot/nodes/{node_id}",
        json={"status": "retired"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res4.status_code == 200
    assert res4.json["status"] == "retired"
    assert res4.json["active"] is False


def test_authority_station_monitoring(client):
    """Authority can view active stations; regular users cannot."""
    auth_token = _login_user(client, "authority")
    user_token = _login_user(client, "user")

    # Regular user forbidden
    res1 = client.get("/api/v1/authority/iot/nodes", headers={"Authorization": f"Bearer {user_token}"})
    assert res1.status_code == 403

    # Authority allowed
    res2 = client.get("/api/v1/authority/iot/nodes", headers={"Authorization": f"Bearer {auth_token}"})
    assert res2.status_code == 200
    assert "nodes" in res2.json


def test_location_deletion_preserves_spatial_snapshot(client):
    """Deleting a MonitoringLocation sets node.location_id to NULL but retains uplink snapshot."""
    dev_eui = f"SNP{uuid4().hex[:13].upper()}"
    loc_id = None
    uplink_id = None

    with client.application.app_context():
        session = db_session()
        owner = User(email=f"test-{uuid4()}@example.com", display_name="Owner", password_hash="fake")
        session.add(owner)
        session.flush()

        loc = MonitoringLocation(
            owner_id=owner.id,
            name="Pre-Deletion Historic Location",
            location_type=LocationType.point,
            point=WKTElement("POINT(-4.9876 34.1234)", srid=4326),
        )
        session.add(loc)
        session.flush()
        loc_id = loc.id

        node = SensorNode(
            node_identifier=f"test-node-{uuid4().hex[:8]}",
            name="Snapshot Station",
            dev_eui=dev_eui,
            location_id=loc.id,
            status="active",
        )
        session.add(node)
        session.commit()

    # Ingest uplink
    payload = make_tts_uplink_payload(dev_eui=dev_eui, session_key_id="01HSNAPSHOTSESSION", f_cnt=1)
    res = client.post("/api/v1/iot/webhook/tts", json=payload, headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"})
    assert res.status_code == 201
    uplink_id = res.json["uplink_id"]

    # Delete the location
    with client.application.app_context():
        session = db_session()
        loc = session.get(MonitoringLocation, loc_id)
        session.delete(loc)
        session.commit()

        # Verify uplink still exists, location_id is NULL, but spatial snapshot is frozen:
        up = session.get(IOTUplink, uplink_id)
        assert up is not None
        assert up.location_id is None
        assert up.location_name_snapshot == "Pre-Deletion Historic Location"
        assert up.location_point is not None


def test_telemetry_query_authorization_matrix(client):
    """Public users can view only telemetry for owned/granted locations; authority/admin can view all."""
    admin_token = _login_user(client, "admin")
    auth_token = _login_user(client, "authority")
    owner_token = _login_user(client, "farm_owner")
    unrelated_user_token = _login_user(client, "user")

    dev_eui = f"QRY{uuid4().hex[:13].upper()}"
    node_id = None

    with client.application.app_context():
        session = db_session()
        owner = session.query(User).filter(User.email.like("test-%@example.com")).filter(User.roles.any(name="farm_owner")).first()
        loc = MonitoringLocation(
            owner_id=owner.id,
            name="Private Farm Station",
            location_type=LocationType.farm,
            point=WKTElement("POINT(-5.0 34.0)", srid=4326),
        )
        session.add(loc)
        session.flush()

        node = SensorNode(
            node_identifier=f"test-node-{uuid4().hex[:8]}",
            name="Private Farm Node",
            dev_eui=dev_eui,
            location_id=loc.id,
            status="active",
        )
        session.add(node)
        session.commit()
        node_id = node.id

    # Ingest one uplink
    payload = make_tts_uplink_payload(dev_eui=dev_eui, session_key_id="01HQUERYKEY", f_cnt=1)
    client.post("/api/v1/iot/webhook/tts", json=payload, headers={"Authorization": "Bearer test-iot-webhook-secret-phase13"})

    # 1. Unrelated user -> 403 Forbidden
    res1 = client.get(f"/api/v1/iot/nodes/{node_id}/telemetry/latest", headers={"Authorization": f"Bearer {unrelated_user_token}"})
    assert res1.status_code == 403

    # 2. Location owner -> 200 OK
    res2 = client.get(f"/api/v1/iot/nodes/{node_id}/telemetry/latest", headers={"Authorization": f"Bearer {owner_token}"})
    assert res2.status_code == 200
    assert res2.json["node_id"] == str(node_id)
    assert len(res2.json["measurements"]) == 4

    # 3. Authority -> 200 OK
    res3 = client.get(f"/api/v1/iot/nodes/{node_id}/telemetry/latest", headers={"Authorization": f"Bearer {auth_token}"})
    assert res3.status_code == 200

    # 4. Admin -> 200 OK
    res4 = client.get(f"/api/v1/iot/nodes/{node_id}/telemetry/history", headers={"Authorization": f"Bearer {admin_token}"})
    assert res4.status_code == 200
    assert res4.json["count"] == 1
