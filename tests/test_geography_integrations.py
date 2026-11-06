import json
from io import BytesIO

import pytest

from polaris_x.integrations.geography import GeoPoint, GraphHopperAdapter, NominatimAdapter, OSRMAdapter, ProviderError, RequestClient

class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return json.dumps(self.payload).encode()

def fake_opener(payloads):
    calls=[]
    def opener(request, timeout):
        calls.append((request.full_url, timeout, dict(request.headers)))
        return FakeResponse(payloads[len(calls)-1])
    opener.calls=calls
    return opener

def test_nominatim_search_reverse_normalize_cache_and_user_agent():
    opener=fake_opener([[{"place_id": 1, "display_name": "Rabat", "lat": "34.02", "lon": "-6.84", "type": "city", "class": "place"}], {"place_id": 2, "display_name": "Rabat address", "lat": "34.03", "lon": "-6.83", "type": "road", "class": "highway"}])
    adapter=NominatimAdapter("https://nominatim.example", RequestClient("POLARIS-X-test", opener=opener), min_interval=0)
    assert adapter.search("Rabat")[0].point == GeoPoint(-6.84, 34.02)
    assert adapter.search("Rabat")[0].display_name == "Rabat"
    assert adapter.reverse(GeoPoint(-6.83, 34.03)).display_name == "Rabat address"
    assert len(opener.calls) == 2
    assert opener.calls[0][2]["User-agent"] == "POLARIS-X-test"

def test_osrm_route_preview_is_normalized_and_cached():
    opener=fake_opener([{ "routes": [{"distance": 1234, "duration": 321, "geometry": {"type": "LineString", "coordinates": [[-6.8, 33.9], [-6.81, 33.91]]}}]}])
    adapter=OSRMAdapter("https://osrm.example", RequestClient("test", opener=opener))
    result=adapter.preview(GeoPoint(-6.8, 33.9), GeoPoint(-6.81, 33.91), [], "foot")
    assert result.distance_m == 1234 and result.duration_s == 321
    assert adapter.preview(GeoPoint(-6.8, 33.9), GeoPoint(-6.81, 33.91), [], "foot") == result
    assert len(opener.calls) == 1

def test_graphhopper_key_is_not_sent_to_result_or_errors():
    opener=fake_opener([{ "paths": [{"distance": 500, "time": 2000, "points": {"type": "LineString", "coordinates": []}}]}])
    adapter=GraphHopperAdapter("https://graphhopper.example", "secret-key", RequestClient("test", opener=opener))
    result=adapter.preview(GeoPoint(-6.8, 33.9), GeoPoint(-6.81, 33.91), [], "hike")
    assert result.provider == "graphhopper"
    assert "secret-key" not in repr(result)
    assert "secret-key" in opener.calls[0][0]

def test_provider_rate_limit_maps_to_structured_error():
    from urllib.error import HTTPError
    def opener(request, timeout): raise HTTPError(request.full_url, 429, "limited", {}, BytesIO())
    adapter=NominatimAdapter("https://nominatim.example", RequestClient("test", opener=opener), min_interval=0)
    with pytest.raises(ProviderError) as exc: adapter.search("Rabat")
    assert exc.value.code == "provider_rate_limited" and exc.value.status == 429

def test_coordinate_order_is_longitude_then_latitude():
    item = GeoPoint(-6.84, 34.02)
    assert item.longitude == -6.84
    assert item.latitude == 34.02
