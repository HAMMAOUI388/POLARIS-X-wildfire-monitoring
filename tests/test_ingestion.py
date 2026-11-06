import csv
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from polaris_x.db.models import DataSource, IngestionRejectedRecord, IngestionRun, SatelliteFireObservation
from polaris_x.db.session import make_session_factory
from polaris_x.ingestion.firms import import_csv, normalize_row

def write_csv(path: Path, rows: list[dict]):
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def test_normalize_realistic_viirs_and_modis_headers():
    viirs = normalize_row({
        "latitude": "33.9", "longitude": "-6.8", "scan": "0.4", "track": "0.3",
        "acq_date": "2024-01-02", "acq_time": "0345", "satellite": "N21",
        "instrument": "VIIRS", "confidence": "n", "version": "2.0NRT",
        "bright_ti4": "310.2", "bright_ti5": "295.1", "frp": "12.4", "daynight": "D",
    }, "viirs", 2)
    assert viirs["observed_at"].isoformat() == "2024-01-02T03:45:00+00:00"
    assert viirs["confidence_original"] == "n"
    assert viirs["raw_payload"]["satellite"] == "N21"
    assert viirs["raw_payload"]["version"] == "2.0NRT"

    modis = normalize_row({
        "latitude": "33.9", "longitude": "-6.8", "scan": "1.0", "track": "1.0",
        "acq_date": "2024-01-02", "acq_time": "0345", "satellite": "Aqua",
        "instrument": "MODIS", "confidence": "66", "version": "6.1NRT",
        "brightness": "315.4", "bright_t31": "300.0", "frp": "20.0", "daynight": "N",
    }, "modis", 2)
    assert str(modis["brightness_temperature"]) == "315.4"
    assert modis["confidence_original"] == "66"
    assert modis["raw_payload"]["satellite"] == "Aqua"

def test_corrupted_spreadsheet_values_are_rejected():
    with pytest.raises(ValueError, match="latitude must be numeric"):
        normalize_row({"latitude": "-2,34738", "longitude": "-6.8", "acq_date": "2024-01-02", "acq_time": "0345"}, "viirs", 2)
    with pytest.raises(ValueError, match="frp must be numeric"):
        normalize_row({"latitude": "33.9", "longitude": "-6.8", "acq_date": "2024-01-02", "acq_time": "0345", "frp": "janv.-49"}, "viirs", 2)

def test_invalid_rows_are_rejected_and_reimport_is_idempotent(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    test_id = uuid4().hex
    external_id = f"synthetic-{test_id}"
    source_name = f"Phase 3 test {test_id}"
    path = tmp_path / "synthetic_viirs.csv"
    write_csv(path, [
        {"external_id": external_id, "latitude": "33.9", "longitude": "-6.8", "acq_date": "2024-01-02", "acq_time": "0345", "confidence": "n", "frp": "12.4"},
        {"external_id": f"bad-{test_id}", "latitude": "200", "longitude": "-6.8", "acq_date": "2024-01-02", "acq_time": "0345", "confidence": "l", "frp": "1"},
    ])
    factory = make_session_factory(url)
    try:
        result = import_csv(path, "viirs", source_name=source_name, session=factory())
        assert result.inserted == 1
        assert result.rejected == 1
        second = import_csv(path, "viirs", source_name=source_name, session=factory())
        assert second.duplicate == 1
        with factory() as session:
            observation = session.scalar(select(SatelliteFireObservation).where(SatelliteFireObservation.external_id == external_id))
            assert observation is not None
            run = session.scalar(select(IngestionRun).where(IngestionRun.id == second.run_id))
            assert run.rejected_count == 1
            assert session.scalar(select(IngestionRejectedRecord).where(IngestionRejectedRecord.ingestion_run_id == run.id))
    finally:
        with factory.kw["bind"].begin() as connection:
            session = factory(bind=connection)
            source = session.scalar(select(DataSource).where(DataSource.name == source_name))
            if source is not None:
                run_ids = select(IngestionRun.id).where(IngestionRun.source_id == source.id)
                session.execute(delete(IngestionRejectedRecord).where(IngestionRejectedRecord.ingestion_run_id.in_(run_ids)))
                session.execute(delete(IngestionRun).where(IngestionRun.source_id == source.id))
                session.execute(delete(SatelliteFireObservation).where(SatelliteFireObservation.source_id == source.id))
                session.execute(delete(DataSource).where(DataSource.id == source.id))
        factory.kw["bind"].dispose()
