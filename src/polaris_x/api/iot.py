"""IoT Webhook and Telemetry Query API Blueprint."""
from __future__ import annotations

import hmac
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from geoalchemy2.shape import to_shape
from sqlalchemy import desc, select

from polaris_x.api.authz import current_user, has_role
from polaris_x.api.errors import error_response
from polaris_x.db.models import IOTUplink, LocationAccess, MonitoringLocation, SensorMeasurement, SensorNode
from polaris_x.extensions import db_session
from polaris_x.ingestion.iot_service import ingest_tts_uplink_transactional

bp = Blueprint("iot", __name__)


def _can_read_node_telemetry(user, node: SensorNode, session) -> bool:
    """Checks if user has permission to read telemetry for a node."""
    if has_role(user, "admin", "authority"):
        return True
    if not node.location_id:
        return False
    loc = session.get(MonitoringLocation, node.location_id)
    if loc is None:
        return False
    if loc.owner_id == user.id:
        return True
    grant = session.query(LocationAccess).filter_by(
        location_id=loc.id,
        user_id=user.id
    ).one_or_none()
    return grant is not None


@bp.post("/webhook/tts")
def tts_webhook():
    """Receives and processes The Things Stack v3 OTAA uplink webhooks."""
    auth_header = request.headers.get("Authorization", "")
    expected_token = current_app.config.get("IOT_WEBHOOK_SECRET")
    if not expected_token or not expected_token.strip():
        return error_response("unauthorized", "Webhook authentication is not configured.", 401)

    if not auth_header.startswith("Bearer "):
        return error_response("unauthorized", "Missing or invalid Bearer token.", 401)

    token = auth_header.split(" ", 1)[1].strip()
    if not hmac.compare_digest(token, expected_token.strip()):
        return error_response("unauthorized", "Invalid authentication secret.", 401)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("bad_request", "Expected JSON object payload.", 400)

    session = db_session()
    result, status_code = ingest_tts_uplink_transactional(session, payload)
    if status_code in (200, 201):
        session.commit()
        return jsonify(result), status_code
    else:
        session.rollback()
        code = result.get("error", "error")
        msg = result.get("message", "Error processing uplink.")
        return error_response(code, msg, status_code)


@bp.get("/nodes/<uuid:node_id>/telemetry/latest")
@jwt_required()
def latest_telemetry(node_id: UUID):
    """Retrieves latest telemetry reading and station health for a node."""
    session = db_session()
    node = session.get(SensorNode, node_id)
    if node is None:
        return error_response("not_found", "Sensor node not found.", 404)

    user = current_user()
    if not _can_read_node_telemetry(user, node, session):
        return error_response("forbidden", "Access denied to node telemetry.", 403)

    latest_uplink = session.execute(
        select(IOTUplink)
        .where(IOTUplink.node_id == node.id)
        .order_by(desc(IOTUplink.lns_received_at))
        .limit(1)
    ).scalar_one_or_none()

    measurements_data = []
    if latest_uplink:
        meas_rows = session.execute(
            select(SensorMeasurement)
            .where(SensorMeasurement.uplink_id == latest_uplink.id)
        ).scalars().all()
        for m in meas_rows:
            measurements_data.append({
                "sensor_id": str(m.sensor_id),
                "sensor_kind": m.sensor.kind.value if m.sensor else None,
                "sensor_identifier": m.sensor.sensor_identifier if m.sensor else None,
                "value_numeric": float(m.value_numeric) if m.value_numeric is not None else None,
                "raw_value_numeric": float(m.raw_value_numeric) if m.raw_value_numeric is not None else None,
                "unit": m.sensor.unit if m.sensor else None,
                "raw_value_unit": m.raw_value_unit,
                "quality_flag": m.quality_flag,
                "measured_at": m.measured_at.isoformat() if m.measured_at else None,
                "received_at": m.received_at.isoformat(),
            })

    loc_point = None
    if latest_uplink and latest_uplink.location_point is not None:
        pt = to_shape(latest_uplink.location_point)
        loc_point = {"longitude": pt.x, "latitude": pt.y}

    return jsonify({
        "node_id": str(node.id),
        "node_identifier": node.node_identifier,
        "name": node.name,
        "status": node.status,
        "active": node.active,
        "dev_eui": node.dev_eui,
        "battery_voltage": float(node.battery_voltage) if node.battery_voltage is not None else None,
        "last_seen_at": node.last_seen_at.isoformat() if node.last_seen_at else None,
        "last_f_cnt": node.last_f_cnt,
        "latest_uplink": {
            "id": str(latest_uplink.id) if latest_uplink else None,
            "session_id": latest_uplink.session_id if latest_uplink else None,
            "f_cnt": latest_uplink.f_cnt if latest_uplink else None,
            "lns_received_at": latest_uplink.lns_received_at.isoformat() if latest_uplink else None,
            "rssi_dbm": latest_uplink.rssi_dbm if latest_uplink else None,
            "snr_db": float(latest_uplink.snr_db) if latest_uplink and latest_uplink.snr_db is not None else None,
            "gateway_count": latest_uplink.gateway_count if latest_uplink else 0,
            "location_snapshot": {
                "name": latest_uplink.location_name_snapshot if latest_uplink else None,
                "point": loc_point,
            } if latest_uplink else None,
        } if latest_uplink else None,
        "measurements": measurements_data,
    })


@bp.get("/nodes/<uuid:node_id>/telemetry/history")
@jwt_required()
def history_telemetry(node_id: UUID):
    """Retrieves historical telemetry uplinks for a node."""
    session = db_session()
    node = session.get(SensorNode, node_id)
    if node is None:
        return error_response("not_found", "Sensor node not found.", 404)

    user = current_user()
    if not _can_read_node_telemetry(user, node, session):
        return error_response("forbidden", "Access denied to node telemetry.", 403)

    limit = min(int(request.args.get("limit", 50)), 200)
    uplinks = session.execute(
        select(IOTUplink)
        .where(IOTUplink.node_id == node.id)
        .order_by(desc(IOTUplink.lns_received_at))
        .limit(limit)
    ).scalars().all()

    history = []
    for up in uplinks:
        pt = to_shape(up.location_point) if up.location_point is not None else None
        meas_list = [{
            "sensor_identifier": m.sensor.sensor_identifier if m.sensor else None,
            "kind": m.sensor.kind.value if m.sensor else None,
            "value": float(m.value_numeric) if m.value_numeric is not None else None,
            "unit": m.sensor.unit if m.sensor else None,
            "quality_flag": m.quality_flag,
        } for m in up.measurements]

        history.append({
            "uplink_id": str(up.id),
            "f_cnt": up.f_cnt,
            "lns_received_at": up.lns_received_at.isoformat(),
            "rssi_dbm": up.rssi_dbm,
            "snr_db": float(up.snr_db) if up.snr_db is not None else None,
            "location_name": up.location_name_snapshot,
            "location_point": {"longitude": pt.x, "latitude": pt.y} if pt else None,
            "measurements": meas_list,
        })

    return jsonify(history=history, count=len(history))
