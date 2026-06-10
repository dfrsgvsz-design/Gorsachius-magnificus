from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

try:
    from runtime_paths import get_backend_dir
except ImportError:  # pragma: no cover - package import path
    from .runtime_paths import get_backend_dir

try:
    from taxonomy_release_builder import (
        normalize_submodule_counts,
        validate_source_files,
        validate_source_manifest_payload,
    )
except ImportError:  # pragma: no cover - package import path
    from .taxonomy_release_builder import (
        normalize_submodule_counts,
        validate_source_files,
        validate_source_manifest_payload,
    )


BACKEND_DIR = get_backend_dir()
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
DEFAULT_STORAGE_DIR = DATA_DIR / "survey_store"
DEFAULT_DB_PATH = DEFAULT_STORAGE_DIR / "taxonomy_catalog.sqlite3"
IMPORTER_VERSION = "2026.04.23-v2"
NAME_FIELD_ALIASES = {
    "scientific_name": ("scientific_name", "scientific"),
    "simplified_chinese_name": ("simplified_chinese_name", "chinese_name", "chinese"),
    "traditional_chinese_name": ("traditional_chinese_name",),
    "english_common_name": ("english_common_name", "english_name", "english"),
}
NAME_LOCALES = {
    "scientific_name": "scientific",
    "simplified_chinese_name": "zh-Hans",
    "traditional_chinese_name": "zh-Hant",
    "english_common_name": "en",
    "synonym": "und",
}

_CATALOG_SINGLETON: Optional["TaxonomyCatalog"] = None
_CATALOG_LOCK = threading.Lock()


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return " ".join(text.split())


