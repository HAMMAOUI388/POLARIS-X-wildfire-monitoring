"""
POLARIS X Data Ingestion Orchestration CLI

Unified command-line interface for ingesting external data:
- NASA FIRMS active fire observations
- Open-Meteo operational weather forecasts
- Open-Meteo historical reanalysis archives

Usage:
    python3 -m polaris_x.ingestion firms-api --source VIIRS_SNPP_NRT --west -15 --south 21 --east -1 --north 36
    python3 -m polaris_x.ingestion weather-forecast
    python3 -m polaris_x.ingestion weather-archive --start-date 2024-01-01 --end-date 2024-01-31
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from polaris_x.config import Config
from polaris_x.db.models import MonitoringLocation
from polaris_x.db.session import make_session_factory
from polaris_x.ingestion.firms import FirmsApiAdapter, import_api as import_firms_api
from polaris_x.ingestion.weather import ingest_for_all_locations
from polaris_x.integrations.weather import OpenMeteoClient


def main() -> int:
    """CLI entry point for data ingestion orchestration."""
    parser = argparse.ArgumentParser(
        description="POLARIS X Data Ingestion Orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Ingestion command")

    # NASA FIRMS API ingestion
    firms_parser = subparsers.add_parser(
        "firms-api",
        help="Ingest NASA FIRMS active fire data via API",
    )
    firms_parser.add_argument(
        "--source",
        required=True,
        choices=["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT", "MODIS_SP"],
        help="FIRMS data source",
    )
    firms_parser.add_argument(
        "--west",
        required=True,
        type=float,
        help="Western longitude boundary (-180 to 180)",
    )
    firms_parser.add_argument(
        "--south",
        required=True,
        type=float,
        help="Southern latitude boundary (-90 to 90)",
    )
    firms_parser.add_argument(
        "--east",
        required=True,
        type=float,
        help="Eastern longitude boundary (-180 to 180)",
    )
    firms_parser.add_argument(
        "--north",
        required=True,
        type=float,
        help="Northern latitude boundary (-90 to 90)",
    )
    firms_parser.add_argument(
        "--day-range",
        type=int,
        default=1,
        help="Number of days to retrieve (1-10, default: 1)",
    )
    firms_parser.add_argument(
        "--date",
        type=str,
        help="Optional start date YYYY-MM-DD (default: most recent)",
    )

    # Open-Meteo forecast ingestion
    forecast_parser = subparsers.add_parser(
        "weather-forecast",
        help="Ingest operational weather forecasts for all monitoring locations",
    )
    forecast_parser.add_argument(
        "--past-days",
        type=int,
        default=0,
        help="Number of past days to include (0-92, default: 0)",
    )
    forecast_parser.add_argument(
        "--forecast-days",
        type=int,
        default=7,
        help="Number of forecast days (0-16, default: 7)",
    )

    # Open-Meteo archive/reanalysis ingestion
    archive_parser = subparsers.add_parser(
        "weather-archive",
        help="Ingest historical weather reanalysis for all monitoring locations",
    )
    archive_parser.add_argument(
        "--start-date",
        required=True,
        type=str,
        help="Start date YYYY-MM-DD",
    )
    archive_parser.add_argument(
        "--end-date",
        required=True,
        type=str,
        help="End date YYYY-MM-DD",
    )

    args = parser.parse_args()

    try:
        if args.command == "firms-api":
            print(f"Fetching FIRMS {args.source} data for area ({args.west},{args.south},{args.east},{args.north})...")
            result = import_firms_api(
                source=args.source,
                west=args.west,
                south=args.south,
                east=args.east,
                north=args.north,
                day_range=args.day_range,
                date=args.date,
            )
            print(f"✓ FIRMS ingestion completed:")
            print(f"  Run ID: {result.run_id}")
            print(f"  Inserted: {result.inserted}")
            print(f"  Updated: {result.updated}")
            print(f"  Duplicates: {result.duplicate}")
            print(f"  Rejected: {result.rejected}")
            return 0 if result.rejected == 0 else 1

        elif args.command == "weather-forecast":
            print(f"Ingesting weather forecasts (past_days={args.past_days}, forecast_days={args.forecast_days})...")
            client = OpenMeteoClient(
                forecast_url=Config.OPEN_METEO_FORECAST_URL,
                archive_url=Config.OPEN_METEO_ARCHIVE_URL,
                api_key=Config.OPEN_METEO_API_KEY or None,
            )

            SessionFactory = make_session_factory()
            with SessionFactory.begin() as session:
                result = ingest_for_all_locations(
                    session=session,
                    client=client,
                    mode="forecast",
                    past_days=args.past_days,
                    forecast_days=args.forecast_days,
                )

            print(f"✓ Weather forecast ingestion completed:")
            print(f"  Forecasts inserted: {result.forecast_inserted}")
            print(f"  Locations processed: {result.locations_processed}")
            if result.errors:
                print(f"  Errors: {len(result.errors)}")
                for error in result.errors[:5]:  # Show first 5 errors
                    print(f"    - {error}")
            return 0 if not result.errors else 1

        elif args.command == "weather-archive":
            # Validate date format
            try:
                datetime.strptime(args.start_date, "%Y-%m-%d")
                datetime.strptime(args.end_date, "%Y-%m-%d")
            except ValueError as exc:
                print(f"Error: Invalid date format. Use YYYY-MM-DD.", file=sys.stderr)
                return 1

            print(f"Ingesting weather archive from {args.start_date} to {args.end_date}...")
            client = OpenMeteoClient(
                forecast_url=Config.OPEN_METEO_FORECAST_URL,
                archive_url=Config.OPEN_METEO_ARCHIVE_URL,
                api_key=Config.OPEN_METEO_API_KEY or None,
            )

            SessionFactory = make_session_factory()
            with SessionFactory.begin() as session:
                result = ingest_for_all_locations(
                    session=session,
                    client=client,
                    mode="archive",
                    start_date=args.start_date,
                    end_date=args.end_date,
                )

            print(f"✓ Weather archive ingestion completed:")
            print(f"  Observations inserted: {result.observation_inserted}")
            print(f"  Locations processed: {result.locations_processed}")
            if result.errors:
                print(f"  Errors: {len(result.errors)}")
                for error in result.errors[:5]:
                    print(f"    - {error}")
            return 0 if not result.errors else 1

        else:
            parser.error(f"Unknown command: {args.command}")
            return 1

    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
