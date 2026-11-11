"""Detection matching service — identifies satellite observations relevant to monitored locations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from geoalchemy2.functions import ST_Distance
from geoalchemy2.functions import ST_DWithin
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from polaris_x.db.models import FireEvent, LocationAccess, MonitoringLocation, MonitoringSubscription, SatelliteFireObservation


@dataclass(frozen=True)
class DetectionMatch:
    """A satellite observation matched to a user's monitoring subscription."""
    observation_id: UUID
    subscription_id: UUID
    user_id: UUID
    location_id: UUID
    distance_m: Decimal
    observed_at: datetime
    event_id: UUID | None
    observation: SatelliteFireObservation
    location: MonitoringLocation
    matching_policy: dict


def find_matches_for_observation(
    session: Session,
    observation_id: UUID,
    event_id: UUID | None = None,
) -> list[DetectionMatch]:
    """
    Find all monitoring subscriptions matched by a specific satellite observation.

    Returns matches where:
    - The observation falls within the subscription's monitoring radius
    - The subscription is enabled
    - The user has permission to view the location (owner or explicit grant)

    Args:
        session: Database session
        observation_id: UUID of the satellite observation
        event_id: Optional UUID of the associated fire event

    Returns:
        List of DetectionMatch objects
    """
    observation = session.get(SatelliteFireObservation, observation_id)
    if observation is None:
        return []

    # A subscription is usable only by the location owner or someone who has
    # explicitly been granted access.  The EXISTS form avoids duplicate rows
    # while retaining PostGIS filtering in the database.
    access_granted = exists(
        select(LocationAccess.location_id).where(
            LocationAccess.location_id == MonitoringLocation.id,
            LocationAccess.user_id == MonitoringSubscription.user_id,
        )
    )

    # ST_DWithin performs the radius predicate in PostGIS; ST_Distance is
    # selected only for matches so the exact distance can be preserved.
    query = (
        select(
            MonitoringSubscription,
            MonitoringLocation,
            ST_Distance(
                observation.point,
                MonitoringLocation.point
            ).label("distance_m")
        )
        .join(MonitoringLocation, MonitoringLocation.id == MonitoringSubscription.location_id)
        .where(
            and_(
                MonitoringSubscription.enabled == True,  # noqa: E712
                MonitoringSubscription.location_id.isnot(None),
                ST_DWithin(
                    observation.point,
                    MonitoringLocation.point,
                    MonitoringSubscription.radius_m,
                ),
                or_(MonitoringLocation.owner_id == MonitoringSubscription.user_id, access_granted),
            )
        )
    )

    results = session.execute(query).all()

    matches = []
    for subscription, location, distance_m in results:
        matches.append(
            DetectionMatch(
                observation_id=observation.id,
                subscription_id=subscription.id,
                user_id=subscription.user_id,
                location_id=location.id,
                distance_m=Decimal(str(distance_m)),
                observed_at=observation.observed_at,
                event_id=event_id,
                observation=observation,
                location=location,
                matching_policy={
                    "version": "phase8-subscription-radius-v1",
                    "spatial_predicate": "ST_DWithin",
                    "radius_m": str(subscription.radius_m),
                    "authorization": "owner_or_explicit_location_access",
                },
            )
        )

    return matches


def find_new_observations_for_location(
    session: Session,
    location_id: UUID,
    since: datetime | None = None,
    user_id: UUID | None = None,
) -> list[tuple[SatelliteFireObservation, Decimal, UUID | None]]:
    """
    Find satellite observations near a monitoring location.

    Args:
        session: Database session
        location_id: UUID of the monitoring location
        since: Optional datetime to filter observations after this time

    Returns:
        List of (observation, distance_m, event_id) tuples
    """
    from polaris_x.geospatial import observations_near_location
    from polaris_x.db.models import FireEventObservation

    location = session.get(MonitoringLocation, location_id)
    if location is None:
        return []

    # A summary must use the requesting user's own configured radius rather
    # than reveal detections that happen to match another subscriber.
    conditions = [
        MonitoringSubscription.location_id == location_id,
        MonitoringSubscription.enabled == True,  # noqa: E712
    ]
    if user_id is not None:
        conditions.append(MonitoringSubscription.user_id == user_id)
    subscriptions = session.execute(select(MonitoringSubscription).where(and_(*conditions))).scalars().all()

    if not subscriptions:
        return []

    max_radius = max(sub.radius_m for sub in subscriptions)

    # Get observations within max radius
    results = observations_near_location(
        session,
        location,
        max_radius,
        start=since,
    )

    # Look up associated events
    output = []
    for obs, distance in results:
        event_assoc = session.execute(
            select(FireEventObservation)
            .where(FireEventObservation.observation_id == obs.id)
        ).scalar_one_or_none()

        event_id = event_assoc.fire_event_id if event_assoc else None
        output.append((obs, distance, event_id))

    return output
