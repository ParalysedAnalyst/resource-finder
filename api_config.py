"""
Tiny config + helper calls for Mapbox Isochrone and OSRM route distance.

Dependencies (pip):
    pip install requests

Usage:
    from api_config import fetch_isochrone, osrm_route
"""

import os
from typing import Dict, Any, List

import requests

#Mapbox Isochrone
API_KEY = os.getenv(
    "MAPBOX_TOKEN",
    "pk.eyJ1IjoiYWxleGNsYXJrZ2MiLCJhIjoiY2lqNXY4YWdhMDA0N3Z4bTNtd3NubXdjaSJ9.rEKvp-TAA_eCrA-snwCgsg",
)
BASE_URL = "https://api.mapbox.com/isochrone/v1/mapbox"
PROFILE = "driving-traffic"
CONTOUR_LEVELS = [15, 30, 45, 60]  # minutes
SAVE_DIR = r"C:\Users\alex.clark\OneDrive - Ground Control\Learning Resources\Data Science Degree\Computational Concepts and Algorithms\010\Isochrones\"

def fetch_isochrone(lon: float, lat: float, minutes: List[int] = CONTOUR_LEVELS) -> Dict[str, Any]:
    """
    Return GeoJSON isochrone polygons for the given point.
    Keep it simple: polygons=true, default Mapbox generalisation.
    """
    url = f"{BASE_URL}/{PROFILE}/{lon},{lat}"
    params = {
        "contours_minutes": ",".join(str(m) for m in minutes),
        "polygons": "true",
        "access_token": API_KEY,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# OSRM  for route distance & simple CO2 estimate
OSRM_BASE = os.getenv("OSRM_BASE", "https://router.project-osrm.org")

# Simple average tailpipe factor (kg CO2e per km). Tweak later as needed.
CO2_PER_KM_KG = float(os.getenv("CO2_PER_KM_KG", "0.171"))

def osrm_route(
    start_lon: float,
    start_lat: float,
    dest_lon: float,
    dest_lat: float,
) -> Dict[str, float]:
    """
    Query OSRM for a single driving route.
    Returns distance (km), duration (minutes), and a basic CO2 estimate (kg).
    """
    url = f"{OSRM_BASE}/route/v1/driving/{start_lon},{start_lat};{dest_lon},{dest_lat}"
    params = {
        "overview": "false",
        "alternatives": "false",
        "steps": "false",
    }
    r = requests.get(url, params=params, timeout=30)
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