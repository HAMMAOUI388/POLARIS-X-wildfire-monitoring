from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import sessionmaker

from polaris_x.db.models import DataSource, LocationAccess, LocationType, MonitoringLocation, MonitoringSubscription, SatelliteFireObservation, Severity, User, WeatherForecast, WeatherObservation
from polaris_x.db.session import make_engine
from polaris_x.intelligence.alerts import AlertContext, generate_alert_for_match, weather_context_for_location
from polaris_x.intelligence.detection import find_matches_for_observation
from polaris_x.intelligence.notifications import NotificationPayload, PushNotificationProviderStub, SMSProviderStub


TEST_URL = "postgresql+psycopg://polaris:polaris_dev@localhost:55432/polaris_x_phase3_test"


@pytest.fixture
def session():
    engine = make_engine(TEST_URL)
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
    engine.dispose()


def setup_match(session):
    suffix = uuid4().hex
    owner = User(email=f"alert-owner-{suffix}@example.com", display_name="Owner", password_hash="x")
    source = DataSource(name=f"firms-{suffix}", source_type="satellite", provider="NASA FIRMS", metadata_json={})
    session.add_all([owner, source])
    session.flush()
    location = MonitoringLocation(owner_id=owner.id, name="Alert location", location_type=LocationType.point, point=WKTElement("POINT(70 10)", srid=4326))
    session.add(location)
    session.flush()
    subscription = MonitoringSubscription(user_id=owner.id, location_id=location.id, radius_m=Decimal("10000"), minimum_severity=Severity.low, enabled=True)
    observation = SatelliteFireObservation(source_id=source.id, external_id=f"firms-{suffix}", product="viirs", observed_at=datetime.now(timezone.utc), point=WKTElement("POINT(70.05 10)", srid=4326), raw_payload={})
    session.add_all([subscription, observation])
    session.flush()
    return owner, location, source, subscription, observation


def test_matching_requires_sharing_and_alert_is_idempotent(session):
    owner, location, _source, _subscription, observation = setup_match(session)
    viewer = User(email=f"alert-viewer-{uuid4()}@example.com", display_name="Viewer", password_hash="x")
    session.add(viewer)
    session.flush()
    session.add(MonitoringSubscription(user_id=viewer.id, location_id=location.id, radius_m=Decimal("10000"), minimum_severity=Severity.low, enabled=True))
    session.flush()
    assert {match.user_id for match in find_matches_for_observation(session, observation.id)} == {owner.id}
    session.add(LocationAccess(location_id=location.id, user_id=viewer.id, permission="view"))
    session.flush()
    matches = find_matches_for_observation(session, observation.id)
    assert {match.user_id for match in matches} == {owner.id, viewer.id}
    alert = generate_alert_for_match(session, AlertContext(matches[0]))
    assert alert is not None and "not a confirmed wildfire" in alert.message
    assert generate_alert_for_match(session, AlertContext(matches[0])) is None


def test_weather_context_preserves_forecast_and_reanalysis_categories(session):
    _owner, location, _source, _subscription, observation = setup_match(session)
    weather_source = DataSource(name=f"weather-{uuid4()}", source_type="reanalysis", provider="Open-Meteo", metadata_json={})
    session.add(weather_source)
    session.flush()
    reanalysis = WeatherObservation(source_id=weather_source.id, location_id=location.id, observed_at=observation.observed_at - timedelta(hours=1), variables={"temperature_2m": 20}, raw_payload={})
    session.add(reanalysis)
    session.flush()
    assert weather_context_for_location(session, location.id, observation.observed_at).category == "historical_reanalysis"
    forecast = WeatherForecast(source_id=weather_source.id, location_id=location.id, issued_at=None, valid_from=observation.observed_at - timedelta(hours=1), valid_to=observation.observed_at + timedelta(hours=1), variables={"wind_speed_10m": 12}, raw_payload={})
    session.add(forecast)
    session.flush()
    assert weather_context_for_location(session, location.id, observation.observed_at).category == "operational_forecast"


def test_notification_stubs_never_send_real_messages():
    payload = NotificationPayload(user_id=uuid4(), alert_id=uuid4(), channel="sms", title="test", message="test", severity=Severity.low)
    sms_ok, sms = SMSProviderStub().send(payload)
    push_ok, push = PushNotificationProviderStub().send(payload)
    assert sms_ok and sms["stub"] and "not sent" in sms["warning"]
    assert push_ok and push["stub"] and "not sent" in push["warning"]


def test_alert_api_uses_authenticated_recipient_for_read_and_idor():
    from polaris_x.app import create_app
    from polaris_x.extensions import db_session

    app = create_app({"TESTING": True, "DATABASE_URL": TEST_URL, "JWT_SECRET_KEY": "integration-test-secret-with-32-bytes-minimum"})
    owner_email, other_email = f"alert-api-owner-{uuid4()}@example.com", f"alert-api-other-{uuid4()}@example.com"
    with app.test_client() as client:
        for email in (owner_email, other_email):
            assert client.post("/api/v1/auth/register", json={"email": email, "password": "Correct-Horse-Battery-1", "display_name": "Alert API"}).status_code == 201
        def token(email):
            return client.post("/api/v1/auth/login", json={"email": email, "password": "Correct-Horse-Battery-1"}).json["access_token"]
        owner_token, other_token = token(owner_email), token(other_email)
        longitude = Decimal(str((uuid4().int % 2_000_000) / 10_000 - 100))
        with app.app_context():
            session = db_session()
            owner = session.query(User).filter_by(email=owner_email).one()
            source = DataSource(name=f"api-firms-{uuid4()}", source_type="satellite", provider="NASA FIRMS", metadata_json={})
            location = MonitoringLocation(owner_id=owner.id, name="API alert location", location_type=LocationType.point, point=WKTElement(f"POINT({longitude} 10)", srid=4326))
            session.add_all([source, location]); session.flush()
            subscription = MonitoringSubscription(user_id=owner.id, location_id=location.id, radius_m=Decimal("10000"), minimum_severity=Severity.low, enabled=True)
            observation = SatelliteFireObservation(source_id=source.id, external_id=f"api-obs-{uuid4()}", product="viirs", observed_at=datetime.now(timezone.utc), point=WKTElement(f"POINT({longitude + Decimal('0.05')} 10)", srid=4326), raw_payload={})
            session.add_all([subscription, observation]); session.flush()
            alert = generate_alert_for_match(session, AlertContext(find_matches_for_observation(session, observation.id)[0]))
            session.commit()
            alert_id = str(alert.id)
        headers = {"Authorization": f"Bearer {owner_token}"}
        listed = client.get("/api/v1/alerts?unread_only=true", headers=headers)
        assert listed.status_code == 200 and any(row["id"] == alert_id and row["status"] == "unread" for row in listed.json["alerts"])
        assert client.get(f"/api/v1/alerts/{alert_id}", headers={"Authorization": f"Bearer {other_token}"}).status_code == 404
        marked = client.post(f"/api/v1/alerts/{alert_id}/read", headers=headers)
        assert marked.status_code == 200 and marked.json["alert"]["status"] == "read" and marked.json["alert"]["read_at"]
        assert all(row["id"] != alert_id for row in client.get("/api/v1/alerts?unread_only=true", headers=headers).json["alerts"])
