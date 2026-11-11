"""Tests for NASA FIRMS API client and live ingestion."""

import os
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import select

from polaris_x.db.models import DataSource, IngestionRun, MonitoringLocation, SatelliteFireObservation, User
from polaris_x.db.session import make_session_factory
from polaris_x.ingestion.firms import FirmsApiAdapter, import_api


# Mock FIRMS API CSV response
FIRMS_CSV_RESPONSE = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
33.5,-6.8,320.5,0.4,0.4,2024-11-09,0230,N,nominal,2.0NRT,290.3,12.5,N
34.2,-7.1,315.2,0.4,0.4,2024-11-09,0235,N,nominal,2.0NRT,285.1,8.3,N"""

FIRMS_EMPTY_RESPONSE = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"

FIRMS_ERROR_RESPONSE = "ERROR: Invalid MAP_KEY or area coordinates"


def test_firms_api_adapter_requires_key():
    """Verify that FirmsApiAdapter requires NASA_FIRMS_API_KEY."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="NASA_FIRMS_API_KEY is required"):
            FirmsApiAdapter()


def test_firms_api_adapter_accepts_key_parameter():
    """Verify that FirmsApiAdapter accepts API key as parameter."""
    client = FirmsApiAdapter(api_key="test-key-123")
    assert client.api_key == "test-key-123"


def test_firms_api_adapter_reads_environment():
    """Verify that FirmsApiAdapter reads NASA_FIRMS_API_KEY from environment."""
    with patch.dict(os.environ, {"NASA_FIRMS_API_KEY": "env-key-456"}):
        client = FirmsApiAdapter()
        assert client.api_key == "env-key-456"


def test_firms_api_validates_coordinates():
    """Verify that fetch validates coordinate bounds."""
    client = FirmsApiAdapter(api_key="test-key")

    # Invalid longitude
    with pytest.raises(ValueError, match="Longitude must be between -180 and 180"):
        client.fetch("VIIRS_SNPP_NRT", west=-200, south=20, east=-1, north=40)

    # Invalid latitude
    with pytest.raises(ValueError, match="Latitude must be between -90 and 90"):
        client.fetch("VIIRS_SNPP_NRT", west=-10, south=-100, east=-1, north=40)


def test_firms_api_validates_day_range():
    """Verify that fetch validates day_range parameter."""
    client = FirmsApiAdapter(api_key="test-key")

    with pytest.raises(ValueError, match="Day range must be between 1 and 10"):
        client.fetch("VIIRS_SNPP_NRT", west=-10, south=20, east=-1, north=40, day_range=0)

    with pytest.raises(ValueError, match="Day range must be between 1 and 10"):
        client.fetch("VIIRS_SNPP_NRT", west=-10, south=20, east=-1, north=40, day_range=15)


