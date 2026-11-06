# Phase 4 geospatial intelligence

Phase 4 treats every FIRMS row as a satellite thermal-anomaly observation. Association creates a derived `FireEvent`; it does not confirm a fire, overwrite source data, or calculate fire-front velocity.

## Prototype association policy

`SpatialPolicy` defaults to a 5,000 m radius and six-hour temporal window. These are configurable prototype defaults selected to exercise local event grouping; they are not universal wildfire-science thresholds and have not been ground-truth validated. Each association stores a policy snapshot.

An observation is associated with at most one event. Candidate events are selected using constituent observations within the temporal window, then accepted only when the new observation is within the configured radius of every existing event member. This avoids uncontrolled A-near-B-near-C chain merging. Multiple eligible candidates are resolved deterministically by smallest maximum member distance, then event UUID. Existing events are never silently merged.

Events begin with status `observed`. Their start/end times and centroid are reproducible summaries of associated observations. The centroid is a simple arithmetic mean of member longitude/latitude values and must not be interpreted as fire-front movement.

## Spatial API

Authenticated endpoints:

```text
GET /api/v1/geospatial/locations/<location_id>/observations
GET /api/v1/geospatial/locations/<location_id>/events
```

Both require owner, admin, or explicit location access. Unauthorized private locations retain the existing 404 behavior. Radius is limited to 100 km, page size to 100, and raw payloads/internal association evidence are not returned.

Location queries use geography-aware PostGIS distance functions and existing GiST indexes. Route corridor retrieval is not exposed yet because the current schema has route ownership but no route-sharing grant model; adding route sharing is deferred rather than duplicating authorization schemas.

## Limitations

The current phase does not implement frontend maps, prediction, alerts, external notifications, event merging, route API retrieval, or scientific validation against ground truth. Query plans should be benchmarked with representative production-sized data before deployment.

## External geographic integration contract

The backend exposes provider-neutral, authenticated endpoints:

```text
GET  /api/v1/geography/search?q=Rabat&limit=5&countrycodes=ma
GET  /api/v1/geography/reverse?longitude=-6.84&latitude=34.02
POST /api/v1/geography/routes/preview
```

Search and reverse geocoding use explicit user-triggered Nominatim requests. Public Nominatim autocomplete is intentionally not used. Requests carry `GEOGRAPHY_USER_AGENT`, are rate-gated to one request per second, bounded, cached in memory with TTL, and protected by timeouts. Results are never automatically saved as monitoring locations.

Route previews use the configured `ROUTING_PROVIDER` (`osrm` or `graphhopper`). The standard public OSRM demo is not a production dependency and is not assumed to provide suitable hiking coverage. GraphHopper credentials are environment-only. Preview responses are never saved; route persistence requires a future explicit confirmation endpoint.

MapLibre preparation is configuration-only. `MAP_STYLE_URL` and `MAP_ATTRIBUTION` are exposed as deployment settings; no public OSM tile URL is hard-coded. Future React and Flutter clients must display the configured attribution and follow the selected tile provider's licensing and caching rules.
