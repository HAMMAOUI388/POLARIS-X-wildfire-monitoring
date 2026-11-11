# POLARIS X — Live Data Ingestion

Phase 7 provides live data ingestion from external APIs:

1. **NASA FIRMS** — Active fire observations from MODIS and VIIRS satellites
2. **Open-Meteo Forecast API** — Operational NWP weather forecasts
3. **Open-Meteo Archive API** — Historical ERA5/ERA5-Land reanalysis

## Prerequisites

### Required API Credentials

#### NASA FIRMS MAP_KEY

Get a free MAP_KEY at: https://firms.modaps.eosdis.nasa.gov/api/map_key

- Free for research, education, and operational use
- Rate limit: 5000 transactions per 10-minute window
- Resets automatically after 10 minutes

Set in environment:
```bash
export NASA_FIRMS_API_KEY=your_map_key_here
```

#### Open-Meteo API Key (Optional)

**Free tier** (non-commercial use only):
- No API key required
- Rate limits apply
- CC-BY 4.0 attribution mandatory

**Commercial tier**:
- Requires API key and customer-server prefix
- Review licensing at: https://open-meteo.com/en/pricing
- Set `OPEN_METEO_COMMERCIAL=true`

Set in environment:
```bash
export OPEN_METEO_API_KEY=your_api_key_here  # Commercial tier only
export OPEN_METEO_COMMERCIAL=true            # If using commercial tier
```

## Configuration

Update `.env` or export environment variables:

```bash
# NASA FIRMS
NASA_FIRMS_API_KEY=your_map_key_here
NASA_FIRMS_BASE_URL=https://firms.modaps.eosdis.nasa.gov

# Open-Meteo
OPEN_METEO_FORECAST_URL=https://api.open-meteo.com/v1/forecast
OPEN_METEO_ARCHIVE_URL=https://archive-api.open-meteo.com/v1/archive
OPEN_METEO_API_KEY=
OPEN_METEO_COMMERCIAL=false
WEATHER_ATTRIBUTION=Weather data by Open-Meteo.com (CC-BY 4.0, https://doi.org/10.5281/zenodo.7970649)
```

## Usage

### Unified CLI

```bash
# NASA FIRMS - Morocco bounding box (most recent 24 hours)
python3 -m polaris_x.ingestion firms-api \
  --source VIIRS_SNPP_NRT \
  --west -15 --south 21 --east -1 --north 36 \
  --day-range 1

# FIRMS - Specific date range
python3 -m polaris_x.ingestion firms-api \
  --source MODIS_NRT \
  --west -15 --south 21 --east -1 --north 36 \
  --day-range 5 \
  --date 2024-11-01

# Weather forecasts (all monitoring locations)
python3 -m polaris_x.ingestion weather-forecast

# Weather forecasts with past days
python3 -m polaris_x.ingestion weather-forecast \
  --past-days 1 \
  --forecast-days 7

# Historical weather archive (ERA5/ERA5-Land)
python3 -m polaris_x.ingestion weather-archive \
  --start-date 2024-10-01 \
  --end-date 2024-10-31
```

### Individual Module CLIs

```bash
# FIRMS CSV import (Phase 3 compatibility)
python3 -m polaris_x.ingestion.firms csv \
  --file path/to/firms.csv \
  --product viirs

# FIRMS API import
python3 -m polaris_x.ingestion.firms api \
  --source VIIRS_SNPP_NRT \
  --west -15 --south 21 --east -1 --north 36 \
  --day-range 1

# Weather ingestion (Phase 6 compatibility)
python3 -m polaris_x.ingestion.weather \
  --mode forecast \
  --past-days 0 \
  --forecast-days 7

python3 -m polaris_x.ingestion.weather \
  --mode archive \
  --start-date 2024-10-01 \
  --end-date 2024-10-31
```

## NASA FIRMS API

### Supported Data Sources

- **VIIRS_SNPP_NRT** — VIIRS Suomi-NPP Near Real-Time (375m resolution)
- **VIIRS_NOAA20_NRT** — VIIRS NOAA-20 Near Real-Time (375m resolution)
- **VIIRS_NOAA21_NRT** — VIIRS NOAA-21 Near Real-Time (375m resolution)
- **MODIS_NRT** — MODIS Near Real-Time (1km resolution, Aqua & Terra combined)
- **MODIS_SP** — MODIS Standard Processing (1km resolution)

NRT data is available within 3 hours of satellite overpass.

### Geographic Bounds

Morocco bounding box (recommended):
- West: -15° (Atlantic coast)
- South: 21° (southern border)
- East: -1° (eastern border)
- North: 36° (Mediterranean coast)

**Important**: FIRMS expects `west,south,east,north` format (longitude, latitude).

### Date Range Limits

- **day_range**: 1-10 days per request
- **date**: Optional start date (YYYY-MM-DD)
- If `date` is omitted, returns most recent data

Historical data availability varies by source (typically 7-10 days for NRT).

### Rate Limits

- 5000 API transactions per 10-minute window
- After exceeding limit, wait 10 minutes for reset
- Check status: https://firms.modaps.eosdis.nasa.gov/api/map_key_status/{MAP_KEY}

### Error Handling

The client handles:
- Invalid credentials (401/403)
- Rate limiting (429)
- Network timeouts (30s default)
- Malformed responses
- Empty result sets

Rejected records are persisted with validation errors in `ingestion_rejected_records`.

### Data Provenance

All FIRMS observations preserve:
- Original source product (VIIRS/MODIS)
- Satellite and instrument metadata
- Acquisition timestamp (UTC)
- Original confidence representation
- Complete raw API response in `raw_payload`

**Important**: FIRMS detects thermal anomalies, not confirmed fires. Confidence values indicate detection quality, not fire confirmation.

