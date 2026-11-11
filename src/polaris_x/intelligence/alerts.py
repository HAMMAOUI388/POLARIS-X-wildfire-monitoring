"""Operational alerts with explicit uncertainty and traceable source evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from polaris_x.db.models import Alert, AlertEvidence, AlertRecipient, DataSource, FireEventObservation, MonitoringSubscription, Severity, WeatherForecast, WeatherObservation
from polaris_x.intelligence.detection import DetectionMatch, find_matches_for_observation


AlertType = Literal["satellite_thermal_anomaly", "event_update", "weather_context"]


@dataclass(frozen=True)
class WeatherContext:
    record_id: UUID
    category: str
    variables: dict
    valid_at: datetime
    source_name: str
    provider: str
    evidence_type: str


@dataclass(frozen=True)
class AlertContext:
    match: DetectionMatch
    weather: WeatherContext | None = None


def weather_context_for_location(session: Session, location_id: UUID, at: datetime) -> WeatherContext | None:
    """Return factual weather context without presenting reanalysis as live weather."""
    forecast = session.execute(select(WeatherForecast, DataSource).join(DataSource, DataSource.id == WeatherForecast.source_id).where(WeatherForecast.location_id == location_id, WeatherForecast.valid_from <= at, WeatherForecast.valid_to >= at).order_by(WeatherForecast.valid_from.desc()).limit(1)).one_or_none()
    if forecast:
        row, source = forecast
        return WeatherContext(row.id, "operational_forecast", row.variables, row.valid_from, source.name, source.provider, "weather_forecast")
    observation = session.execute(select(WeatherObservation, DataSource).join(DataSource, DataSource.id == WeatherObservation.source_id).where(WeatherObservation.location_id == location_id, WeatherObservation.observed_at <= at).order_by(WeatherObservation.observed_at.desc()).limit(1)).one_or_none()
    if not observation:
        return None
    row, source = observation
    source_type = source.source_type.lower()
    category = "historical_reanalysis" if source_type == "reanalysis" else "direct_weather_station_observation" if source_type in {"station", "weather_station"} else "weather_observation"
    return WeatherContext(row.id, category, row.variables, row.observed_at, source.name, source.provider, "weather_observation")


def _informational_severity() -> Severity:
    # No validated danger score or fire-occurrence probability exists here.
    return Severity.low


def _subscription_wants_alert(session: Session, match: DetectionMatch) -> bool:
    subscription = session.get(MonitoringSubscription, match.subscription_id)
    if subscription is None or not subscription.enabled:
        return False
    order = {Severity.low: 1, Severity.moderate: 2, Severity.high: 3, Severity.critical: 4}
    return order[_informational_severity()] >= order[subscription.minimum_severity]


def _deduplication_key(match: DetectionMatch, alert_type: AlertType, weather: WeatherContext | None) -> str:
    subject = match.observation_id
    if alert_type == "event_update":
        subject = match.event_id or match.observation_id
    elif alert_type == "weather_context":
        subject = weather.record_id if weather else match.observation_id
    return f"{alert_type}:{match.subscription_id}:{subject}"


def _format_weather(weather: WeatherContext) -> list[str]:
    lines = ["", f"Weather context ({weather.category.replace('_', ' ')}):", f"- Source: {weather.source_name} ({weather.provider})", f"- Valid/observed time: {weather.valid_at.strftime('%Y-%m-%d %H:%M UTC')}"]
    labels = {"temperature_2m": "Temperature", "wind_speed_10m": "Wind speed", "wind_direction_10m": "Wind direction", "relative_humidity_2m": "Relative humidity"}
    for key, label in labels.items():
        if key in weather.variables:
            lines.append(f"- {label}: {weather.variables[key]}")
    if weather.category == "historical_reanalysis":
        lines.append("- This is historical gridded reanalysis, not live weather or a station observation.")
    return lines


def _format_alert(context: AlertContext, alert_type: AlertType, source: DataSource | None) -> tuple[str, str]:
    match, observation, location = context.match, context.match.observation, context.match.location
    distance_km = float(match.distance_m) / 1000
    source_label = source.name if source else "NASA FIRMS satellite data"
    base = [f"Source: {source_label}", f"Observation identifier: {observation.external_id}", f"Observation time: {observation.observed_at.strftime('%Y-%m-%d %H:%M UTC')}", f"Detection ingested: {observation.ingested_at.strftime('%Y-%m-%d %H:%M UTC')}", f"Monitored location: {location.name}", f"Distance: {distance_km:.2f} km", "Classification: informational satellite thermal anomaly; not a confirmed wildfire.", "Provenance: NASA FIRMS thermal observation, matched with the stored subscription-radius policy."]
    if alert_type == "satellite_thermal_anomaly":
        title = f"Satellite thermal anomaly near {location.name}"
        intro = f"A satellite thermal anomaly was observed {distance_km:.1f} km from your monitored location. It is not a confirmed wildfire."
    elif alert_type == "event_update":
        title = f"Observed-event update near {location.name}"
        intro = "A new satellite thermal anomaly was associated with an existing observed event near your monitored location. This association does not confirm a wildfire."
    else:
        title = f"Weather context for {location.name}"
        intro = "Available weather context is attached to a monitored satellite observation; it is factual context, not a fire prediction."
    if context.weather:
        base.extend(_format_weather(context.weather))
    return title, "\n".join([intro, "", *base])


def generate_alert_for_match(session: Session, context: AlertContext, alert_type: AlertType = "satellite_thermal_anomaly") -> Alert | None:
    """Create one user-owned, idempotent informational alert for a match."""
    match = context.match
    if not _subscription_wants_alert(session, match):
        return None
    key = _deduplication_key(match, alert_type, context.weather)
    if session.scalar(select(AlertRecipient.alert_id).where(AlertRecipient.deduplication_key == key)):
        return None
    source = session.get(DataSource, match.observation.source_id)
    title, message = _format_alert(context, alert_type, source)
    alert = Alert(location_id=match.location_id, event_id=match.event_id, alert_type=alert_type, severity=_informational_severity(), title=title, message=message, created_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    try:
        with session.begin_nested():
            session.add(alert)
            session.flush()
            session.add(AlertRecipient(alert_id=alert.id, user_id=match.user_id, subscription_id=match.subscription_id, observation_id=match.observation_id, event_id=match.event_id, distance_m=match.distance_m, matching_policy=match.matching_policy, status="unread", deduplication_key=key))
            session.flush()
    except IntegrityError:
        return None
    details = {"external_id": match.observation.external_id, "source_id": str(match.observation.source_id), "source_name": source.name if source else None, "observed_at": match.observed_at.isoformat(), "ingested_at": match.observation.ingested_at.isoformat(), "distance_m": str(match.distance_m), "matching_policy": match.matching_policy}
    session.add(AlertEvidence(alert_id=alert.id, evidence_type="observation", evidence_id=match.observation_id, details=details))
    if match.event_id:
        session.add(AlertEvidence(alert_id=alert.id, evidence_type="event", evidence_id=match.event_id, details={"association": "phase4_geospatial_event_association"}))
    if context.weather:
        session.add(AlertEvidence(alert_id=alert.id, evidence_type=context.weather.evidence_type, evidence_id=context.weather.record_id, details={"classification": context.weather.category, "source": context.weather.source_name, "valid_at": context.weather.valid_at.isoformat()}))
    return alert


def process_new_observation(session: Session, observation_id: UUID, event_id: UUID | None = None) -> list[Alert]:
    """Generate anomaly alerts and justified event updates for one observation."""
    matches = find_matches_for_observation(session, observation_id, event_id)
    is_existing_event_update = bool(event_id and session.scalar(select(func.count()).select_from(FireEventObservation).where(FireEventObservation.fire_event_id == event_id)) > 1)
    alerts: list[Alert] = []
    for match in matches:
        context = AlertContext(match=match, weather=weather_context_for_location(session, match.location_id, match.observed_at))
        anomaly = generate_alert_for_match(session, context)
        if anomaly:
            alerts.append(anomaly)
        if is_existing_event_update:
            update = generate_alert_for_match(session, context, "event_update")
            if update:
                alerts.append(update)
    return alerts
