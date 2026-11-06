"""create initial POLARIS X database schema"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    from polaris_x.db.base import Base
    import polaris_x.db.models  # noqa: F401
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

def downgrade():
    from polaris_x.db.base import Base
    import polaris_x.db.models  # noqa: F401
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
