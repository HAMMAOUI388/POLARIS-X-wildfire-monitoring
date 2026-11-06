import os
import pytest
from sqlalchemy import text
from polaris_x.db.session import make_engine

@pytest.fixture
def postgis_connection():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = make_engine(url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT PostGIS_Version()"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(f"PostGIS database unavailable: {exc}")
    yield engine
    engine.dispose()

def test_postgis_is_available(postgis_connection):
    with postgis_connection.connect() as connection:
        assert connection.scalar(text("SELECT PostGIS_Version()"))
