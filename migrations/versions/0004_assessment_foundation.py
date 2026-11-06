"""add assessment quality and provenance fields"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_assess_foundation"
down_revision = "0003_event_assoc"
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("risk_assessments")}
    additions = (
        ("assessment_status", sa.String(30)),
        ("data_quality", postgresql.JSONB),
        ("uncertainty", postgresql.JSONB),
        ("input_provenance", postgresql.JSONB),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column("risk_assessments", sa.Column(name, column_type, nullable=True))
    op.execute("UPDATE risk_assessments SET assessment_status = 'legacy', data_quality = '{}'::jsonb, uncertainty = '{}'::jsonb, input_provenance = '{}'::jsonb WHERE assessment_status IS NULL")
    for name in ("assessment_status", "data_quality", "uncertainty", "input_provenance"):
        op.alter_column("risk_assessments", name, nullable=False)
    op.alter_column("risk_assessments", "risk_level", nullable=True)

def downgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("risk_assessments")}
    for name in ("input_provenance", "uncertainty", "data_quality", "assessment_status"):
        if name in columns:
            op.drop_column("risk_assessments", name)
