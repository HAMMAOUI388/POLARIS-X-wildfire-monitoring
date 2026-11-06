from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text

from polaris_x.db.models import DataSource, FireEvent, FireEventObservation, HikingRoute, MonitoringLocation, SatelliteFireObservation, User
from polaris_x.db.session import make_session_factory
from polaris_x.geospatial import SpatialPolicy, associate_observation, observations_near_location


def test_policy_is_configurable_and_stable():
    policy = SpatialPolicy(Decimal("2500"), timedelta(hours=3), "test-policy")
    assert policy.snapshot() == {"radius_m": "2500", "temporal_window_seconds": 10800, "version": "test-policy"}


def test_postgis_association_is_idempotent_and_does_not_chain():
    import os
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    factory = make_session_factory(url)
    source_name = f"Phase 4 test source {uuid4().hex}"
    now = datetime(2100, 1, 1, tzinfo=timezone.utc)
    try:
        with factory.begin() as session:
            source = DataSource(name=source_name, source_type="satellite", provider="test", metadata_json={})
            session.add(source); session.flush()
            points = [(-6.8, 33.9), (-6.801, 33.9), (-6.802, 33.9), (-7.05, 33.9)]
            observations = []
            for i, (lon, lat) in enumerate(points):
                item = SatelliteFireObservation(source_id=source.id, external_id=f"p4-{uuid4().hex}-{i}", product="viirs", observed_at=now + timedelta(minutes=i), point=WKTElement(f"POINT({lon} {lat})", srid=4326), confidence_original="n", raw_payload={"synthetic": True})
                session.add(item); observations.append(item)
            session.flush()
            event_a, created_a = associate_observation(session, observations[0].id, SpatialPolicy(Decimal("200"), timedelta(hours=1)))
            event_b, created_b = associate_observation(session, observations[1].id, SpatialPolicy(Decimal("200"), timedelta(hours=1)))
            event_c, created_c = associate_observation(session, observations[2].id, SpatialPolicy(Decimal("200"), timedelta(hours=1)))
            event_d, created_d = associate_observation(session, observations[3].id, SpatialPolicy(Decimal("200"), timedelta(hours=1)))
            assert created_a is True
            assert event_a.id == event_b.id == event_c.id
            assert created_d is True and event_d.id != event_a.id
            repeat, created_repeat = associate_observation(session, observations[1].id)
            assert repeat.id == event_a.id and created_repeat is False
            assert session.scalar(select(FireEventObservation).where(FireEventObservation.observation_id == observations[1].id))
            assert session.scalar(select(FireEvent).where(FireEvent.id == event_a.id)).started_at == now
    finally:
        with factory.begin() as session:
            source = session.scalar(select(DataSource).where(DataSource.name == source_name))
            if source:
                session.execute(text("DELETE FROM fire_event_observations WHERE observation_id IN (SELECT id FROM satellite_fire_observations WHERE source_id = :source)"), {"source": str(source.id)})
                session.execute(text("DELETE FROM fire_events WHERE id NOT IN (SELECT fire_event_id FROM fire_event_observations)"))
                session.execute(text("DELETE FROM satellite_fire_observations WHERE source_id = :source"), {"source": str(source.id)})
                session.execute(text("DELETE FROM data_sources WHERE id = :source"), {"source": str(source.id)})
        factory.kw["bind"].dispose()
