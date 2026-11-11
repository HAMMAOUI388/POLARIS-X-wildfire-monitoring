# Weather Integration Documentation

**Phase 6: Open-Meteo Weather Data Integration**

## Overview

This document describes the weather data integration implemented in Phase 6, including licensing requirements, data provenance semantics, and operational constraints.

## Data Sources

### Operational Forecast Data (NWP)

- **Endpoint**: `/v1/forecast` on `api.open-meteo.com`
- **Models**: Best-match ensemble (GFS, ECMWF IFS, ICON, AROME, etc.)
- **Typical Resolution**: ~11 km (varies by model)
- **Update Frequency**: Hourly
- **Historical Coverage**: Up to 92 days back via `past_days` parameter
- **Forecast Horizon**: Up to 16 days ahead

**Storage**: `weather_forecasts` table with:
- `issued_at`: Retrieval time (conservative bound; actual model run time not available from seamless API)
- `valid_from` / `valid_to`: Time window the forecast describes

### Historical Reanalysis (ERA5/ERA5-Land)

- **Endpoint**: `/v1/archive` on `archive-api.open-meteo.com`
- **Model**: ERA5-Land (primary), ERA5 (fallback)
- **Resolution**: ~9 km (ERA5-Land), ~25 km (ERA5)
- **Coverage**: 1950–present (ERA5-Land), 1940–present (ERA5)
- **Update Lag**: ~5 days

**Storage**: `weather_observations` table with:
- `source_id` → `DataSource` with `source_type='reanalysis'`
- `observed_at`: ERA5 reference time (centre of analysis window)

**CRITICAL**: ERA5 and ERA5-Land are **gridded reanalysis products**, NOT local weather-station observations. Values are interpolated from model grids. This distinction must be preserved in all provenance records and user-facing documentation.

## Reanalysis vs. Operational Weather

**CRITICAL DISTINCTION**: ERA5/ERA5-Land reanalysis data is explicitly classified with `source_type='reanalysis'` and stored in `weather_observations`. This data:

- Is NOT operational weather suitable for near-real-time monitoring
- Has a 5-day lag from the Open-Meteo archive endpoint
- Should use longer freshness thresholds (default: 7 days vs. 3 hours for forecasts)
- Must remain available for retrospective/historical analysis

**Feature Builder Requirement**: Before weather data can be supplied to the Phase 5 assessment engine, an explicit source-type-aware feature builder must be implemented that:

1. Reads weather records from the database
2. Adds `max_age_seconds` to provenance based on `source_type`:
   - `nwp_forecast` → `WEATHER_MAX_AGE_FORECAST_SECONDS` (3 hours)
   - `reanalysis` → `WEATHER_MAX_AGE_ERA5_SECONDS` (7 days)
3. Prevents reanalysis from being used as fresh operational weather observations
4. Ensures the assessment engine receives correctly classified weather features

**Current State**: Phase 6 provides the ingestion pipeline only. The feature builder is NOT implemented. No weather data is currently fed into the assessment engine.

## Duplicate Ingestion Behavior

**Current Implementation**: The weather ingestion pipeline uses an **append-only** strategy:

- Every ingestion run inserts new records
- No duplicate checking is performed
- Repeated ingestion of the same time period produces multiple logical copies
- Historical retrieval snapshots are preserved

**Rationale**: Time-series weather data changes with each model run. Preserving multiple retrievals allows tracking forecast evolution and model performance.

**Future Considerations**: If idempotent ingestion is needed (e.g., to prevent unbounded growth from repeated scheduled runs), a future design could:

- Add unique constraints on `(source_id, location_id, valid_from, valid_to)`
- Implement upsert logic similar to FIRMS ingestion
- Add a `retrieved_at` column to track snapshot times

**Recommendation**: Document this as a known limitation. Do not implement complex deduplication without explicit requirements and approval.

## Variables Ingested

The following wildfire-relevant variables are fetched and stored:

| Variable | API Name | Unit | Temporality | Aggregation |
|----------|----------|------|-------------|-------------|
| Temperature 2m | `temperature_2m` | °C | Instantaneous | N/A |
| Relative Humidity 2m | `relative_humidity_2m` | % | Instantaneous | N/A |
| Vapour Pressure Deficit | `vapour_pressure_deficit` | kPa | Instantaneous | N/A |
| Wind Speed 10m | `wind_speed_10m` | km/h | Instantaneous | N/A |
| Wind Direction 10m | `wind_direction_10m` | ° | Instantaneous | N/A |
| Wind Gusts 10m | `wind_gusts_10m` | km/h | Preceding hour | Maximum |
| Precipitation | `precipitation` | mm | Preceding hour | Sum |
| Soil Moisture 0–1 cm | `soil_moisture_0_to_1cm` | m³/m³ | Instantaneous | N/A |
| Soil Moisture 1–3 cm | `soil_moisture_1_to_3cm` | m³/m³ | Instantaneous | N/A |
| ET₀ (FAO) | `et0_fao_evapotranspiration` | mm | Preceding hour | Sum |
| Shortwave Radiation | `shortwave_radiation` | W/m² | Preceding hour | Mean |