## Open-Meteo Weather Data

### Operational Forecasts

- **Source**: Seamless global weather forecast API
- **Models**: Multiple NWP models (GFS, ICON, MeteoFrance, etc.)
- **Update frequency**: Every 1-6 hours
- **Forecast horizon**: Up to 16 days
- **Variables**: Temperature, humidity, wind, precipitation, soil moisture, radiation, ET₀

### Historical Reanalysis

- **Source**: ERA5 and ERA5-Land
- **Type**: Gridded model reanalysis (NOT direct station observations)
- **Resolution**: ~25 km (ERA5), ~9 km (ERA5-Land)
- **Coverage**: 1940-present (5-day delay)
- **Variables**: Same as operational forecasts

### Temporal Semantics (Preserved from Phase 6)

**Forecast `issued_at`**:
- Set to `NULL` when actual forecast run time is unavailable
- The seamless forecast API does NOT expose model initialization times
- `retrieval_time` is stored separately in `raw_payload`

**Variable temporal aggregation**:
- Instantaneous: `valid_from = valid_to = valid_at`
- Preceding hour (precipitation, radiation, gusts): `valid_from = valid_at - 1h, valid_to = valid_at`

**Reanalysis classification**:
- Always stored as `source_type='reanalysis'`
- Never confused with operational forecasts or station observations
- Provenance clearly documents gridded model nature

### Attribution Requirements

**Open-Meteo Free Tier** (non-commercial):
- CC-BY 4.0 license
- Attribution: "Weather data by Open-Meteo.com (CC-BY 4.0)"
- Citation: https://doi.org/10.5281/zenodo.7970649

**Commercial use**:
- Requires commercial license and API key
- Review: https://open-meteo.com/en/pricing
- Update `OPEN_METEO_COMMERCIAL=true`

## Operational Considerations

### Scheduling

Phase 7 provides manual CLI execution. For production automation:

```bash
# Example cron schedule (every 4 hours)
0 */4 * * * cd /path/to/project && python3 -m polaris_x.ingestion firms-api --source VIIRS_SNPP_NRT --west -15 --south 21 --east -1 --north 36

# Weather forecasts (twice daily)
0 6,18 * * * cd /path/to/project && python3 -m polaris_x.ingestion weather-forecast
```

Alternative: systemd timers, Airflow, or other orchestration tools.

### Monitoring Locations

Weather ingestion processes **all** monitoring locations in the database. Ensure:
1. Locations have valid PostGIS `POINT` geometries
2. Coordinates are within global bounds (-90 to 90 lat, -180 to 180 lon)
3. Owner relationships are configured

Create locations via API or seed script before weather ingestion.

### Error Handling

All ingestion operations:
- Log errors to `ingestion_runs` table
- Record rejection details in `ingestion_rejected_records`
- Return non-zero exit codes on failure
- Preserve partial results on network errors

Review ingestion runs:
```sql
SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT 10;
SELECT * FROM ingestion_rejected_records WHERE ingestion_run_id = 'run-uuid';
```

### Data Quality

**FIRMS**:
- Thermal anomalies ≠ confirmed fires
- Confidence thresholds vary by instrument
- Cloud cover affects detection
- Review confidence distributions before classification

**Open-Meteo**:
- Forecast accuracy decreases with lead time
- Reanalysis is interpolated from coarse grids
- Local effects (topography, urban heat) not captured
- Soil moisture limited to shallow depths (0-3 cm)

### Resource Usage

**Network**:
- FIRMS: ~10-100 KB per request (depends on fire activity)
- Open-Meteo: ~5-20 KB per location per request

**Database**:
- FIRMS: ~500 bytes per observation
- Weather: ~1-2 KB per forecast/observation
- Indexes on `observed_at`, `valid_from`, `location_id`

**Rate Limits**:
- FIRMS: 5000 transactions / 10 minutes
- Open-Meteo free tier: ~10,000 requests / day (informal)

## Security

- **Never commit API keys** to version control
- Use environment variables or secrets management
- Rotate keys periodically
- Monitor API usage for anomalies
- Validate all external data before persistence

## Troubleshooting

### FIRMS API Errors

**"authentication failed"**:
- Check `NASA_FIRMS_API_KEY` is set correctly
- Verify MAP_KEY at: https://firms.modaps.eosdis.nasa.gov/api/map_key_status/{KEY}
- Request new key if expired

**"rate limit exceeded"**:
- Wait 10 minutes for reset
- Reduce polling frequency
- Consider multiple keys for different services (if permitted by NASA)

**Empty results**:
- Verify date range (NRT data typically 7-10 days)
- Check geographic bounds are correct
- Confirm recent fire activity in region

### Open-Meteo Errors

**"latitude/longitude invalid"**:
- Check monitoring location coordinates
- Verify PostGIS geometry format
- Ensure coordinates are in WGS84 (SRID 4326)

**Timeout errors**:
- Increase timeout in client initialization
- Reduce number of locations per batch
- Check network connectivity

**"past_days exceeds limit"**:
- Forecast API: max 92 past days
- Use archive API for older data

### Database Issues

**"Column expression expected" errors**:
- Fixed in Phase 6
- Ensure using correct SQLAlchemy 2.0 syntax

**JSON serialization errors**:
- Fixed in Phase 6 (Decimal → float conversion)
- Check `_serialize_for_json` is applied

**PostGIS function errors**:
- Ensure PostGIS extension is installed
- Verify Geography → Geometry casting

## Future Enhancements

Not implemented in Phase 7:

- Automatic scheduling/orchestration
- Real-time streaming ingestion
- Alert triggers on ingestion
- Data quality monitoring dashboard
- Backfill automation
- Multi-region support
- Incremental synchronization optimization

These may be addressed in future phases.
