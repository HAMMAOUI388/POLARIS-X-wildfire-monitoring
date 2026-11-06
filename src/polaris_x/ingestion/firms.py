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
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("NASA_FIRMS_API_KEY")
    def fetch(self, *args: Any, **kwargs: Any):
        raise NotImplementedError("FIRMS API retrieval is not implemented in Phase 3; use offline CSV ingestion")

def main() -> int:
    parser = argparse.ArgumentParser(description="Import an offline NASA FIRMS CSV")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--product", required=True, choices=sorted(PRODUCTS))
    parser.add_argument("--source-name")
    args = parser.parse_args()
    result = import_csv(args.file, args.product, args.source_name)
    print(result.as_dict())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
