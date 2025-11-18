"""
External API helpers:
- postcodes.io geocoding
- Mapbox Isochrones (single call returns 15/30/45/60)
- OSRM routing (distance, time, simple CO2)
"""

import os
import warnings
from typing import Dict
import requests
import urllib3

# TLS / proxy handling
VERIFY_DEFAULT = os.getenv("VERIFY_DEFAULT", "false").lower() in ("1", "true", "yes")
SUPPRESS_TLS_WARNINGS = os.getenv("SUPPRESS_TLS_WARNINGS", "true").lower() in ("1", "true", "yes")
if SUPPRESS_TLS_WARNINGS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    warnings.filterwarnings(
        "ignore",
        message=r"Unverified HTTPS request is being made to host",
        category=urllib3.exceptions.InsecureRequestWarning,
        module=r"urllib3\.connectionpool",
    )

def _verify_arg():
    ca_bundle = os.getenv("REQUESTS_CA_BUNDLE")
    return ca_bundle if ca_bundle else VERIFY_DEFAULT  # False by default

def _proxies():
    http = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    return {"http": http, "https": https} if (http or https) else None

# Mapbox Isochrone API
API_KEY = os.getenv(
    "MAPBOX_TOKEN",
    "pk.eyJ1IjoiYWxleGNsYXJrZ2MiLCJhIjoiY2lqNXY4YWdhMDA0N3Z4bTNtd3NubXdjaSJ9.rEKvp-TAA_eCrA-snwCgsg",
)
BASE_URL = "https://api.mapbox.com/isochrone/v1/mapbox"
PROFILE = "driving-traffic"
CONTOUR_LEVELS = [15, 30, 45, 60]  # minutes

def fetch_isochrone(lon: float, lat: float):
    """Return Isochrone GeoJSON for 15/30/45/60 minutes in a single call."""
    url = f"{BASE_URL}/{PROFILE}/{lon},{lat}"
    params = {
        "contours_minutes": ",".join(str(m) for m in CONTOUR_LEVELS),
        "polygons": "true",
        "access_token": API_KEY,
    }
    r = requests.get(url, params=params, timeout=30, verify=_verify_arg(), proxies=_proxies())
    r.raise_for_status()
    return r.json()

# OSRM routing API
OSRM_BASE = os.getenv("OSRM_BASE", "https://router.project-osrm.org")
CO2_PER_KM_KG = float(os.getenv("CO2_PER_KM_KG", "0.171"))

def osrm_route(
    start_lon: float,
    start_lat: float,
    dest_lon: float,
    dest_lat: float,
) -> Dict[str, float]:
    """Return distance_km, duration_min, co2_kg for a single route."""
    url = f"{OSRM_BASE}/route/v1/driving/{start_lon},{start_lat};{dest_lon},{dest_lat}"
    params = {"overview": "false", "alternatives": "false", "steps": "false", "geometries": "geojson"}
    r = requests.get(url, params=params, timeout=30, verify=_verify_arg(), proxies=_proxies())
    r.raise_for_status()
    route = r.json()["routes"][0]
    distance_km = route["distance"] / 1000.0
    duration_min = route["duration"] / 60.0
    return {"distance_km": distance_km, "duration_min": duration_min, "co2_kg": distance_km * CO2_PER_KM_KG}

# postcodes.io API
class PostcodeNotFound(Exception):
    """Raised when postcodes.io returns 404 for a supplied postcode."""
    pass

def geocode_postcode(postcode: str):
    """
    Return (lon, lat). Raise PostcodeNotFound on 404; HTTPError otherwise.
    """
    pc = postcode.strip().upper()
    url = f"https://api.postcodes.io/postcodes/{pc.replace(' ', '')}"
    r = requests.get(url, timeout=15, verify=_verify_arg(), proxies=_proxies())

    if r.status_code == 404:
        try:
            msg = r.json().get("error", f"Postcode not found: {pc}")
        except Exception:
            msg = f"Postcode not found: {pc}"
        raise PostcodeNotFound(msg)

    r.raise_for_status()
    result = r.json()["result"]
    return float(result["longitude"]), float(result["latitude"])