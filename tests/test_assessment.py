from datetime import datetime, timezone
from math import inf
from uuid import uuid4

import pytest

from polaris_x.risk import AssessmentInput, assess


def test_empty_inputs_return_explicit_insufficient_data():
    result = assess(AssessmentInput(location_id=uuid4(), assessed_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    assert result.assessment_status == "insufficient_data"
    assert result.score is None
    assert result.risk_level is None
    assert {item["feature"] for item in result.data_quality["missing_features"]} == {"weather", "iot", "terrain", "vegetation", "fuel"}
    assert result.uncertainty["status"] == "not_quantified"


def test_features_without_provenance_remain_insufficient():
    result = assess(AssessmentInput(location_id=uuid4(), assessed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), features={"weather": {"temperature_c": 20}}))
    assert result.data_quality["missing_features"] == [{"feature": "weather", "reason": "missing_provenance"}, {"feature": "iot", "reason": "not_available"}, {"feature": "terrain", "reason": "not_available"}, {"feature": "vegetation", "reason": "not_available"}, {"feature": "fuel", "reason": "not_available"}]


def test_stale_features_are_reported_as_insufficient():
    result = assess(AssessmentInput(
        location_id=uuid4(),
        assessed_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        features={"weather": {"temperature_c": 20}},
        provenance={"weather": {"observed_at": "2025-12-31T00:00:00Z", "max_age_seconds": 3600}},
    ))
    assert {item["reason"] for item in result.data_quality["missing_features"]} >= {"stale", "not_available"}
    assert result.score is None


def test_assessment_is_deterministic_and_normalizes_time_to_utc():
    item = AssessmentInput(location_id=uuid4(), assessed_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc), features={"observed": True}, provenance={"observed": {"source": "test"}}, required_features=())
    first = assess(item)
    second = assess(item)
    assert first == second
    assert first.assessed_at.tzinfo == timezone.utc


def test_naive_time_and_nonfinite_feature_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        assess(AssessmentInput(location_id=uuid4(), assessed_at=datetime(2026, 1, 1)))
    with pytest.raises(ValueError, match="finite"):
        assess(AssessmentInput(location_id=uuid4(), assessed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), features={"x": inf}))


def test_insufficient_assessment_persists_with_provenance_and_history():
    import os
    from sqlalchemy import delete, select
    from polaris_x.db.models import MonitoringLocation, RiskAssessment, User, LocationType
    from polaris_x.db.session import make_session_factory
    from geoalchemy2.elements import WKTElement

    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    factory = make_session_factory(url)
    email = f"assessment-{uuid4()}@example.com"
    user_id = uuid4()
    location_id = uuid4()
    try:
        with factory.begin() as session:
            user = User(id=user_id, email=email, display_name="Assessment Test", password_hash="test")
            location = MonitoringLocation(id=location_id, owner_id=user_id, name="Assessment Test Location", location_type=LocationType.point, point=WKTElement("POINT(-6.8 33.9)", srid=4326))
            session.add_all([user, location])
        item = AssessmentInput(location_id=location_id, assessed_at=datetime(2026, 1, 1, tzinfo=timezone.utc), provenance={"weather": {"source": "synthetic-test", "observed_at": "2026-01-01T00:00:00Z", "max_age_seconds": 3600}})
        from polaris_x.risk import persist_assessment
        with factory.begin() as session:
            first = persist_assessment(session, assess(item))
            second = persist_assessment(session, assess(item))
            assert first.id != second.id
        with factory() as session:
            rows = session.scalars(select(RiskAssessment).where(RiskAssessment.location_id == location_id).order_by(RiskAssessment.assessed_at)).all()
            assert len(rows) == 2
            assert all(row.assessment_status == "insufficient_data" and row.score is None for row in rows)
            assert rows[0].input_provenance["weather"]["source"] == "synthetic-test"
    finally:
        with factory.begin() as session:
            session.execute(delete(RiskAssessment).where(RiskAssessment.location_id == location_id))
            session.execute(delete(MonitoringLocation).where(MonitoringLocation.id == location_id))
            session.execute(delete(User).where(User.id == user_id))
        factory.kw["bind"].dispose()
