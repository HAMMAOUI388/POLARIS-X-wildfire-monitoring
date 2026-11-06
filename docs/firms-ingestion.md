# NASA FIRMS ingestion

Phase 3 provides offline CSV ingestion for the `viirs` and `modis` product names. No real FIRMS CSV sample is present in this repository; tests use synthetic fixtures and the mappings are intentionally limited to fields represented by `SatelliteFireObservation`.

## Supported fields

Required fields are latitude, longitude, and either an ISO-8601 `observed_at` value or `acq_date` plus `acq_time`. Optional aliases include `external_id`, `confidence`, `frp`, `bright_ti4`/`bright_t31`/`bright_ti5`, and `published_at`. Product-specific source fields not normalized into columns are preserved in `raw_payload`. Confidence is retained in its original categorical or numeric representation.

Rows with invalid required values, timestamps, coordinates, or numeric fields are persisted as rejected records with the original row and reason. Imports are idempotent by source and external identifier: unchanged rows are duplicates and changed rows are updates.

## CLI

```bash
python3 -m polaris_x.ingestion.firms --file path/to/firms.csv --product viirs
```

The command requires the normal `DATABASE_URL` configuration. It prints counts for inserted, updated, duplicate, and rejected rows. The optional future API adapter reads `NASA_FIRMS_API_KEY` only when instantiated; network retrieval is not implemented in this phase and keys are never included in output or raw CSV payloads.
