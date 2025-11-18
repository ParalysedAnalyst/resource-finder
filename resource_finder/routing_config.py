"""
Routing helpers:
- preselect_by_air_distance: cheap candidate cut
- route_rank_teams: OSRM for selected teams, returns sorted DataFrame
"""

import math
import pandas as pd
from .api_config import osrm_route # amended to relative import

# Distance around postcode calculated to allow filtering of teams within x km to reduce API calls
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2*R*math.asin(math.sqrt(a))

# Filter out those too far from site to avoid unecessary API calls
def preselect_by_air_distance(teams_df: pd.DataFrame, site_lon: float, site_lat: float, top_n: int = 20):
    if teams_df.empty:
        return teams_df.copy()
    tmp = teams_df.copy()
    tmp["air_km"] = [
        haversine_km(site_lat, site_lon, float(r["Latitude"]), float(r["Longitude"]))
        for _, r in tmp.iterrows()
    ]
    return tmp.sort_values("air_km").head(top_n).reset_index(drop=True)

# Call OSRM API for remaining teams and order by driving distance, closest first
def route_rank_teams(teams_df: pd.DataFrame, site_lon: float, site_lat: float, top_n: int = 20, include_geometry: bool = True) -> pd.DataFrame:
    cand = preselect_by_air_distance(teams_df, site_lon, site_lat, top_n=top_n)
    if cand.empty:
        return pd.DataFrame(columns=[
            "intContractorID","Contractor","BusinessUnit","Postcode",
            "InternalContractor","team_lon","team_lat","air_km",
            "drive_km","drive_min","co2_kg","geometry"
        ])
    rows = []
    for _, r in cand.iterrows():
        res = osrm_route(
            start_lon=float(r["Longitude"]),
            start_lat=float(r["Latitude"]),
            dest_lon=site_lon,
            dest_lat=site_lat,
            include_geometry=include_geometry,
        )
        rows.append({
            "intContractorID": r.get("intContractorID"),
            "Contractor": r.get("Contractor"),
            "BusinessUnit": r.get("BusinessUnit"),
            "Postcode": r.get("Postcode"),
            "InternalContractor": r.get("InternalContractor"),
            "team_lon": float(r["Longitude"]),
            "team_lat": float(r["Latitude"]),
            "air_km": float(r.get("air_km", 0.0)),
            "drive_km": res["distance_km"],
            "drive_min": res["duration_min"],
            "co2_kg": res["co2_kg"],
            "geometry": res.get("geometry"),  # may be None if include_geometry=False
        })
    return pd.DataFrame(rows).sort_values(["drive_min", "drive_km"]).reset_index(drop=True)