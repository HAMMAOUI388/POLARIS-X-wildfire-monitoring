# POLARIS X Web Dashboard

## Requirements

- Node.js 20 or newer and npm.
- The Flask/PostGIS backend running at `http://127.0.0.1:5000`.
- Backend CORS configured to allow the frontend origin, normally `http://localhost:3000`.

## Install and run

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local` to the backend API root, for example:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5000/api/v1
```

Start the backend in a second terminal from the repository root. With the project environment installed and a migrated PostgreSQL/PostGIS database configured:

```bash
export DATABASE_URL='postgresql+psycopg://polaris:polaris_dev@localhost:55432/polaris_x'
export JWT_SECRET_KEY='replace-with-a-random-secret-at-least-32-characters'
export CORS_ORIGINS='http://localhost:3000'
flask --app polaris_x.app:create_app run --debug
```

The frontend stores JWTs only in `sessionStorage`, sends them in authorization headers, attempts the backend refresh route after an expired access token, and clears the session on an authorization failure. The LLM key remains on the backend.

## Validate

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

## Demo walkthrough

1. Register a prototype account or sign in.
2. In Live Monitoring Map, search a Moroccan place or click the map, name the point, and save it as a monitoring location.
3. Inspect the location list and its backend-provided summaries.
4. Review satellite thermal anomalies and any event associations returned by the geospatial API. Open Alerts to review and mark notifications as read.
5. Start a conversation with the assistant and ask for your saved locations or recent alerts.

The dashboard only renders records returned by authenticated backend routes. If the database has no monitoring records, create an account and save a location through the UI, then ingest a permitted FIRMS CSV using the existing backend ingestion process. Keep sample data clearly identified as test or synthetic; do not insert seed records into a database containing real operations data.

## Current backend limits shown in the UI

- Geospatial observation and event blueprints are mounted at `/api/v1/geospatial`; place search is mounted at `/api/v1/geography`.
- The map queries a fixed 5 km radius because the location API does not return a user-configured subscription radius.
- Weather data can be ingested, but the backend exposes no authenticated weather read endpoint, so the dashboard labels it unavailable.
- Only event centroids returned through an authorized alert-linked event route are displayed.
- No validated wildfire occurrence or spread prediction is available. Satellite thermal anomalies are not confirmed wildfires.
- Map tiles come from the OpenStreetMap tile service with visible attribution. This setup is intended for a prototype demonstration; choose a suitable tile provider and usage policy before production traffic.
