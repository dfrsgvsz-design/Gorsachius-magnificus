import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxonomy_release_builder import (
    FullReleaseValidationError,
    build_full_release_manifest,
)

FULL_RELEASE_ID = "taxonomy_full_release_2026_04_23"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _source_file_path(
    data_dir: Path, release_id: str, jurisdiction: str, program: str
) -> Path:
    return (
        data_dir
        / "taxonomy_releases"
        / release_id
        / jurisdiction
        / program
        / f"{program}_release_entries.json"
    )


def _source_manifest_path(
    data_dir: Path, release_id: str, jurisdiction: str, program: str
) -> Path:
    return (
        data_dir
        / "taxonomy_sources"
        / release_id
        / jurisdiction
        / program
        / "source_manifest.json"
    )


def _make_source_manifest(
    *,
    release_id: str,
    jurisdiction: str,
    program: str,
    submodule_counts: dict[str, int],
    source_files: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "release_id": release_id,
        "jurisdiction": jurisdiction,
        "program": program,
        "submodule_counts": submodule_counts,
        "official_expected_count": sum(submodule_counts.values()),
        "source_files": source_files,
        "source_version_date": "2026-04-23",
        "license_note": "test fixture",
        "mapping_notes": "normalized fixture",
    }


def _write_valid_full_asset_tree(
    data_dir: Path, *, release_id: str = FULL_RELEASE_ID
) -> None:
    package_matrix = [
        (
            "mainland_china",
            "terrestrial_vertebrates",
            {"birds": 1505, "mammals": 2, "reptiles": 3, "amphibians": 4},
        ),
        ("mainland_china", "plants", {"trees": 11, "shrubs": 7}),
        ("mainland_china", "insects", {"butterflies": 9, "moths": 8}),
        (
            "taiwan",
            "terrestrial_vertebrates",
            {"birds": 12, "mammals": 5, "reptiles": 6, "amphibians": 7},
        ),
        ("taiwan", "plants", {"trees": 10, "herbs": 4}),
        ("taiwan", "insects", {"butterflies": 3, "odonates": 2}),
    ]
    for jurisdiction, program, submodule_counts in package_matrix:
        source_path = _source_file_path(data_dir, release_id, jurisdiction, program)
        _write_json(source_path, {"entries": []})
        _write_json(
            _source_manifest_path(data_dir, release_id, jurisdiction, program),
            _make_source_manifest(
                release_id=release_id,
                jurisdiction=jurisdiction,
                program=program,
                submodule_counts=submodule_counts,
                source_files=[
                    {
                        "path": f"backend/data/taxonomy_releases/{release_id}/{jurisdiction}/{program}/{program}_release_entries.json",
                        "source_kind": "generic_backbone_asset",
                    }
                ],
            ),
        )


class TaxonomyReleaseBuilderTests(unittest.TestCase):
    def test_build_full_release_manifest_from_dual_layer_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            data_dir = repo_root / "backend" / "data"
            _write_valid_full_asset_tree(data_dir)

            manifest = build_full_release_manifest(
                FULL_RELEASE_ID, repo_root=repo_root, data_dir=data_dir
            )

            self.assertEqual(manifest["taxonomy_release_id"], FULL_RELEASE_ID)
            self.assertFalse(manifest["activate_on_build"])
            self.assertEqual(len(manifest["packages"]), 6)

            mainland_vertebrates = next(
                item
                for item in manifest["packages"]
                if item["package_id"] == "cn_mainland_terrestrial_vertebrates_full"
            )
            self.assertFalse(mainland_vertebrates["seed_only"])
            self.assertTrue(mainland_vertebrates["exhaustive_species_content"])
            self.assertNotIn("local_seed_assets", mainland_vertebrates)
            self.assertEqual(
                mainland_vertebrates["submodule_expected_counts"]["birds"], 1505
            )
            self.assertEqual(
                mainland_vertebrates["source_manifest_path"],
                "backend/data/taxonomy_sources/taxonomy_full_release_2026_04_23/mainland_china/terrestrial_vertebrates/source_manifest.json",
            )

    def test_build_full_release_manifest_rejects_mainland_bird_count_not_1505(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            data_dir = repo_root / "backend" / "data"
            _write_valid_full_asset_tree(data_dir)

            broken_manifest_path = _source_manifest_path(
                data_dir,
                FULL_RELEASE_ID,
                "mainland_china",
                "terrestrial_vertebrates",
            )
            payload = json.loads(broken_manifest_path.read_text(encoding="utf-8"))
            payload["submodule_counts"]["birds"] = 1504
            payload["official_expected_count"] = sum(
                payload["submodule_counts"].values()
            )
            _write_json(broken_manifest_path, payload)

            with self.assertRaises(FullReleaseValidationError) as ctx:
                build_full_release_manifest(
                    FULL_RELEASE_ID, repo_root=repo_root, data_dir=data_dir
                )
            self.assertIn("birds count must be 1505", str(ctx.exception))

    def test_build_full_release_manifest_rejects_source_files_outside_release_root(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            data_dir = repo_root / "backend" / "data"
            _write_valid_full_asset_tree(data_dir)

            rogue_path = data_dir / "rogue_entries.json"
            _write_json(rogue_path, {"entries": []})
            broken_manifest_path = _source_manifest_path(
                data_dir,
                FULL_RELEASE_ID,
                "mainland_china",
                "plants",
            )
            payload = json.loads(broken_manifest_path.read_text(encoding="utf-8"))
            payload["source_files"] = [
                {
                    "path": "backend/data/rogue_entries.json",
                    "source_kind": "generic_backbone_asset",
                }
            ]
            _write_json(broken_manifest_path, payload)

            with self.assertRaises(FullReleaseValidationError) as ctx:
                build_full_release_manifest(
                    FULL_RELEASE_ID, repo_root=repo_root, data_dir=data_dir
                )
            self.assertIn(
                "must resolve under backend/data/taxonomy_releases", str(ctx.exception)
            )


if __name__ == "__main__":
    unittest.main()
