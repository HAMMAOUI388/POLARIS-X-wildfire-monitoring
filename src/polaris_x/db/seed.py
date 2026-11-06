from datetime import datetime, timezone
from geoalchemy2.elements import WKTElement
from polaris_x.db.models import (Alert, ChatMessage, ChatSession, DataSource, FireEvent, FireEventObservation, HikingRoute, LocationAccess, MonitoringLocation, MonitoringSubscription, NotificationPreference, RiskAssessment, Role, SatelliteFireObservation, Sensor, SensorKind, SensorMeasurement, SensorNode, Severity, User, WeatherForecast, WeatherObservation)
from polaris_x.db.session import make_session_factory

SYNTHETIC_EMAIL = "synthetic@example.invalid"

def seed_development_data(url: str | None = None):
    Session = make_session_factory(url)
    now = datetime.now(timezone.utc)
    with Session.begin() as session:
        roles = {name: session.query(Role).filter_by(name=name).one_or_none() for name in ("user", "farm_owner", "authority", "admin")}
        for name, role in roles.items():
            if role is None:
                role = Role(name=name); session.add(role); roles[name] = role
        user = session.query(User).filter_by(email=SYNTHETIC_EMAIL).one_or_none()
        if user is None:
            user = User(email=SYNTHETIC_EMAIL, display_name="Synthetic Development User", password_hash="synthetic-only-no-login")
            user.roles.extend([roles["user"], roles["farm_owner"]]); session.add(user); session.flush()
        source = session.query(DataSource).filter_by(name="Synthetic FIRMS Development Source").one_or_none()
        if source is None:
            source = DataSource(name="Synthetic FIRMS Development Source", source_type="satellite", provider="synthetic", metadata_json={"synthetic": True}); session.add(source); session.flush()
        location = session.query(MonitoringLocation).filter_by(name="Synthetic Farm Location").one_or_none()
        if location is None:
            location = MonitoringLocation(owner_id=user.id, name="Synthetic Farm Location", location_type="farm", point=WKTElement("POINT(-6.84 33.97)", srid=4326), description="Synthetic development location; not a real property."); session.add(location); session.flush()
        session.add(LocationAccess(location_id=location.id, user_id=user.id, permission="manage")) if not session.query(LocationAccess).filter_by(location_id=location.id, user_id=user.id).one_or_none() else None
        route = session.query(HikingRoute).filter_by(name="Synthetic Hiking Route").one_or_none()
        if route is None:
            route = HikingRoute(owner_id=user.id, name="Synthetic Hiking Route", path=WKTElement("LINESTRING(-6.85 33.96,-6.84 33.97,-6.83 33.98)", srid=4326)); session.add(route); session.flush()
        if not session.query(MonitoringSubscription).filter_by(user_id=user.id, location_id=location.id).one_or_none(): session.add(MonitoringSubscription(user_id=user.id, location_id=location.id, radius_m=5000, minimum_severity=Severity.moderate))
        if not session.query(MonitoringSubscription).filter_by(user_id=user.id, route_id=route.id).one_or_none(): session.add(MonitoringSubscription(user_id=user.id, route_id=route.id, radius_m=1000, minimum_severity=Severity.high))
        observation = session.query(SatelliteFireObservation).filter_by(external_id="synthetic-firms-001").one_or_none()
        if observation is None:
            observation = SatelliteFireObservation(source_id=source.id, external_id="synthetic-firms-001", product="synthetic-product", observed_at=now, point=WKTElement("POINT(-6.82 33.98)", srid=4326), confidence_original="synthetic-medium", raw_payload={"synthetic": True}); session.add(observation); session.flush()
        event = session.query(FireEvent).filter_by(status="synthetic_observed").one_or_none()
        if event is None:
            event = FireEvent(status="synthetic_observed", started_at=now, centroid=WKTElement("POINT(-6.82 33.98)", srid=4326)); session.add(event); session.flush(); session.add(FireEventObservation(fire_event_id=event.id, observation_id=observation.id))
        session.add(WeatherObservation(source_id=source.id, location_id=location.id, observed_at=now, variables={"temperature_c": 28, "synthetic": True}, raw_payload={"synthetic": True}))
        session.add(WeatherForecast(source_id=source.id, location_id=location.id, issued_at=now, valid_from=now, valid_to=now.replace(hour=(now.hour + 1) % 24), variables={"wind_kph": 15, "synthetic": True}, raw_payload={"synthetic": True}))
        node = session.query(SensorNode).filter_by(node_identifier="synthetic-node-001").one_or_none()
        if node is None:
            node = SensorNode(node_identifier="synthetic-node-001", name="Synthetic ESP32 Node", location_id=location.id); session.add(node); session.flush(); sensor = Sensor(node_id=node.id, sensor_identifier="mq2-001", kind=SensorKind.mq2, unit="adc_raw", calibration_version="uncalibrated"); session.add(sensor); session.flush(); session.add(SensorMeasurement(sensor_id=sensor.id, measured_at=now, received_at=now, value_numeric=312, quality_flag="synthetic", calibration_version="uncalibrated", raw_payload={"synthetic": True, "adc": 312}))
        assessment = RiskAssessment(location_id=location.id, assessed_at=now, model_name="synthetic-baseline", model_version="0.1", risk_level=Severity.moderate, score=0.35, feature_snapshot={"synthetic": True}, evidence_summary={"limitations": "Synthetic development assessment; not validated."}); session.add(assessment); session.flush()
        alert = Alert(location_id=location.id, event_id=event.id, risk_assessment_id=assessment.id, alert_type="synthetic_test", severity=Severity.moderate, title="Synthetic development alert", message="Synthetic alert for local development only."); session.add(alert); session.flush()
        for channel in ("push", "in_app", "sms"): session.add(NotificationPreference(user_id=user.id, channel=channel, minimum_severity=Severity.moderate))
        chat = ChatSession(user_id=user.id, metadata_json={"synthetic": True}); chat.messages.append(ChatMessage(role="user", content="Synthetic development question", source_references={"synthetic": True})); session.add(chat)

if __name__ == "__main__": seed_development_data()
