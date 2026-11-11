from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from geoalchemy2 import Geography
from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_Intersects
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape

from polaris_x.db.models import FireEvent, FireEventObservation, HikingRoute, MonitoringLocation, SatelliteFireObservation

@dataclass(frozen=True)
class SpatialPolicy:
    radius_m: Decimal = Decimal("5000")
    temporal_window: timedelta = timedelta(hours=6)
    version: str = "phase4-prototype-1"

    def snapshot(self) -> dict:
        return {"radius_m": str(self.radius_m), "temporal_window_seconds": int(self.temporal_window.total_seconds()), "version": self.version}

def observations_near_location(session: Session, location: MonitoringLocation, radius_m: Decimal, start: datetime | None = None, end: datetime | None = None):
    # ``location.point`` is a loaded WKB value, not a SQL column expression;
    # both model fields are already Geography(4326), so PostGIS needs no cast.
    query = select(SatelliteFireObservation, ST_Distance(SatelliteFireObservation.point, location.point).label("distance_m")).where(ST_DWithin(SatelliteFireObservation.point, location.point, radius_m)).order_by(SatelliteFireObservation.observed_at.desc(), SatelliteFireObservation.id).limit(1000)
    if start is not None: query = query.where(SatelliteFireObservation.observed_at >= start)
    if end is not None: query = query.where(SatelliteFireObservation.observed_at <= end)
    return session.execute(query).all()

def observations_near_route(session: Session, route: HikingRoute, radius_m: Decimal, start: datetime | None = None, end: datetime | None = None):
    corridor = func.ST_Buffer(route.path.cast(Geography), radius_m)
    query = select(SatelliteFireObservation, ST_Distance(SatelliteFireObservation.point.cast(Geography), route.path.cast(Geography)).label("distance_m")).where(ST_Intersects(SatelliteFireObservation.point, corridor)).order_by(SatelliteFireObservation.observed_at.desc(), SatelliteFireObservation.id).limit(1000)
    if start is not None: query = query.where(SatelliteFireObservation.observed_at >= start)
    if end is not None: query = query.where(SatelliteFireObservation.observed_at <= end)
    return session.execute(query).all()

def _candidate_events(session: Session, observation: SatelliteFireObservation, policy: SpatialPolicy):
    lower = observation.observed_at - policy.temporal_window
    upper = observation.observed_at + policy.temporal_window
    return session.execute(select(FireEvent).join(FireEventObservation, FireEventObservation.fire_event_id == FireEvent.id).join(SatelliteFireObservation, SatelliteFireObservation.id == FireEventObservation.observation_id).where(SatelliteFireObservation.observed_at.between(lower, upper)).with_for_update()).scalars().unique().all()

def _event_observations(session: Session, event_id: UUID):
    return session.execute(select(SatelliteFireObservation).join(FireEventObservation, FireEventObservation.observation_id == SatelliteFireObservation.id).where(FireEventObservation.fire_event_id == event_id).order_by(SatelliteFireObservation.observed_at, SatelliteFireObservation.id)).scalars().all()

def _distance(session: Session, first, second):
    first_wkt = f"SRID=4326;POINT({to_shape(first.point).x} {to_shape(first.point).y})"
    second_wkt = f"SRID=4326;POINT({to_shape(second.point).x} {to_shape(second.point).y})"
    return session.scalar(select(ST_Distance(func.ST_GeogFromText(first_wkt), func.ST_GeogFromText(second_wkt))))

def associate_observation(session: Session, observation_id: UUID, policy: SpatialPolicy = SpatialPolicy()) -> tuple[FireEvent, bool]:
    observation = session.get(SatelliteFireObservation, observation_id, with_for_update=True)
    if observation is None: raise ValueError("observation not found")
    existing = session.scalar(select(FireEvent).join(FireEventObservation, FireEventObservation.fire_event_id == FireEvent.id).where(FireEventObservation.observation_id == observation.id).with_for_update())
    if existing is not None: return existing, False
    candidates = []
    for event in _candidate_events(session, observation, policy):
        members = _event_observations(session, event.id)
        distances = [Decimal(str(_distance(session, observation, member))) for member in members]
        if distances and max(distances) <= policy.radius_m:
            candidates.append((max(distances), event.id, event, members))
    if candidates:
        _, _, event, members = sorted(candidates, key=lambda item: (item[0], item[1]))[0]
        created = False
    else:
        event = FireEvent(status="observed", started_at=observation.observed_at, ended_at=observation.observed_at, centroid=observation.point)
        session.add(event); session.flush(); members = []; created = True
    distance = Decimal(str(_distance(session, observation, members[0]))) if members else Decimal("0")
    session.add(FireEventObservation(fire_event_id=event.id, observation_id=observation.id, distance_m=distance, temporal_delta_seconds=Decimal("0"), policy_snapshot=policy.snapshot()))
    all_members = members + [observation]
    event.started_at = min(item.observed_at for item in all_members)
    event.ended_at = max(item.observed_at for item in all_members)
    coordinates = [session.execute(select(func.ST_X(item.point), func.ST_Y(item.point))).one() for item in all_members]
    centroid_wkt = f"POINT({sum(float(x) for x, _ in coordinates) / len(coordinates)} {sum(float(y) for _, y in coordinates) / len(coordinates)})"
    event.centroid = WKTElement(centroid_wkt, srid=4326)
    return event, created
