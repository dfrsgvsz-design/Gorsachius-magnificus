"""
iNaturalist API Client for Bird Sound Platform.
Provides access to community-verified species observations, photo identification,
and regional biodiversity data across all taxonomic groups.
No API key required for read-only access (rate limit: 60 req/min).
"""

import requests
from typing import Optional

API_BASE = "https://api.inaturalist.org/v1"


def _get(path: str, params: dict = None, timeout: int = 20):
    try:
        resp = requests.get(
            f"{API_BASE}{path}",
            params=params or {},
            headers={"User-Agent": "BirdSoundPlatform/1.0"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"iNaturalist request failed: {e}"}


def search_taxa(query: str, taxon_id: Optional[int] = None, limit: int = 10):
    """Search for taxa by name."""
    params = {"q": query, "per_page": limit}
    if taxon_id:
        params["taxon_id"] = taxon_id
    return _get("/taxa", params)


def get_observations(
    taxon_id: Optional[int] = None,
    taxon_name: Optional[str] = None,
    place_id: Optional[int] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: int = 20,
    quality_grade: str = "research",
    per_page: int = 30,
    iconic_taxa: Optional[str] = None,
):
    """Search observations with filters."""
    params = {
        "quality_grade": quality_grade,
        "per_page": min(per_page, 200),
        "order": "desc",
        "order_by": "observed_on",
    }
    if taxon_id:
        params["taxon_id"] = taxon_id
    if taxon_name:
        params["taxon_name"] = taxon_name
    if place_id:
        params["place_id"] = place_id
    if lat is not None and lng is not None:
        params["lat"] = lat
        params["lng"] = lng
        params["radius"] = radius_km
    if iconic_taxa:
        params["iconic_taxa"] = iconic_taxa
    return _get("/observations", params)


def get_species_counts(
    place_id: Optional[int] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: int = 50,
    iconic_taxa: Optional[str] = None,
    per_page: int = 50,
):
    """Get species counts for an area (most observed species)."""
    params = {"per_page": min(per_page, 500)}
    if place_id:
        params["place_id"] = place_id
    if lat is not None and lng is not None:
        params["lat"] = lat
        params["lng"] = lng
        params["radius"] = radius_km
    if iconic_taxa:
        params["iconic_taxa"] = iconic_taxa
    return _get("/observations/species_counts", params)


def identify_image_url(photo_url: str):
    """Use iNaturalist's computer vision to identify a species from an image URL.
    Note: This is a simplified approach; the full CV API requires authentication.
    """
    return _get("/computervision/score_image", {"image_url": photo_url})


def get_places(query: str):
    """Search for places by name."""
    return _get("/places/autocomplete", {"q": query})


CHINA_PLACE_IDS = {
    "China": 6903,
    "Guangxi": 132536,
    "Guizhou": 132537,
    "Yunnan": 132538,
    "Guangdong": 132539,
    "Hainan": 132545,
    "Fujian": 132540,
    "Sichuan": 132541,
    "Taiwan": 7153,
}

ICONIC_TAXA = {
    "birds": "Aves",
    "amphibians": "Amphibia",
    "reptiles": "Reptilia",
    "mammals": "Mammalia",
    "plants": "Plantae",
    "insects": "Insecta",
    "fungi": "Fungi",
}
