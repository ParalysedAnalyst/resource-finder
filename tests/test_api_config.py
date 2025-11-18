import requests
import pytest
import api_config as api

def test_geocode_postcode_404(monkeypatch):
    class Fake404:
        status_code = 404
        def json(self): return {"status": 404, "error": "Postcode not found"}
        def raise_for_status(self): raise requests.HTTPError("404")
    monkeypatch.setattr(api.requests, "get", lambda *a, **k: Fake404())
    with pytest.raises(api.PostcodeNotFound):
        api.geocode_postcode("INVALID")

def test_osrm_route_ok(monkeypatch):
    class FakeOK:
        status_code = 200
        def json(self): return {"routes":[{"distance": 12345.0, "duration": 900.0}]}
        def raise_for_status(self): return None
    monkeypatch.setattr(api.requests, "get", lambda *a, **k: FakeOK())
    res = api.osrm_route(-0.1, 51.5, -0.2, 51.6)
    assert res["distance_km"] == pytest.approx(12.345)
    assert res["duration_min"] == pytest.approx(15.0)
    assert "co2_kg" in res
