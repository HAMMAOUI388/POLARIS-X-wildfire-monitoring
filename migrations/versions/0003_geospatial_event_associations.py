"""add deterministic geospatial event association evidence"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_event_assoc"
down_revision = "0002_firms_ingestion"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("fire_event_observations", sa.Column("distance_m", sa.Numeric(12, 3), nullable=True))
    op.add_column("fire_event_observations", sa.Column("temporal_delta_seconds", sa.Numeric(14, 3), nullable=True))
    op.add_column("fire_event_observations", sa.Column("policy_snapshot", postgresql.JSONB, nullable=True))
    op.add_column("fire_event_observations", sa.Column("associated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
    op.execute("UPDATE fire_event_observations SET distance_m = 0, temporal_delta_seconds = 0, policy_snapshot = '{}'::jsonb WHERE distance_m IS NULL")
    op.alter_column("fire_event_observations", "distance_m", nullable=False)
    op.alter_column("fire_event_observations", "temporal_delta_seconds", nullable=False)
    op.alter_column("fire_event_observations", "policy_snapshot", nullable=False)
    op.create_unique_constraint("uq_fire_event_observation_one_event", "fire_event_observations", ["observation_id"])

def downgrade():
    op.drop_constraint("uq_fire_event_observation_one_event", "fire_event_observations", type_="unique")
    op.drop_column("fire_event_observations", "associated_at")
    op.drop_column("fire_event_observations", "policy_snapshot")
    op.drop_column("fire_event_observations", "temporal_delta_seconds")
    op.drop_column("fire_event_observations", "distance_m")
