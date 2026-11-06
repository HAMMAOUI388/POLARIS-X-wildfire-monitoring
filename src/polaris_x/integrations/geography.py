from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

class ProviderError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status

@dataclass(frozen=True)
class GeoPoint:
    longitude: float
    latitude: float

@dataclass(frozen=True)
class GeocoderResult:
    provider_id: str
    display_name: str
    point: GeoPoint
    category: str | None
    raw_type: str | None

@dataclass(frozen=True)
class RoutePreview:
    provider: str
    profile: str
    distance_m: float
    duration_s: float
    geometry: dict[str, Any]
    waypoints: list[GeoPoint]

class TTLCache:
    def __init__(self, ttl_seconds: int = 300, max_entries: int = 256):
        self.ttl_seconds, self.max_entries = ttl_seconds, max_entries
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            item = self._items.get(key)
            if item is None: return None
            expires, value = item
            if expires <= time.monotonic():
                self._items.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any):
        with self._lock:
            if len(self._items) >= self.max_entries:
                self._items.pop(next(iter(self._items)))
            self._items[key] = (time.monotonic() + self.ttl_seconds, value)

class RequestClient:
    def __init__(self, user_agent: str, timeout: float = 5, opener: Callable[..., Any] | None = None, retries: int = 1):
        self.user_agent, self.timeout, self.opener, self.retries = user_agent, timeout, opener or urlopen, max(0, retries)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        target = f"{url}?{urlencode(params or {}, doseq=True)}"
        request = Request(target, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        for attempt in range(self.retries + 1):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code == 429: raise ProviderError("provider_rate_limited", "The geographic provider rate-limited the request.", 429) from exc
                if exc.code >= 500 and attempt < self.retries: continue
                raise ProviderError("provider_error", "The geographic provider returned an error.", 503) from exc
            except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                if attempt < self.retries and not isinstance(exc, json.JSONDecodeError): continue
                raise ProviderError("provider_unavailable", "The geographic provider is temporarily unavailable.", 503) from exc

class NominatimAdapter:
    def __init__(self, endpoint: str, client: RequestClient, cache: TTLCache | None = None, min_interval: float = 1.0):
        self.endpoint, self.client, self.cache, self.min_interval = endpoint.rstrip("/"), client, cache or TTLCache(600, 512), min_interval
        self._last_request = 0.0
        self._lock = threading.Lock()

    def _wait_turn(self):
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0: time.sleep(wait)
            self._last_request = time.monotonic()

    @staticmethod
    def _point(item: dict[str, Any]) -> GeoPoint:
        try: return GeoPoint(float(item["lon"]), float(item["lat"]))
        except (KeyError, TypeError, ValueError) as exc: raise ProviderError("provider_invalid_response", "The geocoder returned invalid coordinates.", 503) from exc

    def _normalize(self, item: dict[str, Any]) -> GeocoderResult:
        return GeocoderResult(str(item.get("place_id", "")), str(item.get("display_name", "")), self._point(item), item.get("type"), item.get("class"))

    def search(self, query: str, limit: int = 5, countrycodes: str = "ma") -> list[GeocoderResult]:
        key = f"search:{query.strip().casefold()}:{limit}:{countrycodes}"
        cached = self.cache.get(key)
        if cached is not None: return cached
        self._wait_turn()
        payload = self.client.get_json(f"{self.endpoint}/search", {"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 1, "countrycodes": countrycodes})
        results = [self._normalize(item) for item in payload if isinstance(item, dict)]
        self.cache.set(key, results)
        return results

    def reverse(self, point: GeoPoint) -> GeocoderResult:
        key = f"reverse:{point.longitude:.6f}:{point.latitude:.6f}"
        cached = self.cache.get(key)
        if cached is not None: return cached
        self._wait_turn()
        payload = self.client.get_json(f"{self.endpoint}/reverse", {"lat": point.latitude, "lon": point.longitude, "format": "jsonv2", "addressdetails": 1})
        result = self._normalize(payload)
        self.cache.set(key, result)
        return result

class RoutingAdapter:
    def preview(self, origin: GeoPoint, destination: GeoPoint, waypoints: list[GeoPoint], profile: str) -> RoutePreview:
        raise NotImplementedError

class OSRMAdapter(RoutingAdapter):
    def __init__(self, endpoint: str, client: RequestClient, cache: TTLCache | None = None): self.endpoint, self.client, self.cache = endpoint.rstrip("/"), client, cache or TTLCache(120, 128)
    def preview(self, origin, destination, waypoints, profile):
        if profile not in {"foot", "driving", "cycling"}: raise ProviderError("unsupported_profile", "The configured OSRM adapter does not support this profile.", 422)
        points = [origin, *waypoints, destination]; coords = ";".join(f"{p.longitude},{p.latitude}" for p in points)
        key = f"osrm:{profile}:{coords}"
        cached = self.cache.get(key)
        if cached is not None: return cached
        payload = self.client.get_json(f"{self.endpoint}/route/v1/{profile}/{coords}", {"overview": "full", "geometries": "geojson", "steps": "false"})
        try:
            route = payload["routes"][0]
            result = RoutePreview("osrm", profile, float(route["distance"]), float(route["duration"]), route["geometry"], points)
        except (KeyError, IndexError, TypeError, ValueError) as exc: raise ProviderError("provider_invalid_response", "The routing provider returned an invalid route.", 503) from exc
        self.cache.set(key, result); return result

class GraphHopperAdapter(RoutingAdapter):
    def __init__(self, endpoint: str, api_key: str, client: RequestClient, cache: TTLCache | None = None): self.endpoint, self.api_key, self.client, self.cache = endpoint.rstrip("/"), api_key, client, cache or TTLCache(120, 128)
    def preview(self, origin, destination, waypoints, profile):
        if profile not in {"foot", "hike", "bike", "car"}: raise ProviderError("unsupported_profile", "The configured GraphHopper adapter does not support this profile.", 422)
        points = [origin, *waypoints, destination]; params = {"key": self.api_key, "profile": profile, "points_encoded": "false", "instructions": "false"}
        for point in points: params.setdefault("point", []); params["point"].append(f"{point.latitude},{point.longitude}")
        key = f"graphhopper:{profile}:" + ";".join(f"{p.longitude},{p.latitude}" for p in points)
        cached = self.cache.get(key)
        if cached is not None: return cached
        payload = self.client.get_json(f"{self.endpoint}/route", params)
        try:
            path = payload["paths"][0]; result = RoutePreview("graphhopper", profile, float(path["distance"]), float(path["time"]) / 1000, path["points"], points)
        except (KeyError, IndexError, TypeError, ValueError) as exc: raise ProviderError("provider_invalid_response", "The routing provider returned an invalid route.", 503) from exc
        self.cache.set(key, result); return result
