from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from pydantic import ValidationError
from sqlalchemy import select
from geoalchemy2.shape import to_shape

from polaris_x.api.authz import location_for_user, current_user
from polaris_x.api.errors import error_response
from polaris_x.api.schemas import SpatialQueryRequest
from polaris_x.db.models import FireEvent, FireEventObservation, SatelliteFireObservation
from polaris_x.extensions import db_session
from polaris_x.geospatial import observations_near_location

bp = Blueprint("geospatial", __name__)

def _query():
    try:
        return SpatialQueryRequest.model_validate(request.args.to_dict())
    except ValidationError as exc:
        return None, error_response("validation_error", "Invalid spatial query.", 422, details=exc.errors())

def _time(value):
    if value is None: return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timestamps must be ISO-8601")
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

def _observation(item, distance):
    point = to_shape(item.point)
    return {"id": str(item.id), "external_id": item.external_id, "product": item.product, "observed_at": item.observed_at.isoformat(), "confidence": item.confidence_original, "frp": str(item.frp) if item.frp is not None else None, "brightness_temperature": str(item.brightness_temperature) if item.brightness_temperature is not None else None, "point": {"longitude": point.x, "latitude": point.y}, "distance_m": float(distance)}

@bp.get("/locations/<uuid:location_id>/observations")
@jwt_required()
def observations_for_location(location_id):
    location, response = location_for_user(location_id)
    if response: return response
    query, response = _query()
    if response: return response
    try: start, end = _time(query.start), _time(query.end)
    except ValueError as exc: return error_response("validation_error", str(exc), 422)
    rows = observations_near_location(db_session(), location, query.radius_m, start, end)
    offset = (query.page - 1) * query.limit
    page = rows[offset:offset + query.limit]
    return jsonify(observations=[_observation(item, distance) for item, distance in page], page=query.page, limit=query.limit, returned=len(page), radius_m=query.radius_m)

@bp.get("/locations/<uuid:location_id>/events")
@jwt_required()
def events_for_location(location_id):
    location, response = location_for_user(location_id)
    if response: return response
    query, response = _query()
    if response: return response
    rows = observations_near_location(db_session(), location, query.radius_m, None, None)
    ids = [item.id for item, _ in rows[(query.page - 1) * query.limit:query.page * query.limit]]
    events = db_session().execute(select(FireEvent).join(FireEventObservation).where(FireEventObservation.observation_id.in_(ids)).distinct()).scalars().all() if ids else []
    return jsonify(events=[{"id": str(event.id), "status": event.status, "started_at": event.started_at.isoformat(), "ended_at": event.ended_at.isoformat() if event.ended_at else None, "observation_count": db_session().scalar(select(FireEventObservation.observation_id).where(FireEventObservation.fire_event_id == event.id).count()) if False else None} for event in events], page=query.page, limit=query.limit, radius_m=query.radius_m)
