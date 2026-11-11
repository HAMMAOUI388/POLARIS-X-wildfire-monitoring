"""Professional portal authority operational monitoring API."""
from __future__ import annotations

from flask import Blueprint, jsonify
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select

from polaris_x.api.authz import roles_required
from polaris_x.db.models import FireEvent, SatelliteFireObservation
from polaris_x.extensions import db_session

bp = Blueprint("authority", __name__)


@bp.get("/events")
@roles_required("authority", "admin")
def regional_events():
    session = db_session()
    events = session.execute(select(FireEvent).order_by(FireEvent.started_at.desc()).limit(100)).scalars().all()
    results = []
    for event in events:
        pt = to_shape(event.centroid) if event.centroid is not None else None
        results.append({
            "id": str(event.id),
            "status": event.status,
            "started_at": event.started_at.isoformat(),
            "ended_at": event.ended_at.isoformat() if event.ended_at else None,
            "centroid": {"longitude": pt.x, "latitude": pt.y} if pt else None,
        })
    return jsonify(events=results, count=len(results))


@bp.get("/operational-summary")
@roles_required("authority", "admin")
def operational_summary():
    session = db_session()
    active_events = session.scalar(select(func.count(FireEvent.id)).where(FireEvent.ended_at.is_(None))) or 0
    total_observations = session.scalar(select(func.count(SatelliteFireObservation.id))) or 0
    return jsonify({
        "status": "operational",
        "active_events_count": active_events,
        "total_observations_count": total_observations,
        "mode": "professional_monitoring",
    })


@bp.get("/iot/nodes")
@roles_required("authority", "admin")
def authority_iot_nodes():
    """Authority read-only operational station monitoring endpoint."""
    session = db_session()
    from polaris_x.db.models import SensorNode
    nodes = session.execute(
        select(SensorNode)
        .where(SensorNode.active.is_(True))
        .order_by(SensorNode.name)
    ).scalars().all()

    results = []
    for n in nodes:
        loc_coords = None
        if n.location and n.location.point is not None:
            pt = to_shape(n.location.point)
            loc_coords = {"longitude": pt.x, "latitude": pt.y}

        results.append({
            "id": str(n.id),
            "node_identifier": n.node_identifier,
            "name": n.name,
            "status": n.status,
            "dev_eui": n.dev_eui,
            "battery_voltage": float(n.battery_voltage) if n.battery_voltage is not None else None,
            "last_seen_at": n.last_seen_at.isoformat() if n.last_seen_at else None,
            "location": {
                "id": str(n.location.id),
                "name": n.location.name,
                "coordinates": loc_coords,
            } if n.location else None,
        })

    return jsonify(nodes=results, count=len(results))
