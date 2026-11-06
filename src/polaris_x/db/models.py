from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geography
from polaris_x.db.base import Base

class LocationType(str, Enum):
    farm = "farm"; point = "point"; campsite = "campsite"; trailhead = "trailhead"; other = "other"
class Severity(str, Enum):
    low = "low"; moderate = "moderate"; high = "high"; critical = "critical"
class SensorKind(str, Enum):
    bme280 = "bme280"; anemometer = "anemometer"; wind_vane = "wind_vane"; pms5003 = "pms5003"; mq2 = "mq2"; soil_moisture = "soil_moisture"; other = "other"

def id_col(): return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
def created_col(): return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = id_col(); email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False); display_name: Mapped[str] = mapped_column(String(120), nullable=False); password_hash: Mapped[str] = mapped_column(String(255), nullable=False); is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False); created_at: Mapped[datetime] = created_col()
    roles: Mapped[list[Role]] = relationship(secondary="user_roles", back_populates="users")
class Role(Base):
    __tablename__ = "roles"
    id: Mapped[UUID] = id_col(); name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    users: Mapped[list[User]] = relationship(secondary="user_roles", back_populates="roles")
    __table_args__ = (CheckConstraint("name IN ('user', 'farm_owner', 'authority', 'admin')", name="role_name_values"),)
class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True); role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)

class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[UUID] = id_col(); name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False); source_type: Mapped[str] = mapped_column(String(40), nullable=False); provider: Mapped[str] = mapped_column(String(120), nullable=False); metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False); created_at: Mapped[datetime] = created_col()

class MonitoringLocation(Base):
    __tablename__ = "monitoring_locations"
    id: Mapped[UUID] = id_col(); owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False); name: Mapped[str] = mapped_column(String(160), nullable=False); location_type: Mapped[LocationType] = mapped_column(SAEnum(LocationType, name="location_type"), nullable=False); point = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False); description: Mapped[str | None] = mapped_column(Text); created_at: Mapped[datetime] = created_col()
    owner: Mapped[User] = relationship(); access_grants: Mapped[list[LocationAccess]] = relationship(back_populates="location", cascade="all, delete-orphan"); subscriptions: Mapped[list[MonitoringSubscription]] = relationship(back_populates="location")
    __table_args__ = (Index("ix_monitoring_locations_point", "point", postgresql_using="gist"),)
class LocationAccess(Base):
    __tablename__ = "location_access"
    location_id: Mapped[UUID] = mapped_column(ForeignKey("monitoring_locations.id", ondelete="CASCADE"), primary_key=True); user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True); permission: Mapped[str] = mapped_column(String(20), nullable=False)
    location: Mapped[MonitoringLocation] = relationship(back_populates="access_grants")
    __table_args__ = (CheckConstraint("permission IN ('view', 'manage')", name="permission_values"),)
class HikingRoute(Base):
    __tablename__ = "hiking_routes"
    id: Mapped[UUID] = id_col(); owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False); name: Mapped[str] = mapped_column(String(160), nullable=False); path = mapped_column(Geography(geometry_type="LINESTRING", srid=4326, spatial_index=False), nullable=False); created_at: Mapped[datetime] = created_col()
    owner: Mapped[User] = relationship(); subscriptions: Mapped[list[MonitoringSubscription]] = relationship(back_populates="route")
    __table_args__ = (Index("ix_hiking_routes_path", "path", postgresql_using="gist"),)
class MonitoringSubscription(Base):
    __tablename__ = "monitoring_subscriptions"
    id: Mapped[UUID] = id_col(); user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False); location_id: Mapped[UUID | None] = mapped_column(ForeignKey("monitoring_locations.id", ondelete="CASCADE")); route_id: Mapped[UUID | None] = mapped_column(ForeignKey("hiking_routes.id", ondelete="CASCADE")); radius_m: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False); minimum_severity: Mapped[Severity] = mapped_column(SAEnum(Severity, name="severity"), nullable=False); enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    location: Mapped[MonitoringLocation | None] = relationship(back_populates="subscriptions"); route: Mapped[HikingRoute | None] = relationship(back_populates="subscriptions")
    __table_args__ = (UniqueConstraint("user_id", "location_id", name="uq_subscription_user_location"), UniqueConstraint("user_id", "route_id", name="uq_subscription_user_route"), CheckConstraint("radius_m > 0", name="radius_positive"), CheckConstraint("(location_id IS NOT NULL) <> (route_id IS NOT NULL)", name="subscription_one_target"))

