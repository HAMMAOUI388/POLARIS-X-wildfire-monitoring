import os
from datetime import timedelta

class Config:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://polaris:change-me@localhost:5432/polaris_x")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ERROR_MESSAGE_KEY = "message"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "15")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "30")))
    CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
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
    TESTING = False

class TestingConfig(Config):
    TESTING = True
    JWT_SECRET_KEY = os.getenv("TEST_JWT_SECRET_KEY", "test-only-secret-with-at-least-32-characters")
    DATABASE_URL = os.getenv("TEST_DATABASE_URL", Config.DATABASE_URL)
    CORS_ORIGINS = []
