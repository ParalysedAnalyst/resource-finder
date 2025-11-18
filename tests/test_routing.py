import pandas as pd
import pytest
import routing
import api_config as api

def test_preselect_by_air_distance_order():
    df = pd.DataFrame({
        "Contractor":["Near","Far"],
        "BusinessUnit":["X","X"], "Postcode":["P1","P2"],
        "Latitude":[51.500, 51.600], "Longitude":[-0.100, -0.500],
        "InternalContractor":[1,0]
    })
    out = routing.preselect_by_air_distance(df, site_lon=-0.101, site_lat=51.501, top_n=1)
    assert list(out["Contractor"]) == ["Near"]

def test_route_rank_teams_monkeypatched(monkeypatch):
    # Fake OSRM to avoid HTTP
    def fake_route(start_lon, start_lat, dest_lon, dest_lat):
        return {"distance_km": 10.0, "duration_min": 12.0, "co2_kg": 1.71}
    monkeypatch.setattr(api, "osrm_route", fake_route)

    df = pd.DataFrame({
        "Contractor":["A","B"],
        "BusinessUnit":["X","X"], "Postcode":["P1","P2"],
        "Latitude":[51.5, 51.6], "Longitude":[-0.1, -0.2],
        "InternalContractor":[1,0]
    })
    out = routing.route_rank_teams(df, site_lon=-0.1, site_lat=51.5, top_n=1)
    assert list(out.columns)[-3:] == ["drive_km","drive_min","co2_kg"]
    assert len(out) == 1