"""Professional portal administration API."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select
from uuid import UUID

from polaris_x.api.authz import roles_required
from polaris_x.api.errors import error_response
from polaris_x.db.models import DataSource, MonitoringLocation, Role, SensorNode, User
from polaris_x.extensions import db_session

bp = Blueprint("admin", __name__)


@bp.get("/system")
@roles_required("admin")
def system_overview():
    session = db_session()
    user_count = session.scalar(select(func.count(User.id))) or 0
    roles = session.execute(select(Role)).scalars().all()
    role_distribution = {role.name: len(role.users) for role in roles}
    sources = session.execute(select(DataSource)).scalars().all()

    return jsonify({
        "status": "ok",
        "total_users": user_count,
        "roles": role_distribution,
        "data_sources": [{"id": str(s.id), "name": s.name, "provider": s.provider, "type": s.source_type} for s in sources],
    })


@bp.post("/iot/nodes")
@roles_required("admin")
def provision_iot_node():
    """Admin-only endpoint to provision a new IoT sensor station."""
    body = request.get_json(silent=True) or {}
    node_identifier = body.get("node_identifier", "").strip()
    name = body.get("name", "").strip()
    dev_eui = body.get("dev_eui", "").strip().upper() if body.get("dev_eui") else None

    if not node_identifier or not name:
        return error_response("bad_request", "Fields 'node_identifier' and 'name' are required.", 400)

    session = db_session()
    existing = session.query(SensorNode).filter(
        (SensorNode.node_identifier == node_identifier) |
        ((SensorNode.dev_eui == dev_eui) if dev_eui else False)
    ).first()
    if existing:
        return error_response("conflict", "A sensor node with this identifier or dev_eui already exists.", 409)

    location_id = None
    if body.get("location_id"):
        try:
            loc_uuid = UUID(body["location_id"])
            loc = session.get(MonitoringLocation, loc_uuid)
            if loc is None:
                return error_response("not_found", "Specified location_id does not exist.", 404)
            location_id = loc.id
        except Exception:
            return error_response("bad_request", "Invalid location_id UUID.", 400)

    node = SensorNode(
        node_identifier=node_identifier,
        name=name,
        dev_eui=dev_eui,
        join_eui=body.get("join_eui", "").strip().upper() if body.get("join_eui") else None,
        hardware_version=body.get("hardware_version"),
        firmware_version=body.get("firmware_version"),
        location_id=location_id,
        status="active",
        active=True,
    )
    session.add(node)
    session.commit()

    return jsonify({
        "id": str(node.id),
        "node_identifier": node.node_identifier,
        "name": node.name,
        "dev_eui": node.dev_eui,
        "location_id": str(node.location_id) if node.location_id else None,
        "status": node.status,
    }), 201


@bp.get("/iot/nodes")
@roles_required("admin")
def list_admin_iot_nodes():
    """Admin-only endpoint to inspect all provisioned IoT sensor stations."""
    session = db_session()
    nodes = session.execute(select(SensorNode).order_by(SensorNode.created_at.desc())).scalars().all()
    results = []
    for n in nodes:
        results.append({
            "id": str(n.id),
            "node_identifier": n.node_identifier,
            "name": n.name,
            "dev_eui": n.dev_eui,
            "location_id": str(n.location_id) if n.location_id else None,
            "status": n.status,
            "active": n.active,
            "battery_voltage": float(n.battery_voltage) if n.battery_voltage is not None else None,
            "last_seen_at": n.last_seen_at.isoformat() if n.last_seen_at else None,
            "last_f_cnt": n.last_f_cnt,
        })
    return jsonify(nodes=results, count=len(results))


@bp.patch("/iot/nodes/<uuid:node_id>")
@roles_required("admin")
def update_iot_node(node_id: UUID):
    """Admin-only endpoint to update station lifecycle status or metadata."""
    session = db_session()
    node = session.get(SensorNode, node_id)
    if node is None:
        return error_response("not_found", "Sensor node not found.", 404)

    body = request.get_json(silent=True) or {}
    if "name" in body:
        node.name = body["name"].strip()
    if "status" in body:
        new_status = body["status"].strip().lower()
        if new_status not in ("active", "retired", "decommissioned"):
            return error_response("bad_request", "Invalid status. Allowed: 'active', 'retired', 'decommissioned'.", 400)
        node.status = new_status
        if new_status in ("retired", "decommissioned"):
            node.active = False
        else:
            node.active = True
    elif "active" in body:
        is_act = bool(body["active"])
        node.active = is_act
        if not is_act and node.status == "active":
            node.status = "retired"
        elif is_act and node.status in ("retired", "decommissioned"):
            node.status = "active"

    if "location_id" in body:
        if body["location_id"] is None:
            node.location_id = None
        else:
            try:
                loc_uuid = UUID(body["location_id"])
                if session.get(MonitoringLocation, loc_uuid) is None:
                    return error_response("not_found", "Specified location_id does not exist.", 404)
                node.location_id = loc_uuid
            except Exception:
                return error_response("bad_request", "Invalid location_id UUID.", 400)

    session.commit()
    return jsonify({
        "id": str(node.id),
        "node_identifier": node.node_identifier,
        "name": node.name,
        "status": node.status,
        "active": node.active,
        "location_id": str(node.location_id) if node.location_id else None,
    })
