"""Add user-owned operational alert recipients and match provenance.

Revision ID: 0006_alert_recipients
Revises: 0005_nullable_forecast_issued_at
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_alert_recipients"
down_revision = "0005_nullable_forecast_issued_at"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alert_recipients",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("monitoring_subscriptions.id", ondelete="SET NULL")),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("satellite_fire_observations.id", ondelete="SET NULL")),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fire_events.id", ondelete="SET NULL")),
        sa.Column("distance_m", sa.Numeric(12, 3)),
        sa.Column("matching_policy", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="unread"),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deduplication_key", sa.String(300), nullable=False, unique=True),
        sa.CheckConstraint("status IN ('unread', 'read')", name="alert_recipient_status_values"),
    )
    op.create_index("ix_alert_recipients_user_created", "alert_recipients", ["user_id", "created_at"])


def downgrade():
    op.drop_index("ix_alert_recipients_user_created", table_name="alert_recipients")
    op.drop_table("alert_recipients")
