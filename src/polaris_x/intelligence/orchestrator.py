"""Alert orchestrator — coordinates detection, alert generation, and notification delivery."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from polaris_x.db.models import FireEventObservation, SatelliteFireObservation
from polaris_x.geospatial import associate_observation
from polaris_x.intelligence.alerts import process_new_observation
from polaris_x.intelligence.notifications import deliver_alert_to_all_recipients


def process_recent_observations(
    session: Session,
    since: datetime | None = None,
    limit: int = 1000,
) -> tuple[int, int, int]:
    """
    Process recent satellite observations to generate alerts.

    Args:
        session: Database session
        since: Only process observations after this time (default: last 24 hours)
        limit: Maximum observations to process

    Returns:
        (observations_processed, alerts_generated, notifications_sent)
    """
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Get recent observations
    query = (
        select(SatelliteFireObservation)
        .where(
            SatelliteFireObservation.ingested_at >= since,
            SatelliteFireObservation.processed_at.is_(None),
        )
        .order_by(SatelliteFireObservation.ingested_at.desc())
        .limit(limit)
    )

    observations = session.execute(query).scalars().all()

    observations_processed = 0
    alerts_generated = 0
    notifications_sent = 0

    for observation in observations:
        event_id = _event_id_for_observation(session, observation.id)

        # Generate alerts
        alerts = process_new_observation(session, observation.id, event_id)

        # Deliver notifications
        for alert in alerts:
            attempts = deliver_alert_to_all_recipients(session, alert)
            notifications_sent += len(attempts)

        alerts_generated += len(alerts)
        observations_processed += 1
        observation.processed_at = datetime.now(timezone.utc)

        # Commit after each observation to avoid large transactions
        session.commit()

    return observations_processed, alerts_generated, notifications_sent


def process_single_observation(
    session: Session,
    observation_id: UUID,
) -> tuple[int, int]:
    """
    Process a single observation immediately after ingestion.

    Args:
        session: Database session
        observation_id: UUID of observation to process

    Returns:
        (alerts_generated, notifications_sent)
    """
    observation = session.get(SatelliteFireObservation, observation_id)
    if observation is None:
        raise ValueError("observation not found")
    event_id = _event_id_for_observation(session, observation_id)

    # Generate alerts
    alerts = process_new_observation(session, observation_id, event_id)

    # Deliver notifications
    notifications_sent = 0
    for alert in alerts:
        attempts = deliver_alert_to_all_recipients(session, alert)
        notifications_sent += len(attempts)

    observation.processed_at = datetime.now(timezone.utc)
    session.commit()

    return len(alerts), notifications_sent


def _event_id_for_observation(session: Session, observation_id: UUID) -> UUID:
    """Reuse Phase 4 association before generating any operational alert."""
    event_assoc = session.execute(select(FireEventObservation).where(FireEventObservation.observation_id == observation_id)).scalar_one_or_none()
    if event_assoc is not None:
        return event_assoc.fire_event_id
    event, _created = associate_observation(session, observation_id)
    session.flush()
    return event.id