### Preceding-Hour Variable Semantics

Open-Meteo labels precipitation, radiation, ET₀, and wind gusts with the **end** of their temporal window. The ingestion pipeline adjusts:

- `valid_from = time - 1 hour`
- `valid_to = time`

**Individual Aggregation Types**:
- **Precipitation**: Sum of precipitation during the preceding hour
- **ET₀ (FAO Evapotranspiration)**: Sum of evapotranspiration during the preceding hour
- **Wind Gusts**: Maximum wind gust speed recorded during the preceding hour
- **Shortwave Radiation**: Mean shortwave radiation over the preceding hour

This ensures the temporal window is correctly represented in `weather_forecasts`. Instantaneous variables (temperature, humidity, wind speed/direction, soil moisture) have `valid_from = valid_to = valid_at`.

## Licensing and Compliance

### Free Tier (Non-Commercial)

- **License**: CC-BY 4.0
- **Restrictions**: Non-commercial use only
- **Rate Limits**: 600/min, 5,000/hr, 10,000/day, 300,000/month
- **API Key**: Not required
- **Attribution Required**: Yes (see below)

**Prohibited Uses**:
- Commercial products or services
- Subscription-based offerings
- Advertising-supported applications
- Promotional use
- Undisclosed research at commercial entities

### Commercial Tier

- **Requirement**: API key and `customer-` server prefix
- **Configuration**: Set `OPEN_METEO_API_KEY` and `OPEN_METEO_COMMERCIAL=true`
- **Rate Limits**: Negotiated per plan

**Before deploying POLARIS X commercially**, you MUST:
1. Obtain a commercial Open-Meteo plan
2. Configure `OPEN_METEO_API_KEY` in `.env`
3. Set `OPEN_METEO_COMMERCIAL=true`
4. Update `OPEN_METEO_FORECAST_URL` and `OPEN_METEO_ARCHIVE_URL` to use the `customer-` prefix if provided

### Attribution Requirements

All products using Open-Meteo data must attribute:

