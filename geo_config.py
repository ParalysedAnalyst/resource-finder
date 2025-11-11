"""
Geometry helpers for isochrone filtering.

- isochrone_to_gdf: Mapbox Isochrone GeoJSON -> GeoDataFrame with a 'minutes' column
- teams_to_gdf: field team DataFrame (Latitude/Longitude) -> GeoDataFrame of Points
- filter_teams_by_minutes: keep only teams inside a chosen isochrone band
"""

import geopandas as gpd
from shapely.geometry import Point, shape
import pandas as pd

def isochrone_to_gdf(iso_geojson) -> gpd.GeoDataFrame:
    """
    Convert Mapbox Isochrone GeoJSON to a GeoDataFrame with columns:
      - minutes (int)
      - geometry (Polygon/MultiPolygon)
    """
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


def teams_to_gdf(fieldteams_df: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Build a GeoDataFrame of team locations from columns: Latitude, Longitude.
    Drops rows missing coordinates.
    """
    ft = fieldteams_df.dropna(subset=["Latitude", "Longitude"]).copy()
    ft["Longitude"] = ft["Longitude"].astype(float)
    ft["Latitude"] = ft["Latitude"].astype(float)
    geom = [Point(xy) for xy in zip(ft["Longitude"], ft["Latitude"])]
    return gpd.GeoDataFrame(ft, geometry=geom, crs="EPSG:4326")


def filter_teams_by_minutes(teams_gdf: gpd.GeoDataFrame,
                            iso_gdf: gpd.GeoDataFrame,
                            minutes: int = 60) -> gpd.GeoDataFrame:
    """
    Return only teams contained within the isochrone polygon for `minutes`.

    Notes:
    - If Mapbox returns multiple polygons for the same contour, union them.
    """
    sel = iso_gdf[iso_gdf["minutes"] == minutes]
    if sel.empty:
        # Nothing to filter by; return empty GeoDataFrame with same columns
        return teams_gdf.iloc[0:0].copy()

    # Union in case multiple polygons exist for the chosen contour
    target_poly = sel.unary_union
    mask = teams_gdf.within(target_poly)
    return teams_gdf[mask].reset_index(drop=True)

def list_business_units(df):
    """
    Return a sorted list of distinct Business Units (for a dropdown).
    """
    vals = df["BusinessUnit"].dropna().astype(str).unique().tolist()
    vals.sort()
    return ["(Any)"] + vals

def filter_by_business_unit(teams_gdf, business_unit: str | None):
    """
    If business_unit is '(Any)' or None, return unchanged.
    Otherwise filter rows where BusinessUnit == business_unit.
    """
    if not business_unit or business_unit == "(Any)":
        return teams_gdf
    return teams_gdf[teams_gdf["BusinessUnit"].astype(str) == str(business_unit)].reset_index(drop=True)

def filter_by_internal_flag(teams_gdf, internal_flag: int | None):
    """
    internal_flag can be:
      - 1 for Directly Employed
      - 0 for Contractor
      - None for both (no filtering)
    """
    if internal_flag in (0, 1):
        return teams_gdf[teams_gdf["InternalContractor"].astype(int) == int(internal_flag)].reset_index(drop=True)
    return teams_gdf

def apply_team_filters(teams_gdf, *, business_unit: str | None = None, internal_flag: int | None = None):
    """Chain BU and internal/contractor filters."""
    out = filter_by_business_unit(teams_gdf, business_unit)
    out = filter_by_internal_flag(out, internal_flag)
    return out.reset_index(drop=True)
