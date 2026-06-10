from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree as ET

try:
    from runtime_paths import get_backend_dir, get_data_dir, get_resource_data_dir
except ImportError:  # pragma: no cover - package import path
    from .runtime_paths import get_backend_dir, get_data_dir, get_resource_data_dir

try:
    from taxonomy_catalog import get_taxonomy_catalog
except ImportError:  # pragma: no cover - package import path
    from .taxonomy_catalog import get_taxonomy_catalog


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _coerce_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in ("", None):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    if value in ("", None):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _loads_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _round_float(value: Any, digits: int = 2) -> float:
    number = _coerce_float(value, 0.0) or 0.0
    return round(number, digits)


def _csv_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    if any(char in text for char in [",", '"', "\n", "\r"]):
        return '"' + text.replace('"', '""') + '"'
    return text


def _safe_export_name(value: Any, default: str = "route") -> str:
    text = str(value or "").strip().replace("/", "_").replace("\\", "_")
    return text or default


def _first_non_empty(payload: dict, *paths: str) -> str:
    for path in paths:
        current: Any = payload
        for part in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current not in (None, ""):
            return str(current).strip()
    return ""


def _string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        results: list[str] = []
        for item in value:
            results.extend(_string_list(item))
        return results
    return [str(value).strip()] if str(value).strip() else []


def _summarize_numeric_values(values: list[float]) -> dict:
    if not values:
        return {}
    rounded = [round(value, 2) for value in values]
    return {
        "min": round(min(rounded), 2),
        "max": round(max(rounded), 2),
        "avg": round(sum(rounded) / len(rounded), 2),
    }


def _extract_species_identity(observation: dict) -> dict:
    scientific_name = _first_non_empty(
        observation,
        "scientific_name",
        "ai_suggestion.scientific_name",
        "extra.scientific_name",
    )
    chinese_name = _first_non_empty(
        observation,
        "chinese_name",
        "ai_suggestion.chinese_name",
        "extra.chinese_name",
    )
    english_name = _first_non_empty(
        observation,
        "english_name",
        "ai_suggestion.english_name",
        "extra.english_name",
    )
    display_name = scientific_name or chinese_name or english_name
    if not display_name:
        display_name = (
            "Unknown taxon"
            if _coerce_bool(observation.get("unknown_taxon"))
            else "Unidentified"
        )
    return {
        "scientific_name": scientific_name,
        "chinese_name": chinese_name,
        "english_name": english_name,
        "taxon_group": observation.get("taxon_group") or "",
        "display_name": display_name,
    }


def _observer_names(record: dict) -> list[str]:
    extra = record.get("extra") or {}
    candidates = [
        record.get("observer"),
        record.get("observers"),
        extra.get("observer"),
        extra.get("observers"),
        extra.get("recorded_by"),
        extra.get("recordedBy"),
    ]
    seen: set[str] = set()
    names: list[str] = []
    for candidate in candidates:
        for name in _string_list(candidate):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _weather_samples(record: dict) -> list[dict]:
    samples: list[dict] = []
    seen: set[str] = set()
    extra = record.get("extra") or {}
    dict_candidates = [
        record.get("weather"),
        extra.get("weather"),
    ]
    for candidate in dict_candidates:
        if isinstance(candidate, dict) and candidate:
            sample_key = json.dumps(candidate, sort_keys=True, ensure_ascii=False)
            if sample_key in seen:
                continue
            seen.add(sample_key)
            samples.append(candidate)

    alias_keys = {
        "condition": "condition",
        "conditions": "conditions",
        "sky": "sky",
        "notes": "notes",
        "wind": "wind",
        "precipitation_type": "precipitation_type",
        "temperature_c": "temperature_c",
        "temperature": "temperature_c",
        "humidity_pct": "humidity_pct",
        "humidity": "humidity_pct",
        "wind_speed_mps": "wind_speed_mps",
        "wind_speed": "wind_speed_mps",
        "precipitation_mm": "precipitation_mm",
        "precipitation": "precipitation_mm",
        "visibility_m": "visibility_m",
        "visibility": "visibility_m",
        "cloud_cover_pct": "cloud_cover_pct",
        "cloud_cover": "cloud_cover_pct",
    }
    for source in (record, extra):
        flattened: dict[str, Any] = {}
        for source_key, target_key in alias_keys.items():
            value = source.get(source_key)
            if value not in (None, ""):
                flattened[target_key] = value
        if flattened:
            samples.append(flattened)
    return samples


def _aggregate_weather(records: list[dict]) -> dict:
    text_fields = {
        "conditions": set(),
        "sky": set(),
        "wind": set(),
        "notes": set(),
        "precipitation_type": set(),
    }
    numeric_fields: dict[str, list[float]] = defaultdict(list)
    sample_count = 0

    for record in records:
        for sample in _weather_samples(record):
            sample_count += 1
            for value in _string_list(sample.get("condition")) + _string_list(
                sample.get("conditions")
            ):
                text_fields["conditions"].add(value)
            for field in ("sky", "wind", "notes", "precipitation_type"):
                for value in _string_list(sample.get(field)):
                    text_fields[field].add(value)
            for field in (
                "temperature_c",
                "humidity_pct",
                "wind_speed_mps",
                "precipitation_mm",
                "visibility_m",
                "cloud_cover_pct",
            ):
                numeric_value = _coerce_float(sample.get(field))
                if numeric_value is not None:
                    numeric_fields[field].append(numeric_value)

    summary: dict[str, Any] = {"samples": sample_count}
    for field, values in text_fields.items():
        if values:
            summary[field] = sorted(values)
    for field, values in numeric_fields.items():
        metrics = _summarize_numeric_values(values)
        if metrics:
            summary[field] = metrics
    return summary


def _species_summary_csv(summary: dict) -> str:
    columns = [
        "scientific_name",
        "chinese_name",
        "english_name",
        "taxon_group",
        "observation_count",
        "individual_count",
        "observer_names",
        "first_observed_at",
        "last_observed_at",
    ]
    rows = [",".join(columns)]
    for species in summary.get("species", []):
        rows.append(
            ",".join(
                _csv_escape(value)
                for value in [
                    species.get("scientific_name", ""),
                    species.get("chinese_name", ""),
                    species.get("english_name", ""),
                    species.get("taxon_group", ""),
                    species.get("observation_count", 0),
                    species.get("individual_count", 0),
                    "; ".join(species.get("observers", [])),
                    species.get("first_observed_at", ""),
                    species.get("last_observed_at", ""),
                ]
            )
        )
    return "\n".join(rows) + "\n"


_TERRESTRIAL_VERTEBRATE_PROTOCOLS = {
    "bird_line_transect",
    "bird_point_count",
    "mammal_trap_net",
    "herp_infrared_camera",
}

_TERRESTRIAL_VERTEBRATE_PAYLOADS: dict[str, dict[str, list[str]]] = {
    "bird_line_transect": {
        "event": [
            "transect_name",
            "transect_length_m",
            "survey_round",
            "observer_count",
            "weather",
            "distance_walked_m",
            "duration_min",
            "pace_m_per_min",
            "wind_code",
            "cloud_code",
            "precipitation_code",
            "habitat_type",
            "disturbance_notes",
        ],
        "record": [
            "taxon_id",
            "detection_type",
            "count",
            "observation_time",
            "distance_band",
            "bearing",
            "behavior",
            "breeding_code",
            "flock_size",
            "route_segment_id",
        ],
    },
    "bird_point_count": {
        "event": [
            "point_id",
            "point_visit_index",
            "point_duration_min",
            "observer_count",
            "weather",
            "point_radius_m",
            "station_count",
            "travel_distance_m",
            "wind_code",
            "cloud_code",
            "precipitation_code",
            "habitat_type",
        ],
        "record": [
            "taxon_id",
            "detection_type",
            "count",
            "observation_time",
            "distance_band",
            "behavior",
            "breeding_code",
            "point_id",
            "flock_size",
            "confidence",
        ],
    },
    "mammal_trap_net": {
        "event": [
            "trap_method",
            "trap_station_count",
            "deployment_start_time",
            "deployment_end_time",
            "bait_type",
            "observer_count",
            "trap_model",
            "check_interval_h",
            "microhabitat",
            "permit_reference",
            "welfare_notes",
            "trap_nights",
            "active_trap_count",
            "checked_station_count",
        ],
        "record": [
            "taxon_id",
            "capture_status",
            "observation_time",
            "trap_station_id",
            "protected_coordinate_policy",
            "mark_code",
            "sex",
            "life_stage",
            "body_mass_g",
            "release_status",
            "sample_collected",
        ],
    },
    "herp_infrared_camera": {
        "event": [
            "camera_station_id",
            "camera_action",
            "deployment_start_time",
            "deployment_end_time",
            "camera_model",
            "observer_count",
            "sensor_mode",
            "trigger_interval_s",
            "camera_height_cm",
            "orientation",
            "bait_lure",
            "habitat",
            "camera_days",
            "active_camera_count",
            "file_count",
        ],
        "record": [
            "taxon_id",
            "observation_time",
            "evidence_type",
            "camera_station_id",
            "individual_count",
            "life_stage",
            "behavior",
            "media_file_id",
            "sequence_id",
            "confidence",
        ],
    },
}

_PROTOCOL_FIELD_ALIASES: dict[str, dict[str, dict[str, str]]] = {
    "mammal_trap_net": {
        "event": {
            "animal_welfare_notes": "welfare_notes",
        },
        "record": {
            "individual_mark": "mark_code",
        },
    },
    "herp_infrared_camera": {
        "event": {
            "height_cm": "camera_height_cm",
            "bait_or_lure": "bait_lure",
            "habitat_type": "habitat",
            "image_or_video_file_count": "file_count",
        },
        "record": {
            "detection_time": "observation_time",
            "detection_confidence": "confidence",
        },
    },
}

_EVENT_PAYLOAD_EXCLUDED_FIELDS = {"start_time", "end_time"}

_PAYLOAD_INT_FIELDS = {
    "observer_count",
    "survey_round",
    "point_visit_index",
    "station_count",
    "trap_station_count",
    "active_trap_count",
    "checked_station_count",
    "active_camera_count",
    "file_count",
    "count",
    "flock_size",
    "individual_count",
}

_PAYLOAD_FLOAT_FIELDS = {
    "transect_length_m",
    "distance_walked_m",
    "duration_min",
    "pace_m_per_min",
    "point_duration_min",
    "point_radius_m",
    "travel_distance_m",
    "check_interval_h",
    "trap_nights",
    "body_mass_g",
    "trigger_interval_s",
    "camera_height_cm",
    "camera_days",
    "confidence",
    "bearing",
}

_PAYLOAD_BOOL_FIELDS = {"sample_collected"}


def _weather_text(weather: Any) -> str:
    if isinstance(weather, str):
        return weather.strip()
    if not isinstance(weather, dict):
        return ""
    values: list[str] = []
    for key in (
        "conditions",
        "condition",
        "sky",
        "wind",
        "notes",
        "precipitation_type",
    ):
        for item in _string_list(weather.get(key)):
            if item and item not in values:
                values.append(item)
    return "; ".join(values)


