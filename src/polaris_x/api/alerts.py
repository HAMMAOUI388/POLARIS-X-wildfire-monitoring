"""Authenticated operational-alert and relevant-event API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from geoalchemy2.shape import to_shape
from sqlalchemy import and_, exists, func, or_, select

from polaris_x.api.authz import current_user, location_for_user
from polaris_x.api.errors import error_response
from polaris_x.db.models import Alert, AlertEvidence, AlertRecipient, FireEvent, LocationAccess, MonitoringLocation
from polaris_x.extensions import db_session
from polaris_x.intelligence.detection import find_new_observations_for_location


bp = Blueprint("alerts", __name__, url_prefix="/api/v1/alerts")


def _is_admin(user) -> bool:
    return any(role.name == "admin" for role in user.roles)


def _visible_alert_query(user, alert_id: UUID | None = None):
    """Recipient ownership plus current location authorization; no client user IDs."""
    grant = exists(select(LocationAccess.location_id).where(LocationAccess.location_id == Alert.location_id, LocationAccess.user_id == user.id))
    allowed_location = or_(Alert.location_id.is_(None), MonitoringLocation.owner_id == user.id, grant)
    query = select(Alert, AlertRecipient).join(AlertRecipient, AlertRecipient.alert_id == Alert.id).outerjoin(MonitoringLocation, MonitoringLocation.id == Alert.location_id).where(AlertRecipient.user_id == user.id)
    if not _is_admin(user):
        query = query.where(allowed_location)
    if alert_id is not None:
        query = query.where(Alert.id == alert_id)
    return query


def _evidence(session, alert_id: UUID) -> list[dict]:
    records = session.execute(select(AlertEvidence).where(AlertEvidence.alert_id == alert_id)).scalars().all()
    return [{"type": record.evidence_type, "id": str(record.evidence_id), "details": record.details} for record in records]


def _serialize_alert(session, alert: Alert, recipient: AlertRecipient) -> dict:
    return {
        "id": str(alert.id), "location_id": str(alert.location_id) if alert.location_id else None,
        "event_id": str(alert.event_id) if alert.event_id else None,
        "alert_type": alert.alert_type, "classification": "informational" if alert.severity.value == "low" else alert.severity.value,
        "severity": alert.severity.value, "status": recipient.status,
        "read_at": recipient.read_at.isoformat() if recipient.read_at else None,
        "title": alert.title, "message": alert.message,
        "created_at": alert.created_at.isoformat(), "expires_at": alert.expires_at.isoformat() if alert.expires_at else None,
        "match": {"subscription_id": str(recipient.subscription_id) if recipient.subscription_id else None, "observation_id": str(recipient.observation_id) if recipient.observation_id else None, "event_id": str(recipient.event_id) if recipient.event_id else None, "distance_m": str(recipient.distance_m) if recipient.distance_m is not None else None, "policy": recipient.matching_policy},
        "evidence": _evidence(session, alert.id),
    }


def _pagination():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        return None, error_response("invalid_parameter", "page and per_page must be integers.", 400)
    if not 1 <= page <= 1_000_000 or not 1 <= per_page <= 100:
        return None, error_response("invalid_parameter", "page must be >= 1 and per_page must be between 1 and 100.", 400)
    return (page, per_page), None


@bp.get("")
@jwt_required()
def list_alerts():
    user, session = current_user(), db_session()
    pagination, response = _pagination()
    if response:
        return response
    page, per_page = pagination
    unread = request.args.get("unread_only", "false").lower()
    if unread not in {"true", "false"}:
        return error_response("invalid_parameter", "unread_only must be true or false.", 400)
    location_id = request.args.get("location_id")
    try:
        location_uuid = UUID(location_id) if location_id else None
    except ValueError:
        return error_response("invalid_parameter", "location_id must be a UUID.", 400)
    query = _visible_alert_query(user)
    if location_uuid:
        location, denied = location_for_user(location_uuid)
        if denied:
            return denied
        query = query.where(Alert.location_id == location.id)
    if unread == "true":
        query = query.where(AlertRecipient.status == "unread")
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(query.order_by(Alert.created_at.desc(), Alert.id).offset((page - 1) * per_page).limit(per_page)).all()
    return jsonify(alerts=[_serialize_alert(session, alert, recipient) for alert, recipient in rows], total=total, page=page, per_page=per_page)


@bp.get("/<uuid:alert_id>")
@jwt_required()
def get_alert(alert_id: UUID):
    user, session = current_user(), db_session()
    row = session.execute(_visible_alert_query(user, alert_id)).one_or_none()
    if row is None:
        return error_response("not_found", "Alert not found.", 404)
    return jsonify(alert=_serialize_alert(session, *row))


@bp.post("/<uuid:alert_id>/read")
@jwt_required()
def mark_alert_as_read(alert_id: UUID):
    user, session = current_user(), db_session()
    row = session.execute(_visible_alert_query(user, alert_id)).one_or_none()
    if row is None:
        return error_response("not_found", "Alert not found.", 404)
    alert, recipient = row
    if recipient.status != "read":
        recipient.status, recipient.read_at = "read", datetime.now(timezone.utc)
        session.commit()
    return jsonify(alert=_serialize_alert(session, alert, recipient))


@bp.get("/locations/<uuid:location_id>/summary")
@jwt_required()
def get_location_summary(location_id: UUID):
    user, session = current_user(), db_session()
    location, denied = location_for_user(location_id)
    if denied:
        return denied
    base = _visible_alert_query(user).where(Alert.location_id == location.id)
    total_alerts = session.scalar(select(func.count()).select_from(base.subquery()))
    unread_alerts = session.scalar(select(func.count()).select_from(base.where(AlertRecipient.status == "unread").subquery()))
    recent = find_new_observations_for_location(session, location.id, since=datetime.now(timezone.utc) - timedelta(days=7), user_id=user.id)
    return jsonify(location_id=str(location.id), total_alerts=total_alerts, unread_alerts=unread_alerts, recent_observations_count=len(recent), associated_events_count=len({event_id for _, _, event_id in recent if event_id is not None}), note="Satellite thermal anomalies are observations, not confirmed wildfires.")


@bp.get("/events/<uuid:event_id>")
@jwt_required()
def get_relevant_event(event_id: UUID):
    user, session = current_user(), db_session()
    row = session.execute(_visible_alert_query(user).where(or_(Alert.event_id == event_id, AlertRecipient.event_id == event_id))).first()
    if row is None:
        return error_response("not_found", "Event not found.", 404)
    event = session.get(FireEvent, event_id)
    if event is None:
        return error_response("not_found", "Event not found.", 404)
    point = to_shape(event.centroid)
    return jsonify(event={"id": str(event.id), "status": event.status, "started_at": event.started_at.isoformat(), "ended_at": event.ended_at.isoformat() if event.ended_at else None, "centroid": {"longitude": point.x, "latitude": point.y}, "classification": "observed satellite-associated event; not a confirmed wildfire"})
