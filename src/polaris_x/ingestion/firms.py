from __future__ import annotations

import argparse
import csv
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from geoalchemy2 import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session

from polaris_x.db.models import DataSource, IngestionRejectedRecord, IngestionRun, SatelliteFireObservation
from polaris_x.db.session import make_session_factory

PRODUCTS = {"viirs", "modis"}
ALIASES = {
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "long"),
    "acq_date": ("acq_date", "observation_date", "date"),
    "acq_time": ("acq_time", "observation_time", "time"),
    "observed_at": ("observed_at", "acq_datetime", "observation_datetime", "timestamp"),
    "external_id": ("external_id", "id", "detection_id", "frp_id"),
    "confidence": ("confidence", "conf"),
    "frp": ("frp", "fire_radiative_power"),
    "brightness_temperature": ("bright_ti4", "bright_ti5", "brightness", "brightness_temperature", "bright_t31"),
    "published_at": ("published_at", "publication_time", "published"),
}

@dataclass(frozen=True)
class Rejection:
    row_number: int
    raw_payload: dict[str, Any]
    code: str
    message: str

@dataclass
class ImportResult:
    run_id: str
    inserted: int = 0
    updated: int = 0
    duplicate: int = 0
    rejected: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "inserted": self.inserted, "updated": self.updated, "duplicate": self.duplicate, "rejected": self.rejected}

