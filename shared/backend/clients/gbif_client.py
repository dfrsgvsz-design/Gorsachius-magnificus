"""
GBIF (Global Biodiversity Information Facility) API Client.
Provides access to species occurrence records, taxonomy, and distribution data
for all taxonomic groups (birds, amphibians, reptiles, plants, etc.).
No API key required for read-only access.
"""

import requests
from typing import Optional

API_BASE = "https://api.gbif.org/v1"


def _get(path: str, params: dict = None, timeout: int = 20):
    try:
        resp = requests.get(f"{API_BASE}{path}", params=params or {}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"GBIF request failed: {e}"}


def search_species(name: str, limit: int = 10):
    """Search GBIF for species by name (scientific or common)."""
    return _get("/species/search", {"q": name, "limit": limit})


def get_species(key: int):
    """Get detailed species info by GBIF taxon key."""
    return _get(f"/species/{key}")


def species_match(name: str):
    """Match a name to the GBIF backbone taxonomy."""
    return _get("/species/match", {"name": name, "verbose": "true"})


def get_occurrences(
    taxon_key: Optional[int] = None,
    scientific_name: Optional[str] = None,
    country: str = "CN",
    limit: int = 50,
    has_coordinate: bool = True,
    year: Optional[str] = None,
):
    """Search occurrence records with filters."""
    params = {
        "limit": min(limit, 300),
        "hasCoordinate": str(has_coordinate).lower(),
    }
    if taxon_key:
        params["taxonKey"] = taxon_key
    if scientific_name:
        params["scientificName"] = scientific_name
    if country:
        params["country"] = country
    if year:
        params["year"] = year
    return _get("/occurrence/search", params)


def get_occurrences_by_location(
    lat: float,
    lng: float,
    radius_km: float = 10,
    taxon_key: Optional[int] = None,
    limit: int = 50,
):
    """Search occurrence records near a coordinate."""
    params = {
        "decimalLatitude": f"{lat - radius_km / 111:.4f},{lat + radius_km / 111:.4f}",
        "decimalLongitude": f"{lng - radius_km / (111 * abs(max(0.01, __import__('math').cos(__import__('math').radians(lat))))):.4f},{lng + radius_km / (111 * abs(max(0.01, __import__('math').cos(__import__('math').radians(lat))))):.4f}",
        "hasCoordinate": "true",
        "limit": min(limit, 300),
    }
    if taxon_key:
        params["taxonKey"] = taxon_key
    return _get("/occurrence/search", params)


def get_species_in_country(
    country: str = "CN", class_name: Optional[str] = None, limit: int = 100
):
    """List species recorded in a country, optionally filtered by class."""
    params = {"country": country, "limit": min(limit, 1000)}
    if class_name:
        params["class"] = class_name
    return _get("/species/search", params)


TAXON_CLASSES = {
    "birds": "Aves",
    "amphibians": "Amphibia",
    "reptiles": "Reptilia",
    "mammals": "Mammalia",
    "plants": "Plantae",
    "insects": "Insecta",
    "fish": "Actinopterygii",
}