def test_firms_api_builds_correct_url_without_date():
    """Verify that fetch builds correct URL for most recent data."""
    client = FirmsApiAdapter(api_key="test-map-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = FIRMS_CSV_RESPONSE.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client.fetch("VIIRS_SNPP_NRT", west=-15, south=21, east=-1, north=36, day_range=1)

        # Verify URL structure
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        expected_url = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/test-map-key/VIIRS_SNPP_NRT/-15,21,-1,36/1"
        assert request.full_url == expected_url


def test_firms_api_builds_correct_url_with_date():
    """Verify that fetch builds correct URL with specific date."""
    client = FirmsApiAdapter(api_key="test-map-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = FIRMS_CSV_RESPONSE.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        client.fetch("MODIS_NRT", west=-15, south=21, east=-1, north=36, day_range=5, date="2024-11-01")

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        expected_url = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/test-map-key/MODIS_NRT/-15,21,-1,36/5/2024-11-01"
        assert request.full_url == expected_url


def test_firms_api_parses_csv_response():
    """Verify that fetch correctly parses CSV response."""
    client = FirmsApiAdapter(api_key="test-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = FIRMS_CSV_RESPONSE.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        rows = client.fetch("VIIRS_SNPP_NRT", west=-15, south=21, east=-1, north=36)

        assert len(rows) == 2
        assert rows[0]["latitude"] == "33.5"
        assert rows[0]["longitude"] == "-6.8"
        assert rows[0]["acq_date"] == "2024-11-09"
        assert rows[0]["acq_time"] == "0230"
        assert rows[0]["confidence"] == "nominal"
        assert rows[1]["latitude"] == "34.2"


def test_firms_api_handles_empty_response():
    """Verify that fetch handles empty result sets correctly."""
    client = FirmsApiAdapter(api_key="test-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = FIRMS_EMPTY_RESPONSE.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        rows = client.fetch("VIIRS_SNPP_NRT", west=-15, south=21, east=-1, north=36)

        assert rows == []


def test_firms_api_handles_error_response():
    """Verify that fetch raises RuntimeError on API error messages."""
    client = FirmsApiAdapter(api_key="test-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = FIRMS_ERROR_RESPONSE.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with pytest.raises(RuntimeError, match="FIRMS API error"):
            client.fetch("VIIRS_SNPP_NRT", west=-15, south=21, east=-1, north=36)


def test_firms_api_handles_http_400():
    """Verify that fetch handles HTTP 400 (bad request)."""
    import urllib.error

    client = FirmsApiAdapter(api_key="test-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        error_response = MagicMock()
        error_response.read.return_value = b"Invalid parameters"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=400, msg="Bad Request", hdrs={}, fp=error_response
        )

        with pytest.raises(ValueError, match="FIRMS API invalid request"):
            client.fetch("VIIRS_SNPP_NRT", west=-15, south=21, east=-1, north=36)


def test_firms_api_handles_http_401():
    """Verify that fetch handles HTTP 401 (unauthorized)."""
    import urllib.error

    client = FirmsApiAdapter(api_key="invalid-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        error_response = MagicMock()
        error_response.read.return_value = b"Unauthorized"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=401, msg="Unauthorized", hdrs={}, fp=error_response
        )

        with pytest.raises(ValueError, match="FIRMS API authentication failed"):
            client.fetch("VIIRS_SNPP_NRT", west=-15, south=21, east=-1, north=36)


def test_firms_api_handles_http_429():
    """Verify that fetch handles HTTP 429 (rate limit)."""
    import urllib.error

    client = FirmsApiAdapter(api_key="test-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        error_response = MagicMock()
        error_response.read.return_value = b"Rate limit exceeded"
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="", code=429, msg="Too Many Requests", hdrs={}, fp=error_response
        )

        with pytest.raises(RuntimeError, match="FIRMS API rate limit exceeded"):
            client.fetch("VIIRS_SNPP_NRT", west=-15, south=21, east=-1, north=36)


def test_firms_api_handles_network_error():
    """Verify that fetch handles network errors."""
    import urllib.error

    client = FirmsApiAdapter(api_key="test-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")

        with pytest.raises(RuntimeError, match="FIRMS API network error"):
            client.fetch("VIIRS_SNPP_NRT", west=-15, south=21, east=-1, north=36)


def test_firms_api_integration_ingestion():
    """Verify that import_api integrates with database correctly."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    test_id = uuid4().hex
    factory = make_session_factory(url)

    with factory.begin() as session:
        # Mock the API client with valid test data
        with patch("polaris_x.ingestion.firms.FirmsApiAdapter") as MockClient:
            mock_client = MagicMock()
            mock_client.fetch.return_value = [
                {
                    "latitude": "33.5",
                    "longitude": "-6.8",
                    "acq_date": "2024-11-09",
                    "acq_time": "1430",
                    "bright_ti4": "320.5",
                    "confidence": "nominal",
                    "frp": "12.5",
                    "satellite": "N",
                    "version": "2.0NRT",
                    "external_id": f"test-{test_id}",  # Unique ID to avoid duplicates
                },
            ]
            MockClient.return_value = mock_client

            result = import_api(
                source="VIIRS_SNPP_NRT",
                west=-15,
                south=21,
                east=-1,
                north=36,
                day_range=1,
                source_name=f"Test FIRMS Integration {test_id}",
                session=session,
            )

            assert result.inserted == 1, f"Expected 1 inserted, got {result.inserted}. Rejected: {result.rejected}"
            assert result.duplicate == 0
            assert result.rejected == 0

    # Verify database records (after transaction is committed)
    with factory() as verify_session:
        observations = verify_session.scalars(
            select(SatelliteFireObservation)
        ).all()
        assert len(observations) >= 1

        # Verify data source
        data_source = verify_session.scalar(
            select(DataSource).where(DataSource.name == f"Test FIRMS Integration {test_id}")
        )
        assert data_source is not None
        assert data_source.source_type == "satellite"
        assert data_source.provider == "NASA FIRMS"

        # Verify ingestion run
        run = verify_session.get(IngestionRun, result.run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.inserted_count == 1


def test_firms_api_ingestion_handles_duplicates():
    """Verify that repeated API ingestion correctly identifies duplicates."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    test_id = uuid4().hex
    factory = make_session_factory(url)

    mock_row = {
        "latitude": "33.5",
        "longitude": "-6.8",
        "acq_date": "2024-11-09",
        "acq_time": "0230",
        "bright_ti4": "320.5",
        "confidence": "nominal",
        "frp": "12.5",
        "satellite": "N",
    }

    with factory.begin() as session:
        with patch("polaris_x.ingestion.firms.FirmsApiAdapter") as MockClient:
            mock_client = MagicMock()
            mock_client.fetch.return_value = [mock_row]
            MockClient.return_value = mock_client

            # First ingestion
            result1 = import_api(
                source="VIIRS_SNPP_NRT",
                west=-15,
                south=21,
                east=-1,
                north=36,
                source_name=f"Test FIRMS {test_id}",
                session=session,
            )

            # Second ingestion (same data)
            result2 = import_api(
                source="VIIRS_SNPP_NRT",
                west=-15,
                south=21,
                east=-1,
                north=36,
                source_name=f"Test FIRMS {test_id}",
                session=session,
            )

            assert result1.inserted == 1
            assert result1.duplicate == 0
            assert result2.inserted == 0
            assert result2.duplicate == 1


def test_firms_api_ingestion_handles_validation_errors():
    """Verify that API ingestion handles malformed data correctly."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    test_id = uuid4().hex
    factory = make_session_factory(url)

    # First create a valid import to avoid UUID collision issues
    result = None
    with factory.begin() as session:
        with patch("polaris_x.ingestion.firms.FirmsApiAdapter") as MockClient:
            mock_client = MagicMock()
            mock_client.fetch.return_value = [
                {
                    "latitude": "invalid",  # Invalid numeric value
                    "longitude": "-6.8",
                    "acq_date": "2024-11-09",
                    "acq_time": "0230",
                },
            ]
            MockClient.return_value = mock_client

            result = import_api(
                source="VIIRS_SNPP_NRT",
                west=-15,
                south=21,
                east=-1,
                north=36,
                source_name=f"Test FIRMS Validation {test_id}",
                session=session,
            )

            assert result.inserted == 0
            assert result.rejected == 1

    # Verify rejection record (after transaction is committed)
    with factory() as verify_session:
        run = verify_session.get(IngestionRun, result.run_id)
        assert run is not None
        assert run.rejected_count == 1


def test_firms_product_determination():
    """Verify that import_api correctly determines product from source."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    factory = make_session_factory(url)

    with factory.begin() as session:
        with patch("polaris_x.ingestion.firms.FirmsApiAdapter") as MockClient:
            mock_client = MagicMock()
            mock_client.fetch.return_value = []
            MockClient.return_value = mock_client

            # VIIRS source
            result_viirs = import_api(
                source="VIIRS_NOAA20_NRT",
                west=-15,
                south=21,
                east=-1,
                north=36,
                source_name="Test VIIRS Product",
                session=session,
            )

            viirs_source = session.scalar(
                select(DataSource).where(DataSource.name == "Test VIIRS Product")
            )
            assert viirs_source.metadata_json["product"] == "viirs"

            # MODIS source
            result_modis = import_api(
                source="MODIS_NRT",
                west=-15,
                south=21,
                east=-1,
                north=36,
                source_name="Test MODIS Product",
                session=session,
            )

            modis_source = session.scalar(
                select(DataSource).where(DataSource.name == "Test MODIS Product")
            )
            assert modis_source.metadata_json["product"] == "modis"
