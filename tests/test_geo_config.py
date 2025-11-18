import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
import geo_config as geo

def test_isochrone_to_gdf_basic():
    gj = {"features":[{"type":"Feature","properties":{"contour":"60"},"geometry":{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}}]}
    gdf = geo.isochrone_to_gdf(gj)
    assert list(gdf["minutes"]) == [60]
    assert gdf.crs.to_epsg() == 4326

def test_teams_to_gdf_and_filter_minutes():
    df = pd.DataFrame({
        "Contractor":["A","B"], "BusinessUnit":["X","Y"], "Postcode":["P1","P2"],
        "Latitude":[0.5, 2.0], "Longitude":[0.5, 2.0], "InternalContractor":[1,0]
    })
    teams = geo.teams_to_gdf(df)
    iso = gpd.GeoDataFrame({"minutes":[60]}, geometry=[Polygon([(0,0),(1,0),(1,1),(0,1),(0,0)])], crs="EPSG:4326")
    inside = geo.filter_teams_by_minutes(teams, iso, minutes=60)
    assert len(inside) == 1
    assert inside.iloc[0]["Contractor"] == "A"

def test_apply_team_filters():
    df = pd.DataFrame({
        "Contractor":["A","B","C"], "BusinessUnit":["X","X","Y"], "Postcode":["P1","P2","P3"],
        "Latitude":[0,0,0], "Longitude":[0,0,0], "InternalContractor":[1,0,1]
    })
    teams = geo.teams_to_gdf(df)
    bu = geo.filter_by_business_unit(teams, "X")
    assert set(bu["Contractor"]) == {"A","B"}
    both = geo.apply_team_filters(teams, business_unit="X", internal_flag=1)
    assert list(both["Contractor"]) == ["A"]