import os
from datetime import timedelta

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://polaris:change-me@localhost:5432/polaris_x")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ERROR_MESSAGE_KEY = "message"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "15")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "30")))
    CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
    # Allow Chrome Private Network Access (PNA) preflights from non-loopback origins
    # targeting 127.0.0.1 (e.g. Tailscale/VPN network interface → localhost API).
    # Set to True in development when the Next.js dev server is accessible from a
    # non-loopback interface (the browser will send the PNA preflight header).
    CORS_ALLOW_PRIVATE_NETWORK = os.getenv("CORS_ALLOW_PRIVATE_NETWORK", "false").lower() in ("true", "1", "yes")
    NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
    GEOGRAPHY_USER_AGENT = os.getenv("GEOGRAPHY_USER_AGENT", "POLARIS-X/0.1 (contact: configure-geography-user-agent)")
    GEOGRAPHY_PROVIDER_TIMEOUT = float(os.getenv("GEOGRAPHY_PROVIDER_TIMEOUT", "5"))
    GEOGRAPHY_PROVIDER_RETRIES = int(os.getenv("GEOGRAPHY_PROVIDER_RETRIES", "1"))
    ROUTING_PROVIDER = os.getenv("ROUTING_PROVIDER", "osrm")
    OSRM_URL = os.getenv("OSRM_URL", "")
    GRAPHHOPPER_URL = os.getenv("GRAPHHOPPER_URL", "https://graphhopper.com/api/1")
    GRAPHHOPPER_API_KEY = os.getenv("GRAPHHOPPER_API_KEY", "")
    MAP_STYLE_URL = os.getenv("MAP_STYLE_URL", "")
    MAP_ATTRIBUTION = os.getenv("MAP_ATTRIBUTION", "© OpenStreetMap contributors")
    OPEN_METEO_FORECAST_URL = os.getenv("OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast")
    OPEN_METEO_ARCHIVE_URL = os.getenv("OPEN_METEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive")
    OPEN_METEO_API_KEY = os.getenv("OPEN_METEO_API_KEY", "")
    OPEN_METEO_COMMERCIAL = os.getenv("OPEN_METEO_COMMERCIAL", "false").lower() in ("true", "1", "yes")
    WEATHER_ATTRIBUTION = os.getenv("WEATHER_ATTRIBUTION", "Weather data by Open-Meteo.com (CC-BY 4.0, https://doi.org/10.5281/zenodo.7970649)")
    WEATHER_MAX_AGE_FORECAST_SECONDS = int(os.getenv("WEATHER_MAX_AGE_FORECAST_SECONDS", "10800"))
    WEATHER_MAX_AGE_ERA5_SECONDS = int(os.getenv("WEATHER_MAX_AGE_ERA5_SECONDS", "604800"))
    NASA_FIRMS_API_KEY = os.getenv("NASA_FIRMS_API_KEY", "")
    NASA_FIRMS_BASE_URL = os.getenv("NASA_FIRMS_BASE_URL", "https://firms.modaps.eosdis.nasa.gov")
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "unavailable")
    LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "15"))
    IOT_WEBHOOK_SECRET = os.getenv("POLARIS_IOT_WEBHOOK_SECRET", "change-me-iot-webhook-secret-at-least-32-chars")
    TESTING = False

class TestingConfig(Config):
    TESTING = True
    JWT_SECRET_KEY = os.getenv("TEST_JWT_SECRET_KEY", "test-only-secret-with-at-least-32-characters")
    DATABASE_URL = os.getenv("TEST_DATABASE_URL", Config.DATABASE_URL)
    IOT_WEBHOOK_SECRET = "test-iot-webhook-secret-phase13"
    CORS_ORIGINS = []
