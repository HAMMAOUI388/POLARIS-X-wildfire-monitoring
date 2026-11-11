"""
Weather data ingestion pipeline.

Fetches weather data from Open-Meteo and persists to weather_observations and weather_forecasts tables.
Preserves temporal distinctions:
- Operational forecasts → weather_forecasts (with valid_from/valid_to)
- Historical reanalysis → weather_observations (with observed_at)
- Issue/run times are NOT populated from the seamless forecast API (not available)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from polaris_x.config import Config
from polaris_x.db.models import DataSource, MonitoringLocation, WeatherForecast, WeatherObservation
from polaris_x.db.session import make_session_factory
from polaris_x.integrations.weather import OpenMeteoClient, OpenMeteoResponse


def _serialize_for_json(obj: Any) -> Any:
    """Recursively convert Decimal objects to float for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    return obj


@dataclass
class IngestionResult:
    """Weather ingestion run result."""

    forecast_inserted: int = 0
    observation_inserted: int = 0
    locations_processed: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "forecast_inserted": self.forecast_inserted,
            "observation_inserted": self.observation_inserted,
            "locations_processed": self.locations_processed,
            "errors": self.errors,
        }


def _ensure_data_source(
    session: Session,
    source_name: str,
    source_type: str,
    provider: str,
    metadata: dict[str, Any],
) -> DataSource:
    """Get or create a DataSource record."""
    source = session.scalar(select(DataSource).where(DataSource.name == source_name))
    if source is None:
        source = DataSource(
            name=source_name,
            source_type=source_type,
            provider=provider,
            metadata_json=metadata,
        )
        session.add(source)
        session.flush()
    return source


def ingest_forecast_for_location(
    session: Session,
    client: OpenMeteoClient,
    location: MonitoringLocation,
    past_days: int = 0,
    forecast_days: int = 7,
) -> IngestionResult:
    """
    Fetch and ingest operational forecast data for a single location.

    Args:
        session: Database session.
        client: Configured OpenMeteoClient.
        location: MonitoringLocation to fetch weather for.
        past_days: Number of past days to include.
        forecast_days: Number of forecast days.

    Returns:
        IngestionResult with counts and any errors.
    """
    result = IngestionResult()

    try:
        # Extract coordinates from PostGIS POINT
        # Cast Geography to Geometry for ST_Y/ST_X functions
        coords = session.execute(
            select(
                func.ST_Y(func.ST_GeomFromWKB(MonitoringLocation.point.ST_AsBinary())).label("latitude"),
                func.ST_X(func.ST_GeomFromWKB(MonitoringLocation.point.ST_AsBinary())).label("longitude"),
            ).where(MonitoringLocation.id == location.id)
        ).one()
        latitude, longitude = float(coords.latitude), float(coords.longitude)

        response: OpenMeteoResponse = client.fetch_forecast(
            latitude=latitude,
            longitude=longitude,
            past_days=past_days,
            forecast_days=forecast_days,
        )

        source = _ensure_data_source(
            session=session,
            source_name=f"Open-Meteo {response.model} Forecast",
            source_type=response.source_type,
            provider=response.provider,
            metadata={
                "model": response.model,
                "resolution_km": response.resolution_km,
                "attribution": Config.WEATHER_ATTRIBUTION,
                "api_endpoint": "forecast",
            },
        )

        for point in response.data_points:
            # The seamless forecast API does NOT expose model run/initialization times.
            # issued_at must remain NULL; retrieval_time is preserved in raw_payload.
            issued_at = None

            # Determine valid window
            if point.valid_from and point.valid_to:
                valid_from = point.valid_from
                valid_to = point.valid_to
            else:
                # Instantaneous variables: use valid_at as both bounds
                valid_from = point.valid_at
                valid_to = point.valid_at

            forecast = WeatherForecast(
                source_id=source.id,
                location_id=location.id,
                issued_at=issued_at,
                valid_from=valid_from,
                valid_to=valid_to,
                variables=_serialize_for_json(point.variables),
                raw_payload={
                    "provenance": _serialize_for_json(point.provenance),
                    "retrieval_time": response.retrieval_time.isoformat(),
                    "metadata": _serialize_for_json(response.metadata),
                },
            )
            session.add(forecast)
            result.forecast_inserted += 1

        result.locations_processed += 1

    except Exception as exc:
        result.errors.append(f"Location {location.id}: {exc}")

    return result