def _stringify_weather_payload(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        return _dumps_json(value)
    if isinstance(value, (list, tuple)):
        return _dumps_json(list(value))
    return str(value).strip()


def _normalize_payload_value(field: str, value: Any) -> Any:
    if field in _PAYLOAD_BOOL_FIELDS:
        return _coerce_bool(value)
    if field in _PAYLOAD_INT_FIELDS:
        return _coerce_int(value, 0)
    if field in _PAYLOAD_FLOAT_FIELDS:
        return _round_float(value, 2)
    return "" if value in (None, "") else value


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def _payload_value(
    payload: Optional[dict],
    key: str,
    existing: Optional[dict] = None,
    default: Any = "",
) -> Any:
    if isinstance(payload, dict) and key in payload:
        return payload.get(key)
    if isinstance(existing, dict) and key in existing:
        return existing.get(key)
    return default


def _payload_value_from_keys(
    payload: Optional[dict],
    keys: Iterable[str],
    existing: Optional[dict] = None,
    default: Any = "",
) -> Any:
    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                return payload.get(key)
    if isinstance(existing, dict):
        for key in keys:
            if key in existing:
                return existing.get(key)
    return default


def _normalize_terrestrial_event_payload(
    protocol: str,
    payload: Any,
    *,
    existing: Optional[dict] = None,
    weather: Optional[dict] = None,
    effort_metrics: Optional[dict] = None,
    observers: Optional[list[str]] = None,
    route_name: str = "",
) -> dict:
    if protocol not in _TERRESTRIAL_VERTEBRATE_PROTOCOLS:
        return payload if isinstance(payload, dict) else {}
    incoming = payload if isinstance(payload, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    effort = effort_metrics if isinstance(effort_metrics, dict) else {}
    observer_list = observers or []
    defaults: dict[str, Any] = {}

    if protocol == "bird_line_transect":
        defaults = {
            "transect_name": _first_present(route_name, current.get("transect_name")),
            "transect_length_m": _first_present(
                effort.get("transect_length_m"),
                effort.get("length_m"),
                current.get("transect_length_m"),
            ),
            "survey_round": current.get("survey_round", 0),
            "observer_count": len(observer_list) or current.get("observer_count", 0),
            "weather": _first_present(_weather_text(weather), current.get("weather")),
            "distance_walked_m": _first_present(
                effort.get("distance_walked_m"),
                effort.get("distance_m"),
                current.get("distance_walked_m"),
            ),
            "duration_min": _first_present(
                effort.get("duration_min"), current.get("duration_min")
            ),
            "pace_m_per_min": _first_present(
                effort.get("pace_m_per_min"), current.get("pace_m_per_min")
            ),
            "wind_code": _first_present(
                (weather or {}).get("wind_code"), current.get("wind_code")
            ),
            "cloud_code": _first_present(
                (weather or {}).get("cloud_code"), current.get("cloud_code")
            ),
            "precipitation_code": _first_present(
                (weather or {}).get("precipitation_code"),
                current.get("precipitation_code"),
            ),
            "habitat_type": _first_present(
                effort.get("habitat_type"), current.get("habitat_type")
            ),
            "disturbance_notes": current.get("disturbance_notes", ""),
        }
    elif protocol == "bird_point_count":
        defaults = {
            "point_id": current.get("point_id", ""),
            "point_visit_index": current.get("point_visit_index", 0),
            "point_duration_min": _first_present(
                effort.get("point_duration_min"), current.get("point_duration_min")
            ),
            "observer_count": len(observer_list) or current.get("observer_count", 0),
            "weather": _first_present(_weather_text(weather), current.get("weather")),
            "point_radius_m": _first_present(
                effort.get("point_radius_m"), current.get("point_radius_m")
            ),
            "station_count": _first_present(
                effort.get("station_count"), current.get("station_count")
            ),
            "travel_distance_m": _first_present(
                effort.get("travel_distance_m"),
                effort.get("distance_m"),
                current.get("travel_distance_m"),
            ),
            "wind_code": _first_present(
                (weather or {}).get("wind_code"), current.get("wind_code")
            ),
            "cloud_code": _first_present(
                (weather or {}).get("cloud_code"), current.get("cloud_code")
            ),
            "precipitation_code": _first_present(
                (weather or {}).get("precipitation_code"),
                current.get("precipitation_code"),
            ),
            "habitat_type": _first_present(
                effort.get("habitat_type"), current.get("habitat_type")
            ),
        }
    elif protocol == "mammal_trap_net":
        defaults = {
            "trap_method": current.get("trap_method", ""),
            "trap_station_count": _first_present(
                effort.get("trap_station_count"), current.get("trap_station_count")
            ),
            "deployment_start_time": _first_present(
                effort.get("deployment_start_time"),
                current.get("deployment_start_time"),
            ),
            "deployment_end_time": _first_present(
                effort.get("deployment_end_time"), current.get("deployment_end_time")
            ),
            "bait_type": current.get("bait_type", ""),
            "observer_count": len(observer_list) or current.get("observer_count", 0),
            "trap_model": current.get("trap_model", ""),
            "check_interval_h": _first_present(
                effort.get("check_interval_h"), current.get("check_interval_h")
            ),
            "microhabitat": current.get("microhabitat", ""),
            "permit_reference": current.get("permit_reference", ""),
            "welfare_notes": current.get("welfare_notes", ""),
            "trap_nights": _first_present(
                effort.get("trap_nights"), current.get("trap_nights")
            ),
            "active_trap_count": _first_present(
                effort.get("active_trap_count"), current.get("active_trap_count")
            ),
            "checked_station_count": _first_present(
                effort.get("checked_station_count"),
                current.get("checked_station_count"),
            ),
        }
    elif protocol == "herp_infrared_camera":
        defaults = {
            "camera_station_id": current.get("camera_station_id", ""),
            "camera_action": current.get("camera_action", ""),
            "deployment_start_time": _first_present(
                effort.get("deployment_start_time"),
                current.get("deployment_start_time"),
            ),
            "deployment_end_time": _first_present(
                effort.get("deployment_end_time"), current.get("deployment_end_time")
            ),
            "camera_model": current.get("camera_model", ""),
            "observer_count": len(observer_list) or current.get("observer_count", 0),
            "sensor_mode": current.get("sensor_mode", ""),
            "trigger_interval_s": _first_present(
                effort.get("trigger_interval_s"), current.get("trigger_interval_s")
            ),
            "camera_height_cm": _first_present(
                effort.get("camera_height_cm"), current.get("camera_height_cm")
            ),
            "orientation": current.get("orientation", ""),
            "bait_lure": current.get("bait_lure", ""),
            "habitat": current.get("habitat", ""),
            "camera_days": _first_present(
                effort.get("camera_days"), current.get("camera_days")
            ),
            "active_camera_count": _first_present(
                effort.get("active_camera_count"), current.get("active_camera_count")
            ),
            "file_count": _first_present(
                effort.get("file_count"), current.get("file_count")
            ),
        }

    normalized: dict[str, Any] = {}
    for field in _TERRESTRIAL_VERTEBRATE_PAYLOADS[protocol]["event"]:
        normalized[field] = _normalize_payload_value(
            field,
            _first_present(
                incoming.get(field), defaults.get(field), current.get(field)
            ),
        )
    return normalized


def _normalize_terrestrial_record_payload(
    protocol: str,
    payload: Any,
    *,
    existing: Optional[dict] = None,
    count: Any = None,
    evidence_type: str = "",
    observed_at: str = "",
    behavior: str = "",
    breeding_code: str = "",
    taxon_id: str = "",
) -> dict:
    if protocol not in _TERRESTRIAL_VERTEBRATE_PROTOCOLS:
        return payload if isinstance(payload, dict) else {}
    incoming = payload if isinstance(payload, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    defaults: dict[str, Any] = {}

    if protocol == "bird_line_transect":
        defaults = {
            "taxon_id": _first_present(taxon_id, current.get("taxon_id")),
            "detection_type": _first_present(
                evidence_type, current.get("detection_type")
            ),
            "count": _first_present(count, current.get("count")),
            "observation_time": _first_present(
                observed_at, current.get("observation_time")
            ),
            "distance_band": current.get("distance_band", ""),
            "bearing": current.get("bearing", ""),
            "behavior": _first_present(behavior, current.get("behavior")),
            "breeding_code": _first_present(
                breeding_code, current.get("breeding_code")
            ),
            "flock_size": _first_present(count, current.get("flock_size")),
            "route_segment_id": current.get("route_segment_id", ""),
        }
    elif protocol == "bird_point_count":
        defaults = {
            "taxon_id": _first_present(taxon_id, current.get("taxon_id")),
            "detection_type": _first_present(
                evidence_type, current.get("detection_type")
            ),
            "count": _first_present(count, current.get("count")),
            "observation_time": _first_present(
                observed_at, current.get("observation_time")
            ),
            "distance_band": current.get("distance_band", ""),
            "behavior": _first_present(behavior, current.get("behavior")),
            "breeding_code": _first_present(
                breeding_code, current.get("breeding_code")
            ),
            "point_id": current.get("point_id", ""),
            "flock_size": _first_present(count, current.get("flock_size")),
            "confidence": current.get("confidence", ""),
        }
    elif protocol == "mammal_trap_net":
        defaults = {
            "taxon_id": _first_present(taxon_id, current.get("taxon_id")),
            "capture_status": current.get("capture_status", ""),
            "observation_time": _first_present(
                observed_at, current.get("observation_time")
            ),
            "trap_station_id": current.get("trap_station_id", ""),
            "protected_coordinate_policy": current.get(
                "protected_coordinate_policy", ""
            ),
            "mark_code": current.get("mark_code", ""),
            "sex": current.get("sex", ""),
            "life_stage": current.get("life_stage", ""),
            "body_mass_g": current.get("body_mass_g", ""),
            "release_status": current.get("release_status", ""),
            "sample_collected": current.get("sample_collected", False),
        }
    elif protocol == "herp_infrared_camera":
        defaults = {
            "taxon_id": _first_present(taxon_id, current.get("taxon_id")),
            "observation_time": _first_present(
                observed_at, current.get("observation_time")
            ),
            "evidence_type": _first_present(
                evidence_type, current.get("evidence_type")
            ),
            "camera_station_id": current.get("camera_station_id", ""),
            "individual_count": _first_present(count, current.get("individual_count")),
            "life_stage": current.get("life_stage", ""),
            "behavior": _first_present(behavior, current.get("behavior")),
            "media_file_id": current.get("media_file_id", ""),
            "sequence_id": current.get("sequence_id", ""),
            "confidence": current.get("confidence", ""),
        }

    normalized: dict[str, Any] = {}
    for field in _TERRESTRIAL_VERTEBRATE_PAYLOADS[protocol]["record"]:
        normalized[field] = _normalize_payload_value(
            field,
            _first_present(
                incoming.get(field), defaults.get(field), current.get(field)
            ),
        )
    return normalized


def _coordinates_masked(observation: dict) -> bool:
    sensitivity = str(observation.get("sensitivity") or "").strip().lower()
    if sensitivity in {"sensitive", "protected", "restricted", "private", "masked"}:
        return True
    for container in (
        observation.get("record_payload"),
        observation.get("extra"),
        observation.get("ai_suggestion"),
    ):
        if not isinstance(container, dict):
            continue
        if _coerce_bool(container.get("is_sensitive")) or _coerce_bool(
            container.get("mask_coordinates")
        ):
            return True
        if str(container.get("sensitivity") or "").strip().lower() in {
            "sensitive",
            "protected",
            "restricted",
            "private",
            "masked",
        }:
            return True
        if str(container.get("protected_status") or "").strip():
            return True
        if str(container.get("protection_level") or "").strip():
            return True
    return False


def _masked_point_geometry(geometry: Any) -> Optional[dict]:
    if not isinstance(geometry, dict):
        return None
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return {"type": "Point", "coordinates": [None, None]}
    return {"type": geom_type, "coordinates": [] if coords is not None else None}


def _masked_observation_export(observation: dict, jurisdiction: str) -> dict:
    masked = _clone_jsonable(observation)
    should_mask = _coordinates_masked(observation)
    masked["coordinates_masked"] = should_mask
    masked["export_jurisdiction"] = jurisdiction
    if should_mask:
        masked["latitude"] = None
        masked["longitude"] = None
        masked["geometry"] = _masked_point_geometry(observation.get("geometry"))
    return masked


def _csv_from_rows(columns: list[str], rows: list[dict]) -> str:
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(_csv_escape(row.get(column, "")) for column in columns))
    return "\n".join(lines) + "\n"


_BACKEND_DIR = get_backend_dir()
_REPO_ROOT = _BACKEND_DIR.parent
_DATA_DIR = get_resource_data_dir()
_VERTEBRATE_EXPORT_PROFILES_CACHE: Optional[dict[str, Any]] = None
_TAXONOMY_PACKAGES_ASSET_CACHE: Optional[dict[str, Any]] = None


def _clone_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _load_json_asset(filename: str, default: Any) -> Any:
    raw_path = str(filename or "").replace("\\", "/").strip()
    if not raw_path:
        return _clone_jsonable(default)
    candidate = Path(raw_path)
    search_paths = []
    if candidate.is_absolute():
        search_paths.append(candidate)
    else:
        search_paths.extend(
            [
                _DATA_DIR / candidate,
                _REPO_ROOT / candidate,
                _DATA_DIR / candidate.name,
            ]
        )
    path = next((item for item in search_paths if item.exists()), search_paths[0])
    if not path.exists():
        return _clone_jsonable(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return _clone_jsonable(default)


def _taxonomy_package_assets(package: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for key in ("source_assets", "local_seed_assets"):
        raw_assets = package.get(key) or []
        if not isinstance(raw_assets, list):
            continue
        for asset in raw_assets:
            if not isinstance(asset, dict):
                continue
            normalized_path = str(asset.get("path") or "").replace("\\", "/").strip()
            if normalized_path and normalized_path in seen_paths:
                continue
            cloned = dict(asset)
            cloned["_asset_list_key"] = key
            assets.append(cloned)
            if normalized_path:
                seen_paths.add(normalized_path)
    return assets


def _load_vertebrate_export_profiles() -> dict[str, Any]:
    global _VERTEBRATE_EXPORT_PROFILES_CACHE
    if _VERTEBRATE_EXPORT_PROFILES_CACHE is None:
        _VERTEBRATE_EXPORT_PROFILES_CACHE = _load_json_asset(
            "vertebrate_export_profiles.json", {}
        )
    return _clone_jsonable(_VERTEBRATE_EXPORT_PROFILES_CACHE)


def _load_taxonomy_packages_asset() -> dict[str, Any]:
    global _TAXONOMY_PACKAGES_ASSET_CACHE
    if _TAXONOMY_PACKAGES_ASSET_CACHE is None:
        _TAXONOMY_PACKAGES_ASSET_CACHE = _load_json_asset("taxonomy_packages.json", {})
    return _clone_jsonable(_TAXONOMY_PACKAGES_ASSET_CACHE)


def _taxonomy_manifest_entry(jurisdiction: str, program: str) -> dict[str, Any]:
    asset = _load_taxonomy_packages_asset()
    packages = asset.get("packages") if isinstance(asset, dict) else asset
    if not isinstance(packages, list):
        return {}
    for package in packages:
        if not isinstance(package, dict):
            continue
        if (
            jurisdiction
            and str(package.get("jurisdiction") or "").strip() != jurisdiction
        ):
            continue
        if program and str(package.get("program") or "").strip() != program:
            continue
        return _clone_jsonable(package)
    return {}


def _taxonomy_release_package_status(jurisdiction: str, program: str) -> dict[str, Any]:
    jurisdiction_key = str(jurisdiction or "").strip()
    program_key = str(program or "").strip()
    if not (jurisdiction_key and program_key):
        return {}
    try:
        catalog = get_taxonomy_catalog()
    except Exception:
        return {}
    if not catalog:
        return {}
    try:
        lookup = catalog.package_status_lookup(current_only=True)
    except Exception:
        return {}
    status = lookup.get((jurisdiction_key, program_key))
    return _clone_jsonable(status) if isinstance(status, dict) else {}


def _geometry_to_wkt(geometry: Any) -> str:
    if not isinstance(geometry, dict):
        return ""
    geom_type = str(geometry.get("type") or "").strip()
    coords = geometry.get("coordinates")
    if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        lon = coords[0]
        lat = coords[1]
        if lon in (None, "") or lat in (None, ""):
            return "POINT EMPTY"
        return f"POINT ({lon} {lat})"
    return ""


def _merge_status_flags(*sources: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = _merge_status_flags(merged.get(key), value)
            elif value not in (None, "", [], {}):
                merged[key] = value
    return merged


def _merge_payload_patch(existing: Any, incoming: Any) -> Any:
    if isinstance(existing, dict) and isinstance(incoming, dict):
        merged = dict(existing)
        for key, value in incoming.items():
            merged[key] = _merge_payload_patch(existing.get(key), value)
        return merged
    return incoming


def _taxonomy_program_for_observation(observation: dict) -> str:
    extra = (
        observation.get("extra") if isinstance(observation.get("extra"), dict) else {}
    )
    record_payload = (
        observation.get("record_payload")
        if isinstance(observation.get("record_payload"), dict)
        else {}
    )
    protocol = str(
        observation.get("protocol")
        or record_payload.get("protocol")
        or extra.get("protocol")
        or ""
    ).strip()
    explicit_program = str(
        observation.get("program")
        or record_payload.get("program")
        or extra.get("program")
        or ""
    ).strip()
    return _program_for_protocol(protocol, explicit_program)


def _taxonomy_seed_entries(jurisdiction: str, program: str) -> list[dict[str, Any]]:
    asset = _load_taxonomy_packages_asset()
    packages = asset.get("packages") if isinstance(asset, dict) else asset
    if not isinstance(packages, list):
        return []
    entries: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for package in packages:
        if not isinstance(package, dict):
            continue
        if (
            jurisdiction
            and str(package.get("jurisdiction") or "").strip() != jurisdiction
        ):
            continue
        if program and str(package.get("program") or "").strip() != program:
            continue
        for local_asset in _taxonomy_package_assets(package):
            raw_path = str(local_asset.get("path") or "").replace("\\", "/").strip()
            selector = (
                local_asset.get("entry_selector")
                if isinstance(local_asset.get("entry_selector"), dict)
                else {}
            )
            if not raw_path:
                continue
            asset_entries = _load_json_asset(raw_path, [])
            if isinstance(asset_entries, dict):
                asset_entries = asset_entries.get("entries") or []
            if not isinstance(asset_entries, list):
                continue
            for entry in asset_entries:
                if not isinstance(entry, dict):
                    continue
                selected_jurisdiction = str(
                    selector.get("jurisdiction") or jurisdiction or ""
                ).strip()
                if selected_jurisdiction:
                    jurisdictions = (
                        entry.get("jurisdictions")
                        if isinstance(entry.get("jurisdictions"), dict)
                        else {}
                    )
                    jurisdiction_entry = (
                        jurisdictions.get(selected_jurisdiction)
                        if isinstance(jurisdictions, dict)
                        else {}
                    )
                    if (
                        isinstance(jurisdiction_entry, dict)
                        and jurisdiction_entry.get("present") is False
                    ):
                        continue
                key = str(
                    entry.get("internal_taxon_id") or entry.get("scientific_name") or ""
                ).strip()
                if key and key not in seen_keys:
                    entries.append(entry)
                    seen_keys.add(key)
        for entry in package.get("sample_taxon_examples") or []:
            if isinstance(entry, dict):
                key = str(
                    entry.get("internal_taxon_id") or entry.get("scientific_name") or ""
                ).strip()
                if not key or key in seen_keys:
                    continue
                entries.append(entry)
                seen_keys.add(key)
    return entries


def _taxonomy_package_completeness(jurisdiction: str, program: str) -> dict[str, Any]:
    matched_package = _taxonomy_manifest_entry(jurisdiction, program)
    release_status = _taxonomy_release_package_status(jurisdiction, program)
    seed_catalog_count = len(_taxonomy_seed_entries(jurisdiction, program))
    catalog_count = int(
        release_status.get("catalog_count")
        or release_status.get("imported_count")
        or seed_catalog_count
    )
    expected_count = int(
        release_status.get("expected_count")
        or matched_package.get("expected_count")
        or 0
    )
    count_parity_ok = bool(release_status.get("count_parity_ok"))
    if not release_status and expected_count:
        count_parity_ok = expected_count == catalog_count
    return {
        "taxonomy_release_id": str(
            release_status.get("taxonomy_release_id")
            or release_status.get("release_id")
            or ""
        ),
        "seed_only": bool(
            release_status.get(
                "seed_only", matched_package.get("seed_only", bool(catalog_count))
            )
        ),
        "exhaustive": bool(
            release_status.get(
                "exhaustive_species_content",
                matched_package.get("exhaustive_species_content", False),
            )
        ),
        "catalog_count": catalog_count,
        "expected_count": expected_count,
        "imported_count": int(release_status.get("imported_count") or catalog_count),
        "count_parity_ok": count_parity_ok,
        "review_status": str(release_status.get("review_status") or ""),
        "is_current_release": bool(release_status.get("is_current_release")),
    }


def _taxonomy_entry_for_observation(
    observation: dict, jurisdiction: str
) -> dict[str, Any]:
    extra = (
        observation.get("extra") if isinstance(observation.get("extra"), dict) else {}
    )
    record_payload = (
        observation.get("record_payload")
        if isinstance(observation.get("record_payload"), dict)
        else {}
    )
    taxon_id = str(
        observation.get("taxon_id")
        or record_payload.get("taxon_id")
        or extra.get("taxon_id")
        or ""
    ).strip()
    scientific_name = str(
        observation.get("scientific_name")
        or record_payload.get("scientific_name")
        or extra.get("scientific_name")
        or ""
    ).strip()
    program = _taxonomy_program_for_observation(observation)

    resolved: dict[str, Any] = {}
    try:
        catalog = get_taxonomy_catalog()
    except Exception:
        catalog = None
    if catalog and (taxon_id or scientific_name):
        try:
            resolved = catalog.resolve_taxon(
                program=program,
                jurisdiction=jurisdiction,
                taxon_id=taxon_id,
                scientific_name=scientific_name,
            )
        except Exception:
            resolved = {}

    matched: dict[str, Any] = {}
    if not resolved:
        candidates = _taxonomy_seed_entries(jurisdiction, program)
        for entry in candidates:
            if (
                taxon_id
                and str(entry.get("internal_taxon_id") or "").strip() == taxon_id
            ):
                matched = entry
                break
            if (
                scientific_name
                and str(entry.get("scientific_name") or "").strip().lower()
                == scientific_name.lower()
            ):
                matched = entry
                break

    resolved_names = (
        resolved.get("names") if isinstance(resolved.get("names"), dict) else {}
    )
    resolved_statuses = (
        resolved.get("statuses") if isinstance(resolved.get("statuses"), dict) else {}
    )
    resolved_classification = (
        resolved.get("classification")
        if isinstance(resolved.get("classification"), dict)
        else {}
    )

    names = {
        "zh_cn": str(
            resolved_names.get("simplified_chinese_name")
            or resolved_names.get("zh_cn")
            or matched.get("simplified_chinese_name")
            or observation.get("chinese_name")
            or ""
        ).strip(),
        "zh_tw": str(
            resolved_names.get("traditional_chinese_name")
            or resolved_names.get("zh_tw")
            or matched.get("traditional_chinese_name")
            or observation.get("chinese_name")
            or ""
        ).strip(),
        "scientific": str(
            resolved.get("scientific_name")
            or resolved_names.get("scientific_name")
            or matched.get("scientific_name")
            or scientific_name
            or ""
        ).strip(),
        "en": str(
            resolved_names.get("english_common_name")
            or resolved_names.get("en")
            or matched.get("english_common_name")
            or observation.get("english_name")
            or ""
        ).strip(),
    }
    matched_jurisdictions = (
        matched.get("jurisdictions")
        if isinstance(matched.get("jurisdictions"), dict)
        else {}
    )
    matched_jurisdiction = (
        matched_jurisdictions.get(jurisdiction)
        if isinstance(matched_jurisdictions, dict)
        else {}
    )
    mapped_seed_flags: dict[str, Any] = {}
    if isinstance(matched_jurisdiction, dict):
        sensitive_policy = str(
            matched_jurisdiction.get("sensitive_coordinate_policy") or ""
        ).strip()
        protected_status = str(
            matched_jurisdiction.get("national_protection_status")
            or matched_jurisdiction.get("taiwan_protection_status")
            or ""
        ).strip()
        mapped_seed_flags = {
            jurisdiction: {
                "present": matched_jurisdiction.get("present"),
                "red_list_status": matched_jurisdiction.get("red_list_status"),
                "protected_status": protected_status,
                "protection_level": protected_status,
                "national_protection": matched_jurisdiction.get(
                    "national_protection_status"
                ),
                "taiwan_protection": matched_jurisdiction.get(
                    "taiwan_protection_status"
                ),
                "sensitive_coordinate_policy": sensitive_policy,
                "coordinate_masking": sensitive_policy
                not in {"", "open", "public", "not_applicable"},
                "is_protected": bool(protected_status),
                "is_sensitive": sensitive_policy
                not in {"", "open", "public", "not_applicable"},
            }
        }
    raw_status = _merge_status_flags(
        resolved_statuses,
        matched.get("status_flags"),
        mapped_seed_flags,
        extra.get("taxonomy_status_flags"),
        record_payload.get("taxonomy_status_flags"),
        observation.get("taxonomy_status_flags"),
    )
    jurisdiction_status = raw_status.get(jurisdiction)
    if isinstance(jurisdiction_status, dict):
        jurisdiction_flags = _merge_status_flags(jurisdiction_status)
    else:
        jurisdiction_flags = {}
    if raw_status and not jurisdiction_flags:
        jurisdiction_flags = {
            key: value
            for key, value in raw_status.items()
            if not isinstance(value, dict)
        }
    return {
        "internal_taxon_id": str(
            resolved.get("taxon_id") or resolved.get("internal_taxon_id") or taxon_id
        ).strip(),
        "names": names,
        "status_flags": {
            jurisdiction: jurisdiction_flags,
        },
        "group": str(
            resolved.get("submodule")
            or resolved_classification.get("group")
            or matched.get("group")
            or observation.get("taxon_group")
            or ""
        ).strip(),
    }


def _export_mask_info(
    observation: dict, taxonomy: dict, jurisdiction: str
) -> dict[str, Any]:
    record_payload = (
        observation.get("record_payload")
        if isinstance(observation.get("record_payload"), dict)
        else {}
    )
    extra = (
        observation.get("extra") if isinstance(observation.get("extra"), dict) else {}
    )
    jurisdiction_flags = (taxonomy.get("status_flags") or {}).get(jurisdiction) or {}
    policy = (
        str(
            record_payload.get("protected_coordinate_policy")
            or extra.get("protected_coordinate_policy")
            or ""
        )
        .strip()
        .lower()
    )
    masking_reason = ""
    sensitive_policy = (
        str(jurisdiction_flags.get("sensitive_coordinate_policy") or "").strip().lower()
    )
    if policy in {"mask", "masked", "protected", "sensitive"}:
        masking_reason = "record_coordinate_policy"
    elif (
        _coerce_bool(jurisdiction_flags.get("is_sensitive"))
        or _coerce_bool(jurisdiction_flags.get("is_protected"))
        or _coerce_bool(jurisdiction_flags.get("coordinate_masking"))
        or sensitive_policy not in {"", "open", "public", "not_applicable"}
        or str(jurisdiction_flags.get("protected_status") or "").strip()
    ):
        masking_reason = "taxonomy_status_flags"
    elif _coordinates_masked(observation):
        masking_reason = "record_sensitivity"

    coordinate_masked = bool(masking_reason)
    display_latitude = None if coordinate_masked else observation.get("latitude")
    display_longitude = None if coordinate_masked else observation.get("longitude")
    display_geometry_wkt = (
        "POINT EMPTY"
        if coordinate_masked
        else _geometry_to_wkt(observation.get("geometry"))
    )
    return {
        "coordinate_masked": coordinate_masked,
        "masking_reason": masking_reason,
        "display_latitude": display_latitude,
        "display_longitude": display_longitude,
        "display_geometry_wkt": display_geometry_wkt,
    }


def _resolve_source_value(source: str, context: dict[str, Any]) -> Any:
    alias_map = {
        "event.start_time": "event.started_at",
        "event.end_time": "event.ended_at",
    }
    path = alias_map.get(source, source)
    if path.startswith("record.export_mask."):
        path = path.replace("record.export_mask.", "export_mask.", 1)
    elif path.startswith("record.taxonomy."):
        path = path.replace("record.taxonomy.", "taxonomy.", 1)
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _aggregate_contexts(contexts: list[dict[str, Any]], column: dict[str, Any]) -> Any:
    aggregation = str(column.get("aggregation") or "").strip().lower()
    source = str(column.get("source") or "").strip()
    fallback_source = str(column.get("fallback_source") or "").strip()
    if not aggregation:
        for context in contexts:
            value = _resolve_source_value(source, context)
            if value in (None, "") and fallback_source:
                value = _resolve_source_value(fallback_source, context)
            if value not in (None, ""):
                return value
        return ""

    values: list[Any] = []
    if source == "records":
        values = [context.get("records") or [] for context in contexts]
    else:
        for context in contexts:
            value = _resolve_source_value(source, context)
            if value in (None, "") and fallback_source:
                value = _resolve_source_value(fallback_source, context)
            values.append(value)

    if aggregation == "count":
        if source == "records":
            return sum(len(value) for value in values if isinstance(value, list))
        return sum(1 for value in values if value not in (None, ""))
    if aggregation == "count_distinct":
        distinct = {
            (
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list))
                else str(value)
            )
            for value in values
            if value not in (None, "")
        }
        return len(distinct)
    if aggregation == "sum":
        return round(sum(_coerce_float(value, 0.0) or 0.0 for value in values), 2)
    if aggregation == "max":
        present = [value for value in values if value not in (None, "")]
        return max(present) if present else ""
    if aggregation == "min":
        present = [value for value in values if value not in (None, "")]
        return min(present) if present else ""
    return ""


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius_m = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def _line_length_m(points: Iterable[list]) -> float:
    coords = [p for p in points if len(p) >= 2]
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for first, second in zip(coords, coords[1:]):
        total += _haversine_m(first[0], first[1], second[0], second[1])
    return round(total, 2)


def _extract_line_coordinates(geometry: Optional[dict]) -> list:
    if not geometry or not isinstance(geometry, dict):
        return []
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if geom_type == "LineString":
        return coords
    if geom_type == "MultiLineString":
        merged = []
        for segment in coords:
            if not isinstance(segment, list):
                continue
            if merged and segment and merged[-1] == segment[0]:
                merged.extend(segment[1:])
            else:
                merged.extend(segment)
        return merged
    if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return [coords]
    return []


def _feature_collection_for_line(record: dict) -> dict:
    geometry = record.get("geometry") or {"type": "LineString", "coordinates": []}
    properties = {
        "id": record.get("route_id") or record.get("track_id"),
        "name": record.get("name", ""),
        "route_type": record.get("route_type"),
        "source": record.get("source"),
        "length_m": record.get("length_m") or record.get("distance_m"),
        "project_id": record.get("project_id"),
        "site_id": record.get("site_id"),
    }
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    k: v for k, v in properties.items() if v not in (None, "")
                },
            }
        ],
    }


def _route_summary_csv(record: dict) -> str:
    columns = [
        "id",
        "name",
        "project_id",
        "site_id",
        "route_type",
        "length_m",
        "point_count",
        "source",
        "updated_at",
    ]
    row = [
        record.get("route_id") or record.get("track_id", ""),
        record.get("name", ""),
        record.get("project_id", ""),
        record.get("site_id", ""),
        record.get("route_type", ""),
        str(record.get("length_m") or record.get("distance_m") or 0),
        str(len(_extract_line_coordinates(record.get("geometry")))),
        record.get("source", ""),
        record.get("updated_at", ""),
    ]
    return (
        ",".join(columns)
        + "\n"
        + ",".join(value.replace(",", " ") for value in row)
        + "\n"
    )


def _build_gpx_document(
    name: str, points: list, point_times: Optional[list] = None
) -> str:
    gpx = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "Biodiversity Field Survey Platform",
            "xmlns": "http://www.topografix.com/GPX/1/1",
        },
    )
    trk = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = name or "track"
    trkseg = ET.SubElement(trk, "trkseg")
    for idx, point in enumerate(points):
        if len(point) < 2:
            continue
        trkpt = ET.SubElement(
            trkseg,
            "trkpt",
            {"lon": str(point[0]), "lat": str(point[1])},
        )
        if len(point) >= 3:
            ET.SubElement(trkpt, "ele").text = str(point[2])
        if point_times and idx < len(point_times) and point_times[idx]:
            ET.SubElement(trkpt, "time").text = point_times[idx]
    return ET.tostring(gpx, encoding="unicode", xml_declaration=True)


