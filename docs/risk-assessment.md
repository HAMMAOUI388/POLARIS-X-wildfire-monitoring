# Risk assessment foundation

Phase 5 currently provides an assessment foundation, not a scientific risk model. The service returns `insufficient_data` with a null score when required environmental inputs are unavailable or lack provenance. It does not emit fire-occurrence probabilities, classify FIRMS thermal anomalies as confirmed fires, or predict fire spread.

## Available data

FIRMS VIIRS/MODIS observations and Phase 4 fire events are available for observation and monitoring. Weather and IoT tables exist, but no validated ingestion pipeline is available. Terrain, elevation, vegetation, fuel, independent fire labels, and historical validation data are unavailable. Seed weather and risk rows are synthetic development fixtures and must not be used as scientific inputs.

Each persisted assessment records its model name/version, assessment time, feature snapshot, evidence, data-quality state, uncertainty state, and input provenance. Assessments are append-only historical results; changing a model version does not overwrite earlier rows.

No thresholds, weights, calibration, or probability interpretation has been introduced. A future environmental hazard index requires approved input sources, units, freshness rules, missing-data policy, and justified methodology.
