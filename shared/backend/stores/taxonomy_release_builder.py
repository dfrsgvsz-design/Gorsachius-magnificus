from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from runtime_paths import get_backend_dir
except ImportError:  # pragma: no cover - shared package import path
    from shared.backend.utils.runtime_paths import get_backend_dir


BACKEND_DIR = get_backend_dir()
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
SOURCE_DIR = DATA_DIR / "taxonomy_sources"
RELEASE_DIR = DATA_DIR / "taxonomy_releases"

FULL_RELEASE_PACKAGE_SPECS = (
    {
        "package_id": "cn_mainland_terrestrial_vertebrates_full",
        "jurisdiction": "mainland_china",
        "program": "terrestrial_vertebrates",
    },
    {
        "package_id": "cn_mainland_plants_full",
        "jurisdiction": "mainland_china",
        "program": "plants",
    },
    {
        "package_id": "cn_mainland_insects_full",
        "jurisdiction": "mainland_china",
        "program": "insects",
    },
    {
        "package_id": "tw_terrestrial_vertebrates_full",
        "jurisdiction": "taiwan",
        "program": "terrestrial_vertebrates",
    },
    {
        "package_id": "tw_plants_full",
        "jurisdiction": "taiwan",
        "program": "plants",
    },
    {
        "package_id": "tw_insects_full",
        "jurisdiction": "taiwan",
        "program": "insects",
    },
)
VERTEBRATE_SUBMODULES = ("birds", "mammals", "reptiles", "amphibians")
REQUIRED_SOURCE_MANIFEST_FIELDS = (
    "release_id",
    "jurisdiction",
    "program",
    "submodule_counts",
    "official_expected_count",
    "source_files",
    "source_version_date",
    "license_note",
    "mapping_notes",
)
DEFAULT_SUPPORTED_NAMES = [
    "scientific_name",
    "simplified_chinese_name",
    "traditional_chinese_name",
    "english_common_name",
    "synonyms",
]
DEFAULT_STATUS_SUPPORT = {
    ("mainland_china", "terrestrial_vertebrates"): [
        "national_protection_status",
        "red_list_status",
        "sensitive_coordinate_policy",
    ],
    ("mainland_china", "plants"): [
        "national_protection_status",
        "red_list_status",
        "sensitive_coordinate_policy",
    ],
    ("mainland_china", "insects"): [
        "red_list_status",
        "sensitive_coordinate_policy",
    ],
    ("taiwan", "terrestrial_vertebrates"): [
        "taiwan_protection_status",
        "red_list_status",
        "sensitive_coordinate_policy",
    ],
    ("taiwan", "plants"): [
        "taiwan_protection_status",
        "red_list_status",
        "sensitive_coordinate_policy",
    ],
    ("taiwan", "insects"): [
        "taiwan_protection_status",
        "red_list_status",
        "sensitive_coordinate_policy",
    ],
}


class FullReleaseValidationError(ValueError):
    pass


@dataclass(frozen=True)
class FullReleaseSourceContext:
    release_id: str
    jurisdiction: str
    program: str
    package_id: str
    source_manifest_path: Path


def _json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _repo_relative(path: Path, *, repo_root: Path = REPO_ROOT) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def resolve_manifest_asset_path(
    asset_path: str,
    *,
    manifest_dir: Path,
    repo_root: Path = REPO_ROOT,
    data_dir: Path = DATA_DIR,
) -> Path:
    relative = str(asset_path or "").replace("\\", "/").strip()
    if not relative:
        return manifest_dir
    candidate = Path(relative)
    if candidate.is_absolute():
        return candidate
    search_candidates = (
        manifest_dir / candidate,
        repo_root / candidate,
        data_dir / candidate,
    )
    for resolved in search_candidates:
        if resolved.exists():
            return resolved
    return search_candidates[0]


def normalize_submodule_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw_count in value.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        result[normalized_key] = _coerce_int(raw_count)
    return result


