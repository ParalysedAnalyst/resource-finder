"""
Geometry helpers and local filters:
- isochrone_to_gdf: Mapbox Isochrone GeoJSON -> GeoDataFrame('minutes', 'geometry')
- teams_to_gdf: DataFrame -> GeoDataFrame of Point geometries
- filter_teams_by_minutes: subset inside selected isochrone band
- list_business_units / apply_team_filters: local attribute filters
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, shape


# Create function to convert JSON to geo datafram in GeoPandas
def isochrone_to_gdf(iso_geojson):
    features = iso_geojson.get("features", []) if iso_geojson else []
    if not features:
        return gpd.GeoDataFrame(columns=["minutes", "geometry"], geometry="geometry", crs="EPSG:4326")

    rows = []
    for f in features:
        props = f.get("properties", {})
        minutes = int(props.get("contour"))
        geom = shape(f["geometry"])
        rows.append({"minutes": minutes, "geometry": geom})

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    return gdf.sort_values("minutes").reset_index(drop=True)

# Convert coordinates to point
def teams_to_gdf(fieldteams_df: pd.DataFrame):
    ft = fieldteams_df.dropna(subset=["Latitude", "Longitude"]).copy()
    ft["Longitude"] = ft["Longitude"].astype(float)
    ft["Latitude"] = ft["Latitude"].astype(float)
    return gpd.GeoDataFrame(ft, geometry=[Point(xy) for xy in zip(ft["Longitude"], ft["Latitude"])], crs="EPSG:4326")

# Filter fieldteams within shape file
def filter_teams_by_minutes(teams_gdf: gpd.GeoDataFrame, iso_gdf: gpd.GeoDataFrame, minutes: int = 60):
    sel = iso_gdf[iso_gdf["minutes"] == minutes]
    if sel.empty:
        return teams_gdf.iloc[0:0].copy()
    target_poly = sel.unary_union  # union to handle multi-polygons
    return teams_gdf[teams_gdf.within(target_poly)].reset_index(drop=True)

# Create list of business units for drop-down
def list_business_units(df: pd.DataFrame) -> list[str]:
    vals = df["BusinessUnit"].dropna().astype(str).unique().tolist()
    vals.sort()
    return ["(Any)"] + vals

# Filter fieldteams based on business unit selected 
def filter_by_business_unit(teams_gdf: gpd.GeoDataFrame, business_unit: str | None):
    if not business_unit or business_unit == "(Any)":
        return teams_gdf
    return teams_gdf[teams_gdf["BusinessUnit"].astype(str) == str(business_unit)].reset_index(drop=True)

# Filter fieldteams based on internalcontractor field to select directly employed, sub-contracted or both
def filter_by_internal_flag(teams_gdf: gpd.GeoDataFrame, internal_flag: int | None):
    if internal_flag in (0, 1):
        return teams_gdf[teams_gdf["InternalContractor"].astype(int) == int(internal_flag)].reset_index(drop=True)
    return teams_gdf

# Apply filters to fieldteams
def apply_team_filters(teams_gdf: gpd.GeoDataFrame, *, business_unit: str | None = None, internal_flag: int | None = None):
    out = filter_by_business_unit(teams_gdf, business_unit)
    out = filter_by_internal_flag(out, internal_flag)
    return out.reset_index(drop=True)