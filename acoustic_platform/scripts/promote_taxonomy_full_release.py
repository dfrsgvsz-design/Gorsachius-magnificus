from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from taxonomy_release_builder import (  # noqa: E402
    DATA_DIR,
    FullReleaseValidationError,
    build_full_release_manifest,
    build_release_manifest_payload,
    write_json_file,
)


def _default_manifest_path() -> Path:
    return DATA_DIR / "taxonomy_packages.json"


def _default_release_manifest_path(release_id: str) -> Path:
    return DATA_DIR / "taxonomy_releases" / release_id / "release_manifest.json"


def _backup_path(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}.{timestamp}.bak{path.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate repo-staged full backbone taxonomy assets and promote them into "
            "backend/data/taxonomy_packages.json as the candidate full manifest."
        )
    )
    parser.add_argument("--release-id", required=True, help="Full taxonomy release id, for example taxonomy_full_release_2026_04_23")
    parser.add_argument("--manifest-path", default=str(_default_manifest_path()), help="Target taxonomy_packages.json path")
    parser.add_argument(
        "--release-manifest-path",
        default="",
        help="Optional output path for backend/data/taxonomy_releases/<release_id>/release_manifest.json",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate the asset tree and print the generated manifest summary without writing files",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Overwrite the target manifest without creating a timestamped backup",
    )
    args = parser.parse_args()

    release_id = str(args.release_id or "").strip()
    manifest_path = Path(args.manifest_path).resolve()
    release_manifest_path = (
        Path(args.release_manifest_path).resolve()
        if str(args.release_manifest_path or "").strip()
        else _default_release_manifest_path(release_id).resolve()
    )

    try:
        full_manifest = build_full_release_manifest(release_id, repo_root=REPO_ROOT, data_dir=DATA_DIR)
    except FullReleaseValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    release_manifest = build_release_manifest_payload(full_manifest)
    if not args.check_only:
        if manifest_path.exists() and not args.no_backup:
            backup_path = _backup_path(manifest_path)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_path, backup_path)
        write_json_file(manifest_path, full_manifest)
        write_json_file(release_manifest_path, release_manifest)

    summary = {
        "status": "validated" if args.check_only else "written",
        "taxonomy_release_id": release_id,
        "manifest_path": str(manifest_path),
        "release_manifest_path": str(release_manifest_path),
        "package_count": len(full_manifest.get("packages") or []),
        "packages": [
            {
                "package_id": item.get("package_id"),
                "expected_count": item.get("expected_count"),
                "submodule_expected_counts": item.get("submodule_expected_counts"),
            }
            for item in full_manifest.get("packages") or []
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