**For forecast data**:
> Weather data by Open-Meteo.com (CC-BY 4.0, https://doi.org/10.5281/zenodo.7970649)

**For ERA5/ERA5-Land data** (add upstream attribution):
> Weather data by Open-Meteo.com (CC-BY 4.0, https://doi.org/10.5281/zenodo.7970649)
> ERA5-Land data generated using Copernicus Climate Change Service information

Attribution text is configured via `WEATHER_ATTRIBUTION` in `.env` and stored in `DataSource.metadata_json`.

## Configuration

All weather configuration is in `config.py` and `.env.example`:

```bash
# Weather data ingestion (Open-Meteo)
OPEN_METEO_FORECAST_URL=https://api.open-meteo.com/v1/forecast
OPEN_METEO_ARCHIVE_URL=https://archive-api.open-meteo.com/v1/archive
OPEN_METEO_API_KEY=
OPEN_METEO_COMMERCIAL=false
WEATHER_ATTRIBUTION=Weather data by Open-Meteo.com (CC-BY 4.0, https://doi.org/10.5281/zenodo.7970649)
WEATHER_MAX_AGE_FORECAST_SECONDS=10800
WEATHER_MAX_AGE_ERA5_SECONDS=604800
```

### Default Freshness Policies

- **Forecast data**: 10,800 seconds (3 hours)
- **ERA5 data**: 604,800 seconds (7 days)

These are conservative defaults. Adjust based on your assessment model's requirements.

## Usage

### CLI Ingestion

**Forecast mode** (operational NWP):
```bash
python -m polaris_x.ingestion.weather --mode forecast --past-days 0 --forecast-days 7
```

**Archive mode** (ERA5 reanalysis):
```bash
python -m polaris_x.ingestion.weather --mode archive --start-date 2024-10-01 --end-date 2024-10-31
```

**Single location**:
```bash
python -m polaris_x.ingestion.weather --mode forecast --location-id <UUID>
```

### Programmatic Usage

```python
from polaris_x.integrations.weather import OpenMeteoClient
from polaris_x.ingestion.weather import ingest_forecast_for_location
from polaris_x.db.session import make_session_factory
from polaris_x.config import Config

client = OpenMeteoClient(
    forecast_url=Config.OPEN_METEO_FORECAST_URL,
    archive_url=Config.OPEN_METEO_ARCHIVE_URL,
    api_key=Config.OPEN_METEO_API_KEY or None,
)

SessionFactory = make_session_factory()
with SessionFactory.begin() as session:
    location = session.get(MonitoringLocation, location_id)
    result = ingest_forecast_for_location(session, client, location)
    print(result.as_dict())
```

## Provenance Records

Each weather record stores provenance metadata in `raw_payload`:

```json
{
  "provenance": {
    "source": "open-meteo",
    "source_type": "nwp_forecast",  // or "reanalysis"
    "model": "best_match",           // or "ERA5-Land"
    "resolution_km": 11.0,
    "retrieval_time": "2024-11-09T12:00:00+00:00",
    "valid_at": "2024-11-09T14:00:00+00:00",
    "valid_from": "2024-11-09T13:00:00+00:00",  // for accumulation vars
    "valid_to": "2024-11-09T14:00:00+00:00"
  },
  "metadata": {
    "latitude": 33.97,
    "longitude": -6.84,
    "elevation": 450.0,
    "timezone": "UTC"
  }
}
```

The assessment engine reads `valid_at` (or `observed_at` for observations) and `max_age_seconds` from the feature builder to validate freshness.

## Schema

No migration was required; the existing `weather_observations` and `weather_forecasts` tables already support the required semantics:

- `weather_forecasts`:
  - `issued_at`: When the forecast was issued (recorded as retrieval time in seamless API)
  - `valid_from` / `valid_to`: Time window the forecast describes
  - `variables`: JSONB with weather variable key-value pairs
  - `raw_payload`: JSONB with provenance and metadata

- `weather_observations`:
  - `observed_at`: Reference time for the observation (ERA5 analysis time)
  - `variables`: JSONB with weather variable key-value pairs
  - `raw_payload`: JSONB with provenance and metadata

Both link to `data_sources` with:
- `source_type`: `"nwp_forecast"` or `"reanalysis"`
- `provider`: `"Open-Meteo"`
- `metadata_json`: Model name, resolution, attribution text

## Testing

All tests use static JSON fixtures; no live network calls are made during CI.

**Unit tests**:
- `test_open_meteo_client_parses_forecast_response`: Verifies accumulation variable window adjustment
- `test_open_meteo_client_parses_archive_response`: Verifies ERA5 reanalysis labeling
- `test_open_meteo_client_validates_coordinates`: Validates input bounds
- `test_weather_provenance_compatible_with_assessment_engine`: Confirms provenance contract

**Integration tests** (require `TEST_DATABASE_URL`):
- `test_weather_ingestion_forecast_persists_to_database`: End-to-end forecast ingestion
- `test_weather_ingestion_archive_persists_to_database`: End-to-end archive ingestion with `source_type=reanalysis`

Run tests:
```bash
pytest tests/test_weather_integration.py -v
```

## Known Limitations

1. **Model run/issue times not available**: The seamless forecast API stitches multiple model runs without exposing initialisation times. `issued_at` is set to `NULL` for seamless API forecasts. `retrieval_time` is preserved in `raw_payload`.

2. **ERA5 5-day lag**: ERA5/ERA5-Land data is updated daily with a 5-day delay. Do not use for near-real-time operational monitoring.

3. **Soil moisture layer differences**: Forecast API and ERA5 archive use different soil depth definitions. Only common variables are ingested; soil moisture layers are omitted from archive calls.

4. **No single-run API support**: To obtain exact model run times, integrate the Single Runs API (not implemented in Phase 6).

5. **No duplicate prevention**: Repeated ingestion produces multiple logical copies. This is acceptable for tracking forecast evolution but may require future deduplication logic if scheduled runs cause unbounded growth.

6. **No feature builder**: Weather data is not yet connected to the Phase 5 assessment engine. A source-type-aware feature builder is required before operational use.

## Compliance Checklist

Before commercial deployment:

- [ ] Verify deployment qualifies as non-commercial (e.g., public research at public institution) OR obtain commercial Open-Meteo plan
- [ ] Configure `OPEN_METEO_API_KEY` if commercial
- [ ] Set `OPEN_METEO_COMMERCIAL=true` if commercial
- [ ] Verify attribution is visible in all user-facing products
- [ ] Update ERA5 attribution if using archive endpoint
- [ ] Document any restrictions on derived products (CC-BY 4.0 requires share-alike)

## References

- Open-Meteo API Documentation: https://open-meteo.com/en/docs
- Open-Meteo Zenodo DOI: https://doi.org/10.5281/zenodo.7970649
- CC-BY 4.0 License: https://creativecommons.org/licenses/by/4.0/
- ERA5 Documentation: https://confluence.ecmwf.int/display/CKB/ERA5
- Copernicus Climate Data Store: https://cds.climate.copernicus.eu/

---

**Document Version**: 1.0
**Last Updated**: 2026-11-09
**Phase**: 6 (Weather Integration)
