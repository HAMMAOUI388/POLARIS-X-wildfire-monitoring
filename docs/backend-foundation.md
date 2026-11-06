# Phase 2 backend foundation

## Architecture

`polaris_x.app:create_app` is the Flask application factory. It configures one SQLAlchemy engine/session factory per application, initializes JWT handling, registers JSON error handlers, applies configured CORS origins, and registers modular blueprints.

- `src/polaris_x/config.py`: environment-driven configuration.
- `src/polaris_x/extensions.py`: JWT and SQLAlchemy engine/session integration.
- `src/polaris_x/api/auth.py`: registration, login, refresh, and profile.
- `src/polaris_x/api/locations.py`: monitored location CRUD and sharing.
- `src/polaris_x/api/authz.py`: JWT-derived identity and resource authorization.
- `src/polaris_x/api/schemas.py`: Pydantic request validation.
- `src/polaris_x/api/errors.py`: structured error responses.
- `src/polaris_x/api/health.py`: database readiness check.

The application reuses the Phase 1 SQLAlchemy models and does not create a second schema or model set.

## Authentication

- Registration creates only the ordinary `user` role.
- Passwords are hashed with Werkzeug's password hashing helpers.
- Login returns a fresh short-lived access token and a longer-lived refresh token.
- Refresh tokens issue non-fresh access tokens.
- Protected endpoints derive the user UUID exclusively from the validated JWT.
- Password hashes are never serialized in API responses.
- Production requires `JWT_SECRET_KEY` through the environment.

Default expiry configuration:

- Access token: 15 minutes.
- Refresh token: 30 days.

Override with `JWT_ACCESS_TOKEN_MINUTES` and `JWT_REFRESH_TOKEN_DAYS`.

## Authorization matrix

| Resource/action | Owner | Explicit `view` | Explicit `manage` | Admin |
|---|---:|---:|---:|---:|
| Read location | yes | yes | yes | yes |
| Update location | yes | no | yes | yes |
| Delete location | yes | no | yes | yes |
| Create share | yes | no | yes | yes |

Location lists contain owned locations and locations explicitly shared with the authenticated user. No client-supplied user ID establishes identity.

## API endpoints

- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `GET /api/v1/locations`
- `POST /api/v1/locations`
- `GET /api/v1/locations/<location_id>`
- `PATCH /api/v1/locations/<location_id>`
- `DELETE /api/v1/locations/<location_id>`
- `POST /api/v1/locations/<location_id>/shares`

## Error contract

Errors use this structure:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": []
  }
}
```

Known validation, authentication, authorization, not-found, conflict, malformed JSON, and method errors are returned without stack traces or internal database details. Unexpected errors are logged server-side and returned as a generic `internal_error`.

## Scope boundary

This phase does not implement data ingestion, fire clustering, risk modelling, alert generation, chatbot behavior, frontend, mobile, Celery, Redis, or microservices.
