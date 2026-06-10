"""
eBird API 2.0 Client for Bird Sound Platform.
Provides access to regional species checklists, hotspot data,
and recent observations for cross-referencing acoustic detections.
"""

import os
import json
import requests
from pathlib import Path
from typing import Optional

API_BASE = "https://api.ebird.org/v2"
_CONFIG_DIR = Path(
    os.environ.get("BIRD_PLATFORM_CONFIG_DIR", Path.home() / ".bird_sound_platform")
).expanduser()
_KEY_FILE = _CONFIG_DIR / "ebird_api_key"


def _load_api_key() -> str:
    key = os.environ.get("EBIRD_API_KEY", "")
    if key:
        return key
    try:
        if _KEY_FILE.exists():
            return _KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def set_api_key(key: str):
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_text(key.strip(), encoding="utf-8")


def get_api_key() -> str:
    return _load_api_key()


def _headers():
    return {"X-eBirdApiToken": _load_api_key()}


def _get(path: str, params: dict = None, timeout: int = 20) -> list | dict:
    key = _load_api_key()
    if not key:
        return {
            "error": "eBird API Key not configured. Get one at ebird.org/api/keygen"
        }
    try:
        resp = requests.get(
            f"{API_BASE}{path}",
            params=params or {},
            headers=_headers(),
            timeout=timeout,
        )
        if resp.status_code == 403:
            return {"error": "eBird API Key invalid or expired"}
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"eBird request failed: {e}"}


def get_recent_observations(
    region_code: str, back: int = 14, max_results: int = 100
) -> list | dict:
    """Get recent observations for a region (e.g. 'CN-45' for Guangxi)."""
    return _get(
        f"/data/obs/{region_code}/recent",
        {
            "back": min(back, 30),
            "maxResults": max_results,
        },
    )


def get_recent_notable(region_code: str, back: int = 14) -> list | dict:
    """Get recent notable/rare observations for a region."""
    return _get(f"/data/obs/{region_code}/recent/notable", {"back": min(back, 30)})


def get_nearby_observations(
    lat: float, lng: float, dist: int = 25, back: int = 14
) -> list | dict:
    """Get observations near a coordinate (radius in km, max 50)."""
    return _get(
        "/data/obs/geo/recent",
        {
            "lat": lat,
            "lng": lng,
            "dist": min(dist, 50),
            "back": min(back, 30),
        },
    )


def get_nearby_species(
    lat: float, lng: float, species_code: str, dist: int = 50, back: int = 30
) -> list | dict:
    """Get nearby observations of a specific species."""
    return _get(
        f"/data/obs/geo/recent/{species_code}",
        {
            "lat": lat,
            "lng": lng,
            "dist": min(dist, 50),
            "back": min(back, 30),
        },
    )


def get_hotspots(region_code: str) -> list | dict:
    """List birding hotspots in a region."""
    return _get(f"/ref/hotspot/{region_code}", {"fmt": "json"})


def get_nearby_hotspots(lat: float, lng: float, dist: int = 25) -> list | dict:
    """Find hotspots near a coordinate."""
    return _get(
        "/ref/hotspot/geo",
        {
            "lat": lat,
            "lng": lng,
            "dist": min(dist, 50),
            "fmt": "json",
        },
    )


def get_region_species_list(region_code: str) -> list | dict:
    """Get the complete species list for a region."""
    return _get(f"/product/spplist/{region_code}")


def get_checklist_feed(
    region_code: str, year: int, month: int, day: int, max_results: int = 10
) -> list | dict:
    """Get recent checklists submitted in a region on a given date."""
    return _get(
        f"/product/lists/{region_code}/{year}/{month}/{day}",
        {
            "maxResults": max_results,
        },
    )


CHINA_REGION_CODES = {
    "China": "CN",
    "Guangxi": "CN-45",
    "Guizhou": "CN-52",
    "Yunnan": "CN-53",
    "Guangdong": "CN-44",
    "Hunan": "CN-43",
    "Fujian": "CN-35",
    "Jiangxi": "CN-36",
    "Zhejiang": "CN-33",
    "Sichuan": "CN-51",
    "Hainan": "CN-46",
    "Hubei": "CN-42",
    "Anhui": "CN-34",
    "Chongqing": "CN-50",
    "Taiwan": "TW",
    "Hong Kong": "HK",
    "Macau": "MO",
}
