"""
Pre-Survey Species Planner.
Uses eBird regional data, local species database, and SDM predictions
to generate expected species checklists for survey areas.
"""

from typing import Dict, List, Optional, Set


def generate_expected_species(
    ebird_species_codes: List[str] = None,
    ebird_recent_obs: List[dict] = None,
    local_db_species: List[dict] = None,
    sdm_predicted_species: List[str] = None,
    detection_history: List[dict] = None,
    region: str = "",
) -> dict:
    """Generate a comprehensive expected species list for a survey area.

    Merges data from multiple sources to create a pre-survey checklist
    with priority levels and expected detection methods.
    """
    species_map: Dict[str, dict] = {}

    if ebird_species_codes:
        for code in ebird_species_codes:
            species_map.setdefault(
                code,
                {
                    "code": code,
                    "sources": [],
                    "priority": "low",
                    "expected_detection": [],
                    "recent_observations": 0,
                },
            )
            species_map[code]["sources"].append("ebird_regional")

    if ebird_recent_obs:
        for obs in ebird_recent_obs:
            name = obs.get("comName") or obs.get("sciName", "")
            code = obs.get("speciesCode", name)
            if not code:
                continue
            entry = species_map.setdefault(
                code,
                {
                    "code": code,
                    "sources": [],
                    "priority": "low",
                    "expected_detection": [],
                    "recent_observations": 0,
                },
            )
            if "ebird_recent" not in entry["sources"]:
                entry["sources"].append("ebird_recent")
            entry["recent_observations"] += 1
            entry["common_name"] = obs.get("comName", "")
            entry["scientific_name"] = obs.get("sciName", "")
            entry["location"] = obs.get("locName", "")

    if local_db_species:
        for sp in local_db_species:
            sci = sp.get("scientific_name") or sp.get("scientific", "")
            if not sci:
                continue
            entry = species_map.setdefault(
                sci,
                {
                    "code": sci,
                    "sources": [],
                    "priority": "low",
                    "expected_detection": [],
                    "recent_observations": 0,
                },
            )
            if "local_database" not in entry["sources"]:
                entry["sources"].append("local_database")
            entry["chinese_name"] = sp.get("chinese_name") or sp.get("chinese", "")
            entry["english_name"] = sp.get("english_name") or sp.get("english", "")
            entry.setdefault("scientific_name", sci)
            entry["expected_detection"].append("acoustic")

    if sdm_predicted_species:
        for sp in sdm_predicted_species:
            entry = species_map.setdefault(
                sp,
                {
                    "code": sp,
                    "sources": [],
                    "priority": "low",
                    "expected_detection": [],
                    "recent_observations": 0,
                },
            )
            if "sdm_prediction" not in entry["sources"]:
                entry["sources"].append("sdm_prediction")
            entry["priority"] = "high"

    if detection_history:
        for det in detection_history:
            sp = det.get("species") or det.get("species_scientific", "")
            if sp and sp in species_map:
                if "prior_detection" not in species_map[sp]["sources"]:
                    species_map[sp]["sources"].append("prior_detection")
                species_map[sp]["priority"] = "high"

    for code, entry in species_map.items():
        n_sources = len(entry["sources"])
        if n_sources >= 3:
            entry["priority"] = "very_high"
        elif n_sources >= 2 or entry.get("recent_observations", 0) > 2:
            entry["priority"] = "high"
        elif "sdm_prediction" in entry["sources"]:
            entry["priority"] = "high"
        elif entry.get("recent_observations", 0) > 0:
            entry["priority"] = "medium"

    priority_order = {"very_high": 0, "high": 1, "medium": 2, "low": 3}
    sorted_species = sorted(
        species_map.values(),
        key=lambda x: (
            priority_order.get(x["priority"], 9),
            -x.get("recent_observations", 0),
        ),
    )

    priority_counts = {"very_high": 0, "high": 0, "medium": 0, "low": 0}
    for sp in sorted_species:
        priority_counts[sp["priority"]] = priority_counts.get(sp["priority"], 0) + 1

    return {
        "region": region,
        "total_expected_species": len(sorted_species),
        "priority_breakdown": priority_counts,
        "data_sources_used": list({s for sp in sorted_species for s in sp["sources"]}),
        "species_checklist": sorted_species,
    }


def generate_survey_protocol(
    expected_species: dict,
    site_count: int = 1,
    days_available: int = 5,
    team_size: int = 3,
) -> dict:
    """Generate a survey protocol recommendation based on expected species."""
    total = expected_species.get("total_expected_species", 0)
    high_priority = sum(
        1
        for sp in expected_species.get("species_checklist", [])
        if sp.get("priority") in ("very_high", "high")
    )

    recommended_visits = min(max(3, high_priority // 5 + 2), days_available * 2)
    aru_stations = min(site_count * 2, 10)

    return {
        "recommended_survey_visits": recommended_visits,
        "aru_stations_recommended": aru_stations,
        "camera_traps_recommended": min(site_count * 3, 15),
        "point_count_duration_minutes": 10 if total < 50 else 15,
        "transect_length_m": 500 if total < 50 else 1000,
        "dawn_chorus_recording_hours": "05:00-07:30",
        "dusk_recording_hours": "17:30-19:30",
        "notes": [
            f"Target {high_priority} high-priority species across {site_count} site(s).",
            f"With {team_size} team members, plan ~{recommended_visits} survey visits.",
            "Deploy ARUs for overnight recordings to capture nocturnal species.",
            "Camera traps should be placed along known animal trails near water sources.",
        ],
    }