class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[UUID] = id_col()
    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False)
    product: Mapped[str] = mapped_column(String(80), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    started_at: Mapped[datetime] = created_col()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    inserted_count: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(nullable=False, default=0)
    rejected_records: Mapped[list[IngestionRejectedRecord]] = relationship(back_populates="run", cascade="all, delete-orphan")

class IngestionRejectedRecord(Base):
    __tablename__ = "ingestion_rejected_records"
    id: Mapped[UUID] = id_col()
    ingestion_run_id: Mapped[UUID] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(nullable=False)
    reason_code: Mapped[str] = mapped_column(String(60), nullable=False)
    reason_message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    run: Mapped[IngestionRun] = relationship(back_populates="rejected_records")
    __table_args__ = (UniqueConstraint("ingestion_run_id", "row_number", name="uq_rejected_run_row"),)

class SatelliteFireObservation(Base):
    __tablename__ = "satellite_fire_observations"
    id: Mapped[UUID] = id_col(); source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False); external_id: Mapped[str] = mapped_column(String(180), nullable=False); product: Mapped[str] = mapped_column(String(80), nullable=False); observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); ingested_at: Mapped[datetime] = created_col(); processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); point = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False); confidence_original: Mapped[str | None] = mapped_column(String(80)); brightness_temperature: Mapped[Decimal | None] = mapped_column(Numeric(8,3)); frp: Mapped[Decimal | None] = mapped_column(Numeric(12,3)); raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_fire_observation_source_external"), Index("ix_fire_observations_point", "point", postgresql_using="gist"))
class FireEvent(Base):
    __tablename__ = "fire_events"
    id: Mapped[UUID] = id_col(); status: Mapped[str] = mapped_column(String(30), nullable=False); started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); centroid = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False); created_at: Mapped[datetime] = created_col()
class FireEventObservation(Base):
    __tablename__ = "fire_event_observations"
    fire_event_id: Mapped[UUID] = mapped_column(ForeignKey("fire_events.id", ondelete="CASCADE"), primary_key=True)
    observation_id: Mapped[UUID] = mapped_column(ForeignKey("satellite_fire_observations.id", ondelete="CASCADE"), primary_key=True)
    distance_m: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    temporal_delta_seconds: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    associated_at: Mapped[datetime] = created_col()
    __table_args__ = (UniqueConstraint("observation_id", name="uq_fire_event_observation_one_event"),)

class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    id: Mapped[UUID] = id_col(); source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False); location_id: Mapped[UUID | None] = mapped_column(ForeignKey("monitoring_locations.id", ondelete="SET NULL")); observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); variables: Mapped[dict] = mapped_column(JSONB, nullable=False); raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"
    id: Mapped[UUID] = id_col(); source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False); location_id: Mapped[UUID | None] = mapped_column(ForeignKey("monitoring_locations.id", ondelete="SET NULL")); issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); variables: Mapped[dict] = mapped_column(JSONB, nullable=False); raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (CheckConstraint("valid_to > valid_from", name="forecast_valid_range"),)

class SensorNode(Base):
    __tablename__ = "sensor_nodes"
    id: Mapped[UUID] = id_col(); node_identifier: Mapped[str] = mapped_column(String(120), unique=True, nullable=False); name: Mapped[str] = mapped_column(String(120), nullable=False); location_id: Mapped[UUID | None] = mapped_column(ForeignKey("monitoring_locations.id", ondelete="SET NULL")); active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False); created_at: Mapped[datetime] = created_col()
    sensors: Mapped[list[Sensor]] = relationship(back_populates="node", cascade="all, delete-orphan")
class Sensor(Base):
    __tablename__ = "sensors"
    id: Mapped[UUID] = id_col(); node_id: Mapped[UUID] = mapped_column(ForeignKey("sensor_nodes.id", ondelete="CASCADE"), nullable=False); sensor_identifier: Mapped[str] = mapped_column(String(120), nullable=False); kind: Mapped[SensorKind] = mapped_column(SAEnum(SensorKind, name="sensor_kind"), nullable=False); unit: Mapped[str] = mapped_column(String(40), nullable=False); calibration_version: Mapped[str | None] = mapped_column(String(80)); node: Mapped[SensorNode] = relationship(back_populates="sensors"); measurements: Mapped[list[SensorMeasurement]] = relationship(back_populates="sensor", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("node_id", "sensor_identifier", name="uq_sensor_node_identifier"),)