def _normalize_geojson_geometry(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("GeoJSON payload must be an object")
    geo_type = payload.get("type")
    if geo_type == "FeatureCollection":
        features = payload.get("features") or []
        for feature in features:
            if feature.get("geometry"):
                geometry = feature["geometry"]
                coords = _extract_line_coordinates(geometry)
                if coords:
                    return {"type": "LineString", "coordinates": coords}
        raise ValueError(
            "GeoJSON FeatureCollection does not contain a LineString feature"
        )
    if geo_type == "Feature":
        geometry = payload.get("geometry") or {}
        coords = _extract_line_coordinates(geometry)
        if not coords:
            raise ValueError(
                "GeoJSON feature geometry must be a line or point geometry"
            )
        return {"type": "LineString", "coordinates": coords}
    coords = _extract_line_coordinates(payload)
    if not coords:
        raise ValueError("Unsupported GeoJSON geometry")
    return {"type": "LineString", "coordinates": coords}


def _parse_geojson_text(content: str) -> dict:
    data = json.loads(content)
    geometry = _normalize_geojson_geometry(data)
    return {
        "geometry": geometry,
        "point_times": [],
        "length_m": _line_length_m(geometry.get("coordinates") or []),
    }


def _parse_gpx_text(content: str) -> dict:
    root = ET.fromstring(content)
    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}")[0] + "}"

    points = []
    point_times = []
    for tag_name in ("trkpt", "rtept"):
        for point in root.findall(f".//{namespace}{tag_name}"):
            lon = _coerce_float(point.attrib.get("lon"))
            lat = _coerce_float(point.attrib.get("lat"))
            if lon is None or lat is None:
                continue
            ele = _coerce_float(point.findtext(f"{namespace}ele"))
            coords = [lon, lat]
            if ele is not None:
                coords.append(ele)
            points.append(coords)
            point_times.append(point.findtext(f"{namespace}time") or "")

    if not points:
        raise ValueError("GPX file does not contain track or route points")

    geometry = {"type": "LineString", "coordinates": points}
    return {
        "geometry": geometry,
        "point_times": point_times,
        "length_m": _line_length_m(points),
    }


def _slippy_tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    lat_rad = math.radians(lat)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int(
        (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi)
        / 2.0
        * n
    )
    return x, y


def _estimate_tile_count(bbox: dict, min_zoom: int, max_zoom: int) -> int:
    if not bbox:
        return 0
    min_lat = _coerce_float(bbox.get("min_lat"), 0.0)
    max_lat = _coerce_float(bbox.get("max_lat"), 0.0)
    min_lon = _coerce_float(bbox.get("min_lon"), 0.0)
    max_lon = _coerce_float(bbox.get("max_lon"), 0.0)
    if min_lat is None or max_lat is None or min_lon is None or max_lon is None:
        return 0
    total = 0
    for zoom in range(min_zoom, max_zoom + 1):
        min_x, max_y = _slippy_tile_xy(min_lon, min_lat, zoom)
        max_x, min_y = _slippy_tile_xy(max_lon, max_lat, zoom)
        total += (abs(max_x - min_x) + 1) * (abs(max_y - min_y) + 1)
    return total


def _normalize_protocol_field_name(protocol: str, section: str, field_name: str) -> str:
    aliases = _PROTOCOL_FIELD_ALIASES.get(protocol, {}).get(section, {})
    return aliases.get(str(field_name or "").strip(), str(field_name or "").strip())


def _canonical_payload_fields(
    protocol: str, section: str, field_groups: dict[str, Any]
) -> list[str]:
    section_key = str(section or "").strip()
    configured = {}
    if isinstance(field_groups, dict):
        if any(key in field_groups for key in ("required", "optional", "effort")):
            configured = field_groups
        else:
            configured = field_groups.get(section_key) or {}
    if not isinstance(configured, dict):
        configured = {}
    keys: list[str] = []
    for group_name in ("required", "optional", "effort"):
        for field_name in configured.get(group_name) or []:
            normalized = _normalize_protocol_field_name(
                protocol, section_key, str(field_name or "").strip()
            )
            if not normalized:
                continue
            if section_key == "event" and normalized in _EVENT_PAYLOAD_EXCLUDED_FIELDS:
                continue
            if normalized not in keys:
                keys.append(normalized)
    return keys


def _protocol_submodules(
    protocol: str, program: str = "", definition: Optional[dict[str, Any]] = None
) -> list[str]:
    protocol_key = str(protocol or "").strip()
    if isinstance(definition, dict):
        configured = [
            str(item or "").strip()
            for item in definition.get("submodules") or []
            if str(item or "").strip()
        ]
        if configured:
            return configured
    program_key = str(program or "").strip()
    if program_key == "terrestrial_vertebrates":
        if protocol_key.startswith("bird_"):
            return ["birds"]
        if protocol_key.startswith("mammal_"):
            return ["mammals"]
        if protocol_key.startswith("herp_"):
            return ["reptiles", "amphibians"]
    if program_key in {"plants", "insects"}:
        return [program_key]
    return []


def _protocol_submodule(
    protocol: str, program: str, definition: Optional[dict[str, Any]] = None
) -> str:
    submodules = _protocol_submodules(protocol, program, definition)
    if set(submodules) == {"reptiles", "amphibians"}:
        return "herpetofauna"
    if len(submodules) == 1:
        return submodules[0]
    return ""


def _required_event_fields(protocol: str, event_payload_fields: list[str]) -> list[str]:
    required = ["started_at", "ended_at", "observers"]
    if any(
        field in event_payload_fields
        for field in ("weather", "wind_code", "cloud_code", "precipitation_code")
    ):
        required.append("weather")
    if protocol in _TERRESTRIAL_VERTEBRATE_PROTOCOLS or any(
        field in event_payload_fields
        for field in (
            "distance_walked_m",
            "duration_min",
            "trap_nights",
            "camera_days",
            "sampled_area_m2",
        )
    ):
        required.append("effort_metrics")
    if protocol in {"mammal_trap_net", "herp_infrared_camera"}:
        required.append("event_payload")
    return required


def _required_record_fields(
    protocol: str, record_payload_fields: list[str]
) -> list[str]:
    required = ["event_id", "taxon_id_or_name", "observed_at"]
    if any(field in record_payload_fields for field in ("count", "individual_count")):
        required.append("count")
    if any(
        field in record_payload_fields for field in ("evidence_type", "detection_type")
    ):
        required.append("evidence")
    if protocol in {"bird_line_transect", "bird_point_count", "insect_transect"}:
        required.append("geometry")
    if protocol in {
        "mammal_trap_net",
        "herp_infrared_camera",
        "plant_quadrat",
        "plant_transect",
    }:
        required.append("record_payload")
    return required


def _normalize_protocol_definition(asset_item: dict[str, Any]) -> dict[str, Any]:
    protocol = str(
        asset_item.get("protocol_id") or asset_item.get("protocol") or ""
    ).strip()
    program = str(asset_item.get("program") or "").strip()
    structured_event_fields = (
        asset_item.get("event_fields")
        if isinstance(asset_item.get("event_fields"), dict)
        else {}
    )
    structured_record_fields = (
        asset_item.get("record_fields")
        if isinstance(asset_item.get("record_fields"), dict)
        else {}
    )
    event_payload_fields = _canonical_payload_fields(
        protocol, "event", structured_event_fields
    )
    record_payload_fields = _canonical_payload_fields(
        protocol, "record", structured_record_fields
    )
    submodules = _protocol_submodules(protocol, program, asset_item)
    submodule = _protocol_submodule(protocol, program, asset_item)
    track_policy = str(asset_item.get("track_policy") or "").strip()
    design_asset_types = list(asset_item.get("design_asset_types") or [])
    return {
        "protocol": protocol,
        "protocol_id": protocol,
        "version": str(asset_item.get("version") or ""),
        "program": program,
        "module": str(asset_item.get("module") or program),
        "label": str(
            asset_item.get("display_name") or asset_item.get("label") or protocol
        ),
        "display_name": str(
            asset_item.get("display_name") or asset_item.get("label") or protocol
        ),
        "description": str(asset_item.get("description") or ""),
        "jurisdictions": list(asset_item.get("jurisdictions") or []),
        "sampling_unit": str(asset_item.get("sampling_unit") or ""),
        "design_asset_types": design_asset_types,
        "track_policy": track_policy,
        "offline_requirements": list(asset_item.get("offline_requirements") or []),
        "requires_asset": bool(design_asset_types),
        "supports_track": track_policy in {"required", "optional"},
        "required_event_fields": _required_event_fields(protocol, event_payload_fields),
        "required_record_fields": _required_record_fields(
            protocol, record_payload_fields
        ),
        "event_fields": json.loads(
            json.dumps(structured_event_fields, ensure_ascii=False)
        ),
        "record_fields": json.loads(
            json.dumps(structured_record_fields, ensure_ascii=False)
        ),
        "event_payload_fields": event_payload_fields,
        "record_payload_fields": record_payload_fields,
        "has_structured_event_fields": bool(structured_event_fields),
        "has_structured_record_fields": bool(structured_record_fields),
        "export_profiles": list(asset_item.get("export_profiles") or []),
        "standards_refs": list(asset_item.get("standards_refs") or []),
        "submodules": submodules,
        "submodule": submodule,
        "submodule_label": submodule.replace("_", " ").title() if submodule else "",
    }


def _load_protocol_definitions_asset() -> list[dict[str, Any]]:
    asset = _load_json_asset("survey_protocols.json", {"protocols": []})
    protocol_items = asset.get("protocols") if isinstance(asset, dict) else []
    results: list[dict[str, Any]] = []
    for item in protocol_items or []:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_protocol_definition(item)
        if normalized.get("protocol"):
            results.append(normalized)
    return results


_PROTOCOL_DEFINITIONS: list[dict[str, Any]] = _load_protocol_definitions_asset()

_PROTOCOL_INDEX = {item["protocol"]: item for item in _PROTOCOL_DEFINITIONS}

_TAXONOMY_PACKAGES: list[dict[str, Any]] = [
    {
        "package_id": "cn-mainland-terrestrial-vertebrates",
        "jurisdiction": "mainland_china",
        "region": "mainland_china",
        "label": "Mainland China Terrestrial Vertebrates",
        "label_zh": "中国大陆陆生脊椎动物",
        "program": "terrestrial_vertebrates",
        "protocols": [
            "bird_line_transect",
            "bird_point_count",
            "mammal_trap_net",
            "herp_infrared_camera",
        ],
        "taxa_groups": ["birds", "mammals", "amphibians", "reptiles"],
        "languages": ["zh-Hans", "en", "scientific"],
        "backbone": "MEE biodiversity monitoring standards",
    },
    {
        "package_id": "cn-mainland-plants",
        "jurisdiction": "mainland_china",
        "region": "mainland_china",
        "label": "Mainland China Plants",
        "label_zh": "中国大陆植物",
        "program": "plants",
        "protocols": ["plant_quadrat", "plant_transect"],
        "taxa_groups": ["vascular_plants"],
        "languages": ["zh-Hans", "en", "scientific"],
        "backbone": "MEE terrestrial vascular plant standards",
    },
    {
        "package_id": "cn-mainland-insects",
        "jurisdiction": "mainland_china",
        "region": "mainland_china",
        "label": "Mainland China Insects",
        "label_zh": "中国大陆昆虫",
        "program": "insects",
        "protocols": ["insect_transect"],
        "taxa_groups": ["insects"],
        "languages": ["zh-Hans", "en", "scientific"],
        "backbone": "County biodiversity survey technical regulations",
    },
    {
        "package_id": "tw-terrestrial-vertebrates",
        "jurisdiction": "taiwan",
        "region": "taiwan",
        "label": "Taiwan Terrestrial Vertebrates",
        "label_zh": "台湾陆生脊椎动物",
        "program": "terrestrial_vertebrates",
        "protocols": [
            "bird_line_transect",
            "bird_point_count",
            "mammal_trap_net",
            "herp_infrared_camera",
        ],
        "taxa_groups": ["birds", "mammals", "amphibians", "reptiles"],
        "languages": ["zh-Hant", "en", "scientific"],
        "backbone": "TaiCOL + Taiwan monitoring manuals",
    },
    {
        "package_id": "tw-plants",
        "jurisdiction": "taiwan",
        "region": "taiwan",
        "label": "Taiwan Plants",
        "label_zh": "台湾植物",
        "program": "plants",
        "protocols": ["plant_quadrat", "plant_transect"],
        "taxa_groups": ["vascular_plants"],
        "languages": ["zh-Hant", "en", "scientific"],
        "backbone": "TaiCOL flora mapping package",
    },
    {
        "package_id": "tw-insects",
        "jurisdiction": "taiwan",
        "region": "taiwan",
        "label": "Taiwan Insects",
        "label_zh": "台湾昆虫",
        "program": "insects",
        "protocols": ["insect_transect"],
        "taxa_groups": ["insects"],
        "languages": ["zh-Hant", "en", "scientific"],
        "backbone": "TaiCOL insect checklist package",
    },
]
def _program_for_protocol(protocol: str, fallback: str = "") -> str:
    protocol_key = str(protocol or "").strip()
    if protocol_key and protocol_key in _PROTOCOL_INDEX:
        return str(_PROTOCOL_INDEX[protocol_key]["program"])
    return str(fallback or "").strip()


def _protocol_definition(protocol: str) -> dict[str, Any]:
    protocol_key = str(protocol or "").strip()
    return _clone_jsonable(_PROTOCOL_INDEX.get(protocol_key) or {})


def _submodule_for_protocol(protocol: str, fallback_program: str = "") -> str:
    program = _program_for_protocol(protocol, fallback_program)
    return _protocol_submodule(
        protocol, program, _PROTOCOL_INDEX.get(str(protocol or "").strip()) or {}
    )


def _payload_submodule(payload: Optional[dict], existing: Optional[dict] = None) -> str:
    for source in (payload, existing):
        if not isinstance(source, dict):
            continue
        value = source.get("submodule")
        if value not in (None, ""):
            return str(value).strip()
        extra = source.get("extra")
        if isinstance(extra, dict) and extra.get("submodule") not in (None, ""):
            return str(extra.get("submodule") or "").strip()
    return ""


def _normalize_submodule(
    protocol: str,
    program: str,
    payload: Optional[dict],
    existing: Optional[dict] = None,
) -> str:
    explicit = _payload_submodule(payload, existing)
    definition = _protocol_definition(protocol)
    allowed = _protocol_submodules(protocol, program, definition)
    inferred = _protocol_submodule(protocol, program, definition)
    if explicit and allowed and explicit not in allowed and explicit != inferred:
        raise ValueError(
            f"submodule: protocol {protocol or '<unknown>'} supports {', '.join(allowed)}, received {explicit}"
        )
    if explicit:
        return explicit
    if inferred:
        return inferred
    if len(allowed) == 1:
        return allowed[0]
    if len(allowed) > 1:
        raise ValueError(
            f"submodule: protocol {protocol or '<unknown>'} requires one of {', '.join(allowed)}"
        )
    return ""


def _validate_protocol_context(
    protocol: str, program: str, jurisdiction: str
) -> dict[str, Any]:
    if not protocol:
        return {}
    definition = _protocol_definition(protocol)
    if not definition:
        raise ValueError(f"protocol: unknown survey protocol {protocol}")
    expected_program = str(definition.get("program") or "").strip()
    if program and expected_program and program != expected_program:
        raise ValueError(
            f"program: protocol {protocol} belongs to program {expected_program}, received {program}"
        )
    supported_jurisdictions = {
        str(item or "").strip()
        for item in definition.get("jurisdictions") or []
        if str(item or "").strip()
    }
    if (
        jurisdiction
        and supported_jurisdictions
        and jurisdiction not in supported_jurisdictions
    ):
        raise ValueError(
            f"jurisdiction: protocol {protocol} does not support jurisdiction {jurisdiction}"
        )
    return definition


def _normalize_media_attachments(
    media: Any,
    *,
    event_id: str,
    observation_id: str,
    project_id: str,
    site_id: str,
    route_id: str,
    program: str,
    protocol: str,
    jurisdiction: str,
) -> list[dict[str, Any]]:
    if media in (None, ""):
        return []
    normalized: list[dict[str, Any]] = []
    for raw_item in media if isinstance(media, list) else []:
        if not isinstance(raw_item, dict):
            continue
        attachment = dict(raw_item)
        attachment_event_id = str(attachment.get("event_id") or "").strip()
        if attachment_event_id and attachment_event_id != event_id:
            raise ValueError(
                "event_id: attachment event_id does not match observation event_id"
            )
        attachment_observation_id = str(attachment.get("observation_id") or "").strip()
        if attachment_observation_id and attachment_observation_id != observation_id:
            raise ValueError(
                "observation_id: attachment observation_id does not match owning observation"
            )
        attachment["event_id"] = event_id
        attachment["observation_id"] = observation_id
        attachment["project_id"] = project_id
        attachment["site_id"] = site_id
        attachment["route_id"] = route_id
        attachment["program"] = program
        attachment["protocol"] = protocol
        attachment["jurisdiction"] = jurisdiction
        normalized.append(attachment)
    return normalized


def _validation_conflict_fields(entity_type: str, exc: ValueError) -> list[str]:
    message = str(exc or "").strip()
    if ":" in message:
        candidate = message.split(":", 1)[0].strip()
        if candidate:
            return [candidate]
    return ["validation"] if entity_type else ["validation"]


def _sync_operation_priority(operation: dict) -> tuple[int, int]:
    entity_type = str(operation.get("entity_type") or "").strip()
    action = str(operation.get("operation") or "upsert").strip().lower()
    priorities = {
        "project": 0,
        "site": 1,
        "route": 2,
        "design_asset": 3,
        "event": 4,
        "observation": 5,
        "track": 6,
        "map_package": 7,
    }
    delete_bias = 100 if action == "delete" else 0
    return (delete_bias + priorities.get(entity_type, 50), 0)