def validate_source_manifest_payload(
    payload: Any,
    *,
    expected_release_id: str,
    expected_jurisdiction: str,
    expected_program: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["source manifest payload must be a JSON object"]
    for field in REQUIRED_SOURCE_MANIFEST_FIELDS:
        value = payload.get(field)
        if value in (None, "", [], {}):
            errors.append(f"missing required field: {field}")
    release_id = str(payload.get("release_id") or "").strip()
    if release_id and release_id != expected_release_id:
        errors.append(
            f"release_id mismatch: expected {expected_release_id}, got {release_id}"
        )
    jurisdiction = str(payload.get("jurisdiction") or "").strip()
    if jurisdiction and jurisdiction != expected_jurisdiction:
        errors.append(
            f"jurisdiction mismatch: expected {expected_jurisdiction}, got {jurisdiction}"
        )
    program = str(payload.get("program") or "").strip()
    if program and program != expected_program:
        errors.append(f"program mismatch: expected {expected_program}, got {program}")

    submodule_counts = normalize_submodule_counts(payload.get("submodule_counts"))
    official_expected_count = _coerce_int(payload.get("official_expected_count"))
    if not submodule_counts:
        errors.append("submodule_counts must be a non-empty object")
    elif official_expected_count != sum(submodule_counts.values()):
        errors.append(
            "official_expected_count must equal the sum of submodule_counts "
            f"({official_expected_count} != {sum(submodule_counts.values())})"
        )

    if expected_program == "terrestrial_vertebrates":
        missing_submodules = [
            submodule
            for submodule in VERTEBRATE_SUBMODULES
            if submodule not in submodule_counts
        ]
        if missing_submodules:
            errors.append(
                "terrestrial vertebrates source manifest must include submodule counts for "
                + ", ".join(missing_submodules)
            )
        if expected_jurisdiction == "mainland_china":
            birds_count = submodule_counts.get("birds")
            if birds_count != 1505:
                errors.append(
                    f"mainland_china terrestrial vertebrates birds count must be 1505, got {birds_count}"
                )

    source_files = payload.get("source_files")
    if not isinstance(source_files, list) or not source_files:
        errors.append("source_files must be a non-empty list")
    return errors


def validate_source_files(
    source_files: Any,
    *,
    expected_release_id: str,
    manifest_dir: Path,
    repo_root: Path = REPO_ROOT,
    data_dir: Path = DATA_DIR,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(source_files, list) or not source_files:
        return ["source_files must be a non-empty list"]
    allowed_root = (data_dir / "taxonomy_releases" / expected_release_id).resolve()
    for index, item in enumerate(source_files):
        if not isinstance(item, dict):
            errors.append(f"source_files[{index}] must be an object with a path")
            continue
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            errors.append(f"source_files[{index}] is missing path")
            continue
        resolved = resolve_manifest_asset_path(
            raw_path,
            manifest_dir=manifest_dir,
            repo_root=repo_root,
            data_dir=data_dir,
        )
        if not _is_relative_to(resolved, allowed_root):
            errors.append(
                f"source_files[{index}] must resolve under backend/data/taxonomy_releases/{expected_release_id}: {raw_path}"
            )
        if not resolved.exists():
            errors.append(f"source_files[{index}] does not exist: {raw_path}")
    return errors


def full_release_source_contexts(
    release_id: str,
    *,
    data_dir: Path = DATA_DIR,
) -> list[FullReleaseSourceContext]:
    contexts: list[FullReleaseSourceContext] = []
    for spec in FULL_RELEASE_PACKAGE_SPECS:
        contexts.append(
            FullReleaseSourceContext(
                release_id=release_id,
                jurisdiction=str(spec["jurisdiction"]),
                program=str(spec["program"]),
                package_id=str(spec["package_id"]),
                source_manifest_path=(
                    data_dir
                    / "taxonomy_sources"
                    / release_id
                    / str(spec["jurisdiction"])
                    / str(spec["program"])
                    / "source_manifest.json"
                ),
            )
        )
    return contexts


def validate_full_release_sources(
    release_id: str,
    *,
    repo_root: Path = REPO_ROOT,
    data_dir: Path = DATA_DIR,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for context in full_release_source_contexts(release_id, data_dir=data_dir):
        errors: list[str] = []
        payload: dict[str, Any] = {}
        if not context.source_manifest_path.exists():
            errors.append(
                f"missing source_manifest.json: {_repo_relative(context.source_manifest_path, repo_root=repo_root)}"
            )
        else:
            try:
                raw_payload = _json_load(context.source_manifest_path)
                payload = raw_payload if isinstance(raw_payload, dict) else {}
            except Exception as exc:
                errors.append(
                    f"failed to read source_manifest.json: {context.source_manifest_path.as_posix()} ({exc})"
                )
            if payload:
                errors.extend(
                    validate_source_manifest_payload(
                        payload,
                        expected_release_id=release_id,
                        expected_jurisdiction=context.jurisdiction,
                        expected_program=context.program,
                    )
                )
                errors.extend(
                    validate_source_files(
                        payload.get("source_files"),
                        expected_release_id=release_id,
                        manifest_dir=context.source_manifest_path.parent,
                        repo_root=repo_root,
                        data_dir=data_dir,
                    )
                )
        reports.append(
            {
                "package_id": context.package_id,
                "jurisdiction": context.jurisdiction,
                "program": context.program,
                "source_manifest_path": _repo_relative(
                    context.source_manifest_path, repo_root=repo_root
                ),
                "source_manifest": payload,
                "errors": errors,
            }
        )
    return reports


def _derive_package_version(source_manifest: dict[str, Any]) -> str:
    explicit = str(source_manifest.get("package_version") or "").strip()
    if explicit:
        return explicit
    date_value = str(source_manifest.get("source_version_date") or "").strip()
    if len(date_value) >= 7 and date_value[4] == "-" and date_value[7:8] in {"", "-"}:
        return f"{date_value[:4]}.{date_value[5:7]}-full"
    return "full"


def _default_taxon_groups(
    source_manifest: dict[str, Any], *, program: str
) -> list[str]:
    explicit = source_manifest.get("taxon_groups")
    if isinstance(explicit, list) and explicit:
        return [str(item).strip() for item in explicit if str(item).strip()]
    submodules = list(
        normalize_submodule_counts(source_manifest.get("submodule_counts")).keys()
    )
    if program == "terrestrial_vertebrates":
        ordered = [item for item in VERTEBRATE_SUBMODULES if item in submodules]
        extras = [item for item in submodules if item not in ordered]
        return ordered + extras
    return submodules


def _default_backbone_source(
    source_manifest: dict[str, Any],
    *,
    jurisdiction: str,
    program: str,
    source_manifest_repo_path: str,
) -> list[str]:
    explicit = source_manifest.get("backbone_source")
    if isinstance(explicit, list) and explicit:
        return [str(item).strip() for item in explicit if str(item).strip()]
    label = f"Official frozen source snapshot for {jurisdiction}/{program}"
    return [label, f"source_manifest={source_manifest_repo_path}"]


def build_full_release_manifest(
    release_id: str,
    *,
    repo_root: Path = REPO_ROOT,
    data_dir: Path = DATA_DIR,
) -> dict[str, Any]:
    reports = validate_full_release_sources(
        release_id, repo_root=repo_root, data_dir=data_dir
    )
    error_messages = [
        f"{report['package_id']}: {error}"
        for report in reports
        for error in report["errors"]
    ]
    if error_messages:
        raise FullReleaseValidationError("\n".join(error_messages))

    source_versions = {
        str(report["source_manifest"].get("source_version_date") or "").strip()
        for report in reports
        if isinstance(report.get("source_manifest"), dict)
    }
    source_versions.discard("")
    manifest_source_version = (
        next(iter(source_versions)) if len(source_versions) == 1 else release_id
    )

    packages: list[dict[str, Any]] = []
    for report in reports:
        source_manifest = report["source_manifest"]
        expected_count = _coerce_int(source_manifest.get("official_expected_count"))
        submodule_counts = normalize_submodule_counts(
            source_manifest.get("submodule_counts")
        )
        package = {
            "package_id": report["package_id"],
            "package_version": _derive_package_version(source_manifest),
            "jurisdiction": report["jurisdiction"],
            "program": report["program"],
            "taxon_groups": _default_taxon_groups(
                source_manifest, program=report["program"]
            ),
            "backbone_source": _default_backbone_source(
                source_manifest,
                jurisdiction=report["jurisdiction"],
                program=report["program"],
                source_manifest_repo_path=report["source_manifest_path"],
            ),
            "supported_names": list(
                source_manifest.get("supported_names") or DEFAULT_SUPPORTED_NAMES
            ),
            "status_support": list(
                source_manifest.get("status_support")
                or DEFAULT_STATUS_SUPPORT.get(
                    (report["jurisdiction"], report["program"]), []
                )
            ),
            "source_manifest_path": report["source_manifest_path"],
            "expected_count": expected_count,
            "submodule_expected_counts": submodule_counts,
            "seed_only": False,
            "exhaustive_species_content": True,
            "taxonomy_release_id": release_id,
            "sample_taxon_examples": list(
                source_manifest.get("sample_taxon_examples") or []
            ),
        }
        packages.append(package)

    return {
        "schema_version": "1.0",
        "manifest_version": f"{release_id}-full-backbone",
        "taxonomy_release_id": release_id,
        "source_manifest_version": manifest_source_version,
        "release_label": f"Full taxonomy release {release_id}",
        "activate_on_build": False,
        "description": (
            "Full backbone taxonomy release manifest for the biodiversity field survey platform. "
            "This manifest is candidate-first: rebuild without activate, validate discrepancy/health/"
            "Android checksum, then manually activate."
        ),
        "shared_name_model": {
            "supported_name_fields": DEFAULT_SUPPORTED_NAMES,
            "shared_taxon_key": "internal_taxon_id",
            "jurisdictional_status_fields": [
                "national_protection_status",
                "taiwan_protection_status",
                "red_list_status",
                "sensitive_coordinate_policy",
            ],
        },
        "packages": packages,
    }


def build_release_manifest_payload(full_manifest: dict[str, Any]) -> dict[str, Any]:
    packages = full_manifest.get("packages") if isinstance(full_manifest, dict) else []
    normalized_packages = []
    for package in packages if isinstance(packages, list) else []:
        if not isinstance(package, dict):
            continue
        normalized_packages.append(
            {
                "package_id": str(package.get("package_id") or "").strip(),
                "jurisdiction": str(package.get("jurisdiction") or "").strip(),
                "program": str(package.get("program") or "").strip(),
                "expected_count": _coerce_int(package.get("expected_count")),
                "submodule_expected_counts": normalize_submodule_counts(
                    package.get("submodule_expected_counts")
                ),
                "source_manifest_path": str(
                    package.get("source_manifest_path") or ""
                ).strip(),
            }
        )
    return {
        "taxonomy_release_id": str(
            full_manifest.get("taxonomy_release_id") or ""
        ).strip(),
        "release_label": str(full_manifest.get("release_label") or "").strip(),
        "source_manifest_version": str(
            full_manifest.get("source_manifest_version") or ""
        ).strip(),
        "packages": normalized_packages,
    }


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dump(payload), encoding="utf-8")
