"""
Helper API calls for Mapbox Isochrone, postcodes.io and OSRM route distance.

Dependencies (pip):
    pip install requests

Usage:
    from api_config import fetch_isochrone, osrm_route, geocode_postcode
"""

import os
from typing import Dict, List

import requests

# --- SSL verification controls (for corporate TLS interception) ---
# Set REQUESTS_CA_BUNDLE to your corporate root CA (e.g., C:\certs\corp-root.pem)
# Optionally set DISABLE_SSL_VERIFY=true for a local smoke test (not recommended).
_CA_BUNDLE = os.getenv("REQUESTS_CA_BUNDLE")
_DISABLE_VERIFY = os.getenv("DISABLE_SSL_VERIFY", "").lower() in ("1", "true", "yes")

def _verify_arg():
    if _CA_BUNDLE:
        return _CA_BUNDLE
    return False if _DISABLE_VERIFY else True

# --- Mapbox Isochrone ---
API_KEY = os.getenv(
    "MAPBOX_TOKEN",
    "pk.eyJ1IjoiYWxleGNsYXJrZ2MiLCJhIjoiY2lqNXY4YWdhMDA0N3Z4bTNtd3NubXdjaSJ9.rEKvp-TAA_eCrA-snwCgsg",
)
BASE_URL = "https://api.mapbox.com/isochrone/v1/mapbox"
PROFILE = "driving-traffic"
CONTOUR_LEVELS = [15, 30, 45, 60]  # minutes

# Allow override via env; fall back to your local path
SAVE_DIR = os.getenv(
    "ISOCHRONES_DIR",
    "C:/Users/alex.clark/OneDrive - Ground Control/Learning Resources/Data Science Degree/Computational Concepts and Algorithms/010/Isochrones/",
)

def fetch_isochrone(lon: float, lat: float, minutes: List[int] = None):
    """
    Return GeoJSON isochrone polygons for the given point.
    """
    if minutes is None:
        minutes = CONTOUR_LEVELS
    url = f"{BASE_URL}/{PROFILE}/{lon},{lat}"
    params = {
        "contours_minutes": ",".join(str(m) for m in minutes),
        "polygons": "true",
        "access_token": API_KEY,
    }
    r = requests.get(url, params=params, timeout=30, verify=_verify_arg())
    r.raise_for_status()
    return r.json()

# --- OSRM for route distance & simple CO2 estimate ---
OSRM_BASE = os.getenv("OSRM_BASE", "https://router.project-osrm.org")

# Simple average tailpipe factor (kg CO2e per km)
CO2_PER_KM_KG = float(os.getenv("CO2_PER_KM_KG", "0.171"))

def osrm_route(
    start_lon: float,
    start_lat: float,
    dest_lon: float,
    dest_lat: float,
):
    """
    Query OSRM for a single driving route.
    Returns distance (km), duration (minutes), and a basic CO2 estimate (kg).
    """
    url = f"{OSRM_BASE}/route/v1/driving/{start_lon},{start_lat};{dest_lon},{dest_lat}"
    params = {
        "overview": "false",
        "alternatives": "false",
        "steps": "false",
        "geometries": "geojson",
    }
    r = requests.get(url, params=params, timeout=30, verify=_verify_arg())
    r.raise_for_status()
    data = r.json()
    route = data["routes"][0]

    distance_km = route["distance"] / 1000.0
    duration_min = route["duration"] / 60.0
    co2_kg = distance_km * CO2_PER_KM_KG

    return {
        "distance_km": distance_km,
        "duration_min": duration_min,
        "co2_kg": co2_kg,
    }

# --- postcodes.io geocoding ---
def geocode_postcode(postcode: str):
    """
    Return (lon, lat) for a UK postcode via postcodes.io.
    Keep it minimal; add error handling later if you wish.
    """
    url = f"https://api.postcodes.io/postcodes/{postcode.replace(' ', '')}"
    r = requests.get(url, timeout=15, verify=_verify_arg())
    r.raise_for_status()
    result = r.json()["result"]
    return float(result["longitude"]), float(result["latitude"])