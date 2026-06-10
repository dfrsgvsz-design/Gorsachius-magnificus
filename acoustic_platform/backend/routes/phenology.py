"""Phenology analysis endpoints."""

from fastapi import APIRouter, Query

import main as _main

router = APIRouter(tags=["Phenology"])


@router.get("/api/phenology/{species}")
async def get_phenology(species: str, year: int = Query(default=2025)):
    """Get phenology metrics for a species in a given year."""
    return _main.phenology_engine.compute_phenometrics(species, year)


@router.get("/api/phenology/{species}/trend")
async def get_phenology_trend(
    species: str, years: str = Query(default="2023,2024,2025")
):
    """Detect multi-year phenological shift for a species."""
    year_list = [int(y.strip()) for y in years.split(",") if y.strip().isdigit()]
    return _main.phenology_engine.detect_phenological_shift(species, year_list)


@router.get("/api/phenology/overview/{year}")
async def get_phenology_overview(year: int):
    """Get phenology overview for all species detected in a year."""
    return {"year": year, "species": _main.phenology_engine.get_species_overview(year)}
