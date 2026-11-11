"""Closed chatbot tool registry. Arguments never contain an authority identity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from geoalchemy2.shape import to_shape
from sqlalchemy import exists, or_, select

from polaris_x.db.models import Alert, AlertRecipient, FireEvent, LocationAccess, MonitoringLocation, WeatherForecast, WeatherObservation
from polaris_x.intelligence.detection import find_new_observations_for_location
from polaris_x.intelligence.alerts import weather_context_for_location


class ToolValidationError(ValueError):
    pass


def _location(session, user, location_id: str):
    try: identifier = UUID(location_id)
    except (ValueError, TypeError) as exc: raise ToolValidationError("location_id must be a UUID") from exc
    item = session.get(MonitoringLocation, identifier)
    if item is None or (item.owner_id != user.id and session.scalar(select(LocationAccess.location_id).where(LocationAccess.location_id == identifier, LocationAccess.user_id == user.id)) is None):
        raise ToolValidationError("location not found")
    return item


def _alert(session, user, alert_id: str):
    try: identifier = UUID(alert_id)
    except (ValueError, TypeError) as exc: raise ToolValidationError("alert_id must be a UUID") from exc
    row = session.execute(select(Alert, AlertRecipient).join(AlertRecipient).where(Alert.id == identifier, AlertRecipient.user_id == user.id)).one_or_none()
    if row is None: raise ToolValidationError("alert not found")
    return row


def list_monitoring_locations(session, user, _args):
    grants = select(LocationAccess.location_id).where(LocationAccess.user_id == user.id)
    locations = session.execute(select(MonitoringLocation).where(or_(MonitoringLocation.owner_id == user.id, MonitoringLocation.id.in_(grants))).order_by(MonitoringLocation.name)).scalars().all()
    return [{"id": str(item.id), "name": item.name, "type": item.location_type.value} for item in locations]


def list_recent_alerts(session, user, args):
    limit = args.get("limit", 10)
    if not isinstance(limit, int) or not 1 <= limit <= 50: raise ToolValidationError("limit must be an integer between 1 and 50")
    rows = session.execute(select(Alert, AlertRecipient).join(AlertRecipient).where(AlertRecipient.user_id == user.id).order_by(Alert.created_at.desc()).limit(limit)).all()
    return [{"id": str(alert.id), "title": alert.title, "status": recipient.status, "created_at": alert.created_at.isoformat(), "classification": "satellite thermal anomaly; not confirmed wildfire"} for alert, recipient in rows]


def get_alert_details(session, user, args):
    alert, recipient = _alert(session, user, args.get("alert_id"))
    return {"id": str(alert.id), "title": alert.title, "message": alert.message, "status": recipient.status, "location_id": str(alert.location_id) if alert.location_id else None, "event_id": str(alert.event_id) if alert.event_id else None}


def get_detection_summary(session, user, args):
    location = _location(session, user, args.get("location_id"))
    findings = find_new_observations_for_location(session, location.id, datetime.now(timezone.utc) - timedelta(days=7), user.id)
    return {"location_id": str(location.id), "recent_anomaly_count": len(findings), "associated_event_count": len({event for _, _, event in findings if event}), "note": "Satellite thermal anomalies are not confirmed wildfires."}


def get_event_information(session, user, args):
    try: event_id = UUID(args.get("event_id"))
    except (ValueError, TypeError) as exc: raise ToolValidationError("event_id must be a UUID") from exc
    authorized = session.scalar(select(AlertRecipient.alert_id).where(AlertRecipient.user_id == user.id, AlertRecipient.event_id == event_id))
    event = session.get(FireEvent, event_id)
    if not authorized or event is None: raise ToolValidationError("event not found")
    point = to_shape(event.centroid)
    return {"id": str(event.id), "status": event.status, "started_at": event.started_at.isoformat(), "centroid": {"longitude": point.x, "latitude": point.y}, "note": "Observed satellite-associated event; not a confirmed wildfire."}


def get_weather_context(session, user, args):
    location = _location(session, user, args.get("location_id"))
    context = weather_context_for_location(session, location.id, datetime.now(timezone.utc))
    if context is None: return {"location_id": str(location.id), "available": False, "message": "No weather context is available."}
    return {"location_id": str(location.id), "available": True, "classification": context.category, "source": context.source_name, "valid_at": context.valid_at.isoformat(), "variables": context.variables}


def explain_platform_capabilities(_session, _user, _args):
    return {"capabilities": "Authorized monitoring locations, satellite thermal anomalies, alerts, event associations, and available weather context.", "limitations": "Thermal anomalies are not confirmed wildfires. Forecasts, historical reanalysis, and station observations are distinct. No validated fire occurrence or spread prediction is available."}


TOOLS = {"list_monitoring_locations": list_monitoring_locations, "list_recent_alerts": list_recent_alerts, "get_alert_details": get_alert_details, "get_detection_summary": get_detection_summary, "get_event_information": get_event_information, "get_weather_context": get_weather_context, "explain_platform_capabilities": explain_platform_capabilities}

TOOL_SCHEMAS = [{"type": "function", "function": {"name": name, "description": "Restricted POLARIS X authorized data tool", "parameters": {"type": "object", "properties": {"location_id": {"type": "string"}, "alert_id": {"type": "string"}, "event_id": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False}}} for name in TOOLS]

def execute_tool(session, user, name: str, args: dict):
    if name not in TOOLS: raise ToolValidationError("tool is not available")
    if not isinstance(args, dict): raise ToolValidationError("tool arguments must be an object")
    allowed = {"location_id", "alert_id", "event_id", "limit"}
    if set(args) - allowed or any(key in args for key in {"user_id", "owner_id", "role"}): raise ToolValidationError("unsupported tool arguments")
    return TOOLS[name](session, user, args)
