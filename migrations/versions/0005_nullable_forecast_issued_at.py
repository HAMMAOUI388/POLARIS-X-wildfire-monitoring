"""Make WeatherForecast.issued_at nullable to support unknown forecast run times.

The seamless Open-Meteo Forecast API does not expose model initialization/run times.
This migration makes issued_at nullable so that retrieval_time is not incorrectly
substituted for the genuine forecast issue time.

Revision ID: 0005_nullable_forecast_issued_at
Revises: 0004_assessment_foundation
Create Date: 2026-11-09

"""
from alembic import op
import sqlalchemy as sa


revision = "0005_nullable_forecast_issued_at"
down_revision = "0004_assess_foundation"
branch_labels = None
depends_on = None


def upgrade():
    # Make WeatherForecast.issued_at nullable
    op.alter_column(
        "weather_forecasts",
        "issued_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade():
    # Before making issued_at non-nullable again, we must handle NULL values
    # For downgrade, set any NULL issued_at to valid_from (conservative fallback)
    op.execute(
        """
        UPDATE weather_forecasts
        SET issued_at = valid_from
        WHERE issued_at IS NULL
        """
    )

    op.alter_column(
        "weather_forecasts",
        "issued_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