def ingest_archive_for_location(
    session: Session,
    client: OpenMeteoClient,
    location: MonitoringLocation,
    start_date: str,
    end_date: str,
) -> IngestionResult:
    """
    Fetch and ingest historical reanalysis data (ERA5/ERA5-Land) for a single location.

    Args:
        session: Database session.
        client: Configured OpenMeteoClient.
        location: MonitoringLocation to fetch weather for.
        start_date: ISO date string (YYYY-MM-DD).
        end_date: ISO date string (YYYY-MM-DD).

    Returns:
        IngestionResult with counts and any errors.

    Note:
        ERA5/ERA5-Land data is stored in weather_observations with source_type='reanalysis'.
        These are NOT direct weather-station observations but gridded model reanalysis.
    """
    result = IngestionResult()

    try:
        # Cast Geography to Geometry for ST_Y/ST_X functions
        coords = session.execute(
            select(
                func.ST_Y(func.ST_GeomFromWKB(MonitoringLocation.point.ST_AsBinary())).label("latitude"),
                func.ST_X(func.ST_GeomFromWKB(MonitoringLocation.point.ST_AsBinary())).label("longitude"),
            ).where(MonitoringLocation.id == location.id)
        ).one()
        latitude, longitude = float(coords.latitude), float(coords.longitude)

        response: OpenMeteoResponse = client.fetch_archive(
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
        )

        source = _ensure_data_source(
            session=session,
            source_name=f"Open-Meteo {response.model} Archive",
            source_type=response.source_type,
            provider=response.provider,
            metadata={
                "model": response.model,
                "resolution_km": response.resolution_km,
                "attribution": Config.WEATHER_ATTRIBUTION,
                "api_endpoint": "archive",
                "note": "Reanalysis product; not direct weather-station observations",
            },
        )

        for point in response.data_points:
            observation = WeatherObservation(
                source_id=source.id,
                location_id=location.id,
                observed_at=point.valid_at,
                variables=_serialize_for_json(point.variables),
                raw_payload={
                    "provenance": _serialize_for_json(point.provenance),
                    "metadata": _serialize_for_json(response.metadata),
                },
            )
            session.add(observation)
            result.observation_inserted += 1

        result.locations_processed += 1

    except Exception as exc:
        result.errors.append(f"Location {location.id}: {exc}")

    return result


def ingest_for_all_locations(
    session: Session,
    client: OpenMeteoClient,
    mode: str = "forecast",
    **kwargs: Any,
) -> IngestionResult:
    """
    Ingest weather data for all monitoring locations.

    Args:
        session: Database session.
        client: Configured OpenMeteoClient.
        mode: 'forecast' or 'archive'.
        **kwargs: Additional arguments for ingest_forecast_for_location or ingest_archive_for_location.

    Returns:
        Aggregated IngestionResult.
    """
    locations = session.scalars(select(MonitoringLocation)).all()
    aggregate = IngestionResult()

    for location in locations:
        if mode == "forecast":
            result = ingest_forecast_for_location(session, client, location, **kwargs)
        elif mode == "archive":
            result = ingest_archive_for_location(session, client, location, **kwargs)
        else:
            raise ValueError(f"Unknown ingestion mode: {mode}")

        aggregate.forecast_inserted += result.forecast_inserted
        aggregate.observation_inserted += result.observation_inserted
        aggregate.locations_processed += result.locations_processed
        aggregate.errors.extend(result.errors)

    return aggregate


def main() -> int:
    """CLI entry point for weather ingestion."""
    parser = argparse.ArgumentParser(description="Ingest weather data from Open-Meteo")
    parser.add_argument(
        "--mode",
        choices=["forecast", "archive"],
        default="forecast",
        help="Ingestion mode: 'forecast' for operational data, 'archive' for historical reanalysis",
    )
    parser.add_argument(
        "--location-id",
        type=str,
        help="Ingest for a specific location ID (UUID); if omitted, processes all locations",
    )
    parser.add_argument("--past-days", type=int, default=0, help="Past days to include (forecast mode)")
    parser.add_argument("--forecast-days", type=int, default=7, help="Forecast days (forecast mode)")
    parser.add_argument("--start-date", type=str, help="Start date YYYY-MM-DD (archive mode, required)")
    parser.add_argument("--end-date", type=str, help="End date YYYY-MM-DD (archive mode, required)")

    args = parser.parse_args()

    if args.mode == "archive" and (not args.start_date or not args.end_date):
        parser.error("--start-date and --end-date are required for archive mode")

    client = OpenMeteoClient(
        forecast_url=Config.OPEN_METEO_FORECAST_URL,
        archive_url=Config.OPEN_METEO_ARCHIVE_URL,
        api_key=Config.OPEN_METEO_API_KEY or None,
    )

    SessionFactory = make_session_factory()
    with SessionFactory.begin() as session:
        if args.location_id:
            location = session.get(MonitoringLocation, UUID(args.location_id))
            if not location:
                print(f"Error: Location {args.location_id} not found")
                return 1

            if args.mode == "forecast":
                result = ingest_forecast_for_location(
                    session, client, location, args.past_days, args.forecast_days
                )
            else:
                result = ingest_archive_for_location(
                    session, client, location, args.start_date, args.end_date
                )
        else:
            if args.mode == "forecast":
                result = ingest_for_all_locations(
                    session, client, mode="forecast", past_days=args.past_days, forecast_days=args.forecast_days
                )
            else:
                result = ingest_for_all_locations(
                    session, client, mode="archive", start_date=args.start_date, end_date=args.end_date
                )

        print(result.as_dict())

    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