def _value(row: dict[str, Any], field: str) -> str | None:
    normalized = {key.strip().lower(): (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
    for alias in ALIASES[field]:
        if alias in normalized and normalized[alias] not in (None, ""):
            return str(normalized[alias])
    return None

def _decimal(value: str | None, field: str, row_number: int, row: dict[str, Any]) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number

def _timestamp(row: dict[str, Any], row_number: int) -> datetime:
    direct = _value(row, "observed_at")
    if direct:
        text = direct.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("observed_at is not a valid ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    date = _value(row, "acq_date")
    time = _value(row, "acq_time")
    if not date or not time:
        raise ValueError("acq_date and acq_time are required when observed_at is absent")
    digits = time.zfill(4)
    try:
        return datetime.strptime(f"{date} {digits[:4]}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError("acq_date/acq_time is not a valid UTC acquisition timestamp") from exc

def _external_id(row: dict[str, Any], product: str) -> str:
    explicit = _value(row, "external_id")
    if explicit:
        return explicit
    parts = [product, _value(row, "acq_date") or _value(row, "observed_at") or "", _value(row, "acq_time") or "", _value(row, "latitude") or "", _value(row, "longitude") or "", row.get("satellite", ""), row.get("instrument", "")]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

def normalize_row(row: dict[str, Any], product: str, row_number: int) -> dict[str, Any]:
    if product not in PRODUCTS:
        raise ValueError(f"unsupported product: {product}")
    latitude = _decimal(_value(row, "latitude"), "latitude", row_number, row)
    longitude = _decimal(_value(row, "longitude"), "longitude", row_number, row)
    if latitude is None or longitude is None:
        raise ValueError("latitude and longitude are required")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("latitude or longitude is outside valid bounds")
    brightness = _decimal(_value(row, "brightness_temperature"), "brightness_temperature", row_number, row)
    frp = _decimal(_value(row, "frp"), "frp", row_number, row)
    published = _value(row, "published_at")
    published_at = None
    if published:
        try:
            published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("published_at is not a valid ISO-8601 timestamp") from exc
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        published_at = published_at.astimezone(timezone.utc)
    return {"external_id": _external_id(row, product), "product": product, "observed_at": _timestamp(row, row_number), "published_at": published_at, "point": WKTElement(f"POINT({longitude} {latitude})", srid=4326), "confidence_original": _value(row, "confidence"), "brightness_temperature": brightness, "frp": frp, "raw_payload": dict(row)}

def import_csv(path: str | Path, product: str, source_name: str | None = None, session: Session | None = None) -> ImportResult:
    product = product.lower()
    if product not in PRODUCTS:
        raise ValueError(f"unsupported product: {product}")
    own_session = session is None
    session = session or make_session_factory()()
    source_name = source_name or f"NASA FIRMS {product.upper()}"
    source = session.scalar(select(DataSource).where(DataSource.name == source_name))
    if source is None:
        source = DataSource(name=source_name, source_type="satellite", provider="NASA FIRMS", metadata_json={"product": product})
        session.add(source)
        session.flush()
    run = IngestionRun(source_id=source.id, product=product, source_filename=str(path), status="running")
    session.add(run)
    session.flush()
    result = ImportResult(str(run.id))
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV has no header")
            for row_number, row in enumerate(reader, start=2):
                try:
                    values = normalize_row(row, product, row_number)
                    existing = session.scalar(select(SatelliteFireObservation).where(SatelliteFireObservation.source_id == source.id, SatelliteFireObservation.external_id == values["external_id"]))
                    if existing is None:
                        session.add(SatelliteFireObservation(source_id=source.id, **values))
                        result.inserted += 1
                    else:
                        old = {"observed_at": existing.observed_at, "published_at": existing.published_at, "confidence_original": existing.confidence_original, "brightness_temperature": existing.brightness_temperature, "frp": existing.frp, "raw_payload": existing.raw_payload}
                        current = {key: values[key] for key in old}
                        if old == current:
                            result.duplicate += 1
                        else:
                            for key, value in values.items():
                                if key != "external_id":
                                    setattr(existing, key, value)
                            result.updated += 1
                except (ValueError, TypeError) as exc:
                    session.add(IngestionRejectedRecord(ingestion_run_id=run.id, row_number=row_number, reason_code="validation_error", reason_message=str(exc), raw_payload=dict(row)))
                    result.rejected += 1
        run.status = "completed"
    except Exception:
        run.status = "failed"
        session.rollback()
        raise
    run.completed_at = datetime.now(timezone.utc)
    run.inserted_count, run.updated_count, run.duplicate_count, run.rejected_count = result.inserted, result.updated, result.duplicate, result.rejected
    session.commit()
    if own_session:
        session.close()
    return result

class FirmsApiAdapter:
    """NASA FIRMS API client for live active fire data retrieval.

    API endpoint format:
    /api/area/csv/[MAP_KEY]/[SOURCE]/[AREA_COORDINATES]/[DAY_RANGE]/[DATE]

    Sources: VIIRS_SNPP_NRT, VIIRS_NOAA20_NRT, VIIRS_NOAA21_NRT, MODIS_NRT, MODIS_SP
    Area coordinates: west,south,east,north (e.g., -15,21,-1,36 for Morocco)
    Day range: 1-10 days
    Date: YYYY-MM-DD (optional, defaults to most recent)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://firms.modaps.eosdis.nasa.gov",
        timeout: float = 30.0,
        user_agent: str = "POLARIS-X/0.1",
    ):
        self.api_key = api_key or os.getenv("NASA_FIRMS_API_KEY")
        if not self.api_key:
            raise ValueError("NASA_FIRMS_API_KEY is required for live API access")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch(
        self,
        source: str,
        west: float,
        south: float,
        east: float,
        north: float,
        day_range: int = 1,
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch active fire data from FIRMS API.

        Args:
            source: Data source (e.g., 'VIIRS_SNPP_NRT', 'MODIS_NRT')
            west: Western longitude boundary (-180 to 180)
            south: Southern latitude boundary (-90 to 90)
            east: Eastern longitude boundary (-180 to 180)
            north: Northern latitude boundary (-90 to 90)
            day_range: Number of days to retrieve (1-10)
            date: Optional start date YYYY-MM-DD (defaults to most recent)

        Returns:
            List of fire detection dictionaries parsed from CSV response.

        Raises:
            ValueError: Invalid parameters
            RuntimeError: HTTP errors, timeouts, or API errors
        """
        import csv as csv_module
        import urllib.error
        import urllib.parse
        import urllib.request
        from io import StringIO

        # Validate parameters
        if not (-180 <= west <= 180) or not (-180 <= east <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        if not (-90 <= south <= 90) or not (-90 <= north <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        if not (1 <= day_range <= 10):
            raise ValueError("Day range must be between 1 and 10")

        # Build URL
        area_coords = f"{west},{south},{east},{north}"
        if date:
            url = f"{self.base_url}/api/area/csv/{self.api_key}/{source}/{area_coords}/{day_range}/{date}"
        else:
            url = f"{self.base_url}/api/area/csv/{self.api_key}/{source}/{area_coords}/{day_range}"

        # Execute request
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            if exc.code == 400:
                raise ValueError(f"FIRMS API invalid request: {error_body}") from exc
            elif exc.code == 401 or exc.code == 403:
                raise ValueError("FIRMS API authentication failed: check NASA_FIRMS_API_KEY") from exc
            elif exc.code == 429:
                raise RuntimeError("FIRMS API rate limit exceeded: wait 10 minutes") from exc
            else:
                raise RuntimeError(f"FIRMS API HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"FIRMS API network error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"FIRMS API timeout after {self.timeout}s") from exc

        # Handle empty or error responses
        if not body.strip():
            return []

        # Check for API error messages
        if body.startswith("ERROR") or "error" in body.lower()[:100]:
            raise RuntimeError(f"FIRMS API error: {body[:200]}")

        # Parse CSV response
        reader = csv_module.DictReader(StringIO(body))
        if not reader.fieldnames:
            raise RuntimeError("FIRMS API returned invalid CSV (no header)")

        return list(reader)

def import_api(
    source: str,
    west: float,
    south: float,
    east: float,
    north: float,
    day_range: int = 1,
    date: str | None = None,
    source_name: str | None = None,
    session: Session | None = None,
) -> ImportResult:
    """Fetch and import fire data from FIRMS API.

    Args:
        source: FIRMS data source (e.g., 'VIIRS_SNPP_NRT', 'MODIS_NRT')
        west: Western longitude boundary
        south: Southern latitude boundary
        east: Eastern longitude boundary
        north: Northern latitude boundary
        day_range: Number of days to retrieve (1-10)
        date: Optional start date YYYY-MM-DD
        source_name: Optional data source name override
        session: Optional database session

    Returns:
        ImportResult with counts and run ID.
    """
    # Determine product name from source
    if "VIIRS" in source.upper():
        product = "viirs"
    elif "MODIS" in source.upper():
        product = "modis"
    else:
        raise ValueError(f"Cannot determine product from source: {source}")

    # Fetch data from API
    client = FirmsApiAdapter()
    rows = client.fetch(
        source=source,
        west=west,
        south=south,
        east=east,
        north=north,
        day_range=day_range,
        date=date,
    )

    # Prepare session
    own_session = session is None
    session = session or make_session_factory()()

    source_name = source_name or f"NASA FIRMS {source}"
    data_source = session.scalar(select(DataSource).where(DataSource.name == source_name))
    if data_source is None:
        data_source = DataSource(
            name=source_name,
            source_type="satellite",
            provider="NASA FIRMS",
            metadata_json={"product": product, "source": source},
        )
        session.add(data_source)
        session.flush()

    # Create ingestion run
    run = IngestionRun(
        source_id=data_source.id,
        product=product,
        source_filename=f"API:{source}:{west},{south},{east},{north}",
        status="running",
    )
    session.add(run)
    session.flush()

    result = ImportResult(str(run.id))

    try:
        # Process each row from API
        for row_number, row in enumerate(rows, start=2):  # Start at 2 to match CSV convention
            try:
                values = normalize_row(row, product, row_number)
                existing = session.scalar(
                    select(SatelliteFireObservation).where(
                        SatelliteFireObservation.source_id == data_source.id,
                        SatelliteFireObservation.external_id == values["external_id"],
                    )
                )

                if existing is None:
                    session.add(SatelliteFireObservation(source_id=data_source.id, **values))
                    result.inserted += 1
                else:
                    old = {
                        "observed_at": existing.observed_at,
                        "published_at": existing.published_at,
                        "confidence_original": existing.confidence_original,
                        "brightness_temperature": existing.brightness_temperature,
                        "frp": existing.frp,
                        "raw_payload": existing.raw_payload,
                    }
                    current = {key: values[key] for key in old}
                    if old == current:
                        result.duplicate += 1
                    else:
                        for key, value in values.items():
                            if key != "external_id":
                                setattr(existing, key, value)
                        result.updated += 1
            except (ValueError, TypeError) as exc:
                session.add(
                    IngestionRejectedRecord(
                        ingestion_run_id=run.id,
                        row_number=row_number,
                        reason_code="validation_error",
                        reason_message=str(exc),
                        raw_payload=dict(row),
                    )
                )
                result.rejected += 1

        run.status = "completed"
    except Exception:
        run.status = "failed"
        session.rollback()
        raise

    run.completed_at = datetime.now(timezone.utc)
    run.inserted_count = result.inserted
    run.updated_count = result.updated
    run.duplicate_count = result.duplicate
    run.rejected_count = result.rejected

    if own_session:
        session.commit()
        session.close()
    else:
        session.flush()  # Flush but don't commit if session was provided

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Import NASA FIRMS fire data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # CSV import command
    csv_parser = subparsers.add_parser("csv", help="Import from offline CSV file")
    csv_parser.add_argument("--file", required=True, type=Path)
    csv_parser.add_argument("--product", required=True, choices=sorted(PRODUCTS))
    csv_parser.add_argument("--source-name")

    # API import command
    api_parser = subparsers.add_parser("api", help="Import from NASA FIRMS API")
    api_parser.add_argument(
        "--source",
        required=True,
        choices=["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT", "MODIS_SP"],
        help="FIRMS data source",
    )
    api_parser.add_argument("--west", required=True, type=float, help="Western longitude (-180 to 180)")
    api_parser.add_argument("--south", required=True, type=float, help="Southern latitude (-90 to 90)")
    api_parser.add_argument("--east", required=True, type=float, help="Eastern longitude (-180 to 180)")
    api_parser.add_argument("--north", required=True, type=float, help="Northern latitude (-90 to 90)")
    api_parser.add_argument("--day-range", type=int, default=1, help="Number of days to retrieve (1-10, default: 1)")
    api_parser.add_argument("--date", type=str, help="Optional start date YYYY-MM-DD (default: most recent)")
    api_parser.add_argument("--source-name", help="Optional data source name override")

    args = parser.parse_args()

    if args.command == "csv":
        result = import_csv(args.file, args.product, args.source_name)
    elif args.command == "api":
        result = import_api(
            source=args.source,
            west=args.west,
            south=args.south,
            east=args.east,
            north=args.north,
            day_range=args.day_range,
            date=args.date,
            source_name=args.source_name,
        )
    else:
        parser.error(f"Unknown command: {args.command}")

    print(result.as_dict())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
