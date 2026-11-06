"""add FIRMS ingestion run and rejection persistence"""
from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_firms_ingestion"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

def upgrade():
    inspector = inspect(op.get_bind())
    if inspector.has_table("ingestion_runs"):
        return
    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("product", sa.String(80), nullable=False),
        sa.Column("source_filename", sa.String(500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("inserted_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_table(
        "ingestion_rejected_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("reason_code", sa.String(60), nullable=False),
        sa.Column("reason_message", sa.Text, nullable=False),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("ingestion_run_id", "row_number", name="uq_rejected_run_row"),
    )

def downgrade():
    op.drop_table("ingestion_rejected_records")
    op.drop_table("ingestion_runs")