def _escape_sql_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _slugify(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _package_manifest_dir(package: Optional[dict[str, Any]] = None) -> Path:
    if isinstance(package, dict):
        manifest_dir = str(package.get("_manifest_dir") or "").strip()
        if manifest_dir:
            return Path(manifest_dir)
    return DATA_DIR


def _path_from_asset(asset_path: str, package: Optional[dict[str, Any]] = None) -> Path:
    relative = str(asset_path or "").replace("\\", "/").strip()
    if not relative:
        return _package_manifest_dir(package)
    candidate = Path(relative)
    if candidate.is_absolute():
        return candidate
    manifest_dir = _package_manifest_dir(package)
    search_candidates = [
        manifest_dir / candidate,
        REPO_ROOT / candidate,
        DATA_DIR / candidate,
    ]
    if candidate.name != relative:
        search_candidates.append(DATA_DIR / candidate.name)
    for resolved in search_candidates:
        if resolved.exists():
            return resolved
    return search_candidates[0]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except Exception:
        return False


def _package_asset_entries(package: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for key in ("source_assets", "local_seed_assets"):
        assets = package.get(key) or []
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            normalized_path = str(asset.get("path") or "").replace("\\", "/").strip()
            if normalized_path and normalized_path in seen_paths:
                continue
            cloned = dict(asset)
            cloned["_asset_list_key"] = key
            entries.append(cloned)
            if normalized_path:
                seen_paths.add(normalized_path)
    return entries


def _load_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _first_present(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


class TaxonomyImporter(ABC):
    program: str = ""

    def supports(self, package: dict[str, Any]) -> bool:
        return str(package.get("program") or "").strip() == self.program

    @abstractmethod
    def iter_records(self, package: dict[str, Any]) -> Iterable[dict[str, Any]]:
        raise NotImplementedError

    def _fallback_sample_records(
        self, package: dict[str, Any]
    ) -> Iterable[dict[str, Any]]:
        jurisdiction = str(package.get("jurisdiction") or "").strip()
        program = str(package.get("program") or "").strip()
        for sample in package.get("sample_taxon_examples") or []:
            if not isinstance(sample, dict):
                continue
            taxon_id = str(sample.get("internal_taxon_id") or "").strip() or (
                f"{program}-{jurisdiction}-{_slugify(sample.get('scientific_name'))}"
            )
            scientific_name = str(sample.get("scientific_name") or "").strip()
            if not taxon_id or not scientific_name:
                continue
            submodule = str(
                sample.get("taxon_group") or sample.get("group") or ""
            ).strip()
            names = {
                "scientific_name": scientific_name,
                "simplified_chinese_name": str(
                    sample.get("simplified_chinese_name") or ""
                ).strip(),
                "traditional_chinese_name": str(
                    sample.get("traditional_chinese_name") or ""
                ).strip(),
                "english_common_name": str(
                    sample.get("english_common_name") or ""
                ).strip(),
                "synonyms": [
                    str(item).strip()
                    for item in sample.get("synonyms") or []
                    if str(item).strip()
                ],
            }
            yield {
                "taxon_id": taxon_id,
                "scientific_name": scientific_name,
                "program": program,
                "submodule": submodule,
                "jurisdiction": jurisdiction,
                "present": True,
                "names": names,
                "statuses": {},
                "classification": {},
                "source_kind": "sample_taxon_examples",
                "raw": sample,
            }


class VertebrateBackboneImporter(TaxonomyImporter):
    program = "terrestrial_vertebrates"

    def iter_records(self, package: dict[str, Any]) -> Iterable[dict[str, Any]]:
        emitted = 0
        for asset in _package_asset_entries(package):
            asset_path = _path_from_asset(str(asset.get("path") or ""), package)
            if not asset_path.exists():
                continue
            if asset_path.name == "terrestrial_vertebrates_taxonomy_seed.json":
                for record in self._iter_shared_seed_records(package, asset_path):
                    emitted += 1
                    yield record
            elif asset_path.name == "china_birds.json":
                for record in self._iter_legacy_bird_records(package, asset_path):
                    emitted += 1
                    yield record
            else:
                for record in self._iter_generic_records(package, asset, asset_path):
                    emitted += 1
                    yield record
        if emitted == 0:
            yield from self._fallback_sample_records(package)

    def _iter_shared_seed_records(
        self, package: dict[str, Any], asset_path: Path
    ) -> Iterable[dict[str, Any]]:
        asset = _load_json_file(asset_path, {})
        entries = asset.get("entries") if isinstance(asset, dict) else []
        if not isinstance(entries, list):
            return
        jurisdiction = str(package.get("jurisdiction") or "").strip()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            scientific_name = str(entry.get("scientific_name") or "").strip()
            taxon_id = str(entry.get("internal_taxon_id") or "").strip()
            if not scientific_name or not taxon_id:
                continue
            jurisdiction_status = {}
            jurisdictions = (
                entry.get("jurisdictions")
                if isinstance(entry.get("jurisdictions"), dict)
                else {}
            )
            if jurisdiction:
                jurisdiction_status = (
                    jurisdictions.get(jurisdiction)
                    if isinstance(jurisdictions, dict)
                    else {}
                )
                if (
                    isinstance(jurisdiction_status, dict)
                    and jurisdiction_status.get("present") is False
                ):
                    continue
            submodule = str(
                entry.get("taxon_group") or entry.get("group") or ""
            ).strip()
            names = {
                "scientific_name": scientific_name,
                "simplified_chinese_name": str(
                    entry.get("simplified_chinese_name") or ""
                ).strip(),
                "traditional_chinese_name": str(
                    entry.get("traditional_chinese_name") or ""
                ).strip(),
                "english_common_name": str(
                    entry.get("english_common_name") or ""
                ).strip(),
                "synonyms": [
                    str(item).strip()
                    for item in entry.get("synonyms") or []
                    if str(item).strip()
                ],
            }
            statuses = (
                dict(jurisdiction_status)
                if isinstance(jurisdiction_status, dict)
                else {}
            )
            yield {
                "taxon_id": taxon_id,
                "scientific_name": scientific_name,
                "program": self.program,
                "submodule": submodule,
                "jurisdiction": jurisdiction,
                "present": bool(statuses.get("present", True)),
                "names": names,
                "statuses": statuses,
                "classification": {},
                "source_kind": "shared_seed_asset",
                "raw": entry,
            }

    def _iter_legacy_bird_records(
        self, package: dict[str, Any], asset_path: Path
    ) -> Iterable[dict[str, Any]]:
        asset = _load_json_file(asset_path, {})
        species = asset.get("species") if isinstance(asset, dict) else []
        if not isinstance(species, list):
            return
        jurisdiction = str(package.get("jurisdiction") or "").strip()
        if jurisdiction != "mainland_china":
            return
        for entry in species:
            if not isinstance(entry, dict):
                continue
            scientific_name = str(
                entry.get("scientific") or entry.get("scientific_name") or ""
            ).strip()
            if not scientific_name:
                continue
            names = {
                "scientific_name": scientific_name,
                "simplified_chinese_name": str(
                    entry.get("chinese") or entry.get("simplified_chinese_name") or ""
                ).strip(),
                "traditional_chinese_name": str(
                    entry.get("traditional_chinese_name") or ""
                ).strip(),
                "english_common_name": str(
                    entry.get("english") or entry.get("english_common_name") or ""
                ).strip(),
                "synonyms": [
                    str(item).strip()
                    for item in entry.get("synonyms") or []
                    if str(item).strip()
                ],
            }
            statuses = {
                "iucn_status": str(entry.get("iucn") or "").strip(),
                "national_protection_status": entry.get("protection"),
            }
            yield {
                "taxon_id": "",
                "scientific_name": scientific_name,
                "program": self.program,
                "submodule": "birds",
                "jurisdiction": jurisdiction,
                "present": True,
                "names": names,
                "statuses": statuses,
                "classification": {
                    "order": str(entry.get("order") or "").strip(),
                    "family": str(entry.get("family") or "").strip(),
                },
                "source_kind": "legacy_bird_species",
                "raw": entry,
            }

    def _iter_generic_records(
        self,
        package: dict[str, Any],
        asset: dict[str, Any],
        asset_path: Path,
    ) -> Iterable[dict[str, Any]]:
        payload = _load_json_file(asset_path, [])
        records = payload.get("entries") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return
        default_source_kind = str(asset.get("source_kind") or "").strip() or (
            "vertebrate_backbone_asset"
            if str(asset.get("_asset_list_key") or "") == "source_assets"
            else "generic_seed_asset"
        )
        for entry in records:
            normalized = GenericPlaceholderImporter()._normalize_generic_entry(
                package,
                entry,
                default_source_kind=default_source_kind,
            )
            if normalized:
                yield normalized


class GenericPlaceholderImporter(TaxonomyImporter):
    def iter_records(self, package: dict[str, Any]) -> Iterable[dict[str, Any]]:
        emitted = 0
        for asset in _package_asset_entries(package):
            asset_path = _path_from_asset(str(asset.get("path") or ""), package)
            if not asset_path.exists():
                continue
            payload = _load_json_file(asset_path, [])
            records = payload.get("entries") if isinstance(payload, dict) else payload
            if not isinstance(records, list):
                continue
            default_source_kind = str(asset.get("source_kind") or "").strip() or (
                "generic_backbone_asset"
                if str(asset.get("_asset_list_key") or "") == "source_assets"
                else "generic_seed_asset"
            )
            for entry in records:
                normalized = self._normalize_generic_entry(
                    package,
                    entry,
                    default_source_kind=default_source_kind,
                )
                if not normalized:
                    continue
                emitted += 1
                yield normalized
        if emitted == 0:
            yield from self._fallback_sample_records(package)

    def _normalize_generic_entry(
        self,
        package: dict[str, Any],
        entry: Any,
        *,
        default_source_kind: str = "generic_seed_asset",
    ) -> Optional[dict[str, Any]]:
        if not isinstance(entry, dict):
            return None
        jurisdiction = str(package.get("jurisdiction") or "").strip()
        program = str(package.get("program") or "").strip()
        names_payload = (
            entry.get("names") if isinstance(entry.get("names"), dict) else {}
        )
        status_payload = (
            entry.get("statuses") if isinstance(entry.get("statuses"), dict) else {}
        )
        classification_payload = (
            entry.get("classification")
            if isinstance(entry.get("classification"), dict)
            else {}
        )
        scientific_name = str(
            entry.get("scientific_name") or names_payload.get("scientific_name") or ""
        ).strip()
        if not scientific_name:
            return None
        taxon_id = str(entry.get("internal_taxon_id") or "").strip()
        submodule = str(
            entry.get("submodule")
            or entry.get("taxon_group")
            or entry.get("group")
            or classification_payload.get("group")
            or ""
        ).strip()
        names = {
            "scientific_name": scientific_name,
            "simplified_chinese_name": str(
                names_payload.get("simplified_chinese_name")
                or entry.get("simplified_chinese_name")
                or entry.get("chinese_name")
                or ""
            ).strip(),
            "traditional_chinese_name": str(
                names_payload.get("traditional_chinese_name")
                or entry.get("traditional_chinese_name")
                or ""
            ).strip(),
            "english_common_name": str(
                names_payload.get("english_common_name")
                or entry.get("english_common_name")
                or entry.get("english_name")
                or ""
            ).strip(),
            "synonyms": [
                str(item).strip()
                for item in (
                    names_payload.get("synonyms") or entry.get("synonyms") or []
                )
                if str(item).strip()
            ],
        }
        return {
            "taxon_id": taxon_id,
            "scientific_name": scientific_name,
            "program": program,
            "submodule": submodule,
            "jurisdiction": jurisdiction,
            "present": bool(entry.get("present", True)),
            "names": names,
            "statuses": status_payload,
            "classification": classification_payload,
            "source_kind": str(entry.get("source_kind") or default_source_kind),
            "raw": entry,
        }


class PlantBackboneImporter(GenericPlaceholderImporter):
    program = "plants"


class InsectBackboneImporter(GenericPlaceholderImporter):
    program = "insects"


class TaxonomyCatalog:
    def __init__(
        self,
        *,
        storage_dir: Optional[str | Path] = None,
        db_path: Optional[str | Path] = None,
        manifest_path: Optional[str | Path] = None,
        auto_bootstrap: bool = True,
    ) -> None:
        base_dir = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
        self.db_path = Path(db_path) if db_path else base_dir / DEFAULT_DB_PATH.name
        self.manifest_path = (
            Path(manifest_path)
            if manifest_path
            else DATA_DIR / "taxonomy_packages.json"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._importers = [
            VertebrateBackboneImporter(),
            PlantBackboneImporter(),
            InsectBackboneImporter(),
        ]
        self._init_schema()
        if auto_bootstrap:
            self.ensure_bootstrapped()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def ensure_bootstrapped(self, force: bool = False) -> None:
        manifest = self._load_manifest()
        signature = self._manifest_signature(manifest)
        release_id = self._manifest_release_id(manifest)
        with self._lock:
            current_signature = self._get_meta("manifest_signature")
            current_release_id = self._get_meta("current_taxonomy_release_id")
            existing_rows = self._scalar(
                "SELECT COUNT(*) FROM taxonomy_release_occurrences WHERE release_id=?",
                (release_id,),
            )
            if (
                not force
                and current_signature == signature
                and current_release_id == release_id
                and int(existing_rows or 0) > 0
            ):
                return
            self._rebuild_catalog(manifest, signature)

    def stats(self) -> dict[str, Any]:
        current_release_id = self.current_release_id()
        params: tuple[Any, ...] = (
            (current_release_id,) if current_release_id else tuple()
        )
        release_where = "WHERE release_id=?" if current_release_id else "WHERE 1=0"
        names_where = (
            "WHERE taxon_id IN (SELECT DISTINCT taxon_id FROM taxonomy_release_occurrences WHERE release_id=?)"
            if current_release_id
            else "WHERE 1=0"
        )
        with self._lock:
            return {
                "db_path": str(self.db_path),
                "packages": int(
                    self._scalar(
                        f"SELECT COUNT(*) FROM taxonomy_release_packages {release_where}",
                        params,
                    )
                ),
                "taxa": int(
                    self._scalar(
                        f"SELECT COUNT(DISTINCT taxon_id) FROM taxonomy_release_occurrences {release_where}",
                        params,
                    )
                ),
                "occurrences": int(
                    self._scalar(
                        f"SELECT COUNT(*) FROM taxonomy_release_occurrences {release_where}",
                        params,
                    )
                ),
                "names": int(
                    self._scalar(
                        f"SELECT COUNT(*) FROM taxonomy_taxon_names {names_where}",
                        params,
                    )
                ),
                "manifest_signature": self._get_meta("manifest_signature"),
                "current_taxonomy_release_id": current_release_id,
                "taxonomy_review_backlog_count": int(
                    self._scalar(
                        "SELECT COUNT(*) FROM taxonomy_match_reviews WHERE release_id=? AND status='open'",
                        (current_release_id,),
                    )
                    if current_release_id
                    else 0
                ),
            }

    def current_release_id(self) -> str:
        with self._lock:
            row = self._conn.execute("""
                SELECT release_id
                FROM taxonomy_releases
                WHERE is_current = 1
                ORDER BY activated_at DESC, imported_at DESC
                LIMIT 1
                """).fetchone()
            if row:
                return str(row["release_id"] or "")
            return self._get_meta("current_taxonomy_release_id")

    def current_release_summary(self) -> dict[str, Any]:
        return self.get_release_summary(self.current_release_id())

    def _release_activation_issues_locked(self, release_id: str) -> list[str]:
        row = self._conn.execute(
            """
            SELECT
                status,
                package_count,
                exhaustive_package_count,
                review_backlog_count,
                count_parity_ok
            FROM taxonomy_releases
            WHERE release_id=?
            """,
            (release_id,),
        ).fetchone()
        if not row:
            return ["release_missing"]
        issues: list[str] = []
        if str(row["status"] or "") not in {"imported", "active"}:
            issues.append("release_not_imported")
        package_count = int(row["package_count"] or 0)
        if package_count <= 0:
            issues.append("release_has_no_packages")
        if not bool(row["count_parity_ok"]):
            issues.append("count_parity_failed")
        error_review_count = int(
            self._scalar(
                "SELECT COUNT(*) FROM taxonomy_match_reviews WHERE release_id=? AND status='open' AND severity='error'",
                (release_id,),
            )
        )
        if error_review_count > 0:
            issues.append("review_backlog_open")
        return issues

    def _assert_release_activation_ready_locked(self, release_id: str) -> None:
        issues = self._release_activation_issues_locked(release_id)
        if issues:
            raise ValueError(
                f"Taxonomy release {release_id} is not activation-ready: {', '.join(issues)}"
            )

    def get_release_summary(self, release_id: str) -> dict[str, Any]:
        release_key = str(release_id or "").strip()
        if not release_key:
            return {}
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    release_id,
                    release_label,
                    source_manifest_version,
                    manifest_signature,
                    imported_at,
                    activated_at,
                    status,
                    is_current,
                    package_count,
                    exhaustive_package_count,
                    review_backlog_count,
                    count_parity_ok,
                    raw_json
                FROM taxonomy_releases
                WHERE release_id=?
                """,
                (release_key,),
            ).fetchone()
            if not row:
                return {}
            return {
                "release_id": str(row["release_id"] or ""),
                "taxonomy_release_id": str(row["release_id"] or ""),
                "release_label": str(row["release_label"] or ""),
                "source_manifest_version": str(row["source_manifest_version"] or ""),
                "manifest_signature": str(row["manifest_signature"] or ""),
                "imported_at": str(row["imported_at"] or ""),
                "activated_at": str(row["activated_at"] or ""),
                "status": str(row["status"] or ""),
                "is_current_release": bool(row["is_current"]),
                "package_count": int(row["package_count"] or 0),
                "taxonomy_exhaustive_package_count": int(
                    row["exhaustive_package_count"] or 0
                ),
                "taxonomy_review_backlog_count": int(row["review_backlog_count"] or 0),
                "taxonomy_count_parity_ok": bool(row["count_parity_ok"]),
                "raw": json.loads(row["raw_json"] or "{}"),
            }

    def list_releases(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("""
                SELECT
                    release_id,
                    release_label,
                    source_manifest_version,
                    manifest_signature,
                    imported_at,
                    activated_at,
                    status,
                    is_current,
                    package_count,
                    exhaustive_package_count,
                    review_backlog_count,
                    count_parity_ok
                FROM taxonomy_releases
                ORDER BY is_current DESC, imported_at DESC
                """).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "release_id": str(row["release_id"] or ""),
                    "taxonomy_release_id": str(row["release_id"] or ""),
                    "release_label": str(row["release_label"] or ""),
                    "source_manifest_version": str(
                        row["source_manifest_version"] or ""
                    ),
                    "manifest_signature": str(row["manifest_signature"] or ""),
                    "imported_at": str(row["imported_at"] or ""),
                    "activated_at": str(row["activated_at"] or ""),
                    "status": str(row["status"] or ""),
                    "is_current_release": bool(row["is_current"]),
                    "package_count": int(row["package_count"] or 0),
                    "taxonomy_exhaustive_package_count": int(
                        row["exhaustive_package_count"] or 0
                    ),
                    "taxonomy_review_backlog_count": int(
                        row["review_backlog_count"] or 0
                    ),
                    "taxonomy_count_parity_ok": bool(row["count_parity_ok"]),
                }
            )
        return results

    def list_release_packages(
        self,
        *,
        release_id: str = "",
        jurisdiction: str = "",
        program: str = "",
        current_only: bool = True,
        package_ids: Optional[Sequence[str]] = None,
    ) -> list[dict[str, Any]]:
        release_key = str(release_id or "").strip()
        jurisdiction_key = str(jurisdiction or "").strip()
        program_key = str(program or "").strip()
        normalized_package_ids = [
            str(item).strip() for item in package_ids or [] if str(item).strip()
        ]
        sql = ["""
            SELECT
                rp.release_id,
                rp.package_id,
                rp.package_version,
                rp.jurisdiction,
                rp.program,
                rp.seed_only,
                rp.exhaustive_species_content,
                rp.taxon_groups_json,
                rp.supported_names_json,
                rp.status_support_json,
                rp.backbone_source_json,
                rp.source_manifest_version,
                rp.expected_count,
                rp.imported_count,
                rp.count_parity_ok,
                rp.review_status,
                rp.checksum,
                rp.submodule_counts_json,
                rp.raw_json,
                rp.imported_at,
                r.is_current,
                r.release_label
            FROM taxonomy_release_packages rp
            INNER JOIN taxonomy_releases r ON r.release_id = rp.release_id
            WHERE 1=1
            """]
        params: list[Any] = []
        if release_key:
            sql.append("AND rp.release_id = ?")
            params.append(release_key)
        elif current_only:
            sql.append("AND r.is_current = 1")
        if jurisdiction_key:
            sql.append("AND rp.jurisdiction = ?")
            params.append(jurisdiction_key)
        if program_key:
            sql.append("AND rp.program = ?")
            params.append(program_key)
        if normalized_package_ids:
            placeholders = ",".join("?" for _ in normalized_package_ids)
            sql.append(f"AND rp.package_id IN ({placeholders})")
            params.extend(normalized_package_ids)
        sql.append(
            "ORDER BY r.is_current DESC, rp.jurisdiction ASC, rp.program ASC, rp.package_id ASC"
        )
        with self._lock:
            rows = self._conn.execute("\n".join(sql), params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            submodule_counts = json.loads(row["submodule_counts_json"] or "{}")
            stored_package = json.loads(row["raw_json"] or "{}")
            submodule_expected_counts = (
                stored_package.get("submodule_expected_counts")
                if isinstance(stored_package.get("submodule_expected_counts"), dict)
                else {}
            )
            record = {
                "taxonomy_release_id": str(row["release_id"] or ""),
                "release_id": str(row["release_id"] or ""),
                "release_label": str(row["release_label"] or ""),
                "package_id": str(row["package_id"] or ""),
                "asset_package_id": str(row["package_id"] or ""),
                "package_version": str(row["package_version"] or ""),
                "jurisdiction": str(row["jurisdiction"] or ""),
                "program": str(row["program"] or ""),
                "seed_only": bool(row["seed_only"]),
                "exhaustive_species_content": bool(row["exhaustive_species_content"]),
                "exhaustive": bool(row["exhaustive_species_content"]),
                "taxon_groups": json.loads(row["taxon_groups_json"] or "[]"),
                "supported_names": json.loads(row["supported_names_json"] or "[]"),
                "status_support": json.loads(row["status_support_json"] or "[]"),
                "backbone_source": json.loads(row["backbone_source_json"] or "[]"),
                "source_manifest_version": str(row["source_manifest_version"] or ""),
                "expected_count": int(row["expected_count"] or 0),
                "imported_count": int(row["imported_count"] or 0),
                "catalog_count": int(row["imported_count"] or 0),
                "catalog_entry_count": int(row["imported_count"] or 0),
                "count_parity_ok": bool(row["count_parity_ok"]),
                "review_status": str(row["review_status"] or ""),
                "checksum": str(row["checksum"] or ""),
                "submodule_counts": submodule_counts,
                "submodule_expected_counts": submodule_expected_counts,
                "imported_at": str(row["imported_at"] or ""),
                "is_current_release": bool(row["is_current"]),
                "catalog_status": (
                    "seed_only"
                    if bool(row["seed_only"])
                    else (
                        "exhaustive"
                        if bool(row["exhaustive_species_content"])
                        else "unspecified"
                    )
                ),
            }
            results.append(record)
        return results

    def package_status_lookup(
        self,
        *,
        release_id: str = "",
        current_only: bool = True,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        lookup: dict[tuple[str, str], dict[str, Any]] = {}
        for item in self.list_release_packages(
            release_id=release_id, current_only=current_only
        ):
            key = (str(item.get("jurisdiction") or ""), str(item.get("program") or ""))
            if key not in lookup:
                lookup[key] = item
        return lookup

    def list_match_reviews(
        self, release_id: str = "", status: str = ""
    ) -> list[dict[str, Any]]:
        release_key = str(release_id or "").strip()
        status_key = str(status or "").strip()
        sql = ["""
            SELECT
                review_id,
                release_id,
                package_id,
                taxon_id,
                scientific_name,
                review_type,
                status,
                severity,
                detail_json,
                created_at,
                updated_at
            FROM taxonomy_match_reviews
            WHERE 1=1
            """]
        params: list[Any] = []
        if release_key:
            sql.append("AND release_id=?")
            params.append(release_key)
        if status_key:
            sql.append("AND status=?")
            params.append(status_key)
        sql.append("ORDER BY created_at DESC, review_id DESC")
        with self._lock:
            rows = self._conn.execute("\n".join(sql), params).fetchall()
        return [
            {
                "review_id": str(row["review_id"] or ""),
                "release_id": str(row["release_id"] or ""),
                "package_id": str(row["package_id"] or ""),
                "taxon_id": str(row["taxon_id"] or ""),
                "scientific_name": str(row["scientific_name"] or ""),
                "review_type": str(row["review_type"] or ""),
                "status": str(row["status"] or ""),
                "severity": str(row["severity"] or ""),
                "detail": json.loads(row["detail_json"] or "{}"),
                "created_at": str(row["created_at"] or ""),
                "updated_at": str(row["updated_at"] or ""),
            }
            for row in rows
        ]

    def activate_release(self, release_id: str) -> dict[str, Any]:
        release_key = str(release_id or "").strip()
        if not release_key:
            raise KeyError("release_id required")
        with self._lock:
            row = self._conn.execute(
                "SELECT release_id FROM taxonomy_releases WHERE release_id=?",
                (release_key,),
            ).fetchone()
            if not row:
                raise KeyError(f"Unknown taxonomy release: {release_key}")
            self._assert_release_activation_ready_locked(release_key)
            self._activate_release_locked(release_key)
            self._conn.commit()
        return self.get_release_summary(release_key)

    def rebuild_release(
        self, *, force: bool = True, activate: Optional[bool] = None
    ) -> dict[str, Any]:
        manifest = json.loads(json.dumps(self._load_manifest(), ensure_ascii=False))
        manifest["activate_on_build"] = (
            bool(activate) if activate is not None else False
        )
        signature = self._manifest_signature(manifest)
        self._rebuild_catalog(
            manifest,
            signature,
            force=force,
            enforce_activation_gates=bool(manifest.get("activate_on_build")),
        )
        return self.get_release_summary(self._manifest_release_id(manifest))

    def export_discrepancy_report(self, release_id: str = "") -> dict[str, Any]:
        release_key = str(release_id or "").strip() or self.current_release_id()
        release = self.get_release_summary(release_key)
        packages = self.list_release_packages(
            release_id=release_key, current_only=False
        )
        reviews = self.list_match_reviews(release_key)
        return {
            "taxonomy_release_id": release_key,
            "current_release": release,
            "package_count": len(packages),
            "count_parity_ok": (
                all(bool(item.get("count_parity_ok")) for item in packages)
                if packages
                else False
            ),
            "open_review_count": sum(
                1 for item in reviews if item.get("status") == "open"
            ),
            "packages": [
                {
                    "package_id": item.get("package_id", ""),
                    "jurisdiction": item.get("jurisdiction", ""),
                    "program": item.get("program", ""),
                    "seed_only": bool(item.get("seed_only")),
                    "exhaustive_species_content": bool(
                        item.get("exhaustive_species_content")
                    ),
                    "expected_count": int(item.get("expected_count") or 0),
                    "imported_count": int(item.get("imported_count") or 0),
                    "count_parity_ok": bool(item.get("count_parity_ok")),
                    "review_status": item.get("review_status", ""),
                    "checksum": item.get("checksum", ""),
                    "submodule_counts": item.get("submodule_counts", {}),
                }
                for item in packages
            ],
            "reviews": reviews,
        }

    def search(
        self,
        *,
        program: str = "",
        submodule: str = "",
        jurisdiction: str = "",
        q: str = "",
        limit: int = 25,
        package_ids: Optional[Sequence[str]] = None,
        release_id: str = "",
        current_only: bool = True,
    ) -> list[dict[str, Any]]:
        program = str(program or "").strip()
        submodule = str(submodule or "").strip()
        jurisdiction = str(jurisdiction or "").strip()
        query = _normalize_text(q)
        limit = max(1, min(int(limit or 25), 200))
        with self._lock:
            rows = self._fetch_candidate_rows(
                program=program,
                submodule=submodule,
                jurisdiction=jurisdiction,
                package_ids=package_ids,
                release_id=release_id,
                current_only=current_only,
                query=query,
                limit=limit if not query else max(limit * 12, 200),
            )
            if not rows:
                return []
            taxon_ids = [str(row["taxon_id"]) for row in rows]
            names_by_taxon = self._fetch_names_for_taxa(taxon_ids)

        results: list[dict[str, Any]] = []
        for row in rows:
            names = names_by_taxon.get(str(row["taxon_id"]), {})
            score, matched_name = self._score_row(query, row, names)
            if query and score <= 0:
                continue
            results.append(
                {
                    "taxonomy_release_id": str(row["release_id"] or ""),
                    "release_id": str(row["release_id"] or ""),
                    "scientific_name": str(row["scientific_name"] or ""),
                    "taxon_id": str(row["taxon_id"] or ""),
                    "program": str(row["program"] or ""),
                    "submodule": str(row["submodule"] or ""),
                    "jurisdiction": str(row["jurisdiction"] or ""),
                    "package_id": str(row["package_id"] or ""),
                    "package_version": str(row["package_version"] or ""),
                    "source_manifest_version": str(
                        row["source_manifest_version"] or ""
                    ),
                    "seed_only": bool(row["seed_only"]),
                    "exhaustive_species_content": bool(
                        row["exhaustive_species_content"]
                    ),
                    "present": bool(row["present"]),
                    "expected_count": int(row["expected_count"] or 0),
                    "imported_count": int(row["imported_count"] or 0),
                    "count_parity_ok": bool(row["count_parity_ok"]),
                    "review_status": str(row["review_status"] or ""),
                    "checksum": str(row["checksum"] or ""),
                    "matched_name": matched_name,
                    "names": names,
                    "statuses": json.loads(row["status_json"] or "{}"),
                    "classification": json.loads(row["classification_json"] or "{}"),
                    "source_kind": str(row["source_kind"] or ""),
                    "is_current_release": bool(row["is_current"]),
                    "_score": score,
                }
            )
        results.sort(
            key=lambda item: (
                -int(item.pop("_score", 0)),
                item["scientific_name"].lower(),
                item["package_id"],
            )
        )
        return results[:limit]

    def resolve_taxon(
        self,
        *,
        program: str = "",
        jurisdiction: str = "",
        taxon_id: str = "",
        scientific_name: str = "",
        release_id: str = "",
        current_only: bool = True,
    ) -> dict[str, Any]:
        program_key = str(program or "").strip()
        jurisdiction_key = str(jurisdiction or "").strip()
        taxon_key = str(taxon_id or "").strip()
        scientific_key = str(scientific_name or "").strip()
        if not (taxon_key or scientific_key):
            return {}
        sql = ["""
            SELECT
                o.release_id,
                o.package_id,
                o.taxon_id,
                o.jurisdiction,
                o.program,
                o.submodule,
                o.present,
                o.status_json,
                o.classification_json,
                rp.package_version,
                rp.seed_only,
                rp.exhaustive_species_content,
                rp.source_manifest_version,
                rp.expected_count,
                rp.imported_count,
                rp.count_parity_ok,
                rp.review_status,
                rp.checksum,
                o.source_kind,
                t.scientific_name,
                r.is_current
            FROM taxonomy_release_occurrences o
            INNER JOIN taxonomy_release_packages rp
                ON rp.release_id = o.release_id AND rp.package_id = o.package_id
            INNER JOIN taxonomy_releases r
                ON r.release_id = o.release_id
            INNER JOIN taxonomy_taxa t
                ON t.taxon_id = o.taxon_id
            WHERE o.present = 1
            """]
        params: list[Any] = []
        release_key = str(release_id or "").strip()
        if release_key:
            sql.append("AND o.release_id = ?")
            params.append(release_key)
        elif current_only:
            sql.append("AND r.is_current = 1")
        if program_key:
            sql.append("AND o.program = ?")
            params.append(program_key)
        if jurisdiction_key:
            sql.append("AND o.jurisdiction = ?")
            params.append(jurisdiction_key)
        if taxon_key:
            sql.append("AND o.taxon_id = ?")
            params.append(taxon_key)
        elif scientific_key:
            sql.append("AND LOWER(t.scientific_name) = ?")
            params.append(scientific_key.lower())
        sql.append("ORDER BY r.is_current DESC, o.package_id ASC LIMIT 1")
        with self._lock:
            row = self._conn.execute("\n".join(sql), params).fetchone()
            if not row:
                return {}
            names = self._fetch_names_for_taxa([str(row["taxon_id"])])
        resolved_names = names.get(str(row["taxon_id"]), {})
        return {
            "taxonomy_release_id": str(row["release_id"] or ""),
            "release_id": str(row["release_id"] or ""),
            "taxon_id": str(row["taxon_id"] or ""),
            "scientific_name": str(row["scientific_name"] or ""),
            "program": str(row["program"] or ""),
            "submodule": str(row["submodule"] or ""),
            "jurisdiction": str(row["jurisdiction"] or ""),
            "package_id": str(row["package_id"] or ""),
            "package_version": str(row["package_version"] or ""),
            "source_manifest_version": str(row["source_manifest_version"] or ""),
            "seed_only": bool(row["seed_only"]),
            "exhaustive_species_content": bool(row["exhaustive_species_content"]),
            "expected_count": int(row["expected_count"] or 0),
            "imported_count": int(row["imported_count"] or 0),
            "count_parity_ok": bool(row["count_parity_ok"]),
            "review_status": str(row["review_status"] or ""),
            "checksum": str(row["checksum"] or ""),
            "names": resolved_names,
            "statuses": json.loads(row["status_json"] or "{}"),
            "classification": json.loads(row["classification_json"] or "{}"),
            "source_kind": str(row["source_kind"] or ""),
            "is_current_release": bool(row["is_current"]),
        }

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS taxonomy_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS taxonomy_releases (
                    release_id TEXT PRIMARY KEY,
                    release_label TEXT NOT NULL DEFAULT '',
                    source_manifest_version TEXT NOT NULL DEFAULT '',
                    manifest_signature TEXT NOT NULL DEFAULT '',
                    imported_at TEXT NOT NULL,
                    activated_at TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    is_current INTEGER NOT NULL DEFAULT 0,
                    package_count INTEGER NOT NULL DEFAULT 0,
                    exhaustive_package_count INTEGER NOT NULL DEFAULT 0,
                    review_backlog_count INTEGER NOT NULL DEFAULT 0,
                    count_parity_ok INTEGER NOT NULL DEFAULT 0,
                    raw_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS taxonomy_import_runs (
                    import_run_id TEXT PRIMARY KEY,
                    release_id TEXT NOT NULL,
                    source_manifest_version TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'running',
                    package_count INTEGER NOT NULL DEFAULT 0,
                    imported_taxa_count INTEGER NOT NULL DEFAULT 0,
                    discrepancy_report_json TEXT NOT NULL DEFAULT '{}',
                    raw_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS taxonomy_release_packages (
                    release_id TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    package_version TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    program TEXT NOT NULL,
                    seed_only INTEGER NOT NULL DEFAULT 0,
                    exhaustive_species_content INTEGER NOT NULL DEFAULT 0,
                    taxon_groups_json TEXT NOT NULL DEFAULT '[]',
                    supported_names_json TEXT NOT NULL DEFAULT '[]',
                    status_support_json TEXT NOT NULL DEFAULT '[]',
                    backbone_source_json TEXT NOT NULL DEFAULT '[]',
                    source_manifest_version TEXT NOT NULL DEFAULT '',
                    expected_count INTEGER NOT NULL DEFAULT 0,
                    imported_count INTEGER NOT NULL DEFAULT 0,
                    count_parity_ok INTEGER NOT NULL DEFAULT 0,
                    review_status TEXT NOT NULL DEFAULT '',
                    checksum TEXT NOT NULL DEFAULT '',
                    submodule_counts_json TEXT NOT NULL DEFAULT '{}',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    imported_at TEXT NOT NULL,
                    PRIMARY KEY (release_id, package_id)
                );

                CREATE INDEX IF NOT EXISTS idx_taxonomy_release_packages_filters
                    ON taxonomy_release_packages (release_id, jurisdiction, program);

                CREATE TABLE IF NOT EXISTS taxonomy_taxa (
                    taxon_id TEXT PRIMARY KEY,
                    scientific_name TEXT NOT NULL,
                    canonical_program TEXT NOT NULL DEFAULT '',
                    canonical_submodule TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS taxonomy_taxon_names (
                    taxon_id TEXT NOT NULL,
                    name_type TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (taxon_id, name_type, locale, name)
                );

                CREATE INDEX IF NOT EXISTS idx_taxonomy_taxon_names_normalized
                    ON taxonomy_taxon_names (normalized_name);

                CREATE TABLE IF NOT EXISTS taxonomy_name_crosswalk (
                    release_id TEXT NOT NULL,
                    taxon_id TEXT NOT NULL,
                    match_name TEXT NOT NULL,
                    match_type TEXT NOT NULL DEFAULT '',
                    locale TEXT NOT NULL DEFAULT '',
                    normalized_name TEXT NOT NULL DEFAULT '',
                    source_package_id TEXT NOT NULL DEFAULT '',
                    source_value TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (release_id, taxon_id, match_name, match_type, locale)
                );

                CREATE INDEX IF NOT EXISTS idx_taxonomy_name_crosswalk_normalized
                    ON taxonomy_name_crosswalk (release_id, normalized_name);

                CREATE TABLE IF NOT EXISTS taxonomy_release_occurrences (
                    release_id TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    taxon_id TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    program TEXT NOT NULL,
                    submodule TEXT NOT NULL DEFAULT '',
                    present INTEGER NOT NULL DEFAULT 1,
                    status_json TEXT NOT NULL DEFAULT '{}',
                    classification_json TEXT NOT NULL DEFAULT '{}',
                    source_kind TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (release_id, package_id, taxon_id)
                );

                CREATE INDEX IF NOT EXISTS idx_taxonomy_release_occurrences_filters
                    ON taxonomy_release_occurrences (release_id, program, jurisdiction, submodule, present);

                CREATE TABLE IF NOT EXISTS taxonomy_match_reviews (
                    review_id TEXT PRIMARY KEY,
                    release_id TEXT NOT NULL,
                    package_id TEXT NOT NULL DEFAULT '',
                    taxon_id TEXT NOT NULL DEFAULT '',
                    scientific_name TEXT NOT NULL DEFAULT '',
                    review_type TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    severity TEXT NOT NULL DEFAULT 'warning',
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_taxonomy_match_reviews_release_status
                    ON taxonomy_match_reviews (release_id, status, review_type);
                """)
            self._conn.commit()

    def _load_manifest(self) -> dict[str, Any]:
        manifest = _load_json_file(self.manifest_path, {})
        return manifest if isinstance(manifest, dict) else {}

    def _manifest_signature(self, manifest: dict[str, Any]) -> str:
        payload = {
            "manifest_version": manifest.get("manifest_version"),
            "schema_version": manifest.get("schema_version"),
            "taxonomy_release_id": self._manifest_release_id(manifest),
            "source_manifest_version": self._manifest_source_version(manifest),
            "importer_version": IMPORTER_VERSION,
            "packages": manifest.get("packages") or [],
        }
        return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()

    def _manifest_release_id(self, manifest: dict[str, Any]) -> str:
        release_id = str(manifest.get("taxonomy_release_id") or "").strip()
        if release_id:
            return release_id
        manifest_version = _slugify(
            manifest.get("manifest_version") or "taxonomy-release"
        )
        return f"taxonomy_release_{manifest_version}"

    def _manifest_source_version(self, manifest: dict[str, Any]) -> str:
        return _first_present(
            manifest.get("source_manifest_version"),
            manifest.get("manifest_version"),
            "unspecified",
        )

    def _manifest_release_label(self, manifest: dict[str, Any]) -> str:
        return _first_present(
            manifest.get("release_label"),
            manifest.get("manifest_version"),
            self._manifest_release_id(manifest),
        )

    def _prepare_package_for_import(
        self,
        package: dict[str, Any],
        *,
        manifest_dir: Path,
        default_source_manifest_version: str,
    ) -> dict[str, Any]:
        prepared = json.loads(json.dumps(package, ensure_ascii=False))
        prepared["_manifest_dir"] = str(manifest_dir)
        source_manifest_path = str(prepared.get("source_manifest_path") or "").strip()
        if source_manifest_path:
            resolved_path = _path_from_asset(source_manifest_path, prepared)
            prepared["_source_manifest_resolved_path"] = str(resolved_path)
            source_manifest = _load_json_file(resolved_path, {})
            if isinstance(source_manifest, dict) and source_manifest:
                prepared["_source_manifest"] = source_manifest
                if not prepared.get("source_manifest_version"):
                    prepared["source_manifest_version"] = _first_present(
                        source_manifest.get("source_manifest_version"),
                        source_manifest.get("source_version_date"),
                        default_source_manifest_version,
                    )
                if not prepared.get("expected_count"):
                    prepared["expected_count"] = _coerce_int(
                        source_manifest.get("official_expected_count"),
                        _coerce_int(source_manifest.get("expected_count"), 0),
                    )
                if not prepared.get("submodule_expected_counts") and isinstance(
                    source_manifest.get("submodule_counts"),
                    dict,
                ):
                    prepared["submodule_expected_counts"] = source_manifest.get(
                        "submodule_counts"
                    )
                if not prepared.get("source_assets") and not prepared.get(
                    "local_seed_assets"
                ):
                    source_files = source_manifest.get("source_files")
                    if isinstance(source_files, list):
                        prepared["source_assets"] = [
                            item
                            for item in source_files
                            if isinstance(item, dict)
                            and str(item.get("path") or "").strip()
                        ]
        return prepared

    def _validate_full_release_package(
        self,
        package: dict[str, Any],
        *,
        release_id: str,
    ) -> list[dict[str, Any]]:
        if bool(package.get("seed_only")) or not bool(
            package.get("exhaustive_species_content")
        ):
            return []

        jurisdiction = str(package.get("jurisdiction") or "").strip()
        program = str(package.get("program") or "").strip()
        manifest_root = _package_manifest_dir(package).resolve()
        source_manifest = (
            package.get("_source_manifest")
            if isinstance(package.get("_source_manifest"), dict)
            else {}
        )
        source_manifest_path = str(
            package.get("_source_manifest_resolved_path")
            or package.get("source_manifest_path")
            or ""
        ).strip()
        issues: list[dict[str, Any]] = []

        if package.get("local_seed_assets"):
            issues.append(
                {
                    "review_type": "full_release_uses_local_seed_assets",
                    "severity": "error",
                    "detail": {
                        "detail": "Full release packages must not declare local_seed_assets.",
                        "local_seed_asset_count": len(
                            package.get("local_seed_assets") or []
                        ),
                    },
                }
            )

        if source_manifest_path:
            source_manifest_root = (
                manifest_root / "taxonomy_sources" / release_id
            ).resolve()
            resolved_source_manifest_path = Path(source_manifest_path)
            if not resolved_source_manifest_path.is_absolute():
                resolved_source_manifest_path = _path_from_asset(
                    source_manifest_path, package
                )
            if not _is_relative_to(
                resolved_source_manifest_path.resolve(), source_manifest_root.resolve()
            ):
                issues.append(
                    {
                        "review_type": "full_release_source_manifest_path_invalid",
                        "severity": "error",
                        "detail": {
                            "source_manifest_path": source_manifest_path,
                            "detail": (
                                "Full release source manifests must live under "
                                f"taxonomy_sources/{release_id}/..."
                            ),
                        },
                    }
                )

        manifest_errors = (
            validate_source_manifest_payload(
                source_manifest,
                expected_release_id=release_id,
                expected_jurisdiction=jurisdiction,
                expected_program=program,
            )
            if source_manifest
            else []
        )
        if manifest_errors:
            issues.append(
                {
                    "review_type": "full_release_source_manifest_invalid",
                    "severity": "error",
                    "detail": {
                        "source_manifest_path": source_manifest_path,
                        "errors": manifest_errors,
                    },
                }
            )

        if source_manifest:
            source_file_errors = validate_source_files(
                source_manifest.get("source_files"),
                expected_release_id=release_id,
                manifest_dir=(
                    Path(source_manifest_path).parent
                    if source_manifest_path
                    else _package_manifest_dir(package)
                ),
                repo_root=REPO_ROOT,
                data_dir=manifest_root,
            )
            if source_file_errors:
                issues.append(
                    {
                        "review_type": "full_release_source_files_invalid",
                        "severity": "error",
                        "detail": {
                            "source_manifest_path": source_manifest_path,
                            "errors": source_file_errors,
                        },
                    }
                )

            manifest_expected_count = _coerce_int(
                source_manifest.get("official_expected_count")
            )
            package_expected_count = _coerce_int(package.get("expected_count"))
            if package_expected_count != manifest_expected_count:
                issues.append(
                    {
                        "review_type": "full_release_expected_count_mismatch",
                        "severity": "error",
                        "detail": {
                            "package_expected_count": package_expected_count,
                            "source_manifest_expected_count": manifest_expected_count,
                        },
                    }
                )

            manifest_submodule_counts = normalize_submodule_counts(
                source_manifest.get("submodule_counts")
            )
            package_submodule_counts = normalize_submodule_counts(
                package.get("submodule_expected_counts")
            )
            if package_submodule_counts != manifest_submodule_counts:
                issues.append(
                    {
                        "review_type": "full_release_submodule_expectations_mismatch",
                        "severity": "error",
                        "detail": {
                            "package_submodule_expected_counts": package_submodule_counts,
                            "source_manifest_submodule_counts": manifest_submodule_counts,
                        },
                    }
                )

        return issues

    def _rebuild_catalog(
        self,
        manifest: dict[str, Any],
        signature: str,
        force: bool = True,
        enforce_activation_gates: bool = False,
    ) -> None:
        packages = manifest.get("packages") if isinstance(manifest, dict) else []
        if not isinstance(packages, list):
            packages = []
        manifest_dir = self.manifest_path.parent
        release_id = self._manifest_release_id(manifest)
        source_manifest_version = self._manifest_source_version(manifest)
        release_label = self._manifest_release_label(manifest)
        activate_on_build = bool(manifest.get("activate_on_build", True))
        imported_at = _utc_now_iso()
        import_run_id = f"import_{release_id}_{_slugify(imported_at)}"
        scientific_id_map: dict[str, str] = {}
        with self._lock:
            current_row = self._conn.execute(
                "SELECT is_current FROM taxonomy_releases WHERE release_id=?",
                (release_id,),
            ).fetchone()
            was_current = bool(current_row["is_current"]) if current_row else False
            if not force:
                existing_signature = self._conn.execute(
                    "SELECT manifest_signature FROM taxonomy_releases WHERE release_id=?",
                    (release_id,),
                ).fetchone()
                if (
                    existing_signature
                    and str(existing_signature["manifest_signature"] or "") == signature
                ):
                    if activate_on_build:
                        if enforce_activation_gates:
                            self._assert_release_activation_ready_locked(release_id)
                        self._activate_release_locked(release_id)
                        self._conn.commit()
                    return

            self._conn.execute(
                """
                INSERT OR REPLACE INTO taxonomy_import_runs (
                    import_run_id,
                    release_id,
                    source_manifest_version,
                    started_at,
                    completed_at,
                    status,
                    package_count,
                    imported_taxa_count,
                    discrepancy_report_json,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_run_id,
                    release_id,
                    source_manifest_version,
                    imported_at,
                    "",
                    "running",
                    len(packages),
                    0,
                    "{}",
                    _json_dumps({"manifest": manifest}),
                ),
            )
            self._conn.execute(
                "DELETE FROM taxonomy_release_occurrences WHERE release_id=?",
                (release_id,),
            )
            self._conn.execute(
                "DELETE FROM taxonomy_release_packages WHERE release_id=?",
                (release_id,),
            )
            self._conn.execute(
                "DELETE FROM taxonomy_name_crosswalk WHERE release_id=?", (release_id,)
            )
            self._conn.execute(
                "DELETE FROM taxonomy_match_reviews WHERE release_id=?", (release_id,)
            )
            self._conn.execute(
                """
                INSERT OR REPLACE INTO taxonomy_releases (
                    release_id,
                    release_label,
                    source_manifest_version,
                    manifest_signature,
                    imported_at,
                    activated_at,
                    status,
                    is_current,
                    package_count,
                    exhaustive_package_count,
                    review_backlog_count,
                    count_parity_ok,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    release_id,
                    release_label,
                    source_manifest_version,
                    signature,
                    imported_at,
                    "",
                    "importing",
                    0,
                    0,
                    0,
                    0,
                    0,
                    _json_dumps({"manifest": manifest}),
                ),
            )

            imported_taxa_count = 0
            package_count = 0
            exhaustive_package_count = 0
            package_parity_ok = True

            for package in packages:
                if not isinstance(package, dict):
                    continue
                package = self._prepare_package_for_import(
                    package,
                    manifest_dir=manifest_dir,
                    default_source_manifest_version=source_manifest_version,
                )
                package_id = str(package.get("package_id") or "").strip()
                package_version = str(package.get("package_version") or "").strip()
                jurisdiction = str(package.get("jurisdiction") or "").strip()
                program = str(package.get("program") or "").strip()
                if (
                    not package_id
                    or not package_version
                    or not jurisdiction
                    or not program
                ):
                    continue
                importer = self._resolve_importer(package)
                package_report = self._import_package_release(
                    package=package,
                    importer=importer,
                    release_id=release_id,
                    source_manifest_version=source_manifest_version,
                    imported_at=imported_at,
                    scientific_id_map=scientific_id_map,
                )
                imported_taxa_count += int(package_report["imported_count"])
                package_count += 1
                exhaustive_package_count += (
                    1 if bool(package_report["exhaustive_species_content"]) else 0
                )
                package_parity_ok = package_parity_ok and bool(
                    package_report["count_parity_ok"]
                )

            review_backlog_count = int(
                self._scalar(
                    "SELECT COUNT(*) FROM taxonomy_match_reviews WHERE release_id=? AND status='open'",
                    (release_id,),
                )
            )

            self._conn.execute(
                """
                UPDATE taxonomy_releases
                SET
                    release_label=?,
                    source_manifest_version=?,
                    manifest_signature=?,
                    imported_at=?,
                    status='imported',
                    package_count=?,
                    exhaustive_package_count=?,
                    review_backlog_count=?,
                    count_parity_ok=?,
                    raw_json=?
                WHERE release_id=?
                """,
                (
                    release_label,
                    source_manifest_version,
                    signature,
                    imported_at,
                    package_count,
                    exhaustive_package_count,
                    review_backlog_count,
                    1 if package_parity_ok else 0,
                    _json_dumps({"manifest": manifest}),
                    release_id,
                ),
            )

            discrepancy_report = self.export_discrepancy_report(release_id)
            self._conn.execute(
                """
                UPDATE taxonomy_import_runs
                SET
                    completed_at=?,
                    status='completed',
                    imported_taxa_count=?,
                    discrepancy_report_json=?
                WHERE import_run_id=?
                """,
                (
                    imported_at,
                    imported_taxa_count,
                    _json_dumps(discrepancy_report),
                    import_run_id,
                ),
            )

            if activate_on_build:
                if enforce_activation_gates:
                    self._assert_release_activation_ready_locked(release_id)
                self._activate_release_locked(release_id)

            self._set_meta("manifest_signature", signature)
            self._set_meta("imported_at", imported_at)
            current_release_row = self._conn.execute("""
                SELECT release_id
                FROM taxonomy_releases
                WHERE is_current = 1
                ORDER BY activated_at DESC, imported_at DESC
                LIMIT 1
                """).fetchone()
            if current_release_row:
                self._set_meta(
                    "current_taxonomy_release_id",
                    str(current_release_row["release_id"] or ""),
                )
            else:
                self._set_meta("current_taxonomy_release_id", "")
            self._conn.commit()

    def _import_package_release(
        self,
        *,
        package: dict[str, Any],
        importer: TaxonomyImporter,
        release_id: str,
        source_manifest_version: str,
        imported_at: str,
        scientific_id_map: dict[str, str],
    ) -> dict[str, Any]:
        cursor = self._conn.cursor()
        package_id = str(package.get("package_id") or "").strip()
        package_version = str(package.get("package_version") or "").strip()
        jurisdiction = str(package.get("jurisdiction") or "").strip()
        program = str(package.get("program") or "").strip()
        source_manifest = (
            package.get("_source_manifest")
            if isinstance(package.get("_source_manifest"), dict)
            else {}
        )
        source_manifest_path = str(
            package.get("_source_manifest_resolved_path")
            or package.get("source_manifest_path")
            or ""
        ).strip()
        imported_count = 0
        imported_taxon_ids: list[str] = []
        submodule_counts: dict[str, int] = {}
        missing_name_count = 0
        missing_status_count = 0
        legacy_record_count = 0

        supported_names = [
            str(item or "").strip()
            for item in package.get("supported_names") or []
            if str(item or "").strip()
        ]
        status_support = [
            str(item or "").strip()
            for item in package.get("status_support") or []
            if str(item or "").strip()
        ]

        for record in importer.iter_records(package):
            insert_result = self._insert_record(
                cursor=cursor,
                package=package,
                record=record,
                scientific_id_map=scientific_id_map,
                release_id=release_id,
            )
            if not insert_result:
                continue
            imported_count += 1
            taxon_id = str(insert_result.get("taxon_id") or "")
            if taxon_id:
                imported_taxon_ids.append(taxon_id)
            submodule = str(insert_result.get("submodule") or "")
            if submodule:
                submodule_counts[submodule] = submodule_counts.get(submodule, 0) + 1
            missing_name_count += int(insert_result.get("missing_name_count") or 0)
            missing_status_count += int(insert_result.get("missing_status_count") or 0)
            if str(insert_result.get("source_kind") or "") == "legacy_bird_species":
                legacy_record_count += 1

        expected_count = _coerce_int(
            package.get("expected_count"),
            _coerce_int(
                source_manifest.get("official_expected_count"),
                _coerce_int(source_manifest.get("expected_count"), imported_count),
            ),
        )
        source_manifest_version = _first_present(
            package.get("source_manifest_version"),
            source_manifest.get("source_manifest_version"),
            source_manifest.get("source_version_date"),
            source_manifest_version,
        )
        expected_submodule_counts = (
            package.get("submodule_expected_counts")
            if isinstance(package.get("submodule_expected_counts"), dict)
            else (
                source_manifest.get("submodule_counts")
                if isinstance(source_manifest.get("submodule_counts"), dict)
                else {}
            )
        )
        count_parity_ok = imported_count == expected_count
        checksum = hashlib.sha256(
            _json_dumps(
                self._build_package_checksum_payload_locked(
                    cursor,
                    release_id=release_id,
                    package_id=package_id,
                    package_version=package_version,
                    source_manifest_version=source_manifest_version,
                    expected_count=expected_count,
                    imported_count=imported_count,
                    expected_submodule_counts=expected_submodule_counts,
                    submodule_counts=submodule_counts,
                    imported_taxon_ids=sorted(imported_taxon_ids),
                )
            ).encode("utf-8")
        ).hexdigest()

        error_review_rows = 0
        if not count_parity_ok:
            error_review_rows += 1
            self._create_review_locked(
                release_id=release_id,
                package_id=package_id,
                review_type="count_mismatch",
                severity="error",
                detail={
                    "expected_count": expected_count,
                    "imported_count": imported_count,
                    "program": program,
                    "jurisdiction": jurisdiction,
                },
            )
        if not source_manifest_path:
            error_review_rows += 1
            self._create_review_locked(
                release_id=release_id,
                package_id=package_id,
                review_type="source_manifest_missing",
                severity="error",
                detail={
                    "program": program,
                    "jurisdiction": jurisdiction,
                    "detail": "Package does not declare a source_manifest_path.",
                },
            )
        elif not source_manifest:
            error_review_rows += 1
            self._create_review_locked(
                release_id=release_id,
                package_id=package_id,
                review_type="source_manifest_unreadable",
                severity="error",
                detail={
                    "program": program,
                    "jurisdiction": jurisdiction,
                    "source_manifest_path": source_manifest_path,
                },
            )
        elif expected_submodule_counts:
            mismatches = []
            for submodule, expected_value in expected_submodule_counts.items():
                expected_int = _coerce_int(expected_value, 0)
                imported_int = _coerce_int(
                    submodule_counts.get(str(submodule) or ""), 0
                )
                if expected_int != imported_int:
                    mismatches.append(
                        {
                            "submodule": str(submodule or ""),
                            "expected_count": expected_int,
                            "imported_count": imported_int,
                        }
                    )
            if mismatches:
                error_review_rows += 1
                self._create_review_locked(
                    release_id=release_id,
                    package_id=package_id,
                    review_type="submodule_count_mismatch",
                    severity="error",
                    detail={
                        "mismatches": mismatches,
                        "expected_submodule_counts": expected_submodule_counts,
                        "imported_submodule_counts": submodule_counts,
                    },
                )
        for issue in self._validate_full_release_package(
            package, release_id=release_id
        ):
            issue_severity = str(issue.get("severity") or "error")
            if issue_severity == "error":
                error_review_rows += 1
            self._create_review_locked(
                release_id=release_id,
                package_id=package_id,
                review_type=str(
                    issue.get("review_type") or "full_release_validation_error"
                ),
                severity=str(issue.get("severity") or "error"),
                detail=(
                    issue.get("detail") if isinstance(issue.get("detail"), dict) else {}
                ),
            )
        if missing_name_count > 0:
            self._create_review_locked(
                release_id=release_id,
                package_id=package_id,
                review_type="missing_supported_names",
                severity="warning",
                detail={
                    "missing_supported_name_count": missing_name_count,
                    "supported_names": supported_names,
                },
            )
        if missing_status_count > 0:
            self._create_review_locked(
                release_id=release_id,
                package_id=package_id,
                review_type="missing_status_support",
                severity="warning",
                detail={
                    "missing_status_field_count": missing_status_count,
                    "status_support": status_support,
                },
            )
        if legacy_record_count > 0:
            self._create_review_locked(
                release_id=release_id,
                package_id=package_id,
                review_type="legacy_lookup_dependency",
                severity="warning",
                detail={
                    "legacy_record_count": legacy_record_count,
                    "detail": "Legacy mainland bird supplement is still present in this release.",
                },
            )

        review_status = (
            "needs_review"
            if error_review_rows > 0
            else (
                "approved"
                if bool(package.get("exhaustive_species_content"))
                else ("seed_only" if bool(package.get("seed_only")) else "clean")
            )
        )
        stored_package = {
            key: value for key, value in package.items() if not str(key).startswith("_")
        }
        cursor.execute(
            """
            INSERT OR REPLACE INTO taxonomy_release_packages (
                release_id,
                package_id,
                package_version,
                jurisdiction,
                program,
                seed_only,
                exhaustive_species_content,
                taxon_groups_json,
                supported_names_json,
                status_support_json,
                backbone_source_json,
                source_manifest_version,
                expected_count,
                imported_count,
                count_parity_ok,
                review_status,
                checksum,
                submodule_counts_json,
                raw_json,
                imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                release_id,
                package_id,
                package_version,
                jurisdiction,
                program,
                int(bool(package.get("seed_only"))),
                int(bool(package.get("exhaustive_species_content"))),
                _json_dumps(package.get("taxon_groups") or []),
                _json_dumps(supported_names),
                _json_dumps(status_support),
                _json_dumps(stored_package.get("backbone_source") or []),
                source_manifest_version,
                expected_count,
                imported_count,
                1 if count_parity_ok else 0,
                review_status,
                checksum,
                _json_dumps(submodule_counts),
                _json_dumps(stored_package),
                imported_at,
            ),
        )
        return {
            "release_id": release_id,
            "package_id": package_id,
            "expected_count": expected_count,
            "imported_count": imported_count,
            "count_parity_ok": count_parity_ok,
            "exhaustive_species_content": bool(
                package.get("exhaustive_species_content")
            ),
        }

    def _build_package_checksum_payload_locked(
        self,
        cursor: sqlite3.Cursor,
        *,
        release_id: str,
        package_id: str,
        package_version: str,
        source_manifest_version: str,
        expected_count: int,
        imported_count: int,
        expected_submodule_counts: dict[str, Any],
        submodule_counts: dict[str, Any],
        imported_taxon_ids: list[str],
    ) -> dict[str, Any]:
        occurrence_rows = cursor.execute(
            """
            SELECT
                o.taxon_id,
                o.jurisdiction,
                o.program,
                o.submodule,
                o.present,
                o.status_json,
                o.classification_json,
                o.source_kind,
                o.raw_json,
                t.scientific_name,
                t.canonical_program,
                t.canonical_submodule,
                t.raw_json AS taxon_raw_json
            FROM taxonomy_release_occurrences o
            INNER JOIN taxonomy_taxa t ON t.taxon_id = o.taxon_id
            WHERE o.release_id=? AND o.package_id=?
            ORDER BY o.taxon_id ASC
            """,
            (release_id, package_id),
        ).fetchall()
        taxon_ids = [
            str(row["taxon_id"] or "")
            for row in occurrence_rows
            if str(row["taxon_id"] or "").strip()
        ]
        names_by_taxon: dict[str, list[dict[str, Any]]] = {}
        if taxon_ids:
            placeholders = ",".join("?" for _ in taxon_ids)
            name_rows = cursor.execute(
                f"""
                SELECT
                    taxon_id,
                    name_type,
                    locale,
                    name,
                    normalized_name,
                    is_primary
                FROM taxonomy_taxon_names
                WHERE taxon_id IN ({placeholders})
                ORDER BY taxon_id ASC, name_type ASC, locale ASC, name ASC
                """,
                taxon_ids,
            ).fetchall()
            for row in name_rows:
                taxon_id = str(row["taxon_id"] or "")
                names_by_taxon.setdefault(taxon_id, []).append(
                    {
                        "name_type": str(row["name_type"] or ""),
                        "locale": str(row["locale"] or ""),
                        "name": str(row["name"] or ""),
                        "normalized_name": str(row["normalized_name"] or ""),
                        "is_primary": bool(row["is_primary"]),
                    }
                )
        return {
            "release_id": release_id,
            "package_id": package_id,
            "package_version": package_version,
            "source_manifest_version": source_manifest_version,
            "expected_count": expected_count,
            "imported_count": imported_count,
            "expected_submodule_counts": expected_submodule_counts,
            "submodule_counts": submodule_counts,
            "imported_taxon_ids": imported_taxon_ids,
            "taxa": [
                {
                    "taxon_id": str(row["taxon_id"] or ""),
                    "scientific_name": str(row["scientific_name"] or ""),
                    "canonical_program": str(row["canonical_program"] or ""),
                    "canonical_submodule": str(row["canonical_submodule"] or ""),
                    "jurisdiction": str(row["jurisdiction"] or ""),
                    "program": str(row["program"] or ""),
                    "submodule": str(row["submodule"] or ""),
                    "present": bool(row["present"]),
                    "source_kind": str(row["source_kind"] or ""),
                    "statuses": json.loads(row["status_json"] or "{}"),
                    "classification": json.loads(row["classification_json"] or "{}"),
                    "occurrence_raw": json.loads(row["raw_json"] or "{}"),
                    "taxon_raw": json.loads(row["taxon_raw_json"] or "{}"),
                    "names": names_by_taxon.get(str(row["taxon_id"] or ""), []),
                }
                for row in occurrence_rows
            ],
        }

    def _resolve_importer(self, package: dict[str, Any]) -> TaxonomyImporter:
        for importer in self._importers:
            if importer.supports(package):
                return importer
        return GenericPlaceholderImporter()

    def _insert_record(
        self,
        *,
        cursor: sqlite3.Cursor,
        package: dict[str, Any],
        record: dict[str, Any],
        scientific_id_map: dict[str, str],
        release_id: str,
    ) -> dict[str, Any]:
        package_id = str(package.get("package_id") or "").strip()
        jurisdiction = str(
            record.get("jurisdiction") or package.get("jurisdiction") or ""
        ).strip()
        program = str(record.get("program") or package.get("program") or "").strip()
        scientific_name = str(record.get("scientific_name") or "").strip()
        if not package_id or not jurisdiction or not program or not scientific_name:
            return {}
        taxon_id = str(record.get("taxon_id") or "").strip()
        scientific_key = scientific_name.lower()
        if not taxon_id:
            taxon_id = scientific_id_map.get(scientific_key) or (
                f"{program}-{_slugify(record.get('submodule') or 'taxon')}-{_slugify(scientific_name)}"
            )
        scientific_id_map.setdefault(scientific_key, taxon_id)
        submodule = str(record.get("submodule") or "").strip()
        raw_payload = record.get("raw") if isinstance(record.get("raw"), dict) else {}
        cursor.execute(
            """
            INSERT INTO taxonomy_taxa (taxon_id, scientific_name, canonical_program, canonical_submodule, raw_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(taxon_id) DO UPDATE SET
                scientific_name=excluded.scientific_name,
                canonical_program=CASE
                    WHEN taxonomy_taxa.canonical_program='' THEN excluded.canonical_program
                    ELSE taxonomy_taxa.canonical_program
                END,
                canonical_submodule=CASE
                    WHEN taxonomy_taxa.canonical_submodule='' THEN excluded.canonical_submodule
                    ELSE taxonomy_taxa.canonical_submodule
                END,
                raw_json=CASE
                    WHEN taxonomy_taxa.raw_json='{}' THEN excluded.raw_json
                    ELSE taxonomy_taxa.raw_json
                END
            """,
            (taxon_id, scientific_name, program, submodule, _json_dumps(raw_payload)),
        )
        inserted_names = self._insert_names(cursor, taxon_id, record.get("names"))
        self._insert_name_crosswalk(
            cursor=cursor,
            release_id=release_id,
            package_id=package_id,
            taxon_id=taxon_id,
            names=inserted_names,
        )
        source_kind = str(record.get("source_kind") or "")
        existing_occurrence = cursor.execute(
            """
            SELECT source_kind
            FROM taxonomy_release_occurrences
            WHERE release_id=? AND package_id=? AND taxon_id=?
            """,
            (release_id, package_id, taxon_id),
        ).fetchone()
        preserve_existing = (
            existing_occurrence is not None
            and str(existing_occurrence["source_kind"] or "") == "shared_seed_asset"
            and source_kind == "legacy_bird_species"
        )
        if not preserve_existing:
            cursor.execute(
                """
                INSERT OR REPLACE INTO taxonomy_release_occurrences (
                    release_id,
                    package_id,
                    taxon_id,
                    jurisdiction,
                    program,
                    submodule,
                    present,
                    status_json,
                    classification_json,
                    source_kind,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    release_id,
                    package_id,
                    taxon_id,
                    jurisdiction,
                    program,
                    submodule,
                    int(bool(record.get("present", True))),
                    _json_dumps(record.get("statuses") or {}),
                    _json_dumps(record.get("classification") or {}),
                    source_kind,
                    _json_dumps(raw_payload),
                ),
            )

        effective_source_kind = (
            str(existing_occurrence["source_kind"] or "")
            if preserve_existing and existing_occurrence is not None
            else source_kind
        )
        missing_name_count = self._count_missing_supported_names(
            package=package,
            names=record.get("names") if isinstance(record.get("names"), dict) else {},
        )
        missing_status_count = self._count_missing_status_support(
            package=package,
            statuses=(
                record.get("statuses")
                if isinstance(record.get("statuses"), dict)
                else {}
            ),
        )
        return {
            "taxon_id": taxon_id,
            "submodule": submodule,
            "source_kind": effective_source_kind,
            "missing_name_count": missing_name_count,
            "missing_status_count": missing_status_count,
        }

    def _insert_names(
        self, cursor: sqlite3.Cursor, taxon_id: str, names: Any
    ) -> dict[str, Any]:
        mapping = names if isinstance(names, dict) else {}
        inserted: dict[str, Any] = {"synonyms": []}
        for field, aliases in NAME_FIELD_ALIASES.items():
            value = ""
            for alias in aliases:
                candidate = mapping.get(alias) if isinstance(mapping, dict) else ""
                if candidate:
                    value = str(candidate).strip()
                    break
            inserted[field] = value
            if not value:
                continue
            cursor.execute(
                """
                INSERT OR REPLACE INTO taxonomy_taxon_names (
                    taxon_id,
                    name_type,
                    locale,
                    name,
                    normalized_name,
                    is_primary
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    taxon_id,
                    field,
                    NAME_LOCALES[field],
                    value,
                    _normalize_text(value),
                    1,
                ),
            )
        for synonym in mapping.get("synonyms") or []:
            synonym_value = str(synonym or "").strip()
            if not synonym_value:
                continue
            inserted["synonyms"].append(synonym_value)
            cursor.execute(
                """
                INSERT OR REPLACE INTO taxonomy_taxon_names (
                    taxon_id,
                    name_type,
                    locale,
                    name,
                    normalized_name,
                    is_primary
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    taxon_id,
                    "synonym",
                    NAME_LOCALES["synonym"],
                    synonym_value,
                    _normalize_text(synonym_value),
                    0,
                ),
            )
        return inserted

    def _insert_name_crosswalk(
        self,
        *,
        cursor: sqlite3.Cursor,
        release_id: str,
        package_id: str,
        taxon_id: str,
        names: dict[str, Any],
    ) -> None:
        for field in (
            "scientific_name",
            "simplified_chinese_name",
            "traditional_chinese_name",
            "english_common_name",
        ):
            value = str(names.get(field) or "").strip()
            if not value:
                continue
            locale = NAME_LOCALES.get(field, "")
            cursor.execute(
                """
                INSERT OR REPLACE INTO taxonomy_name_crosswalk (
                    release_id,
                    taxon_id,
                    match_name,
                    match_type,
                    locale,
                    normalized_name,
                    source_package_id,
                    source_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    release_id,
                    taxon_id,
                    value,
                    field,
                    locale,
                    _normalize_text(value),
                    package_id,
                    value,
                ),
            )
        for synonym in names.get("synonyms") or []:
            synonym_value = str(synonym or "").strip()
            if not synonym_value:
                continue
            cursor.execute(
                """
                INSERT OR REPLACE INTO taxonomy_name_crosswalk (
                    release_id,
                    taxon_id,
                    match_name,
                    match_type,
                    locale,
                    normalized_name,
                    source_package_id,
                    source_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    release_id,
                    taxon_id,
                    synonym_value,
                    "synonym",
                    NAME_LOCALES["synonym"],
                    _normalize_text(synonym_value),
                    package_id,
                    synonym_value,
                ),
            )

    def _count_missing_supported_names(
        self, *, package: dict[str, Any], names: dict[str, Any]
    ) -> int:
        supported_names = [
            str(item or "").strip()
            for item in package.get("supported_names") or []
            if str(item or "").strip()
        ]
        missing = 0
        for field in supported_names:
            if field == "synonyms":
                continue
            if not str(names.get(field) or "").strip():
                missing += 1
        return missing

    def _count_missing_status_support(
        self, *, package: dict[str, Any], statuses: dict[str, Any]
    ) -> int:
        expected_fields = [
            str(item or "").strip()
            for item in package.get("status_support") or []
            if str(item or "").strip()
        ]
        missing = 0
        for field in expected_fields:
            value = statuses.get(field)
            if value in (None, "", [], {}):
                missing += 1
        return missing

    def _create_review_locked(
        self,
        *,
        release_id: str,
        package_id: str,
        review_type: str,
        severity: str,
        detail: dict[str, Any],
        taxon_id: str = "",
        scientific_name: str = "",
    ) -> None:
        review_key = hashlib.sha1(
            f"{release_id}:{package_id}:{review_type}:{taxon_id}:{scientific_name}:{_json_dumps(detail)}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        review_id = f"review_{review_key}"
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO taxonomy_match_reviews (
                review_id,
                release_id,
                package_id,
                taxon_id,
                scientific_name,
                review_type,
                status,
                severity,
                detail_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                release_id,
                package_id,
                str(taxon_id or ""),
                str(scientific_name or ""),
                str(review_type or ""),
                "open",
                str(severity or "warning"),
                _json_dumps(detail),
                now,
                now,
            ),
        )

    def _activate_release_locked(self, release_id: str) -> None:
        activated_at = _utc_now_iso()
        self._conn.execute("UPDATE taxonomy_releases SET is_current = 0")
        self._conn.execute(
            """
            UPDATE taxonomy_releases
            SET
                is_current = 1,
                activated_at = ?,
                status = CASE WHEN status = 'draft' THEN 'imported' ELSE status END
            WHERE release_id = ?
            """,
            (activated_at, release_id),
        )
        self._set_meta("current_taxonomy_release_id", release_id)

    def _fetch_candidate_rows(
        self,
        *,
        program: str,
        submodule: str,
        jurisdiction: str,
        package_ids: Optional[Sequence[str]],
        release_id: str,
        current_only: bool,
        query: str = "",
        limit: int,
    ) -> list[sqlite3.Row]:
        sql = ["""
            SELECT
                o.release_id,
                o.package_id,
                o.taxon_id,
                o.jurisdiction,
                o.program,
                o.submodule,
                o.present,
                o.status_json,
                o.classification_json,
                rp.package_version,
                rp.seed_only,
                rp.exhaustive_species_content,
                rp.source_manifest_version,
                rp.expected_count,
                rp.imported_count,
                rp.count_parity_ok,
                rp.review_status,
                rp.checksum,
                o.source_kind,
                t.scientific_name,
                r.is_current
            FROM taxonomy_release_occurrences o
            INNER JOIN taxonomy_release_packages rp
                ON rp.release_id = o.release_id AND rp.package_id = o.package_id
            INNER JOIN taxonomy_releases r
                ON r.release_id = o.release_id
            INNER JOIN taxonomy_taxa t
                ON t.taxon_id = o.taxon_id
            WHERE o.present = 1
            """]
        params: list[Any] = []
        release_key = str(release_id or "").strip()
        if release_key:
            sql.append("AND o.release_id = ?")
            params.append(release_key)
        elif current_only:
            sql.append("AND r.is_current = 1")
        if program:
            sql.append("AND o.program = ?")
            params.append(program)
        if submodule:
            sql.append("AND o.submodule = ?")
            params.append(submodule)
        if jurisdiction:
            sql.append("AND o.jurisdiction = ?")
            params.append(jurisdiction)
        normalized_package_ids = [
            str(item).strip() for item in package_ids or [] if str(item).strip()
        ]
        if normalized_package_ids:
            placeholders = ",".join("?" for _ in normalized_package_ids)
            sql.append(f"AND o.package_id IN ({placeholders})")
            params.extend(normalized_package_ids)
        if query:
            sql.append(
                """
                AND o.taxon_id IN (
                    SELECT DISTINCT nx.taxon_id
                    FROM taxonomy_name_crosswalk nx
                    WHERE nx.release_id = o.release_id
                      AND nx.normalized_name LIKE ? ESCAPE '\\'
                )
                """
            )
            params.append(f"%{_escape_sql_like(query)}%")
        sql.append(
            "ORDER BY t.scientific_name COLLATE NOCASE ASC, o.package_id ASC LIMIT ?"
        )
        params.append(limit)
        return list(self._conn.execute("\n".join(sql), params).fetchall())

    def _fetch_names_for_taxa(
        self, taxon_ids: Sequence[str]
    ) -> dict[str, dict[str, Any]]:
        unique_ids = [item for item in dict.fromkeys(taxon_ids) if item]
        if not unique_ids:
            return {}
        placeholders = ",".join("?" for _ in unique_ids)
        rows = self._conn.execute(
            f"""
            SELECT taxon_id, name_type, name, is_primary
            FROM taxonomy_taxon_names
            WHERE taxon_id IN ({placeholders})
            ORDER BY is_primary DESC, name_type ASC, name ASC
            """,
            unique_ids,
        ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            taxon_id = str(row["taxon_id"])
            bucket = result.setdefault(
                taxon_id,
                {
                    "scientific_name": "",
                    "simplified_chinese_name": "",
                    "traditional_chinese_name": "",
                    "english_common_name": "",
                    "synonyms": [],
                },
            )
            name_type = str(row["name_type"])
            name_value = str(row["name"] or "")
            if name_type == "synonym":
                if name_value and name_value not in bucket["synonyms"]:
                    bucket["synonyms"].append(name_value)
            elif not bucket.get(name_type):
                bucket[name_type] = name_value
        return result

    def _score_row(
        self, query: str, row: sqlite3.Row, names: dict[str, Any]
    ) -> tuple[int, str]:
        scientific_name = str(row["scientific_name"] or "")
        if not query:
            return 1, scientific_name
        candidates: list[tuple[str, int]] = []
        if scientific_name:
            candidates.append((scientific_name, 0))
        for field in (
            "simplified_chinese_name",
            "traditional_chinese_name",
            "english_common_name",
        ):
            value = str(names.get(field) or "")
            if value:
                candidates.append((value, 1))
        for synonym in names.get("synonyms") or []:
            synonym_value = str(synonym or "")
            if synonym_value:
                candidates.append((synonym_value, 2))
        best_score = 0
        best_name = ""
        for value, priority in candidates:
            normalized = _normalize_text(value)
            if not normalized:
                continue
            score = 0
            if normalized == query:
                score = 600 - (priority * 20)
            elif normalized.startswith(query):
                score = 450 - (priority * 20)
            elif query in normalized:
                score = 250 - (priority * 20)
            if score > best_score:
                best_score = score
                best_name = value
        return best_score, best_name

    def _get_meta(self, key: str) -> str:
        row = self._conn.execute(
            "SELECT value FROM taxonomy_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else ""

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO taxonomy_meta (key, value) VALUES (?, ?)",
            (key, str(value or "")),
        )

    def _scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self._conn.execute(sql, params).fetchone()
        if not row:
            return 0
        return row[0]


def get_taxonomy_catalog(
    *,
    storage_dir: Optional[str | Path] = None,
    db_path: Optional[str | Path] = None,
    force_reload: bool = False,
) -> TaxonomyCatalog:
    global _CATALOG_SINGLETON
    with _CATALOG_LOCK:
        if _CATALOG_SINGLETON is None or force_reload:
            if _CATALOG_SINGLETON is not None:
                _CATALOG_SINGLETON.close()
            _CATALOG_SINGLETON = TaxonomyCatalog(
                storage_dir=storage_dir, db_path=db_path
            )
        return _CATALOG_SINGLETON
