"""
Open-Meteo weather data integration.

This module provides HTTP client adapters for the Open-Meteo API, including:
- Operational NWP forecast data (/v1/forecast)
- Historical reanalysis (ERA5/ERA5-Land, /v1/archive)

Time semantics:
- All timestamps from Open-Meteo are valid times (the moment the data describes).
- Forecast run/issue times are NOT returned by the seamless forecast API; only retrieval time is recorded.
- ERA5 reference times represent the centre of the reanalysis analysis window.

Data provenance:
- ERA5 and ERA5-Land are gridded reanalysis products, NOT weather-station observations.
- All values are interpolated from model grids (~25 km for ERA5, ~9 km for ERA5-Land).
- Provider, model name, and resolution must be preserved in all provenance records.

Preceding-hour variables (precipitation, ET₀, wind gusts, radiation):
- Open-Meteo labels these with the END of their temporal window.
- Each has different aggregation semantics (sum, max, mean) but covers the preceding hour.
- valid_from should be set to (time - 1 hour); valid_to to time.

Licensing:
- Free tier: CC-BY 4.0, non-commercial use only, no API key required.
- Commercial tier: requires API key and customer- server prefix.
- Attribution is mandatory (see WEATHER_ATTRIBUTION config).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

WILDFIRE_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "vapour_pressure_deficit",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "precipitation",
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "et0_fao_evapotranspiration",
    "shortwave_radiation",
)

# Variables that cover the preceding hour (not instantaneous)
# Each has different aggregation semantics but all use the same temporal window:
# valid_from = time - 1 hour, valid_to = time
PRECEDING_HOUR_VARIABLES = {
    "precipitation",              # sum of preceding hour
    "et0_fao_evapotranspiration", # sum of preceding hour
    "wind_gusts_10m",             # maximum during preceding hour
    "shortwave_radiation",        # mean over preceding hour
}


@dataclass(frozen=True)
class WeatherDataPoint:
    """Single weather data point with temporal and provenance metadata."""

    valid_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    variables: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True)
class OpenMeteoResponse:
    """Normalized Open-Meteo API response."""

    data_points: list[WeatherDataPoint]
    source_type: str
    provider: str
    model: str
    resolution_km: float
    retrieval_time: datetime
    metadata: dict[str, Any]


class OpenMeteoClient:
    """HTTP client for Open-Meteo APIs."""

    def __init__(
        self,
        forecast_url: str,
        archive_url: str,
        api_key: str | None = None,
        user_agent: str = "POLARIS-X/0.1",
        timeout: float = 10.0,
    ):
        self.forecast_url = forecast_url.rstrip("/")
        self.archive_url = archive_url.rstrip("/")
        self.api_key = api_key.strip() if api_key else None
        self.user_agent = user_agent
        self.timeout = timeout

    def _build_url(self, base: str, params: dict[str, Any]) -> str:
        """Build URL with query parameters, adding API key if configured."""
        filtered = {k: v for k, v in params.items() if v is not None}
        if self.api_key:
            filtered["apikey"] = self.api_key
        query = urllib.parse.urlencode(filtered)
        return f"{base}?{query}"

    def _http_get(self, url: str) -> dict[str, Any]:
        """Execute HTTP GET with error handling."""
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Open-Meteo HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Open-Meteo network error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Open-Meteo invalid JSON: {exc}") from exc

    def _parse_response(
        self,
        payload: dict[str, Any],
        source_type: str,
        model: str,
        resolution_km: float,
        retrieval_time: datetime,
    ) -> OpenMeteoResponse:
        """Parse and normalize Open-Meteo JSON response."""
        if "error" in payload and payload["error"]:
            raise ValueError(f"Open-Meteo API error: {payload.get('reason', 'unknown')}")

        hourly = payload.get("hourly")
        if not hourly or "time" not in hourly:
            raise ValueError("Open-Meteo response missing hourly.time array")

        times = hourly["time"]
        if not isinstance(times, list):
            raise ValueError("Open-Meteo hourly.time must be a list")

        data_points: list[WeatherDataPoint] = []
        for i, time_str in enumerate(times):
            valid_at = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            if valid_at.tzinfo is None:
                valid_at = valid_at.replace(tzinfo=timezone.utc)
            valid_at = valid_at.astimezone(timezone.utc)

            variables: dict[str, Any] = {}
            has_preceding_hour = False
            for var_name in WILDFIRE_VARIABLES:
                if var_name in hourly and isinstance(hourly[var_name], list) and i < len(hourly[var_name]):
                    value = hourly[var_name][i]
                    if value is not None:
                        variables[var_name] = Decimal(str(value)) if isinstance(value, (int, float)) else value
                        if var_name in PRECEDING_HOUR_VARIABLES:
                            has_preceding_hour = True

            if not variables:
                continue

            # Preceding-hour variables cover the preceding hour (time - 1h to time)
            if has_preceding_hour:
                valid_from = valid_at - timedelta(hours=1)
                valid_to = valid_at
            else:
                valid_from = None
                valid_to = None

            provenance = {
                "source": "open-meteo",
                "source_type": source_type,
                "model": model,
                "resolution_km": resolution_km,
                "retrieval_time": retrieval_time.isoformat(),
                "valid_at": valid_at.isoformat(),
            }
            if valid_from and valid_to:
                provenance["valid_from"] = valid_from.isoformat()
                provenance["valid_to"] = valid_to.isoformat()

            data_points.append(
                WeatherDataPoint(
                    valid_at=valid_at,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    variables=variables,
                    provenance=provenance,
                )
            )

        metadata = {
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "elevation": payload.get("elevation"),
            "timezone": payload.get("timezone"),
            "utc_offset_seconds": payload.get("utc_offset_seconds"),
        }

        return OpenMeteoResponse(
            data_points=data_points,
            source_type=source_type,
            provider="Open-Meteo",
            model=model,
            resolution_km=resolution_km,
            retrieval_time=retrieval_time,
            metadata=metadata,
        )

    def fetch_forecast(
        self,
        latitude: float,
        longitude: float,
        past_days: int = 0,
        forecast_days: int = 7,
        model: str = "best_match",
    ) -> OpenMeteoResponse:
        """
        Fetch operational NWP forecast data.

        Args:
            latitude: Decimal degrees, -90 to 90.
            longitude: Decimal degrees, -180 to 180.
            past_days: Number of past days to include (max 92).
            forecast_days: Number of forecast days (max 16).
            model: Model preference (default 'best_match').

        Returns:
            OpenMeteoResponse with forecast data and provenance.

        Note:
            The seamless forecast API does NOT expose model run/issue times.
            Only retrieval_time is recorded in provenance.
        """
        if not (-90 <= latitude <= 90):
            raise ValueError("latitude must be between -90 and 90")
        if not (-180 <= longitude <= 180):
            raise ValueError("longitude must be between -180 and 180")
        if not (0 <= past_days <= 92):
            raise ValueError("past_days must be between 0 and 92")
        if not (0 <= forecast_days <= 16):
            raise ValueError("forecast_days must be between 0 and 16")

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(WILDFIRE_VARIABLES),
            "timezone": "UTC",
            "past_days": past_days if past_days > 0 else None,
            "forecast_days": forecast_days if forecast_days > 0 else None,
            "models": model if model != "best_match" else None,
        }

        url = self._build_url(self.forecast_url, params)
        retrieval_time = datetime.now(timezone.utc)
        payload = self._http_get(url)

        # Resolution varies by model; use conservative estimate
        resolution_km = 11.0  # ICON-D2 / ICON-EU typical resolution
        return self._parse_response(
            payload=payload,
            source_type="nwp_forecast",
            model=model,
            resolution_km=resolution_km,
            retrieval_time=retrieval_time,
        )

    def fetch_archive(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
    ) -> OpenMeteoResponse:
        """
        Fetch historical reanalysis data (ERA5/ERA5-Land).

        Args:
            latitude: Decimal degrees, -90 to 90.
            longitude: Decimal degrees, -180 to 180.
            start_date: ISO date string (YYYY-MM-DD).
            end_date: ISO date string (YYYY-MM-DD).

        Returns:
            OpenMeteoResponse with reanalysis data.

        Note:
            ERA5 and ERA5-Land are gridded reanalysis products, NOT local weather-station observations.
            Data has a ~5-day delay and should not be used for operational near-real-time monitoring.
        """
        if not (-90 <= latitude <= 90):
            raise ValueError("latitude must be between -90 and 90")
        if not (-180 <= longitude <= 180):
            raise ValueError("longitude must be between -180 and 180")

        # ERA5-Land uses different soil layer names; use only variables available in both
        archive_variables = [v for v in WILDFIRE_VARIABLES if not v.startswith("soil_moisture_")]

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(archive_variables),
            "timezone": "UTC",
        }

        url = self._build_url(self.archive_url, params)
        retrieval_time = datetime.now(timezone.utc)
        payload = self._http_get(url)

        # ERA5-Land is ~9 km, ERA5 is ~25 km; use ERA5-Land as default
        return self._parse_response(
            payload=payload,
            source_type="reanalysis",
            model="ERA5-Land",
            resolution_km=9.0,
            retrieval_time=retrieval_time,
        )
