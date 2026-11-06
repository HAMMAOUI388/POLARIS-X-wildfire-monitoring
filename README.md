# POLARIS-X-wildfire-monitoring

An intelligent wildfire monitoring and early-warning support platform for Morocco, integrating NASA FIRMS satellite observations, IoT environmental sensing, weather data, geospatial analysis, and real-time alerting to improve wildfire situational awareness.

## Phase 1 and Phase 2 setup

The project uses PostgreSQL 16+ with PostGIS, SQLAlchemy 2, GeoAlchemy2, Alembic, Flask, Flask-JWT-Extended, Pydantic, and Shapely. See [docs/database-design.md](docs/database-design.md) and [docs/backend-foundation.md](docs/backend-foundation.md).

### Local Mac setup

Using Homebrew PostgreSQL/PostGIS:

```bash
brew install postgresql@16 postgis
brew services start postgresql@16
createdb polaris_x
psql polaris_x -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Alternatively, use the verified Docker environment:

```bash
colima start --cpu 2 --memory 4 --disk 20
docker run -d --name polaris-x-postgis \
  -e POSTGRES_USER=polaris \
  -e POSTGRES_PASSWORD=polaris_dev \
  -e POSTGRES_DB=polaris_x \
  -p 55432:5432 postgis/postgis:16-3.4
export DATABASE_URL='postgresql+psycopg://polaris:polaris_dev@localhost:55432/polaris_x'
```

Install dependencies and configure secrets:

```bash
python3 -m pip install -e '.[dev]'
cp .env.example .env
export DATABASE_URL='postgresql+psycopg://polaris:polaris_dev@localhost:55432/polaris_x'
export JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

Apply the database migration and synthetic development seed:

```bash
alembic upgrade head
python3 -m polaris_x.db.seed
```

Run the application:

```bash
flask --app polaris_x.app:create_app run --debug
```

### Verification and tests

```bash
export TEST_DATABASE_URL="$DATABASE_URL"
pytest -q
```

The test suite includes schema tests, live PostGIS checks, authentication tests, JWT tests, validation tests, and owned/shared/unauthorized location tests. Test fixtures use unique test email addresses and remove only their own records; they do not truncate development fixtures.

### API examples

Register:

```bash
curl -X POST http://127.0.0.1:5000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"person@example.com","password":"Correct-Horse-Battery-1","display_name":"Example User"}'
```

Login:

```bash
curl -X POST http://127.0.0.1:5000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"person@example.com","password":"Correct-Horse-Battery-1"}'
```

Authenticated profile:

```bash
curl http://127.0.0.1:5000/api/v1/auth/me \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

Create a monitored location:

```bash
curl -X POST http://127.0.0.1:5000/api/v1/locations \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Example Farm","location_type":"farm","longitude":-6.84,"latitude":33.97}'
```

Health check:

```bash
curl http://127.0.0.1:5000/api/v1/health
```

Phase 3 offline NASA FIRMS CSV ingestion is implemented for the explicitly supported VIIRS and MODIS mappings; see [docs/firms-ingestion.md](docs/firms-ingestion.md). Prediction, alert generation, chatbot services, web dashboard, and mobile application are not implemented.

## Phase 5 assessment foundation

The current Phase 5 implementation is an insufficient-data assessment foundation. It preserves model/version, feature snapshots, evidence, data quality, uncertainty, and input provenance, but returns no score when validated environmental inputs are unavailable. It does not produce fire-occurrence probabilities or fire-spread predictions. Weather and IoT models exist without validated ingestion pipelines; terrain, vegetation, fuel, and independent ground-truth data are not available.
