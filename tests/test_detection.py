"""Tests for detection matching service."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from geoalchemy2.elements import WKTElement

from polaris_x.db.models import (
    DataSource,
    LocationAccess,
    LocationType,
    MonitoringLocation,
    MonitoringSubscription,
    Role,
    SatelliteFireObservation,
    Severity,
    User,
)
from polaris_x.db.session import make_engine
from polaris_x.intelligence.detection import (
    find_matches_for_observation,
    find_new_observations_for_location,
)


@pytest.fixture
def session():
    engine = make_engine("postgresql+psycopg://polaris:polaris_dev@localhost:55432/polaris_x_phase3_test")
    connection = engine.connect()
    transaction = connection.begin()
    from sqlalchemy.orm import sessionmaker
    session = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
    engine.dispose()


def point(base_data, offset: str = "0"):
    return WKTElement(f"POINT({base_data['origin'] + Decimal(offset)} 0)", srid=4326)


@pytest.fixture
def base_data(session):
    """Create base test data: users, roles, data source."""
    # Roles
    user_role = session.query(Role).filter_by(name="user").one_or_none()
    if user_role is None:
        user_role = Role(name="user")
        session.add(user_role)
        session.flush()
    suffix = uuid4().hex

    # Users
    user1 = User(
        email=f"user1-{suffix}@example.com",
        display_name="User One",
        password_hash="hash1",
        roles=[user_role],
    )
    user2 = User(
        email=f"user2-{suffix}@example.com",
        display_name="User Two",
        password_hash="hash2",
        roles=[user_role],
    )
    session.add_all([user1, user2])

    # Data source
    source = DataSource(
        name=f"VIIRS_TEST_{suffix}",
        source_type="satellite",
        provider="NASA FIRMS",
        metadata_json={},
    )
    session.add(source)

    session.commit()

    return {
        "user1": user1,
        "user2": user2,
        "source": source,
        # Keep rows away from the fixed longitudes used by older fixtures and
        # committed integration tests in the shared dedicated test database.
        "origin": Decimal("-150") + Decimal(uuid4().int % 20_000) / Decimal("1000"),
    }


def test_find_matches_within_radius(session, base_data):
    """Test that observations within subscription radius are matched."""
    user = base_data["user1"]
    source = base_data["source"]

    # Create location at (0, 0)
    location = MonitoringLocation(
        owner_id=user.id,
        name="Test Location",
        location_type=LocationType.farm,
        point=point(base_data),
    )
    session.add(location)
    session.commit()

    # Create subscription with 10km radius
    subscription = MonitoringSubscription(
        user_id=user.id,
        location_id=location.id,
        radius_m=Decimal("10000"),
        minimum_severity=Severity.low,
        enabled=True,
    )
    session.add(subscription)
    session.commit()

    # Create observation ~5km away (0.05 degrees ≈ 5.5km)
    observation = SatelliteFireObservation(
        source_id=source.id,
        external_id="obs_near",
        product="VIIRS_SNPP_NRT",
        observed_at=datetime.now(timezone.utc),
        point=point(base_data, "0.05"),
        raw_payload={},
    )
    session.add(observation)
    session.commit()

    # Find matches
    matches = find_matches_for_observation(session, observation.id)

    assert len(matches) == 1
    match = matches[0]
    assert match.observation_id == observation.id
    assert match.subscription_id == subscription.id
    assert match.user_id == user.id
    assert match.location_id == location.id
    assert match.distance_m < Decimal("10000")


def test_no_match_outside_radius(session, base_data):
    """Test that observations outside subscription radius are not matched."""
    user = base_data["user1"]
    source = base_data["source"]

    # Create location at (0, 0)
    location = MonitoringLocation(
        owner_id=user.id,
        name="Test Location",
        location_type=LocationType.farm,
        point=point(base_data),
    )
    session.add(location)
    session.commit()

    # Create subscription with 5km radius
    subscription = MonitoringSubscription(
        user_id=user.id,
        location_id=location.id,
        radius_m=Decimal("5000"),
        minimum_severity=Severity.low,
        enabled=True,
    )
    session.add(subscription)
    session.commit()

    # Create observation ~100km away
    observation = SatelliteFireObservation(
        source_id=source.id,
        external_id="obs_far",
        product="VIIRS_SNPP_NRT",
        observed_at=datetime.now(timezone.utc),
        point=point(base_data, "1"),
        raw_payload={},
    )
    session.add(observation)
    session.commit()

    # Find matches
    matches = find_matches_for_observation(session, observation.id)

    assert len(matches) == 0


def test_multiple_users_subscribed(session, base_data):
    """Test that multiple subscribed users get matched."""
    user1 = base_data["user1"]
    user2 = base_data["user2"]
    source = base_data["source"]

    # Create location at (0, 0)
    location = MonitoringLocation(
        owner_id=user1.id,
        name="Shared Location",
        location_type=LocationType.farm,
        point=point(base_data),
    )
    session.add(location)
    session.commit()

    # Both users subscribe
    sub1 = MonitoringSubscription(
        user_id=user1.id,
        location_id=location.id,
        radius_m=Decimal("10000"),
        minimum_severity=Severity.low,
        enabled=True,
    )
    sub2 = MonitoringSubscription(
        user_id=user2.id,
        location_id=location.id,
        radius_m=Decimal("10000"),
        minimum_severity=Severity.low,
        enabled=True,
    )
    session.add_all([sub1, sub2])
    session.add(LocationAccess(location_id=location.id, user_id=user2.id, permission="view"))
    session.commit()

    # Create nearby observation
    observation = SatelliteFireObservation(
        source_id=source.id,
        external_id="obs_shared",
        product="VIIRS_SNPP_NRT",
        observed_at=datetime.now(timezone.utc),
        point=point(base_data, "0.05"),
        raw_payload={},
    )
    session.add(observation)
    session.commit()

    # Find matches
    matches = find_matches_for_observation(session, observation.id)

    assert len(matches) == 2
    user_ids = {match.user_id for match in matches}
    assert user1.id in user_ids
    assert user2.id in user_ids


def test_disabled_subscription_not_matched(session, base_data):
    """Test that disabled subscriptions are not matched."""
    user = base_data["user1"]
    source = base_data["source"]

    # Create location
    location = MonitoringLocation(
        owner_id=user.id,
        name="Test Location",
        location_type=LocationType.farm,
        point=point(base_data),
    )
    session.add(location)
    session.commit()

    # Create disabled subscription
    subscription = MonitoringSubscription(
        user_id=user.id,
        location_id=location.id,
        radius_m=Decimal("10000"),
        minimum_severity=Severity.low,
        enabled=False,  # Disabled
    )
    session.add(subscription)
    session.commit()

    # Create nearby observation
    observation = SatelliteFireObservation(
        source_id=source.id,
        external_id="obs_disabled",
        product="VIIRS_SNPP_NRT",
        observed_at=datetime.now(timezone.utc),
        point=point(base_data, "0.05"),
        raw_payload={},
    )
    session.add(observation)
    session.commit()

    # Find matches
    matches = find_matches_for_observation(session, observation.id)

    assert len(matches) == 0


def test_multiple_locations_per_user(session, base_data):
    """Test user monitoring multiple locations."""
    user = base_data["user1"]
    source = base_data["source"]

    # Create two locations
    location1 = MonitoringLocation(
        owner_id=user.id,
        name="Location 1",
        location_type=LocationType.farm,
        point=point(base_data),
    )
    location2 = MonitoringLocation(
        owner_id=user.id,
        name="Location 2",
        location_type=LocationType.campsite,
        point=point(base_data, "0.2"),  # ~22km away
    )
    session.add_all([location1, location2])
    session.commit()

    # Subscribe to both
    sub1 = MonitoringSubscription(
        user_id=user.id,
        location_id=location1.id,
        radius_m=Decimal("10000"),
        minimum_severity=Severity.low,
        enabled=True,
    )
    sub2 = MonitoringSubscription(
        user_id=user.id,
        location_id=location2.id,
        radius_m=Decimal("10000"),
        minimum_severity=Severity.low,
        enabled=True,
    )
    session.add_all([sub1, sub2])
    session.commit()

    # Create observation near location1
    observation = SatelliteFireObservation(
        source_id=source.id,
        external_id="obs_multi",
        product="VIIRS_SNPP_NRT",
        observed_at=datetime.now(timezone.utc),
        point=point(base_data, "0.05"),
        raw_payload={},
    )
    session.add(observation)
    session.commit()

    # Find matches
    matches = find_matches_for_observation(session, observation.id)

    # Should match location1 only (location2 is ~11km away from origin)
    assert len(matches) == 1
    assert matches[0].location_id == location1.id


def test_find_new_observations_for_location(session, base_data):
    """Test finding observations near a specific location."""
    user = base_data["user1"]
    source = base_data["source"]

    # Create location
    location = MonitoringLocation(
        owner_id=user.id,
        name="Test Location",
        location_type=LocationType.farm,
        point=point(base_data),
    )
    session.add(location)
    session.commit()

    # Create subscription
    subscription = MonitoringSubscription(
        user_id=user.id,
        location_id=location.id,
        radius_m=Decimal("10000"),
        minimum_severity=Severity.low,
        enabled=True,
    )
    session.add(subscription)
    session.commit()

    # Create observations
    obs1 = SatelliteFireObservation(
        source_id=source.id,
        external_id="obs1",
        product="VIIRS_SNPP_NRT",
        observed_at=datetime.now(timezone.utc),
        point=point(base_data, "0.05"),  # ~5.5km
        raw_payload={},
    )
    obs2 = SatelliteFireObservation(
        source_id=source.id,
        external_id="obs2",
        product="VIIRS_SNPP_NRT",
        observed_at=datetime.now(timezone.utc),
        point=point(base_data, "1"),  # ~100km
        raw_payload={},
    )
    session.add_all([obs1, obs2])
    session.commit()

    # Find observations
    observations = find_new_observations_for_location(session, location.id)

    # Should find obs1 only
    assert len(observations) == 1
    assert observations[0][0].id == obs1.id
    assert observations[0][1] < Decimal("10000")