class SurveyStore:
    _WRITE_RETRY_ATTEMPTS = 5
    _RETRYABLE_SQLITE_TOKENS = (
        "database is locked",
        "database table is locked",
        "busy",
    )
    _RETRY_BASE_DELAY_S = 0.05
    _RETRY_MAX_DELAY_S = 0.5

    _DDL = """
    CREATE TABLE IF NOT EXISTS survey_projects (
        project_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        region TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS survey_sites (
        site_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        name TEXT NOT NULL,
        latitude REAL,
        longitude REAL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_sites_project ON survey_sites(project_id);
    CREATE TABLE IF NOT EXISTS survey_routes (
        route_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        name TEXT NOT NULL,
        route_type TEXT DEFAULT 'transect',
        length_m REAL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_routes_project ON survey_routes(project_id);
    CREATE INDEX IF NOT EXISTS idx_survey_routes_site ON survey_routes(site_id);
    CREATE TABLE IF NOT EXISTS survey_observations (
        observation_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        route_id TEXT DEFAULT '',
        event_id TEXT DEFAULT '',
        program TEXT DEFAULT '',
        submodule TEXT DEFAULT '',
        protocol TEXT DEFAULT '',
        jurisdiction TEXT DEFAULT '',
        snapped_route_id TEXT DEFAULT '',
        scientific_name TEXT DEFAULT '',
        chinese_name TEXT DEFAULT '',
        english_name TEXT DEFAULT '',
        taxon_id TEXT DEFAULT '',
        taxon_group TEXT DEFAULT '',
        observed_at TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_observations_project ON survey_observations(project_id);
    CREATE INDEX IF NOT EXISTS idx_survey_observations_site ON survey_observations(site_id);
    CREATE INDEX IF NOT EXISTS idx_survey_observations_route ON survey_observations(route_id);
    CREATE TABLE IF NOT EXISTS survey_tracks (
        track_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        route_id TEXT DEFAULT '',
        event_id TEXT DEFAULT '',
        program TEXT DEFAULT '',
        submodule TEXT DEFAULT '',
        protocol TEXT DEFAULT '',
        jurisdiction TEXT DEFAULT '',
        name TEXT NOT NULL,
        source TEXT DEFAULT 'recorded',
        distance_m REAL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_tracks_project ON survey_tracks(project_id);
    CREATE INDEX IF NOT EXISTS idx_survey_tracks_site ON survey_tracks(site_id);
    CREATE INDEX IF NOT EXISTS idx_survey_tracks_route ON survey_tracks(route_id);
    CREATE TABLE IF NOT EXISTS survey_map_packages (
        package_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        name TEXT NOT NULL,
        min_zoom INTEGER DEFAULT 8,
        max_zoom INTEGER DEFAULT 14,
        status TEXT DEFAULT 'draft',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_map_packages_project ON survey_map_packages(project_id);
    CREATE TABLE IF NOT EXISTS survey_design_assets (
        asset_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        asset_type TEXT DEFAULT 'route',
        program TEXT DEFAULT '',
        submodule TEXT DEFAULT '',
        protocol TEXT DEFAULT '',
        name TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_design_assets_project ON survey_design_assets(project_id);
    CREATE INDEX IF NOT EXISTS idx_survey_design_assets_site ON survey_design_assets(site_id);
    CREATE INDEX IF NOT EXISTS idx_survey_design_assets_program ON survey_design_assets(program);
    CREATE INDEX IF NOT EXISTS idx_survey_design_assets_protocol ON survey_design_assets(protocol);
    CREATE INDEX IF NOT EXISTS idx_survey_design_assets_type ON survey_design_assets(asset_type);
    CREATE TABLE IF NOT EXISTS survey_events (
        event_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        site_id TEXT DEFAULT '',
        design_asset_id TEXT DEFAULT '',
        route_id TEXT DEFAULT '',
        program TEXT DEFAULT '',
        submodule TEXT DEFAULT '',
        protocol TEXT DEFAULT '',
        jurisdiction TEXT DEFAULT '',
        started_at TEXT DEFAULT '',
        ended_at TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_events_project ON survey_events(project_id);
    CREATE INDEX IF NOT EXISTS idx_survey_events_site ON survey_events(site_id);
    CREATE INDEX IF NOT EXISTS idx_survey_events_asset ON survey_events(design_asset_id);
    CREATE INDEX IF NOT EXISTS idx_survey_events_program ON survey_events(program);
    CREATE INDEX IF NOT EXISTS idx_survey_events_protocol ON survey_events(protocol);
    CREATE TABLE IF NOT EXISTS survey_export_jobs (
        export_job_id TEXT PRIMARY KEY,
        project_id TEXT DEFAULT '',
        jurisdiction TEXT DEFAULT '',
        status TEXT DEFAULT 'ready',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_export_jobs_project ON survey_export_jobs(project_id);
    CREATE INDEX IF NOT EXISTS idx_survey_export_jobs_jurisdiction ON survey_export_jobs(jurisdiction);
    CREATE TABLE IF NOT EXISTS survey_sync_jobs (
        sync_job_id TEXT PRIMARY KEY,
        device_id TEXT DEFAULT '',
        user_id TEXT DEFAULT '',
        status TEXT DEFAULT 'applied',
        operation_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        operations_json TEXT NOT NULL,
        conflicts_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS survey_sync_conflicts (
        conflict_id TEXT PRIMARY KEY,
        sync_job_id TEXT DEFAULT '',
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        status TEXT DEFAULT 'open',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        fields_json TEXT NOT NULL,
        incoming_json TEXT NOT NULL,
        server_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_survey_sync_conflicts_job ON survey_sync_conflicts(sync_job_id);
    """

    _ENTITY_META = {
        "project": {
            "table": "survey_projects",
            "id_field": "project_id",
            "default_prefix": "proj",
            "material_fields": [
                "name",
                "region",
                "survey_window",
                "team_members",
                "target_taxa",
                "notes",
            ],
        },
        "site": {
            "table": "survey_sites",
            "id_field": "site_id",
            "default_prefix": "site",
            "material_fields": [
                "name",
                "project_id",
                "latitude",
                "longitude",
                "geometry",
                "habitat_type",
                "admin_region",
                "region_code",
                "notes",
                "sensitivity",
            ],
        },
        "route": {
            "table": "survey_routes",
            "id_field": "route_id",
            "default_prefix": "route",
            "material_fields": [
                "name",
                "project_id",
                "site_id",
                "route_type",
                "geometry",
                "length_m",
                "source",
            ],
        },
        "observation": {
            "table": "survey_observations",
            "id_field": "observation_id",
            "default_prefix": "obs",
            "material_fields": [
                "project_id",
                "site_id",
                "route_id",
                "event_id",
                "program",
                "submodule",
                "protocol",
                "jurisdiction",
                "scientific_name",
                "chinese_name",
                "english_name",
                "taxon_id",
                "count",
                "evidence_type",
                "behavior",
                "confidence",
                "certainty",
                "latitude",
                "longitude",
                "geometry",
                "media",
                "observer",
                "observed_at",
                "snapped_route_id",
                "snapped_distance_m",
                "unknown_taxon",
                "trace_only",
                "ai_suggestion",
                "record_payload",
                "sensitivity",
            ],
        },
        "track": {
            "table": "survey_tracks",
            "id_field": "track_id",
            "default_prefix": "track",
            "material_fields": [
                "project_id",
                "site_id",
                "route_id",
                "event_id",
                "program",
                "submodule",
                "protocol",
                "jurisdiction",
                "name",
                "source",
                "geometry",
                "distance_m",
                "duration_s",
                "started_at",
                "ended_at",
            ],
        },
        "map_package": {
            "table": "survey_map_packages",
            "id_field": "package_id",
            "default_prefix": "pkg",
            "material_fields": [
                "project_id",
                "name",
                "bbox",
                "min_zoom",
                "max_zoom",
                "tile_url",
                "tile_count_estimate",
                "storage_bytes_estimate",
                "expires_at",
                "status",
            ],
        },
        "design_asset": {
            "table": "survey_design_assets",
            "id_field": "asset_id",
            "default_prefix": "asset",
            "material_fields": [
                "project_id",
                "site_id",
                "asset_type",
                "program",
                "submodule",
                "protocol",
                "name",
                "geometry",
                "status",
                "sensitivity",
                "parent_asset_id",
                "route_id",
            ],
        },
        "event": {
            "table": "survey_events",
            "id_field": "event_id",
            "default_prefix": "event",
            "material_fields": [
                "project_id",
                "site_id",
                "design_asset_id",
                "route_id",
                "program",
                "submodule",
                "protocol",
                "jurisdiction",
                "started_at",
                "ended_at",
                "geometry",
                "weather",
                "effort_metrics",
                "event_payload",
                "observers",
                "team",
                "notes",
            ],
        },
    }

    def __init__(self, storage_dir: Optional[str] = None):
        root = Path(storage_dir) if storage_dir else (get_data_dir() / "survey_store")
        self._dir = root
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / "survey_store.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level="IMMEDIATE",
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()
        with self._lock:
            self._conn.executescript(self._DDL)
            with self._conn:
                self._migrate_schema()

    def close(self):
        with self._lock:
            try:
                self._conn.commit()
            except Exception:
                pass
            finally:
                self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _configure_connection(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def _migrate_schema(self) -> None:
        observation_columns = {
            row["name"]
            for row in self._conn.execute(
                "PRAGMA table_info(survey_observations)"
            ).fetchall()
        }
        required_observation_columns = {
            "snapped_route_id": "",
            "event_id": "",
            "program": "",
            "submodule": "",
            "protocol": "",
            "jurisdiction": "",
            "taxon_id": "",
        }
        for column_name, default_value in required_observation_columns.items():
            if column_name not in observation_columns:
                self._conn.execute(
                    f"ALTER TABLE survey_observations ADD COLUMN {column_name} TEXT DEFAULT '{default_value}'"
                )
        rows = self._conn.execute(
            "SELECT observation_id, payload_json FROM survey_observations"
        ).fetchall()
        for row in rows:
            payload = _loads_json(row["payload_json"], {})
            if not isinstance(payload, dict):
                continue
            updates: dict[str, str] = {
                "snapped_route_id": str(payload.get("snapped_route_id") or "").strip(),
                "event_id": str(
                    payload.get("event_id")
                    or (
                        (payload.get("extra") or {}).get("event_id")
                        if isinstance(payload.get("extra"), dict)
                        else ""
                    )
                    or ""
                ).strip(),
                "program": str(
                    payload.get("program")
                    or (
                        (payload.get("extra") or {}).get("program")
                        if isinstance(payload.get("extra"), dict)
                        else ""
                    )
                    or ""
                ).strip(),
                "submodule": str(
                    payload.get("submodule")
                    or (
                        (payload.get("extra") or {}).get("submodule")
                        if isinstance(payload.get("extra"), dict)
                        else ""
                    )
                    or ""
                ).strip(),
                "protocol": str(
                    payload.get("protocol")
                    or (
                        (payload.get("extra") or {}).get("protocol")
                        if isinstance(payload.get("extra"), dict)
                        else ""
                    )
                    or ""
                ).strip(),
                "jurisdiction": str(
                    payload.get("jurisdiction")
                    or (
                        (payload.get("extra") or {}).get("jurisdiction")
                        if isinstance(payload.get("extra"), dict)
                        else ""
                    )
                    or ""
                ).strip(),
                "taxon_id": str(
                    payload.get("taxon_id")
                    or (
                        (payload.get("record_payload") or {}).get("taxon_id")
                        if isinstance(payload.get("record_payload"), dict)
                        else ""
                    )
                    or ""
                ).strip(),
            }
            if any(updates.values()):
                self._conn.execute(
                    """
                    UPDATE survey_observations
                    SET snapped_route_id=?, event_id=?, program=?, submodule=?, protocol=?, jurisdiction=?, taxon_id=?
                    WHERE observation_id=?
                    """,
                    (
                        updates["snapped_route_id"],
                        updates["event_id"],
                        updates["program"],
                        updates["submodule"],
                        updates["protocol"],
                        updates["jurisdiction"],
                        updates["taxon_id"],
                        row["observation_id"],
                    ),
                )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_observations_event ON survey_observations(event_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_observations_program ON survey_observations(program)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_observations_submodule ON survey_observations(submodule)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_observations_protocol ON survey_observations(protocol)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_observations_jurisdiction ON survey_observations(jurisdiction)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_observations_snapped_route ON survey_observations(snapped_route_id)"
        )

        track_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(survey_tracks)").fetchall()
        }
        required_track_columns = {
            "event_id": "",
            "program": "",
            "submodule": "",
            "protocol": "",
            "jurisdiction": "",
        }
        for column_name, default_value in required_track_columns.items():
            if column_name not in track_columns:
                self._conn.execute(
                    f"ALTER TABLE survey_tracks ADD COLUMN {column_name} TEXT DEFAULT '{default_value}'"
                )
        rows = self._conn.execute(
            "SELECT track_id, payload_json FROM survey_tracks"
        ).fetchall()
        for row in rows:
            payload = _loads_json(row["payload_json"], {})
            if not isinstance(payload, dict):
                continue
            extra = (
                payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
            )
            updates: dict[str, str] = {
                "event_id": str(
                    payload.get("event_id") or extra.get("event_id") or ""
                ).strip(),
                "program": str(
                    payload.get("program") or extra.get("program") or ""
                ).strip(),
                "submodule": str(
                    payload.get("submodule") or extra.get("submodule") or ""
                ).strip(),
                "protocol": str(
                    payload.get("protocol") or extra.get("protocol") or ""
                ).strip(),
                "jurisdiction": str(
                    payload.get("jurisdiction") or extra.get("jurisdiction") or ""
                ).strip(),
            }
            if any(updates.values()):
                self._conn.execute(
                    """
                    UPDATE survey_tracks
                    SET event_id=?, program=?, submodule=?, protocol=?, jurisdiction=?
                    WHERE track_id=?
                    """,
                    (
                        updates["event_id"],
                        updates["program"],
                        updates["submodule"],
                        updates["protocol"],
                        updates["jurisdiction"],
                        row["track_id"],
                    ),
                )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_tracks_event ON survey_tracks(event_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_tracks_program ON survey_tracks(program)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_tracks_submodule ON survey_tracks(submodule)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_tracks_protocol ON survey_tracks(protocol)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_tracks_jurisdiction ON survey_tracks(jurisdiction)"
        )

        design_asset_columns = {
            row["name"]
            for row in self._conn.execute(
                "PRAGMA table_info(survey_design_assets)"
            ).fetchall()
        }
        for column_name in ("submodule",):
            if column_name not in design_asset_columns:
                self._conn.execute(
                    f"ALTER TABLE survey_design_assets ADD COLUMN {column_name} TEXT DEFAULT ''"
                )
        for row in self._conn.execute(
            "SELECT asset_id, payload_json FROM survey_design_assets"
        ).fetchall():
            payload = _loads_json(row["payload_json"], {})
            if not isinstance(payload, dict):
                continue
            extra = (
                payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
            )
            submodule = str(
                payload.get("submodule") or extra.get("submodule") or ""
            ).strip()
            if submodule:
                self._conn.execute(
                    "UPDATE survey_design_assets SET submodule=? WHERE asset_id=?",
                    (submodule, row["asset_id"]),
                )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_design_assets_submodule ON survey_design_assets(submodule)"
        )

        event_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(survey_events)").fetchall()
        }
        for column_name in ("submodule",):
            if column_name not in event_columns:
                self._conn.execute(
                    f"ALTER TABLE survey_events ADD COLUMN {column_name} TEXT DEFAULT ''"
                )
        for row in self._conn.execute(
            "SELECT event_id, payload_json FROM survey_events"
        ).fetchall():
            payload = _loads_json(row["payload_json"], {})
            if not isinstance(payload, dict):
                continue
            extra = (
                payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
            )
            submodule = str(
                payload.get("submodule") or extra.get("submodule") or ""
            ).strip()
            if submodule:
                self._conn.execute(
                    "UPDATE survey_events SET submodule=? WHERE event_id=?",
                    (submodule, row["event_id"]),
                )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_events_submodule ON survey_events(submodule)"
        )

        # Soft-delete migration: add `deleted_at` to every entity table so the
        # only way to remove rows is to mark them; recovery is just clearing the
        # column. Empty string represents "not deleted" so existing rows stay
        # active without any backfill.
        soft_delete_tables = (
            "survey_projects",
            "survey_sites",
            "survey_routes",
            "survey_observations",
            "survey_tracks",
            "survey_map_packages",
            "survey_design_assets",
            "survey_events",
        )
        for tbl in soft_delete_tables:
            cols = {
                row["name"]
                for row in self._conn.execute(f"PRAGMA table_info({tbl})")
            }
            if "deleted_at" not in cols:
                self._conn.execute(
                    f"ALTER TABLE {tbl} ADD COLUMN deleted_at TEXT DEFAULT ''"
                )
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{tbl}_deleted_at ON {tbl}(deleted_at)"
            )

    def _make_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def _is_retryable_sqlite_error(self, exc: sqlite3.OperationalError) -> bool:
        message = str(exc).strip().lower()
        return any(token in message for token in self._RETRYABLE_SQLITE_TOKENS)

    def _run_with_retry(self, operation, *, write: bool = False):
        max_attempts = self._WRITE_RETRY_ATTEMPTS if write else 1
        delay_s = self._RETRY_BASE_DELAY_S
        last_exc: Optional[Exception] = None

        for attempt in range(max_attempts):
            should_retry = False
            with self._lock:
                try:
                    if write:
                        with self._conn:
                            result = operation()
                    else:
                        result = operation()
                    return result
                except sqlite3.OperationalError as exc:
                    last_exc = exc
                    if (
                        write
                        and attempt + 1 < max_attempts
                        and self._is_retryable_sqlite_error(exc)
                    ):
                        should_retry = True
                    else:
                        raise
                except Exception:
                    raise
            if should_retry:
                time.sleep(delay_s)
                delay_s = min(delay_s * 2, self._RETRY_MAX_DELAY_S)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("database operation failed without an exception")

    def _normalize_payload_for_compare(self, value: Any) -> Any:
        ignored_keys = {
            "updated_at",
            "sync_state",
            "server_updated_at",
            "base_updated_at",
        }
        if isinstance(value, dict):
            return {
                key: self._normalize_payload_for_compare(item)
                for key, item in sorted(value.items())
                if key not in ignored_keys
            }
        if isinstance(value, list):
            return [self._normalize_payload_for_compare(item) for item in value]
        return value

    def _payloads_equivalent(self, left: Optional[dict], right: Optional[dict]) -> bool:
        if not left or not right:
            return False
        return self._normalize_payload_for_compare(
            left
        ) == self._normalize_payload_for_compare(right)

    def _row_to_payload(self, row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        payload = _loads_json(row["payload_json"], {})
        if isinstance(payload, dict):
            row_keys = set(row.keys())
            payload.setdefault("created_at", row["created_at"])
            payload.setdefault("updated_at", row["updated_at"])
            observation_field_map = {
                "event_id": "event_id",
                "program": "program",
                "submodule": "submodule",
                "protocol": "protocol",
                "jurisdiction": "jurisdiction",
                "taxon_id": "taxon_id",
                "snapped_route_id": "snapped_route_id",
            }
            track_field_map = {
                "event_id": "event_id",
                "program": "program",
                "submodule": "submodule",
                "protocol": "protocol",
                "jurisdiction": "jurisdiction",
            }
            if "observation_id" in row_keys:
                for payload_key, row_key in observation_field_map.items():
                    if row_key in row_keys:
                        value = str(row[row_key] or "").strip()
                        if value:
                            payload.setdefault(payload_key, value)
                extra = payload.get("extra")
                if not isinstance(extra, dict):
                    extra = {}
                    payload["extra"] = extra
                for payload_key in (
                    "event_id",
                    "program",
                    "submodule",
                    "protocol",
                    "jurisdiction",
                ):
                    value = str(payload.get(payload_key) or "").strip()
                    if value:
                        extra.setdefault(payload_key, value)
                record_payload = payload.get("record_payload")
                if not isinstance(record_payload, dict):
                    record_payload = {}
                    payload["record_payload"] = record_payload
                taxon_id = str(payload.get("taxon_id") or "").strip()
                if taxon_id:
                    record_payload.setdefault("taxon_id", taxon_id)
            elif "track_id" in row_keys:
                for payload_key, row_key in track_field_map.items():
                    if row_key in row_keys:
                        value = str(row[row_key] or "").strip()
                        if value:
                            payload.setdefault(payload_key, value)
                extra = payload.get("extra")
                if not isinstance(extra, dict):
                    extra = {}
                    payload["extra"] = extra
                for payload_key in (
                    "event_id",
                    "program",
                    "submodule",
                    "protocol",
                    "jurisdiction",
                ):
                    value = str(payload.get(payload_key) or "").strip()
                    if value:
                        extra.setdefault(payload_key, value)
        return payload

    def _list_payloads_locked(self, query: str, params: tuple = ()) -> list[dict]:
        rows = self._conn.execute(query, params).fetchall()
        payloads: list[dict] = []
        for row in rows:
            payload = self._row_to_payload(row)
            if payload:
                payloads.append(payload)
        return payloads

    def _get_by_id_locked(self, entity_type: str, entity_id: str) -> Optional[dict]:
        meta = self._ENTITY_META[entity_type]
        row = self._conn.execute(
            f"SELECT * FROM {meta['table']} WHERE {meta['id_field']}=?",
            (entity_id,),
        ).fetchone()
        return self._row_to_payload(row)

    def _store_payload_locked(
        self,
        table: str,
        id_field: str,
        payload: dict,
        summary: dict,
    ) -> dict:
        columns = (
            [id_field]
            + list(summary.keys())
            + ["created_at", "updated_at", "payload_json"]
        )
        placeholders = ",".join("?" for _ in columns)
        values = (
            [payload[id_field]]
            + [summary[key] for key in summary]
            + [
                payload["created_at"],
                payload["updated_at"],
                _dumps_json(payload),
            ]
        )
        self._conn.execute(
            f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return payload

    def _list_entity_ids_locked(
        self, entity_type: str, where_clause: str = "", params: tuple[Any, ...] = ()
    ) -> list[str]:
        meta = self._ENTITY_META[entity_type]
        rows = self._conn.execute(
            f"SELECT {meta['id_field']} FROM {meta['table']} {where_clause}",
            params,
        ).fetchall()
        ids: list[str] = []
        for row in rows:
            entity_id = str(row[0] or "").strip()
            if entity_id:
                ids.append(entity_id)
        return ids

    def _track_ids_for_event_locked(self, event_id: str) -> list[str]:
        track_ids: list[str] = []
        for track in self._list_payloads_locked(
            "SELECT * FROM survey_tracks WHERE deleted_at=''"
        ):
            extra = track.get("extra") if isinstance(track.get("extra"), dict) else {}
            track_event_id = str(
                track.get("event_id") or extra.get("event_id") or ""
            ).strip()
            if track_event_id == event_id:
                track_id = str(track.get("track_id") or "").strip()
                if track_id:
                    track_ids.append(track_id)
        return track_ids

    def _delete_entity_locked(self, entity_type: str, entity_id: str) -> bool:
        """Soft-delete an entity by stamping `deleted_at`.

        Cascading semantics are preserved: deleting a project also marks every
        descendant site, route, design asset, event, observation, and track as
        deleted. The original row stays in the database so an admin can restore
        it via `_restore_entity_locked` within the retention window.
        """
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            return False
        existing = self._get_by_id_locked(entity_type, entity_id)
        if not existing:
            return False
        if str(existing.get("deleted_at") or "").strip():
            # Already soft-deleted; treat as idempotent no-op so cascades are safe.
            return False

        deleted_at = _utc_now()

        if entity_type == "project":
            for child_id in self._list_entity_ids_locked(
                "site", "WHERE project_id=? AND deleted_at=''", (entity_id,)
            ):
                self._delete_entity_locked("site", child_id)
            for child_id in self._list_entity_ids_locked(
                "route", "WHERE project_id=? AND deleted_at=''", (entity_id,)
            ):
                self._delete_entity_locked("route", child_id)
            for child_id in self._list_entity_ids_locked(
                "design_asset",
                "WHERE project_id=? AND deleted_at=''",
                (entity_id,),
            ):
                self._delete_entity_locked("design_asset", child_id)
            for child_id in self._list_entity_ids_locked(
                "event", "WHERE project_id=? AND deleted_at=''", (entity_id,)
            ):
                self._delete_entity_locked("event", child_id)
            self._conn.execute(
                "UPDATE survey_observations SET deleted_at=? "
                "WHERE project_id=? AND deleted_at=''",
                (deleted_at, entity_id),
            )
            self._conn.execute(
                "UPDATE survey_tracks SET deleted_at=? "
                "WHERE project_id=? AND deleted_at=''",
                (deleted_at, entity_id),
            )
            self._conn.execute(
                "UPDATE survey_map_packages SET deleted_at=? "
                "WHERE project_id=? AND deleted_at=''",
                (deleted_at, entity_id),
            )
            # Export jobs are operational artefacts, not survey data — keep
            # the historical hard-delete to avoid trash bloat.
            self._conn.execute(
                "DELETE FROM survey_export_jobs WHERE project_id=?", (entity_id,)
            )
        elif entity_type == "site":
            for child_id in self._list_entity_ids_locked(
                "route", "WHERE site_id=? AND deleted_at=''", (entity_id,)
            ):
                self._delete_entity_locked("route", child_id)
            for child_id in self._list_entity_ids_locked(
                "design_asset",
                "WHERE site_id=? AND deleted_at=''",
                (entity_id,),
            ):
                self._delete_entity_locked("design_asset", child_id)
            for child_id in self._list_entity_ids_locked(
                "event", "WHERE site_id=? AND deleted_at=''", (entity_id,)
            ):
                self._delete_entity_locked("event", child_id)
            self._conn.execute(
                "UPDATE survey_observations SET deleted_at=? "
                "WHERE site_id=? AND deleted_at=''",
                (deleted_at, entity_id),
            )
            self._conn.execute(
                "UPDATE survey_tracks SET deleted_at=? "
                "WHERE site_id=? AND deleted_at=''",
                (deleted_at, entity_id),
            )
        elif entity_type == "route":
            for asset in self._list_payloads_locked(
                "SELECT * FROM survey_design_assets WHERE deleted_at=''"
            ):
                if str(asset.get("route_id") or "").strip() == entity_id:
                    self._delete_entity_locked(
                        "design_asset", asset.get("asset_id", "")
                    )
            for child_id in self._list_entity_ids_locked(
                "event", "WHERE route_id=? AND deleted_at=''", (entity_id,)
            ):
                self._delete_entity_locked("event", child_id)
            for observation in self._list_payloads_locked(
                "SELECT * FROM survey_observations WHERE deleted_at=''"
            ):
                route_match = (
                    str(observation.get("route_id") or "").strip() == entity_id
                )
                snapped_match = (
                    str(observation.get("snapped_route_id") or "").strip() == entity_id
                )
                if route_match or snapped_match:
                    self._delete_entity_locked(
                        "observation", observation.get("observation_id", "")
                    )
            self._conn.execute(
                "UPDATE survey_tracks SET deleted_at=? "
                "WHERE route_id=? AND deleted_at=''",
                (deleted_at, entity_id),
            )
        elif entity_type == "design_asset":
            for asset in self._list_payloads_locked(
                "SELECT * FROM survey_design_assets WHERE deleted_at=''"
            ):
                if str(asset.get("parent_asset_id") or "").strip() == entity_id:
                    self._delete_entity_locked(
                        "design_asset", asset.get("asset_id", "")
                    )
            for child_id in self._list_entity_ids_locked(
                "event", "WHERE design_asset_id=? AND deleted_at=''", (entity_id,)
            ):
                self._delete_entity_locked("event", child_id)
        elif entity_type == "event":
            self._conn.execute(
                "UPDATE survey_observations SET deleted_at=? "
                "WHERE event_id=? AND deleted_at=''",
                (deleted_at, entity_id),
            )
            track_ids = self._track_ids_for_event_locked(entity_id)
            if track_ids:
                placeholders = ",".join("?" for _ in track_ids)
                self._conn.execute(
                    f"UPDATE survey_tracks SET deleted_at=? "
                    f"WHERE track_id IN ({placeholders}) AND deleted_at=''",
                    (deleted_at, *track_ids),
                )
        meta = self._ENTITY_META[entity_type]
        cur = self._conn.execute(
            f"UPDATE {meta['table']} SET deleted_at=? "
            f"WHERE {meta['id_field']}=? AND deleted_at=''",
            (deleted_at, entity_id),
        )
        return cur.rowcount > 0

    def _restore_entity_locked(self, entity_type: str, entity_id: str) -> bool:
        """Clear `deleted_at` on a soft-deleted row. Restoration is intentionally
        non-cascading: the admin must explicitly restore each level. This keeps
        the trash UI predictable and prevents an accidental bulk restore from
        resurrecting a child whose parent was intentionally tombstoned."""
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            return False
        meta = self._ENTITY_META.get(entity_type)
        if not meta:
            return False
        cur = self._conn.execute(
            f"UPDATE {meta['table']} SET deleted_at='' "
            f"WHERE {meta['id_field']}=? AND deleted_at!=''",
            (entity_id,),
        )
        return cur.rowcount > 0

    def restore_entity(self, entity_type: str, entity_id: str) -> bool:
        return self._run_with_retry(
            lambda: self._restore_entity_locked(entity_type, entity_id),
            write=True,
        )

    def list_trash(self, entity_type: str = "") -> list[dict]:
        """Return all soft-deleted entities, newest tombstone first.

        When `entity_type` is provided, only that entity type is returned.
        Each row is augmented with `entity_type` so callers can render a
        unified trash view across all tables.
        """
        targets: list[tuple[str, str]] = []
        if entity_type:
            meta = self._ENTITY_META.get(entity_type)
            if not meta:
                return []
            targets.append((entity_type, meta["table"]))
        else:
            for et, meta in self._ENTITY_META.items():
                targets.append((et, meta["table"]))

        results: list[dict] = []
        for et, tbl in targets:
            try:
                rows = self._list_payloads(
                    f"SELECT * FROM {tbl} WHERE deleted_at!='' ORDER BY deleted_at DESC"
                )
            except sqlite3.OperationalError:
                # Table without deleted_at column (e.g. operational tables).
                continue
            for row in rows:
                row["entity_type"] = et
                results.append(row)
        results.sort(
            key=lambda r: str(r.get("deleted_at") or ""),
            reverse=True,
        )
        return results

    def _upsert_project_locked(self, payload: dict) -> dict:
        now = _utc_now()
        project_id = payload.get("project_id") or self._make_id("proj")
        existing = self._get_by_id_locked("project", project_id)
        if existing:
            payload = _merge_payload_patch(existing, payload)
        project = {
            "project_id": project_id,
            "name": payload.get("name") or "鏈懡鍚嶉」鐩?",
            "team_members": _payload_value(payload, "team_members", existing, []),
            "target_taxa": _payload_value(payload, "target_taxa", existing, []),
            "region": _payload_value(payload, "region", existing, ""),
            "survey_window": _payload_value(payload, "survey_window", existing, {}),
            "notes": _payload_value(payload, "notes", existing, ""),
            "sync_state": _payload_value(payload, "sync_state", existing, "synced"),
            "extra": _payload_value(payload, "extra", existing, {}),
            "created_at": payload.get("created_at")
            or (existing or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        if self._payloads_equivalent(project, existing):
            return existing
        return self._store_payload_locked(
            "survey_projects",
            "project_id",
            project,
            {"name": project["name"], "region": project["region"]},
        )

    def _upsert_site_locked(self, payload: dict) -> dict:
        now = _utc_now()
        site_id = payload.get("site_id") or self._make_id("site")
        existing = self._get_by_id_locked("site", site_id)
        if existing:
            payload = _merge_payload_patch(existing, payload)
        geometry = payload.get("geometry")
        latitude = _coerce_float(
            payload.get("latitude"), (existing or {}).get("latitude")
        )
        longitude = _coerce_float(
            payload.get("longitude"), (existing or {}).get("longitude")
        )
        if not geometry and latitude is not None and longitude is not None:
            geometry = {"type": "Point", "coordinates": [longitude, latitude]}
        elif geometry and geometry.get("type") == "Point":
            coords = geometry.get("coordinates") or []
            if len(coords) >= 2:
                longitude = _coerce_float(coords[0], longitude)
                latitude = _coerce_float(coords[1], latitude)
        site = {
            "site_id": site_id,
            "project_id": payload.get("project_id") or "",
            "name": payload.get("name")
            or payload.get("site_name")
            or "未命名样点",
            "latitude": latitude,
            "longitude": longitude,
            "geometry": geometry,
            "habitat_type": payload.get("habitat_type") or "",
            "admin_region": payload.get("admin_region") or payload.get("region") or "",
            "region_code": payload.get("region_code") or "",
            "notes": payload.get("notes") or "",
            "sensitivity": payload.get("sensitivity") or "public",
            "sync_state": payload.get("sync_state") or "synced",
            "extra": payload.get("extra") or {},
            "created_at": payload.get("created_at")
            or (existing or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        if self._payloads_equivalent(site, existing):
            return existing
        return self._store_payload_locked(
            "survey_sites",
            "site_id",
            site,
            {
                "project_id": site["project_id"],
                "name": site["name"],
                "latitude": site["latitude"],
                "longitude": site["longitude"],
            },
        )

    def _upsert_route_locked(self, payload: dict) -> dict:
        now = _utc_now()
        route_id = payload.get("route_id") or self._make_id("route")
        existing = self._get_by_id_locked("route", route_id)
        if existing:
            payload = _merge_payload_patch(existing, payload)
        geometry = (
            payload.get("geometry")
            or (existing or {}).get("geometry")
            or {"type": "LineString", "coordinates": []}
        )
        coordinates = _extract_line_coordinates(geometry)
        route = {
            "route_id": route_id,
            "project_id": payload.get("project_id") or "",
            "site_id": payload.get("site_id") or "",
            "name": payload.get("name") or "鏈懡鍚嶈矾绾?",
            "route_type": payload.get("route_type") or "transect",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "length_m": round(
                _coerce_float(payload.get("length_m"), _line_length_m(coordinates))
                or 0.0,
                2,
            ),
            "source": payload.get("source") or "manual",
            "imported_format": payload.get("imported_format") or "",
            "original_filename": payload.get("original_filename") or "",
            "point_times": payload.get("point_times") or [],
            "sync_state": payload.get("sync_state") or "synced",
            "extra": payload.get("extra") or {},
            "created_at": payload.get("created_at")
            or (existing or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        if self._payloads_equivalent(route, existing):
            return existing
        return self._store_payload_locked(
            "survey_routes",
            "route_id",
            route,
            {
                "project_id": route["project_id"],
                "site_id": route["site_id"],
                "name": route["name"],
                "route_type": route["route_type"],
                "length_m": route["length_m"],
            },
        )

    def _upsert_observation_locked(self, payload: dict) -> dict:
        now = _utc_now()
        observation_id = payload.get("observation_id") or self._make_id("obs")
        existing = self._get_by_id_locked("observation", observation_id)
        if existing:
            payload = _merge_payload_patch(existing, payload)
        incoming_extra = (
            payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        )
        existing_extra = (
            (existing or {}).get("extra")
            if isinstance((existing or {}).get("extra"), dict)
            else {}
        )
        geometry = payload.get("geometry")
        latitude = _coerce_float(
            payload.get("latitude"), (existing or {}).get("latitude")
        )
        longitude = _coerce_float(
            payload.get("longitude"), (existing or {}).get("longitude")
        )
        if not geometry and latitude is not None and longitude is not None:
            geometry = {"type": "Point", "coordinates": [longitude, latitude]}
        if geometry and geometry.get("type") == "Point":
            coords = geometry.get("coordinates") or []
            if len(coords) >= 2:
                longitude = _coerce_float(coords[0], longitude)
                latitude = _coerce_float(coords[1], latitude)
        protocol = str(
            payload.get("protocol")
            or incoming_extra.get("protocol")
            or (existing or {}).get("protocol")
            or existing_extra.get("protocol")
            or ""
        ).strip()
        jurisdiction = str(
            payload.get("jurisdiction")
            or incoming_extra.get("jurisdiction")
            or (existing or {}).get("jurisdiction")
            or existing_extra.get("jurisdiction")
            or ""
        ).strip()
        requested_program = str(
            payload.get("program")
            or incoming_extra.get("program")
            or (existing or {}).get("program")
            or existing_extra.get("program")
            or ""
        ).strip()
        definition = _validate_protocol_context(
            protocol, requested_program, jurisdiction
        )
        program = _program_for_protocol(protocol, requested_program)
        submodule = _normalize_submodule(protocol, program, payload, existing)
        event_id = str(
            payload.get("event_id")
            or incoming_extra.get("event_id")
            or (existing or {}).get("event_id")
            or existing_extra.get("event_id")
            or ""
        ).strip()
        if not event_id:
            raise ValueError("event_id: observation requires explicit event_id linkage")
        linked_event = self._get_by_id_locked("event", event_id)
        if not linked_event:
            raise ValueError(
                f"event_id: linked event {event_id} was not found for observation"
            )
        event_program = str(linked_event.get("program") or "").strip()
        event_protocol = str(linked_event.get("protocol") or "").strip()
        event_jurisdiction = str(linked_event.get("jurisdiction") or "").strip()
        if event_protocol:
            definition = _validate_protocol_context(
                event_protocol,
                event_program or program,
                event_jurisdiction or jurisdiction,
            )
        if protocol and event_protocol and protocol != event_protocol:
            raise ValueError(
                f"protocol: observation protocol {protocol} does not match linked event protocol {event_protocol}"
            )
        protocol = event_protocol or protocol
        program = _program_for_protocol(protocol, event_program or program)
        jurisdiction = event_jurisdiction or jurisdiction or "mainland_china"
        _validate_protocol_context(protocol, program, jurisdiction)
        submodule = _normalize_submodule(protocol, program, payload, linked_event)
        project_id = str(
            payload.get("project_id") or linked_event.get("project_id") or ""
        ).strip()
        site_id = str(
            payload.get("site_id") or linked_event.get("site_id") or ""
        ).strip()
        route_id = str(
            payload.get("route_id")
            or (existing or {}).get("route_id")
            or linked_event.get("route_id")
            or ""
        ).strip()
        event_route_id = str(linked_event.get("route_id") or "").strip()
        if event_route_id and route_id and route_id != event_route_id:
            raise ValueError(
                f"route_id: observation route_id {route_id} does not match linked event route_id {event_route_id}"
            )
        if event_route_id:
            route_id = event_route_id
        payload_project_id = str(payload.get("project_id") or "").strip()
        if payload_project_id and project_id and payload_project_id != project_id:
            raise ValueError(
                "project_id: observation project_id does not match linked event project_id"
            )
        payload_site_id = str(payload.get("site_id") or "").strip()
        if payload_site_id and site_id and payload_site_id != site_id:
            raise ValueError(
                "site_id: observation site_id does not match linked event site_id"
            )
        taxon_id = str(
            payload.get("taxon_id")
            or incoming_extra.get("taxon_id")
            or (existing or {}).get("taxon_id")
            or ((existing or {}).get("record_payload") or {}).get("taxon_id")
            or ""
        ).strip()
        record_payload = _normalize_terrestrial_record_payload(
            protocol,
            payload.get("record_payload") or incoming_extra.get("record_payload"),
            existing=(existing or {}).get("record_payload"),
            count=payload.get("count"),
            evidence_type=payload.get("evidence_type")
            or (existing or {}).get("evidence_type")
            or "",
            observed_at=payload.get("observed_at")
            or (existing or {}).get("observed_at")
            or now,
            behavior=payload.get("behavior") or (existing or {}).get("behavior") or "",
            breeding_code=payload.get("breeding_code")
            or (existing or {}).get("breeding_code")
            or "",
            taxon_id=taxon_id,
        )
        extra = dict(existing_extra)
        extra.update(incoming_extra)
        if protocol:
            extra["protocol"] = protocol
        if program:
            extra["program"] = program
        if jurisdiction:
            extra["jurisdiction"] = jurisdiction
        extra["event_id"] = event_id
        if submodule:
            extra["submodule"] = submodule
        if taxon_id:
            extra["taxon_id"] = taxon_id
        if record_payload:
            extra["record_payload"] = record_payload
        snapped_route_id = str(payload.get("snapped_route_id") or "").strip()
        if event_route_id and not snapped_route_id:
            snapped_route_id = event_route_id
        media = _normalize_media_attachments(
            payload.get("media") or (existing or {}).get("media") or [],
            event_id=event_id,
            observation_id=observation_id,
            project_id=project_id,
            site_id=site_id,
            route_id=route_id or snapped_route_id,
            program=program,
            protocol=protocol,
            jurisdiction=jurisdiction,
        )
        media_ids = {
            str(item.get("media_id") or "").strip()
            for item in media
            if str(item.get("media_id") or "").strip()
        }
        record_media_file_id = str(record_payload.get("media_file_id") or "").strip()
        if record_media_file_id and media_ids and record_media_file_id not in media_ids:
            raise ValueError(
                "media_file_id: record_payload media_file_id does not match attached media"
            )
        if (
            not record_media_file_id
            and protocol == "herp_infrared_camera"
            and len(media_ids) == 1
        ):
            record_payload["media_file_id"] = next(iter(media_ids))
            extra["record_payload"] = record_payload
        observation = {
            "observation_id": observation_id,
            "project_id": project_id,
            "site_id": site_id,
            "route_id": route_id,
            "event_id": event_id,
            "program": program,
            "submodule": submodule,
            "protocol": protocol,
            "jurisdiction": jurisdiction,
            "scientific_name": payload.get("scientific_name") or "",
            "chinese_name": payload.get("chinese_name") or "",
            "english_name": payload.get("english_name") or "",
            "taxon_id": taxon_id,
            "taxon_group": payload.get("taxon_group") or "",
            "count": _coerce_int(payload.get("count"), 1),
            "evidence_type": payload.get("evidence_type") or "visual",
            "behavior": payload.get("behavior") or "",
            "breeding_code": payload.get("breeding_code") or "",
            "habitat_notes": payload.get("habitat_notes") or "",
            "confidence": round(
                _coerce_float(payload.get("confidence"), 0.5) or 0.0, 4
            ),
            "certainty": payload.get("certainty") or "review_needed",
            "sign_type": payload.get("sign_type") or "",
            "unknown_taxon": _coerce_bool(payload.get("unknown_taxon")),
            "trace_only": _coerce_bool(payload.get("trace_only")),
            "latitude": latitude,
            "longitude": longitude,
            "geometry": geometry,
            "media": media,
            "observer": payload.get("observer") or "",
            "observed_at": payload.get("observed_at") or now,
            "snapped_route_id": snapped_route_id,
            "snapped_distance_m": round(
                _coerce_float(payload.get("snapped_distance_m"), 0.0) or 0.0, 2
            ),
            "sensitivity": payload.get("sensitivity") or "public",
            "record_payload": record_payload,
            "ai_suggestion": payload.get("ai_suggestion") or {},
            "sync_state": payload.get("sync_state") or "synced",
            "extra": extra,
            "created_at": payload.get("created_at")
            or (existing or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        if self._payloads_equivalent(observation, existing):
            return existing
        return self._store_payload_locked(
            "survey_observations",
            "observation_id",
            observation,
            {
                "project_id": observation["project_id"],
                "site_id": observation["site_id"],
                "route_id": observation["route_id"],
                "snapped_route_id": observation["snapped_route_id"],
                "scientific_name": observation["scientific_name"],
                "chinese_name": observation["chinese_name"],
                "english_name": observation["english_name"],
                "taxon_id": observation["taxon_id"],
                "taxon_group": observation["taxon_group"],
                "event_id": observation["event_id"],
                "program": observation["program"],
                "submodule": observation["submodule"],
                "protocol": observation["protocol"],
                "jurisdiction": observation["jurisdiction"],
                "observed_at": observation["observed_at"],
            },
        )

    def _upsert_track_locked(self, payload: dict) -> dict:
        now = _utc_now()
        track_id = payload.get("track_id") or self._make_id("track")
        incoming_observer = payload.get("observer") if "observer" in payload else None
        incoming_weather_supplied = "weather" in payload
        incoming_weather = payload.get("weather") if incoming_weather_supplied else None
        existing = self._get_by_id_locked("track", track_id)
        if existing:
            payload = _merge_payload_patch(existing, payload)
        geometry = (
            payload.get("geometry")
            or (existing or {}).get("geometry")
            or {"type": "LineString", "coordinates": []}
        )
        coordinates = _extract_line_coordinates(geometry)
        started_at = (
            payload.get("started_at") or (existing or {}).get("started_at") or now
        )
        ended_at = payload.get("ended_at") or now
        existing_extra = (
            (existing or {}).get("extra")
            if isinstance((existing or {}).get("extra"), dict)
            else {}
        )
        incoming_extra = (
            payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        )
        extra = dict(existing_extra)
        extra.update(incoming_extra)
        event_id = str(
            payload.get("event_id")
            or extra.get("event_id")
            or (existing or {}).get("event_id")
            or ""
        ).strip()
        if not event_id:
            raise ValueError("event_id: track requires explicit event_id linkage")
        linked_event = self._get_by_id_locked("event", event_id)
        if not linked_event:
            raise ValueError(
                f"event_id: linked event {event_id} was not found for track"
            )
        event_program = str(linked_event.get("program") or "").strip()
        event_protocol = str(linked_event.get("protocol") or "").strip()
        event_jurisdiction = str(linked_event.get("jurisdiction") or "").strip()
        requested_program = str(
            payload.get("program")
            or extra.get("program")
            or (existing or {}).get("program")
            or ""
        ).strip()
        requested_protocol = str(
            payload.get("protocol")
            or extra.get("protocol")
            or (existing or {}).get("protocol")
            or ""
        ).strip()
        requested_jurisdiction = str(
            payload.get("jurisdiction")
            or extra.get("jurisdiction")
            or (existing or {}).get("jurisdiction")
            or ""
        ).strip()
        if (
            requested_protocol
            and event_protocol
            and requested_protocol != event_protocol
        ):
            raise ValueError(
                f"protocol: track protocol {requested_protocol} does not match linked event protocol {event_protocol}"
            )
        protocol = event_protocol or requested_protocol
        program = _program_for_protocol(protocol, event_program or requested_program)
        jurisdiction = event_jurisdiction or requested_jurisdiction or "mainland_china"
        _validate_protocol_context(protocol, program, jurisdiction)
        submodule = _normalize_submodule(protocol, program, payload, linked_event)
        route_id = str(
            payload.get("route_id")
            or (existing or {}).get("route_id")
            or linked_event.get("route_id")
            or ""
        ).strip()
        event_route_id = str(linked_event.get("route_id") or "").strip()
        if event_route_id and route_id and route_id != event_route_id:
            raise ValueError(
                f"route_id: track route_id {route_id} does not match linked event route_id {event_route_id}"
            )
        if event_route_id:
            route_id = event_route_id
        project_id = str(
            payload.get("project_id") or linked_event.get("project_id") or ""
        ).strip()
        payload_project_id = str(payload.get("project_id") or "").strip()
        if payload_project_id and project_id and payload_project_id != project_id:
            raise ValueError(
                "project_id: track project_id does not match linked event project_id"
            )
        site_id = str(
            payload.get("site_id") or linked_event.get("site_id") or ""
        ).strip()
        payload_site_id = str(payload.get("site_id") or "").strip()
        if payload_site_id and site_id and payload_site_id != site_id:
            raise ValueError(
                "site_id: track site_id does not match linked event site_id"
            )
        extra["event_id"] = event_id
        if protocol:
            extra["protocol"] = protocol
        if program:
            extra["program"] = program
        if jurisdiction:
            extra["jurisdiction"] = jurisdiction
        if submodule:
            extra["submodule"] = submodule
        if incoming_observer not in (None, ""):
            extra["observer"] = incoming_observer
        if incoming_weather_supplied:
            extra["weather"] = incoming_weather
        duration_s = _coerce_float(payload.get("duration_s"))
        if duration_s is None:
            try:
                started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                ended = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                duration_s = max(0.0, (ended - started).total_seconds())
            except ValueError:
                duration_s = 0.0
        track = {
            "track_id": track_id,
            "project_id": project_id,
            "site_id": site_id,
            "route_id": route_id,
            "event_id": event_id,
            "program": program,
            "submodule": submodule,
            "protocol": protocol,
            "jurisdiction": jurisdiction,
            "name": payload.get("name") or "鐜板満杞ㄨ抗",
            "source": payload.get("source") or "recorded",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "point_times": payload.get("point_times") or [],
            "distance_m": round(
                _coerce_float(payload.get("distance_m"), _line_length_m(coordinates))
                or 0.0,
                2,
            ),
            "duration_s": round(duration_s or 0.0, 2),
            "started_at": started_at,
            "ended_at": ended_at,
            "observer": payload.get("observer") or extra.get("observer") or "",
            "weather": payload.get("weather") or extra.get("weather") or {},
            "sync_state": payload.get("sync_state") or "synced",
            "extra": extra,
            "created_at": payload.get("created_at")
            or (existing or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        if self._payloads_equivalent(track, existing):
            return existing
        return self._store_payload_locked(
            "survey_tracks",
            "track_id",
            track,
            {
                "project_id": track["project_id"],
                "site_id": track["site_id"],
                "route_id": track["route_id"],
                "event_id": track["event_id"],
                "program": track["program"],
                "submodule": track["submodule"],
                "protocol": track["protocol"],
                "jurisdiction": track["jurisdiction"],
                "name": track["name"],
                "source": track["source"],
                "distance_m": track["distance_m"],
            },
        )

    def _create_map_package_locked(self, payload: dict) -> dict:
        now = _utc_now()
        package_id = payload.get("package_id") or self._make_id("pkg")
        existing = self._get_by_id_locked("map_package", package_id)
        if existing:
            payload = _merge_payload_patch(existing, payload)
        bbox = payload.get("bbox") or {}
        min_zoom = _coerce_int(payload.get("min_zoom"), 8)
        max_zoom = _coerce_int(payload.get("max_zoom"), 14)
        tile_count = _coerce_int(
            payload.get("tile_count_estimate"),
            _estimate_tile_count(bbox, min_zoom, max_zoom),
        )
        storage_estimate = _coerce_int(
            payload.get("storage_bytes_estimate"), tile_count * 18000
        )
        expires_at = payload.get("expires_at")
        if not expires_at:
            expires_at = (
                (datetime.now(UTC) + timedelta(days=30))
                .isoformat()
                .replace("+00:00", "Z")
            )
        package = {
            "package_id": package_id,
            "project_id": payload.get("project_id") or "",
            "name": payload.get("name") or "绂荤嚎搴曞浘鍖?",
            "bbox": bbox,
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "tile_url": payload.get("tile_url") or "",
            "tile_count_estimate": tile_count,
            "storage_bytes_estimate": storage_estimate,
            "expires_at": expires_at,
            "status": payload.get("status") or "planned",
            "sync_state": payload.get("sync_state") or "synced",
            "extra": payload.get("extra") or {},
            "created_at": payload.get("created_at")
            or (existing or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        if self._payloads_equivalent(package, existing):
            return existing
        return self._store_payload_locked(
            "survey_map_packages",
            "package_id",
            package,
            {
                "project_id": package["project_id"],
                "name": package["name"],
                "min_zoom": package["min_zoom"],
                "max_zoom": package["max_zoom"],
                "status": package["status"],
            },
        )

    def _upsert_design_asset_locked(self, payload: dict) -> dict:
        now = _utc_now()
        asset_id = payload.get("asset_id") or self._make_id("asset")
        existing = self._get_by_id_locked("design_asset", asset_id)
        if existing:
            payload = _merge_payload_patch(existing, payload)
        protocol = str(
            payload.get("protocol") or (existing or {}).get("protocol") or ""
        ).strip()
        program = _program_for_protocol(
            protocol, payload.get("program") or (existing or {}).get("program") or ""
        )
        submodule = _normalize_submodule(protocol, program, payload, existing)
        geometry = payload.get("geometry")
        if geometry is None:
            geometry = (existing or {}).get("geometry")
        asset = {
            "asset_id": asset_id,
            "project_id": payload.get("project_id") or "",
            "site_id": payload.get("site_id") or "",
            "asset_type": payload.get("asset_type")
            or (existing or {}).get("asset_type")
            or "route",
            "program": program,
            "submodule": submodule,
            "protocol": protocol,
            "name": payload.get("name")
            or (existing or {}).get("name")
            or "Unnamed Design Asset",
            "geometry": geometry,
            "parent_asset_id": payload.get("parent_asset_id") or "",
            "route_id": payload.get("route_id") or "",
            "status": payload.get("status")
            or (existing or {}).get("status")
            or "active",
            "sensitivity": payload.get("sensitivity")
            or (existing or {}).get("sensitivity")
            or "public",
            "notes": payload.get("notes") or "",
            "sync_state": payload.get("sync_state") or "synced",
            "extra": {
                **(
                    (
                        (existing or {}).get("extra")
                        if isinstance((existing or {}).get("extra"), dict)
                        else {}
                    )
                    or {}
                ),
                **(
                    (
                        payload.get("extra")
                        if isinstance(payload.get("extra"), dict)
                        else {}
                    )
                    or {}
                ),
                **({"submodule": submodule} if submodule else {}),
            },
            "created_at": payload.get("created_at")
            or (existing or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        if self._payloads_equivalent(asset, existing):
            return existing
        return self._store_payload_locked(
            "survey_design_assets",
            "asset_id",
            asset,
            {
                "project_id": asset["project_id"],
                "site_id": asset["site_id"],
                "asset_type": asset["asset_type"],
                "program": asset["program"],
                "submodule": asset["submodule"],
                "protocol": asset["protocol"],
                "name": asset["name"],
                "status": asset["status"],
            },
        )

    def _upsert_event_locked(self, payload: dict) -> dict:
        now = _utc_now()
        event_id = payload.get("event_id") or self._make_id("event")
        existing = self._get_by_id_locked("event", event_id)
        if existing:
            payload = _merge_payload_patch(existing, payload)
        protocol = str(
            payload.get("protocol") or (existing or {}).get("protocol") or ""
        ).strip()
        jurisdiction = str(
            payload.get("jurisdiction")
            or (existing or {}).get("jurisdiction")
            or "mainland_china"
        ).strip()
        requested_program = str(
            payload.get("program") or (existing or {}).get("program") or ""
        ).strip()
        _validate_protocol_context(protocol, requested_program, jurisdiction)
        program = _program_for_protocol(protocol, requested_program)
        submodule = _normalize_submodule(protocol, program, payload, existing)
        started_at = (
            payload.get("started_at") or (existing or {}).get("started_at") or now
        )
        ended_at = (
            payload.get("ended_at") or (existing or {}).get("ended_at") or started_at
        )
        observers = payload.get("observers")
        if not observers:
            observers = (
                _string_list(payload.get("observer"))
                or (existing or {}).get("observers")
                or []
            )
        geometry = payload.get("geometry")
        if geometry is None:
            geometry = (existing or {}).get("geometry")
        event_payload = _normalize_terrestrial_event_payload(
            protocol,
            payload.get("event_payload"),
            existing=(existing or {}).get("event_payload"),
            weather=payload.get("weather") or (existing or {}).get("weather") or {},
            effort_metrics=payload.get("effort_metrics")
            or (existing or {}).get("effort_metrics")
            or {},
            observers=observers,
            route_name=payload.get("name") or payload.get("route_name") or "",
        )
        extra = dict((existing or {}).get("extra") or {})
        incoming_extra = (
            payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        )
        extra.update(incoming_extra)
        if protocol:
            extra["protocol"] = protocol
        if program:
            extra["program"] = program
        extra["jurisdiction"] = jurisdiction
        if submodule:
            extra["submodule"] = submodule
        event = {
            "event_id": event_id,
            "project_id": payload.get("project_id") or "",
            "site_id": payload.get("site_id") or "",
            "design_asset_id": payload.get("design_asset_id") or "",
            "route_id": payload.get("route_id") or "",
            "program": program,
            "submodule": submodule,
            "protocol": protocol,
            "jurisdiction": jurisdiction,
            "started_at": started_at,
            "ended_at": ended_at,
            "geometry": geometry,
            "weather": payload.get("weather") or (existing or {}).get("weather") or {},
            "effort_metrics": payload.get("effort_metrics")
            or (existing or {}).get("effort_metrics")
            or {},
            "event_payload": event_payload,
            "observers": observers,
            "team": payload.get("team") or (existing or {}).get("team") or [],
            "notes": payload.get("notes") or "",
            "sync_state": payload.get("sync_state") or "synced",
            "extra": extra,
            "created_at": payload.get("created_at")
            or (existing or {}).get("created_at")
            or now,
            "updated_at": now,
        }
        if self._payloads_equivalent(event, existing):
            return existing
        return self._store_payload_locked(
            "survey_events",
            "event_id",
            event,
            {
                "project_id": event["project_id"],
                "site_id": event["site_id"],
                "design_asset_id": event["design_asset_id"],
                "route_id": event["route_id"],
                "program": event["program"],
                "submodule": event["submodule"],
                "protocol": event["protocol"],
                "jurisdiction": event["jurisdiction"],
                "started_at": event["started_at"],
                "ended_at": event["ended_at"],
            },
        )

    def _apply_entity_upsert_locked(self, entity_type: str, payload: dict) -> dict:
        meta = self._ENTITY_META[entity_type]
        entity_id = str(payload.get(meta["id_field"]) or "").strip()
        if entity_id:
            existing = self._get_by_id_locked(entity_type, entity_id)
            if existing:
                payload = _merge_payload_patch(existing, payload)
        if entity_type == "project":
            return self._upsert_project_locked(payload)
        if entity_type == "site":
            return self._upsert_site_locked(payload)
        if entity_type == "route":
            return self._upsert_route_locked(payload)
        if entity_type == "observation":
            return self._upsert_observation_locked(payload)
        if entity_type == "track":
            return self._upsert_track_locked(payload)
        if entity_type == "design_asset":
            return self._upsert_design_asset_locked(payload)
        if entity_type == "event":
            return self._upsert_event_locked(payload)
        return self._create_map_package_locked(payload)

    def _list_payloads(self, query: str, params: tuple = ()) -> list[dict]:
        return self._run_with_retry(
            lambda: self._list_payloads_locked(query, params),
            write=False,
        )

    def _get_by_id(self, entity_type: str, entity_id: str) -> Optional[dict]:
        return self._run_with_retry(
            lambda: self._get_by_id_locked(entity_type, entity_id),
            write=False,
        )

    def _store_payload(
        self,
        table: str,
        id_field: str,
        payload: dict,
        summary: dict,
    ) -> dict:
        return self._run_with_retry(
            lambda: self._store_payload_locked(table, id_field, payload, summary),
            write=True,
        )

    def list_projects(self) -> list[dict]:
        return self._list_payloads(
            "SELECT * FROM survey_projects WHERE deleted_at='' "
            "ORDER BY updated_at DESC, created_at DESC"
        )

    def upsert_project(self, payload: dict) -> dict:
        return self._run_with_retry(
            lambda: self._upsert_project_locked(payload),
            write=True,
        )

    def list_sites(self, project_id: str = "") -> list[dict]:
        if project_id:
            return self._list_payloads(
                "SELECT * FROM survey_sites WHERE deleted_at='' AND project_id=? "
                "ORDER BY updated_at DESC, created_at DESC",
                (project_id,),
            )
        return self._list_payloads(
            "SELECT * FROM survey_sites WHERE deleted_at='' "
            "ORDER BY updated_at DESC, created_at DESC"
        )

    def upsert_site(self, payload: dict) -> dict:
        return self._run_with_retry(
            lambda: self._upsert_site_locked(payload),
            write=True,
        )

    def list_routes(self, project_id: str = "", site_id: str = "") -> list[dict]:
        filters: list[str] = ["deleted_at=''"]
        params: list = []
        if project_id:
            filters.append("project_id=?")
            params.append(project_id)
        if site_id:
            filters.append("site_id=?")
            params.append(site_id)
        where = f"WHERE {' AND '.join(filters)}"
        return self._list_payloads(
            f"SELECT * FROM survey_routes {where} ORDER BY updated_at DESC, created_at DESC",
            tuple(params),
        )

    def upsert_route(self, payload: dict) -> dict:
        return self._run_with_retry(
            lambda: self._upsert_route_locked(payload),
            write=True,
        )

    def import_route(
        self,
        *,
        project_id: str,
        site_id: str,
        name: str,
        route_type: str,
        filename: str,
        content: str,
    ) -> dict:
        lower_name = (filename or "").lower()
        if lower_name.endswith(".gpx"):
            parsed = _parse_gpx_text(content)
            imported_format = "gpx"
        else:
            parsed = _parse_geojson_text(content)
            imported_format = "geojson"
        return self.upsert_route(
            {
                "project_id": project_id,
                "site_id": site_id,
                "name": name or Path(filename or "").stem or "Imported Route",
                "route_type": route_type or "transect",
                "geometry": parsed["geometry"],
                "length_m": parsed["length_m"],
                "source": "imported",
                "imported_format": imported_format,
                "original_filename": filename,
                "point_times": parsed["point_times"],
            }
        )

    def export_route(self, route_id: str, export_format: str) -> dict:
        route = self._get_by_id("route", route_id)
        if not route:
            raise KeyError("route not found")
        fmt = (export_format or "geojson").strip().lower()
        coordinates = _extract_line_coordinates(route.get("geometry"))
        if fmt == "gpx":
            content = _build_gpx_document(
                route.get("name", "route"), coordinates, route.get("point_times")
            )
            media_type = "application/gpx+xml"
            suffix = "gpx"
        elif fmt == "csv":
            content = _route_summary_csv(route)
            media_type = "text/csv"
            suffix = "csv"
        else:
            content = json.dumps(
                _feature_collection_for_line(route), ensure_ascii=False, indent=2
            )
            media_type = "application/geo+json"
            suffix = "geojson"
        safe_name = (
            (route.get("name") or "route").replace("/", "_").replace("\\", "_").strip()
        )
        return {
            "filename": f"{safe_name or 'route'}.{suffix}",
            "content": content,
            "media_type": media_type,
            "format": fmt,
        }

    def get_route_summary(self, route_id: str) -> dict:
        route = self._get_by_id("route", route_id)
        if not route:
            raise KeyError("route not found")

        observations = [
            observation
            for observation in self.list_observations(
                project_id=route.get("project_id", ""),
                site_id=route.get("site_id", ""),
            )
            if observation.get("route_id") == route_id
            or observation.get("snapped_route_id") == route_id
        ]
        tracks = [
            track
            for track in self.list_tracks(
                project_id=route.get("project_id", ""),
                site_id=route.get("site_id", ""),
            )
            if track.get("route_id") == route_id
        ]
        tracks.sort(
            key=lambda track: (track.get("started_at", ""), track.get("updated_at", ""))
        )

        species_index: dict[str, dict] = {}
        observer_index: dict[str, dict] = {}
        observed_times: list[datetime] = []
        individual_count = 0

        for observation in observations:
            observed_at = observation.get("observed_at") or ""
            observed_dt = _parse_iso_datetime(observed_at)
            if observed_dt is not None:
                observed_times.append(observed_dt)

            count = max(_coerce_int(observation.get("count"), 1), 0)
            individual_count += count

            species_identity = _extract_species_identity(observation)
            species_key = "|".join(
                [
                    species_identity.get("scientific_name", ""),
                    species_identity.get("chinese_name", ""),
                    species_identity.get("english_name", ""),
                    species_identity.get("display_name", ""),
                ]
            )
            species_entry = species_index.setdefault(
                species_key,
                {
                    **species_identity,
                    "observation_count": 0,
                    "individual_count": 0,
                    "first_observed_at": observed_at,
                    "last_observed_at": observed_at,
                    "observers": [],
                },
            )
            species_entry["observation_count"] += 1
            species_entry["individual_count"] += count
            if observed_at:
                if (
                    not species_entry.get("first_observed_at")
                    or observed_at < species_entry["first_observed_at"]
                ):
                    species_entry["first_observed_at"] = observed_at
                if (
                    not species_entry.get("last_observed_at")
                    or observed_at > species_entry["last_observed_at"]
                ):
                    species_entry["last_observed_at"] = observed_at

            for observer_name in _observer_names(observation):
                if observer_name not in species_entry["observers"]:
                    species_entry["observers"].append(observer_name)
                observer_entry = observer_index.setdefault(
                    observer_name,
                    {
                        "name": observer_name,
                        "observation_count": 0,
                        "individual_count": 0,
                        "track_count": 0,
                    },
                )
                observer_entry["observation_count"] += 1
                observer_entry["individual_count"] += count

        walked_distance_m = 0.0
        total_duration_s = 0.0
        for track in tracks:
            walked_distance_m += _coerce_float(track.get("distance_m"), 0.0) or 0.0
            duration_s = _coerce_float(track.get("duration_s"), 0.0) or 0.0
            if duration_s <= 0:
                started = _parse_iso_datetime(track.get("started_at"))
                ended = _parse_iso_datetime(track.get("ended_at"))
                if started and ended:
                    duration_s = max(0.0, (ended - started).total_seconds())
            total_duration_s += duration_s

            for observer_name in _observer_names(track):
                observer_entry = observer_index.setdefault(
                    observer_name,
                    {
                        "name": observer_name,
                        "observation_count": 0,
                        "individual_count": 0,
                        "track_count": 0,
                    },
                )
                observer_entry["track_count"] += 1

        effort_minutes = round(total_duration_s / 60.0, 2)
        if effort_minutes == 0.0 and len(observed_times) >= 2:
            span_s = max(
                0.0, (max(observed_times) - min(observed_times)).total_seconds()
            )
            effort_minutes = round(span_s / 60.0, 2)

        species = sorted(
            species_index.values(),
            key=lambda item: (
                -item.get("individual_count", 0),
                -item.get("observation_count", 0),
                item.get("display_name", ""),
            ),
        )
        observers = sorted(
            observer_index.values(),
            key=lambda item: (
                -(item.get("observation_count", 0) + item.get("track_count", 0)),
                -item.get("individual_count", 0),
                item.get("name", ""),
            ),
        )

        return {
            "route": route,
            "totals": {
                "observation_count": len(observations),
                "individual_count": individual_count,
                "unique_species_count": len(species),
                "track_count": len(tracks),
                "planned_distance_m": round(
                    _coerce_float(route.get("length_m"), 0.0) or 0.0, 2
                ),
                "walked_distance_m": round(walked_distance_m, 2),
                "effort_minutes": effort_minutes,
            },
            "species": species,
            "observations": observations,
            "tracks": tracks,
            "observers": observers,
            "weather": _aggregate_weather(observations + tracks),
        }

    def export_route_report(self, route_id: str, export_format: str) -> dict:
        summary = self.get_route_summary(route_id)
        fmt = (export_format or "json").strip().lower()
        route_name = summary.get("route", {}).get("name") or "route"

        if fmt == "json":
            content = json.dumps(
                {"status": "ok", "summary": summary}, ensure_ascii=False, indent=2
            )
            media_type = "application/json"
            suffix = "json"
        elif fmt == "csv":
            content = _species_summary_csv(summary)
            media_type = "text/csv"
            suffix = "csv"
        else:
            raise ValueError("unsupported export format")

        safe_name = _safe_export_name(route_name)
        return {
            "filename": f"{safe_name}-report.{suffix}",
            "content": content,
            "media_type": media_type,
            "format": fmt,
        }

    def list_observations(
        self,
        project_id: str = "",
        site_id: str = "",
        *,
        event_id: str = "",
        program: str = "",
        submodule: str = "",
        protocol: str = "",
        jurisdiction: str = "",
    ) -> list[dict]:
        filters: list[str] = ["deleted_at=''"]
        params: list = []
        if project_id:
            filters.append("project_id=?")
            params.append(project_id)
        if site_id:
            filters.append("site_id=?")
            params.append(site_id)
        where = f"WHERE {' AND '.join(filters)}"
        observations = self._list_payloads(
            f"SELECT * FROM survey_observations {where} ORDER BY observed_at DESC, updated_at DESC",
            tuple(params),
        )
        if not any([event_id, program, submodule, protocol, jurisdiction]):
            return observations

        filtered: list[dict] = []
        for observation in observations:
            extra = (
                observation.get("extra")
                if isinstance(observation.get("extra"), dict)
                else {}
            )
            observation_event_id = str(
                observation.get("event_id") or extra.get("event_id") or ""
            ).strip()
            observation_protocol = str(
                observation.get("protocol") or extra.get("protocol") or ""
            ).strip()
            observation_program = _program_for_protocol(
                observation_protocol,
                observation.get("program") or extra.get("program") or "",
            )
            observation_submodule = str(
                observation.get("submodule") or extra.get("submodule") or ""
            ).strip()
            observation_jurisdiction = str(
                observation.get("jurisdiction") or extra.get("jurisdiction") or ""
            ).strip()
            if event_id and observation_event_id != event_id:
                continue
            if protocol and observation_protocol != protocol:
                continue
            if program and observation_program != program:
                continue
            if submodule and observation_submodule != submodule:
                continue
            if jurisdiction and observation_jurisdiction != jurisdiction:
                continue
            filtered.append(observation)
        return filtered

    def upsert_observation(self, payload: dict) -> dict:
        return self._run_with_retry(
            lambda: self._upsert_observation_locked(payload),
            write=True,
        )

    def list_tracks(
        self,
        project_id: str = "",
        site_id: str = "",
        *,
        event_id: str = "",
        program: str = "",
        submodule: str = "",
        protocol: str = "",
        jurisdiction: str = "",
    ) -> list[dict]:
        filters: list[str] = ["deleted_at=''"]
        params: list = []
        if project_id:
            filters.append("project_id=?")
            params.append(project_id)
        if site_id:
            filters.append("site_id=?")
            params.append(site_id)
        if event_id:
            filters.append("event_id=?")
            params.append(event_id)
        if program:
            filters.append("program=?")
            params.append(program)
        if submodule:
            filters.append("submodule=?")
            params.append(submodule)
        if protocol:
            filters.append("protocol=?")
            params.append(protocol)
        if jurisdiction:
            filters.append("jurisdiction=?")
            params.append(jurisdiction)
        where = f"WHERE {' AND '.join(filters)}"
        return self._list_payloads(
            f"SELECT * FROM survey_tracks {where} ORDER BY updated_at DESC, created_at DESC",
            tuple(params),
        )

    def upsert_track(self, payload: dict) -> dict:
        return self._run_with_retry(
            lambda: self._upsert_track_locked(payload),
            write=True,
        )

    def create_map_package(self, payload: dict) -> dict:
        return self._run_with_retry(
            lambda: self._create_map_package_locked(payload),
            write=True,
        )

    def list_map_packages(self, project_id: str = "") -> list[dict]:
        if project_id:
            return self._list_payloads(
                "SELECT * FROM survey_map_packages WHERE deleted_at='' AND project_id=? "
                "ORDER BY updated_at DESC, created_at DESC",
                (project_id,),
            )
        return self._list_payloads(
            "SELECT * FROM survey_map_packages WHERE deleted_at='' "
            "ORDER BY updated_at DESC, created_at DESC"
        )

    def list_protocol_definitions(
        self, program: str = "", protocol: str = ""
    ) -> list[dict]:
        program_filter = str(program or "").strip()
        protocol_filter = str(protocol or "").strip()
        results: list[dict] = []
        for item in _PROTOCOL_DEFINITIONS:
            if program_filter and item.get("program") != program_filter:
                continue
            if protocol_filter and item.get("protocol") != protocol_filter:
                continue
            results.append(_clone_jsonable(item))
        return results

    def list_taxonomy_packages(
        self,
        *,
        jurisdiction: str = "",
        region: str = "",
        program: str = "",
        protocol: str = "",
    ) -> list[dict]:
        jurisdiction_filter = str(jurisdiction or "").strip()
        region_filter = str(region or "").strip()
        program_filter = str(program or "").strip()
        protocol_filter = str(protocol or "").strip()
        taxonomy_asset = _load_taxonomy_packages_asset()
        manifest_release_id = (
            str(taxonomy_asset.get("taxonomy_release_id") or "").strip()
            if isinstance(taxonomy_asset, dict)
            else ""
        )
        manifest_source_version = (
            str(taxonomy_asset.get("source_manifest_version") or "").strip()
            if isinstance(taxonomy_asset, dict)
            else ""
        )
        try:
            catalog = get_taxonomy_catalog()
        except Exception:
            catalog = None
        release_lookup = (
            catalog.package_status_lookup(current_only=True) if catalog else {}
        )
        results: list[dict] = []
        for item in _TAXONOMY_PACKAGES:
            if jurisdiction_filter and item.get("jurisdiction") != jurisdiction_filter:
                continue
            if region_filter and item.get("region") != region_filter:
                continue
            if program_filter and item.get("program") != program_filter:
                continue
            if protocol_filter and protocol_filter not in (item.get("protocols") or []):
                continue
            record = _clone_jsonable(item)
            manifest = _taxonomy_manifest_entry(
                str(record.get("jurisdiction") or ""),
                str(record.get("program") or ""),
            )
            release_status = release_lookup.get(
                (
                    str(record.get("jurisdiction") or "").strip(),
                    str(record.get("program") or "").strip(),
                ),
                {},
            )
            seed_entries = _taxonomy_seed_entries(
                str(record.get("jurisdiction") or ""),
                str(record.get("program") or ""),
            )
            if manifest:
                record["asset_package_id"] = str(
                    release_status.get("asset_package_id")
                    or release_status.get("package_id")
                    or manifest.get("package_id")
                    or ""
                )
                record["asset_package_version"] = str(
                    release_status.get("package_version")
                    or manifest.get("package_version")
                    or ""
                )
                record["seed_only"] = bool(
                    release_status.get("seed_only", manifest.get("seed_only"))
                )
                record["exhaustive_species_content"] = bool(
                    release_status.get(
                        "exhaustive_species_content",
                        manifest.get("exhaustive_species_content"),
                    )
                )
                record["local_seed_asset_count"] = len(
                    [
                        asset
                        for asset in _taxonomy_package_assets(manifest)
                        if isinstance(asset, dict)
                    ]
                )
            else:
                record["asset_package_id"] = str(
                    release_status.get("asset_package_id")
                    or release_status.get("package_id")
                    or ""
                )
                record["asset_package_version"] = str(
                    release_status.get("package_version") or ""
                )
                record["seed_only"] = bool(release_status.get("seed_only"))
                record["exhaustive_species_content"] = bool(
                    release_status.get("exhaustive_species_content")
                )
                record["local_seed_asset_count"] = 0
            record["taxonomy_release_id"] = str(
                release_status.get("taxonomy_release_id")
                or release_status.get("release_id")
                or manifest_release_id
            )
            record["source_manifest_version"] = str(
                release_status.get("source_manifest_version")
                or manifest_source_version
                or manifest.get("source_manifest_version")
                or ""
            )
            record["expected_count"] = int(
                release_status.get("expected_count")
                or manifest.get("expected_count")
                or 0
            )
            record["catalog_entry_count"] = int(
                release_status.get("catalog_entry_count")
                or release_status.get("catalog_count")
                or release_status.get("imported_count")
                or len(seed_entries)
            )
            record["exhaustive"] = bool(record["exhaustive_species_content"])
            record["catalog_count"] = int(record["catalog_entry_count"])
            record["imported_count"] = int(
                release_status.get("imported_count") or record["catalog_entry_count"]
            )
            record["count_parity_ok"] = bool(release_status.get("count_parity_ok"))
            if not release_status and record["expected_count"]:
                record["count_parity_ok"] = (
                    record["expected_count"] == record["imported_count"]
                )
            record["review_status"] = str(release_status.get("review_status") or "")
            record["checksum"] = str(release_status.get("checksum") or "")
            record["is_current_release"] = bool(
                release_status.get("is_current_release")
            )
            record["submodule_counts"] = _clone_jsonable(
                release_status.get("submodule_counts")
                or manifest.get("submodule_expected_counts")
                or {}
            )
            record["submodule_expected_counts"] = _clone_jsonable(
                manifest.get("submodule_expected_counts")
                or release_status.get("submodule_expected_counts")
                or release_status.get("submodule_counts")
                or {}
            )
            record["catalog_status"] = (
                "seed_only"
                if record["seed_only"]
                else (
                    "exhaustive"
                    if record["exhaustive_species_content"]
                    else "unspecified"
                )
            )
            results.append(record)
        return results

    def list_design_assets(
        self,
        *,
        project_id: str = "",
        site_id: str = "",
        asset_type: str = "",
        program: str = "",
        submodule: str = "",
        protocol: str = "",
    ) -> list[dict]:
        filters: list[str] = ["deleted_at=''"]
        params: list[Any] = []
        if project_id:
            filters.append("project_id=?")
            params.append(project_id)
        if site_id:
            filters.append("site_id=?")
            params.append(site_id)
        if asset_type:
            filters.append("asset_type=?")
            params.append(asset_type)
        if program:
            filters.append("program=?")
            params.append(program)
        if submodule:
            filters.append("submodule=?")
            params.append(submodule)
        if protocol:
            filters.append("protocol=?")
            params.append(protocol)
        where = f"WHERE {' AND '.join(filters)}"
        return self._list_payloads(
            f"SELECT * FROM survey_design_assets {where} ORDER BY updated_at DESC, created_at DESC",
            tuple(params),
        )

    def upsert_design_asset(self, payload: dict) -> dict:
        return self._run_with_retry(
            lambda: self._upsert_design_asset_locked(payload),
            write=True,
        )

    def list_events(
        self,
        *,
        project_id: str = "",
        site_id: str = "",
        event_id: str = "",
        design_asset_id: str = "",
        program: str = "",
        submodule: str = "",
        protocol: str = "",
        jurisdiction: str = "",
    ) -> list[dict]:
        filters: list[str] = ["deleted_at=''"]
        params: list[Any] = []
        if project_id:
            filters.append("project_id=?")
            params.append(project_id)
        if site_id:
            filters.append("site_id=?")
            params.append(site_id)
        if event_id:
            filters.append("event_id=?")
            params.append(event_id)
        if design_asset_id:
            filters.append("design_asset_id=?")
            params.append(design_asset_id)
        if program:
            filters.append("program=?")
            params.append(program)
        if submodule:
            filters.append("submodule=?")
            params.append(submodule)
        if protocol:
            filters.append("protocol=?")
            params.append(protocol)
        if jurisdiction:
            filters.append("jurisdiction=?")
            params.append(jurisdiction)
        where = f"WHERE {' AND '.join(filters)}"
        return self._list_payloads(
            f"SELECT * FROM survey_events {where} ORDER BY started_at DESC, updated_at DESC",
            tuple(params),
        )

    def upsert_event(self, payload: dict) -> dict:
        return self._run_with_retry(
            lambda: self._upsert_event_locked(payload),
            write=True,
        )

    def list_export_jobs(
        self, project_id: str = "", jurisdiction: str = ""
    ) -> list[dict]:
        filters: list[str] = []
        params: list[Any] = []
        if project_id:
            filters.append("project_id=?")
            params.append(project_id)
        if jurisdiction:
            filters.append("jurisdiction=?")
            params.append(jurisdiction)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        return self._list_payloads(
            f"SELECT * FROM survey_export_jobs {where} ORDER BY updated_at DESC, created_at DESC",
            tuple(params),
        )

    def _basic_export_job(self, jurisdiction: str, payload: dict) -> dict:
        now = _utc_now()
        jurisdiction_key = (
            str(jurisdiction or payload.get("jurisdiction") or "").strip()
            or "mainland_china"
        )
        project_id = str(payload.get("project_id") or "").strip()
        site_id = str(payload.get("site_id") or "").strip()
        program = str(payload.get("program") or "").strip()
        submodule = str(payload.get("submodule") or "").strip()
        protocol = str(payload.get("protocol") or "").strip()
        event_id = str(payload.get("event_id") or "").strip()
        extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
        route_id = str(payload.get("route_id") or extra.get("route_id") or "").strip()
        design_asset_id = str(
            payload.get("design_asset_id") or extra.get("design_asset_id") or ""
        ).strip()
        export_format = str(payload.get("format") or "json").strip().lower()

        design_assets = self.list_design_assets(
            project_id=project_id,
            site_id=site_id,
            program=program,
            submodule=submodule,
            protocol=protocol,
        )
        if design_asset_id:
            design_assets = [
                asset
                for asset in design_assets
                if str(asset.get("asset_id") or "").strip() == design_asset_id
            ]
        events = self.list_events(
            project_id=project_id,
            site_id=site_id,
            event_id=event_id,
            program=program,
            submodule=submodule,
            protocol=protocol,
            jurisdiction=jurisdiction_key if jurisdiction_key else "",
        )
        if route_id:
            events = [
                event
                for event in events
                if str(event.get("route_id") or "").strip() == route_id
            ]
        if design_asset_id:
            events = [
                event
                for event in events
                if str(event.get("design_asset_id") or "").strip() == design_asset_id
            ]
        all_candidate_observations = self.list_observations(
            project_id=project_id,
            site_id=site_id,
            event_id=event_id,
            program=program,
            submodule=submodule,
            protocol=protocol,
            jurisdiction="",
        )
        selected_event_ids = {
            str(item.get("event_id") or "").strip()
            for item in events
            if str(item.get("event_id") or "").strip()
        }
        if selected_event_ids:
            observations_for_export = []
            for observation in all_candidate_observations:
                extra = (
                    observation.get("extra")
                    if isinstance(observation.get("extra"), dict)
                    else {}
                )
                observation_event_id = str(
                    observation.get("event_id") or extra.get("event_id") or ""
                ).strip()
                if observation_event_id in selected_event_ids:
                    observations_for_export.append(observation)
        else:
            observations_for_export = []
            if not protocol:
                observations_for_export = [
                    observation
                    for observation in all_candidate_observations
                    if not jurisdiction_key
                    or str(
                        observation.get("jurisdiction")
                        or (
                            (
                                observation.get("extra")
                                if isinstance(observation.get("extra"), dict)
                                else {}
                            ).get("jurisdiction")
                        )
                        or ""
                    ).strip()
                    == jurisdiction_key
                ]
        if route_id:
            observations_for_export = [
                observation
                for observation in observations_for_export
                if str(
                    observation.get("route_id")
                    or observation.get("snapped_route_id")
                    or ""
                ).strip()
                == route_id
            ]
        tracks_for_export = self.list_tracks(
            project_id=project_id,
            site_id=site_id,
            submodule=submodule,
            program=program,
            protocol=protocol,
        )
        if route_id:
            tracks_for_export = [
                track
                for track in tracks_for_export
                if str(track.get("route_id") or "").strip() == route_id
            ]
        if selected_event_ids:
            tracks_for_export = [
                track
                for track in tracks_for_export
                if str(
                    track.get("event_id")
                    or (
                        (
                            track.get("extra")
                            if isinstance(track.get("extra"), dict)
                            else {}
                        ).get("event_id")
                    )
                    or ""
                ).strip()
                in selected_event_ids
            ]
        elif protocol:
            tracks_for_export = []
        packages = self.list_taxonomy_packages(
            jurisdiction=jurisdiction_key,
            program=program,
            protocol=protocol,
        )
        summary = {
            "project_id": project_id,
            "site_id": site_id,
            "jurisdiction": jurisdiction_key,
            "program": program,
            "protocol": protocol,
            "route_id": route_id,
            "design_asset_id": design_asset_id,
            "taxonomy_package_count": len(packages),
            "design_asset_count": len(design_assets),
            "event_count": len(events),
            "observation_count": len(observations_for_export),
            "track_count": len(tracks_for_export),
            "generated_at": now,
        }
        return {
            "export_job_id": self._make_id("export"),
            "project_id": project_id,
            "jurisdiction": jurisdiction_key,
            "format": export_format,
            "status": "ready",
            "filters": {
                "project_id": project_id,
                "site_id": site_id,
                "program": program,
                "protocol": protocol,
                "event_id": event_id,
                "route_id": route_id,
                "design_asset_id": design_asset_id,
            },
            "summary": summary,
            "bundle": {
                "manifest": {
                    "jurisdiction": jurisdiction_key,
                    "generated_at": now,
                    "project_id": project_id,
                    "site_id": site_id,
                    "program": program,
                    "protocol": protocol,
                    "event_id": event_id,
                    "route_id": route_id,
                    "design_asset_id": design_asset_id,
                },
                "summary": summary,
                "taxonomy_packages": packages,
                "design_assets": design_assets,
                "events": events,
                "observations": observations_for_export,
                "tracks": tracks_for_export,
                "files": [],
            },
            "extra": extra,
            "created_at": now,
            "updated_at": now,
        }

    def _build_event_export_contexts(
        self,
        *,
        events: list[dict],
        observations: list[dict],
        design_assets: list[dict],
        tracks: list[dict],
        jurisdiction: str,
    ) -> list[dict[str, Any]]:
        assets_by_id = {
            str(asset.get("asset_id") or "").strip(): asset
            for asset in design_assets
            if str(asset.get("asset_id") or "").strip()
        }
        tracks_by_event: dict[str, list[dict]] = defaultdict(list)
        for track in tracks:
            extra = track.get("extra") if isinstance(track.get("extra"), dict) else {}
            key = str(track.get("event_id") or extra.get("event_id") or "").strip()
            if key:
                tracks_by_event[key].append(track)
        contexts: list[dict[str, Any]] = []
        for event in events:
            event_id = str(event.get("event_id") or "").strip()
            design_asset = (
                assets_by_id.get(str(event.get("design_asset_id") or "").strip()) or {}
            )
            related_records: list[dict[str, Any]] = []
            for observation in observations:
                extra = (
                    observation.get("extra")
                    if isinstance(observation.get("extra"), dict)
                    else {}
                )
                observation_event_id = str(
                    observation.get("event_id") or extra.get("event_id") or ""
                ).strip()
                if observation_event_id != event_id:
                    continue
                taxonomy = _taxonomy_entry_for_observation(observation, jurisdiction)
                export_mask = _export_mask_info(observation, taxonomy, jurisdiction)
                related_records.append(
                    {
                        "event": event,
                        "record": observation,
                        "taxonomy": taxonomy,
                        "design_asset": design_asset,
                        "tracks": tracks_by_event.get(event_id, []),
                        "record_payload": observation.get("record_payload") or {},
                        "export_mask": export_mask,
                    }
                )
            event_context = {
                "event": {
                    **event,
                    "track_log_id": (
                        (tracks_by_event.get(event_id) or [{}])[0].get("track_id")
                        if tracks_by_event.get(event_id)
                        else ""
                    ),
                },
                "design_asset": design_asset,
                "records": related_records,
                "tracks": tracks_by_event.get(event_id, []),
                "record": related_records[0]["record"] if related_records else {},
                "taxonomy": (
                    related_records[0]["taxonomy"]
                    if related_records
                    else {
                        "names": {},
                        "status_flags": {jurisdiction: {}},
                    }
                ),
                "record_payload": (
                    related_records[0]["record_payload"] if related_records else {}
                ),
                "export_mask": (
                    related_records[0]["export_mask"] if related_records else {}
                ),
            }
            contexts.append(event_context)
        return contexts

    def _group_export_contexts(
        self,
        output_name: str,
        output_profile: dict,
        event_contexts: list[dict[str, Any]],
        jurisdiction: str,
    ) -> list[dict[str, Any]]:
        aggregation = str(output_profile.get("aggregation") or "").strip()
        if output_name in {"event_summary", "effort_summary"} or not aggregation:
            return event_contexts

        grouped: dict[str, dict[str, Any]] = {}
        for event_context in event_contexts:
            records = event_context.get("records") or []
            if not records:
                if aggregation in {
                    "group_by_route_or_segment",
                    "group_by_trap_station_id",
                }:
                    continue
                records = [
                    {
                        "event": event_context.get("event") or {},
                        "record": {},
                        "taxonomy": {"names": {}, "status_flags": {jurisdiction: {}}},
                        "record_payload": {},
                        "export_mask": {},
                        "design_asset": event_context.get("design_asset") or {},
                        "tracks": event_context.get("tracks") or [],
                    }
                ]
            for record_context in records:
                event = record_context.get("event") or event_context.get("event") or {}
                record_payload = record_context.get("record_payload") or {}
                if aggregation == "group_by_event_and_taxon":
                    group_key = "|".join(
                        [
                            str(event.get("event_id") or ""),
                            str(record_payload.get("taxon_id") or ""),
                        ]
                    )
                elif aggregation == "group_by_route_or_segment":
                    group_key = "|".join(
                        [
                            str(event.get("design_asset_id") or ""),
                            str(record_payload.get("route_segment_id") or ""),
                        ]
                    )
                elif aggregation == "group_by_trap_station_id":
                    group_key = str(record_payload.get("trap_station_id") or "")
                elif aggregation == "group_by_event_point_and_taxon":
                    group_key = "|".join(
                        [
                            str(event.get("event_id") or ""),
                            str(
                                record_payload.get("point_id")
                                or (event.get("event_payload") or {}).get("point_id")
                                or ""
                            ),
                            str(record_payload.get("taxon_id") or ""),
                        ]
                    )
                elif aggregation == "group_by_point_id":
                    group_key = str(
                        record_payload.get("point_id")
                        or (event.get("event_payload") or {}).get("point_id")
                        or ""
                    )
                else:
                    group_key = str(event.get("event_id") or "")
                if not group_key:
                    continue
                group = grouped.setdefault(
                    group_key,
                    {
                        "event": event_context.get("event") or {},
                        "design_asset": event_context.get("design_asset") or {},
                        "records": [],
                        "tracks": event_context.get("tracks") or [],
                        "record": record_context.get("record") or {},
                        "taxonomy": record_context.get("taxonomy")
                        or {"names": {}, "status_flags": {jurisdiction: {}}},
                        "record_payload": record_payload,
                        "export_mask": record_context.get("export_mask") or {},
                    },
                )
                group["records"].append(record_context)
        return list(grouped.values())

    def _build_export_file_descriptor(
        self,
        *,
        output_name: str,
        output_profile: dict,
        grouped_contexts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        columns = output_profile.get("columns") or []
        rows: list[dict[str, Any]] = []
        for grouped_context in grouped_contexts:
            row = {}
            member_contexts = grouped_context.get("records") or [grouped_context]
            for column in columns:
                row[str(column.get("column_id") or "")] = _aggregate_contexts(
                    member_contexts, column
                )
            rows.append(row)
        headers = [str(column.get("column_id") or "") for column in columns]
        content = _csv_from_rows(headers, rows)
        filename = f"{output_profile.get('file_stub') or output_name}.csv"
        return {
            "output_id": output_name,
            "filename": filename,
            "format": str(output_profile.get("format") or "csv"),
            "media_type": "text/csv",
            "content": content,
            "row_count": len(rows),
            "columns": headers,
        }

    def _build_generic_export_files(
        self, export_job: dict[str, Any]
    ) -> list[dict[str, Any]]:
        bundle = export_job.get("bundle") or {}
        observations = bundle.get("observations") or []
        events = bundle.get("events") or []
        tracks = bundle.get("tracks") or []
        design_assets = bundle.get("design_assets") or []
        manifest = bundle.get("manifest") or {}
        summary = export_job.get("summary") or {}
        taxonomy_packages = bundle.get("taxonomy_packages") or []

        files: list[dict[str, Any]] = [
            {
                "output_id": "bundle_manifest",
                "filename": "bundle_manifest.json",
                "format": "json",
                "media_type": "application/json",
                "content": json.dumps(
                    {
                        "manifest": manifest,
                        "summary": summary,
                        "taxonomy_packages": [
                            {
                                "package_id": item.get("package_id", ""),
                                "label": item.get("label", ""),
                                "jurisdiction": item.get("jurisdiction", ""),
                                "program": item.get("program", ""),
                                "taxonomy_release_id": item.get(
                                    "taxonomy_release_id", ""
                                ),
                                "source_manifest_version": item.get(
                                    "source_manifest_version", ""
                                ),
                                "seed_only": bool(item.get("seed_only")),
                                "exhaustive": bool(
                                    item.get("exhaustive")
                                    or item.get("exhaustive_species_content")
                                ),
                                "expected_count": int(item.get("expected_count") or 0),
                                "catalog_count": int(
                                    item.get("catalog_count")
                                    or item.get("catalog_entry_count")
                                    or 0
                                ),
                                "count_parity_ok": bool(item.get("count_parity_ok")),
                                "review_status": item.get("review_status", ""),
                                "checksum": item.get("checksum", ""),
                                "is_current_release": bool(
                                    item.get("is_current_release")
                                ),
                            }
                            for item in taxonomy_packages
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        ]

        event_rows = [
            {
                "event_id": item.get("event_id", ""),
                "protocol": item.get("protocol", ""),
                "jurisdiction": item.get("jurisdiction", ""),
                "project_id": item.get("project_id", ""),
                "site_id": item.get("site_id", ""),
                "route_id": item.get("route_id", ""),
                "design_asset_id": item.get("design_asset_id", ""),
                "started_at": item.get("started_at", ""),
                "ended_at": item.get("ended_at", ""),
                "observer_count": len(item.get("observers") or []),
                "observers": "; ".join(_string_list(item.get("observers"))),
                "effort_metrics": json.dumps(
                    item.get("effort_metrics") or {},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "event_payload": json.dumps(
                    item.get("event_payload") or {},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "notes": item.get("notes", ""),
            }
            for item in events
        ]
        files.append(
            {
                "output_id": "sampling_events",
                "filename": "sampling_events.csv",
                "format": "csv",
                "media_type": "text/csv",
                "content": _csv_from_rows(
                    [
                        "event_id",
                        "protocol",
                        "jurisdiction",
                        "project_id",
                        "site_id",
                        "route_id",
                        "design_asset_id",
                        "started_at",
                        "ended_at",
                        "observer_count",
                        "observers",
                        "effort_metrics",
                        "event_payload",
                        "notes",
                    ],
                    event_rows,
                ),
                "row_count": len(event_rows),
            }
        )

        species_record_rows = []
        species_rollup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for item in observations:
            identity = _extract_species_identity(item)
            observed_at = str(item.get("observed_at") or "")
            record_payload = (
                item.get("record_payload")
                or (
                    (
                        item.get("extra") if isinstance(item.get("extra"), dict) else {}
                    ).get("record_payload")
                )
                or {}
            )
            species_record_rows.append(
                {
                    "observation_id": item.get("observation_id", ""),
                    "event_id": item.get("event_id", ""),
                    "route_id": item.get("route_id", ""),
                    "snapped_route_id": item.get("snapped_route_id", ""),
                    "scientific_name": identity.get("scientific_name", ""),
                    "chinese_name": identity.get("chinese_name", ""),
                    "english_name": identity.get("english_name", ""),
                    "taxon_group": identity.get("taxon_group", ""),
                    "count": item.get("count", 0),
                    "observed_at": observed_at,
                    "observer": item.get("observer", ""),
                    "evidence_type": item.get("evidence_type", ""),
                    "latitude": item.get("latitude", ""),
                    "longitude": item.get("longitude", ""),
                    "media_count": len(item.get("media") or []),
                    "record_payload": json.dumps(
                        record_payload, ensure_ascii=False, separators=(",", ":")
                    ),
                }
            )
            key = (
                identity.get("scientific_name", ""),
                identity.get("chinese_name", ""),
                identity.get("english_name", ""),
                identity.get("taxon_group", ""),
            )
            species_entry = species_rollup.setdefault(
                key,
                {
                    "scientific_name": identity.get("scientific_name", ""),
                    "chinese_name": identity.get("chinese_name", ""),
                    "english_name": identity.get("english_name", ""),
                    "taxon_group": identity.get("taxon_group", ""),
                    "observation_count": 0,
                    "individual_count": 0,
                    "first_observed_at": observed_at,
                    "last_observed_at": observed_at,
                },
            )
            species_entry["observation_count"] += 1
            species_entry["individual_count"] += _coerce_int(item.get("count"), 0)
            if observed_at and (
                not species_entry["first_observed_at"]
                or observed_at < species_entry["first_observed_at"]
            ):
                species_entry["first_observed_at"] = observed_at
            if observed_at and (
                not species_entry["last_observed_at"]
                or observed_at > species_entry["last_observed_at"]
            ):
                species_entry["last_observed_at"] = observed_at

        files.append(
            {
                "output_id": "species_records",
                "filename": "species_records.csv",
                "format": "csv",
                "media_type": "text/csv",
                "content": _csv_from_rows(
                    [
                        "observation_id",
                        "event_id",
                        "route_id",
                        "snapped_route_id",
                        "scientific_name",
                        "chinese_name",
                        "english_name",
                        "taxon_group",
                        "count",
                        "observed_at",
                        "observer",
                        "evidence_type",
                        "latitude",
                        "longitude",
                        "media_count",
                        "record_payload",
                    ],
                    species_record_rows,
                ),
                "row_count": len(species_record_rows),
            }
        )

        species_list_rows = list(species_rollup.values())
        files.append(
            {
                "output_id": "species_list",
                "filename": "species_list.csv",
                "format": "csv",
                "media_type": "text/csv",
                "content": _csv_from_rows(
                    [
                        "scientific_name",
                        "chinese_name",
                        "english_name",
                        "taxon_group",
                        "observation_count",
                        "individual_count",
                        "first_observed_at",
                        "last_observed_at",
                    ],
                    species_list_rows,
                ),
                "row_count": len(species_list_rows),
            }
        )

        scope_rows: dict[str, dict[str, Any]] = {}
        assets_by_id = {
            str(asset.get("asset_id") or "").strip(): asset
            for asset in design_assets
            if str(asset.get("asset_id") or "").strip()
        }

        def ensure_scope(
            scope_id: str, scope_type: str, scope_name: str = ""
        ) -> dict[str, Any]:
            key = f"{scope_type}:{scope_id or 'site_scope'}"
            row = scope_rows.setdefault(
                key,
                {
                    "scope_id": scope_id or "site_scope",
                    "scope_type": scope_type,
                    "scope_name": scope_name or scope_id or "Site scope",
                    "event_count": 0,
                    "observation_count": 0,
                    "track_count": 0,
                },
            )
            return row

        for event in events:
            asset_id = str(event.get("design_asset_id") or "").strip()
            route_id = str(event.get("route_id") or "").strip()
            if asset_id:
                asset = assets_by_id.get(asset_id) or {}
                ensure_scope(
                    asset_id, "design_asset", str(asset.get("name") or asset_id)
                )["event_count"] += 1
            else:
                ensure_scope(route_id, "route", route_id or "Site scope")[
                    "event_count"
                ] += 1

        for observation in observations:
            route_key = str(
                observation.get("route_id") or observation.get("snapped_route_id") or ""
            ).strip()
            ensure_scope(route_key, "route", route_key or "Site scope")[
                "observation_count"
            ] += 1

        for track in tracks:
            route_key = str(track.get("route_id") or "").strip()
            ensure_scope(route_key, "route", route_key or "Site scope")[
                "track_count"
            ] += 1

        files.append(
            {
                "output_id": "route_or_station_summary",
                "filename": "route_or_station_summary.csv",
                "format": "csv",
                "media_type": "text/csv",
                "content": _csv_from_rows(
                    [
                        "scope_id",
                        "scope_type",
                        "scope_name",
                        "event_count",
                        "observation_count",
                        "track_count",
                    ],
                    list(scope_rows.values())
                    or [
                        {
                            "scope_id": "site_scope",
                            "scope_type": "site",
                            "scope_name": "Site scope",
                            "event_count": 0,
                            "observation_count": 0,
                            "track_count": 0,
                        }
                    ],
                ),
                "row_count": max(len(scope_rows), 1),
            }
        )

        if tracks:
            track_rows = [
                {
                    "track_id": item.get("track_id", ""),
                    "route_id": item.get("route_id", ""),
                    "name": item.get("name", ""),
                    "started_at": item.get("started_at", ""),
                    "ended_at": item.get("ended_at", ""),
                    "distance_m": item.get("distance_m", 0),
                    "duration_s": item.get("duration_s", 0),
                    "observer": item.get("observer")
                    or (
                        (
                            item.get("extra")
                            if isinstance(item.get("extra"), dict)
                            else {}
                        ).get("observer")
                    )
                    or "",
                    "weather": (
                        _dumps_json(
                            item.get("weather")
                            or (
                                (
                                    item.get("extra")
                                    if isinstance(item.get("extra"), dict)
                                    else {}
                                ).get("weather")
                            )
                        )
                        if isinstance(
                            item.get("weather")
                            or (
                                (
                                    item.get("extra")
                                    if isinstance(item.get("extra"), dict)
                                    else {}
                                ).get("weather")
                            ),
                            (dict, list),
                        )
                        else _stringify_weather_payload(
                            item.get("weather")
                            or (
                                (
                                    item.get("extra")
                                    if isinstance(item.get("extra"), dict)
                                    else {}
                                ).get("weather")
                            )
                        )
                    ),
                }
                for item in tracks
            ]
            files.append(
                {
                    "output_id": "track_logs",
                    "filename": "track_logs.csv",
                    "format": "csv",
                    "media_type": "text/csv",
                    "content": _csv_from_rows(
                        [
                            "track_id",
                            "route_id",
                            "name",
                            "started_at",
                            "ended_at",
                            "distance_m",
                            "duration_s",
                            "observer",
                            "weather",
                        ],
                        track_rows,
                    ),
                    "row_count": len(track_rows),
                }
            )

        return files

    def create_export_job(
        self, jurisdiction: str, payload: Optional[dict] = None
    ) -> dict:
        payload = payload or {}
        export_job = self._basic_export_job(jurisdiction, payload)
        jurisdiction_key = export_job["jurisdiction"]
        protocol = str(export_job.get("filters", {}).get("protocol") or "").strip()
        profiles = _load_vertebrate_export_profiles()
        profile = (
            ((profiles.get("profiles") or {}).get(jurisdiction_key) or {})
            .get("protocols", {})
            .get(protocol)
        )

        if profile and protocol in _TERRESTRIAL_VERTEBRATE_PROTOCOLS:
            bundle = export_job["bundle"]
            design_assets = bundle.get("design_assets") or []
            events = bundle.get("events") or []
            observations = bundle.get("observations") or []
            tracks = bundle.get("tracks") or []
            event_contexts = self._build_event_export_contexts(
                events=events,
                observations=observations,
                design_assets=design_assets,
                tracks=tracks,
                jurisdiction=jurisdiction_key,
            )
            bundle_outputs = profile.get("bundle_outputs") or {}
            files: list[dict[str, Any]] = []
            for output_name in profiles.get("required_bundle_outputs") or []:
                output_profile = bundle_outputs.get(output_name)
                if not isinstance(output_profile, dict):
                    continue
                grouped_contexts = self._group_export_contexts(
                    output_name,
                    output_profile,
                    event_contexts,
                    jurisdiction_key,
                )
                files.append(
                    self._build_export_file_descriptor(
                        output_name=output_name,
                        output_profile=output_profile,
                        grouped_contexts=grouped_contexts,
                    )
                )

            taxonomy_packages = bundle.get("taxonomy_packages") or []
            bundle["manifest"].update(
                {
                    "profile_version": profiles.get("profile_version", ""),
                    "bundle_outputs": [item["output_id"] for item in files],
                    "event_ids": [
                        event.get("event_id")
                        for event in events
                        if event.get("event_id")
                    ],
                    "design_asset_ids": [
                        asset.get("asset_id")
                        for asset in design_assets
                        if asset.get("asset_id")
                    ],
                }
            )
            bundle["profile"] = {
                "jurisdiction": jurisdiction_key,
                "protocol": protocol,
                "display_name": (
                    (profiles.get("profiles") or {}).get(jurisdiction_key) or {}
                ).get("display_name", ""),
                "column_language": (
                    (profiles.get("profiles") or {}).get(jurisdiction_key) or {}
                ).get("column_language", ""),
            }
            bundle["files"] = files
            bundle["masked_observation_count"] = sum(
                1
                for observation in observations
                if _export_mask_info(
                    observation,
                    _taxonomy_entry_for_observation(observation, jurisdiction_key),
                    jurisdiction_key,
                )["coordinate_masked"]
            )
            export_job["summary"].update(
                {
                    "bundle_file_count": len(files),
                    "masked_observation_count": bundle["masked_observation_count"],
                    "taxonomy_package_count": len(taxonomy_packages),
                }
            )
        else:
            bundle = export_job["bundle"]
            files = self._build_generic_export_files(export_job)
            bundle["files"] = files
            bundle["manifest"].update(
                {
                    "bundle_outputs": [item["output_id"] for item in files],
                    "event_ids": [
                        event.get("event_id")
                        for event in bundle.get("events") or []
                        if event.get("event_id")
                    ],
                    "design_asset_ids": [
                        asset.get("asset_id")
                        for asset in bundle.get("design_assets") or []
                        if asset.get("asset_id")
                    ],
                }
            )
            export_job["summary"].update(
                {
                    "bundle_file_count": len(files),
                    "taxonomy_package_count": len(
                        bundle.get("taxonomy_packages") or []
                    ),
                }
            )
        return self._store_payload(
            "survey_export_jobs",
            "export_job_id",
            export_job,
            {
                "project_id": export_job["project_id"],
                "jurisdiction": export_job["jurisdiction"],
                "status": export_job["status"],
            },
        )

    def _material_differences(
        self, entity_type: str, incoming: dict, existing: dict
    ) -> list[str]:
        fields = self._ENTITY_META[entity_type]["material_fields"]
        differences = []
        for field in fields:
            if self._normalize_payload_for_compare(
                incoming.get(field)
            ) != self._normalize_payload_for_compare(existing.get(field)):
                differences.append(field)
        return differences

    def _store_conflict(
        self,
        *,
        sync_job_id: str,
        entity_type: str,
        entity_id: str,
        fields: list[str],
        incoming: dict,
        server: dict,
    ) -> dict:
        now = _utc_now()
        record = {
            "conflict_id": self._make_id("conflict"),
            "sync_job_id": sync_job_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "status": "open",
            "fields": fields,
            "incoming": incoming,
            "server": server,
            "created_at": now,
            "updated_at": now,
        }
        self._conn.execute(
            """
            INSERT INTO survey_sync_conflicts
            (conflict_id, sync_job_id, entity_type, entity_id, status, created_at, updated_at, fields_json, incoming_json, server_json)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record["conflict_id"],
                sync_job_id,
                entity_type,
                entity_id,
                record["status"],
                now,
                now,
                _dumps_json(fields),
                _dumps_json(incoming),
                _dumps_json(server),
            ),
        )
        return record

    def get_conflicts(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM survey_sync_conflicts ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conflicts = []
        for row in rows:
            conflicts.append(
                {
                    "conflict_id": row["conflict_id"],
                    "sync_job_id": row["sync_job_id"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "fields": _loads_json(row["fields_json"], []),
                    "incoming": _loads_json(row["incoming_json"], {}),
                    "server": _loads_json(row["server_json"], {}),
                }
            )
        return conflicts

    def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        return self._run_with_retry(
            lambda: self._delete_entity_locked(entity_type, entity_id),
            write=True,
        )

    def sync_push(
        self, *, device_id: str, user_id: str, operations: list[dict]
    ) -> dict:
        def _sync_push_locked() -> dict:
            sync_job_id = self._make_id("sync")
            created_at = _utc_now()
            applied = []
            conflicts = []
            deleted = []

            for operation in sorted(operations, key=_sync_operation_priority):
                entity_type = (operation.get("entity_type") or "").strip()
                action = (operation.get("operation") or "upsert").strip().lower()
                payload = operation.get("payload") or {}
                if entity_type not in self._ENTITY_META:
                    continue
                meta = self._ENTITY_META[entity_type]
                entity_id = (
                    payload.get(meta["id_field"]) or operation.get("entity_id") or ""
                )
                existing = (
                    self._get_by_id_locked(entity_type, entity_id)
                    if entity_id
                    else None
                )

                if action == "delete":
                    if entity_id and self._delete_entity_locked(entity_type, entity_id):
                        deleted.append(
                            {"entity_type": entity_type, "entity_id": entity_id}
                        )
                    continue

                base_updated_at = (
                    payload.get("server_updated_at")
                    or payload.get("base_updated_at")
                    or ""
                )
                if (
                    existing
                    and base_updated_at
                    and base_updated_at != existing.get("updated_at")
                ):
                    if self._payloads_equivalent(payload, existing):
                        applied.append({"entity_type": entity_type, "record": existing})
                        continue
                    differing_fields = self._material_differences(
                        entity_type, payload, existing
                    )
                    if differing_fields:
                        conflict = self._store_conflict(
                            sync_job_id=sync_job_id,
                            entity_type=entity_type,
                            entity_id=entity_id,
                            fields=differing_fields,
                            incoming=payload,
                            server=existing,
                        )
                        conflicts.append(conflict)
                        continue

                try:
                    saved = self._apply_entity_upsert_locked(entity_type, payload)
                except ValueError as exc:
                    conflict = self._store_conflict(
                        sync_job_id=sync_job_id,
                        entity_type=entity_type,
                        entity_id=entity_id or str(payload.get(meta["id_field"]) or ""),
                        fields=_validation_conflict_fields(entity_type, exc),
                        incoming=payload,
                        server={"error": str(exc)},
                    )
                    conflicts.append(conflict)
                    continue
                applied.append({"entity_type": entity_type, "record": saved})

            status = (
                "conflict"
                if conflicts and not applied
                else ("partial" if conflicts else "applied")
            )
            job = {
                "sync_job_id": sync_job_id,
                "device_id": device_id,
                "user_id": user_id,
                "status": status,
                "operation_count": len(operations),
                "applied_count": len(applied),
                "deleted_count": len(deleted),
                "conflict_count": len(conflicts),
                "created_at": created_at,
                "updated_at": _utc_now(),
                "applied": applied,
                "deleted": deleted,
                "conflicts": conflicts,
            }
            self._conn.execute(
                """
                INSERT INTO survey_sync_jobs
                (sync_job_id, device_id, user_id, status, operation_count, created_at, updated_at, operations_json, conflicts_json)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    sync_job_id,
                    device_id,
                    user_id,
                    status,
                    len(operations),
                    created_at,
                    job["updated_at"],
                    _dumps_json(operations),
                    _dumps_json(conflicts),
                ),
            )
            return job

        return self._run_with_retry(_sync_push_locked, write=True)

    def _list_attachment_metadata(self) -> list[dict]:
        attachments: list[dict] = []
        seen_ids: set[str] = set()
        for observation in self.list_observations():
            for attachment in observation.get("media") or []:
                if not isinstance(attachment, dict):
                    continue
                attachment_id = str(
                    attachment.get("attachment_id")
                    or attachment.get("media_id")
                    or attachment.get("storage_key")
                    or ""
                ).strip()
                if not attachment_id or attachment_id in seen_ids:
                    continue
                seen_ids.add(attachment_id)
                attachments.append(
                    {
                        "attachment_id": attachment_id,
                        "event_id": str(
                            attachment.get("event_id")
                            or observation.get("event_id")
                            or ""
                        ).strip(),
                        "owner_type": str(
                            attachment.get("owner_type") or "observation"
                        ).strip(),
                        "owner_id": str(
                            attachment.get("owner_id")
                            or attachment.get("observation_id")
                            or observation.get("observation_id")
                            or ""
                        ).strip(),
                        "observation_id": str(
                            attachment.get("observation_id")
                            or observation.get("observation_id")
                            or ""
                        ).strip(),
                        "track_id": str(attachment.get("track_id") or "").strip(),
                        "mime_type": str(
                            attachment.get("mime_type") or attachment.get("type") or ""
                        ).strip(),
                        "filename": str(
                            attachment.get("filename") or attachment.get("name") or ""
                        ).strip(),
                        "byte_size": _coerce_int(
                            attachment.get("byte_size") or attachment.get("size"), 0
                        ),
                        "storage_key": str(attachment.get("storage_key") or "").strip(),
                        "checksum": str(attachment.get("checksum") or "").strip(),
                        "sync_state": str(attachment.get("sync_state") or "").strip(),
                        "updated_at": str(
                            attachment.get("server_updated_at")
                            or attachment.get("updated_at")
                            or observation.get("updated_at")
                            or ""
                        ).strip(),
                    }
                )
        return attachments

    def sync_pull(self, since: str = "") -> dict:
        def _filter(records: list[dict]) -> list[dict]:
            if not since:
                return records
            return [
                record for record in records if record.get("updated_at", "") > since
            ]

        return {
            "projects": _filter(self.list_projects()),
            "sites": _filter(self.list_sites()),
            "routes": _filter(self.list_routes()),
            "observations": _filter(self.list_observations()),
            "tracks": _filter(self.list_tracks()),
            "attachments": _filter(self._list_attachment_metadata()),
            "map_packages": _filter(self.list_map_packages()),
            "design_assets": _filter(self.list_design_assets()),
            "events": _filter(self.list_events()),
            "export_jobs": _filter(self.list_export_jobs()),
            "conflicts": self.get_conflicts(limit=100),
            "pulled_at": _utc_now(),
        }


_survey_store: Optional[SurveyStore] = None


def get_survey_store(storage_dir: Optional[str] = None) -> SurveyStore:
    global _survey_store
    if _survey_store is None:
        _survey_store = SurveyStore(storage_dir=storage_dir)
    return _survey_store