class SensorMeasurement(Base):
    __tablename__ = "sensor_measurements"
    id: Mapped[UUID] = id_col(); sensor_id: Mapped[UUID] = mapped_column(ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False); measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(16,6)); value_text: Mapped[str | None] = mapped_column(String(120)); quality_flag: Mapped[str | None] = mapped_column(String(40)); calibration_version: Mapped[str | None] = mapped_column(String(80)); raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False); sensor: Mapped[Sensor] = relationship(back_populates="measurements")
    __table_args__ = (CheckConstraint("value_numeric IS NOT NULL OR value_text IS NOT NULL", name="measurement_has_value"), Index("ix_sensor_measurements_sensor_measured", "sensor_id", "measured_at"))

class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    id: Mapped[UUID] = id_col(); location_id: Mapped[UUID] = mapped_column(ForeignKey("monitoring_locations.id", ondelete="CASCADE"), nullable=False); assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False); model_name: Mapped[str] = mapped_column(String(120), nullable=False); model_version: Mapped[str] = mapped_column(String(80), nullable=False); assessment_status: Mapped[str] = mapped_column(String(30), nullable=False, default="insufficient_data"); risk_level: Mapped[Severity | None] = mapped_column(SAEnum(Severity, name="risk_severity"), nullable=True); score: Mapped[Decimal | None] = mapped_column(Numeric(7,5)); feature_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False); evidence_summary: Mapped[dict] = mapped_column(JSONB, nullable=False); data_quality: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict); uncertainty: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict); input_provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[UUID] = id_col(); location_id: Mapped[UUID | None] = mapped_column(ForeignKey("monitoring_locations.id", ondelete="SET NULL")); event_id: Mapped[UUID | None] = mapped_column(ForeignKey("fire_events.id", ondelete="SET NULL")); risk_assessment_id: Mapped[UUID | None] = mapped_column(ForeignKey("risk_assessments.id", ondelete="SET NULL")); alert_type: Mapped[str] = mapped_column(String(50), nullable=False); severity: Mapped[Severity] = mapped_column(SAEnum(Severity, name="alert_severity"), nullable=False); title: Mapped[str] = mapped_column(String(200), nullable=False); message: Mapped[str] = mapped_column(Text, nullable=False); created_at: Mapped[datetime] = created_col(); expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
class AlertEvidence(Base):
    __tablename__ = "alert_evidence"
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True); evidence_type: Mapped[str] = mapped_column(String(50), primary_key=True); evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True); details: Mapped[dict] = mapped_column(JSONB, nullable=False)
class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    id: Mapped[UUID] = id_col(); user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False); channel: Mapped[str] = mapped_column(String(20), nullable=False); enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False); minimum_severity: Mapped[Severity] = mapped_column(SAEnum(Severity, name="preference_severity"), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "channel", name="uq_notification_preference_user_channel"), CheckConstraint("channel IN ('push', 'in_app', 'sms')", name="notification_channel_values"))
class NotificationDeliveryAttempt(Base):
    __tablename__ = "notification_delivery_attempts"
    id: Mapped[UUID] = id_col(); alert_id: Mapped[UUID] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False); user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False); channel: Mapped[str] = mapped_column(String(20), nullable=False); status: Mapped[str] = mapped_column(String(30), nullable=False); attempted_at: Mapped[datetime] = created_col(); provider_response: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    __table_args__ = (CheckConstraint("channel IN ('push', 'in_app', 'sms')", name="delivery_channel_values"),)

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[UUID] = id_col(); user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False); started_at: Mapped[datetime] = created_col(); ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    messages: Mapped[list[ChatMessage]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")
class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[UUID] = id_col(); session_id: Mapped[UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False); role: Mapped[str] = mapped_column(String(20), nullable=False); content: Mapped[str] = mapped_column(Text, nullable=False); created_at: Mapped[datetime] = created_col(); source_references: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    session: Mapped[ChatSession] = relationship(back_populates="messages")
    __table_args__ = (CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name="chat_message_role_values"), Index("ix_chat_messages_session_created", "session_id", "created_at"))
