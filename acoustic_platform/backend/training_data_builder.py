"""
Enhanced training data builder for bioacoustic species classification.

Integrates multiple data sources:
1. Xeno-canto (existing client)
2. BirdSet via HuggingFace datasets (6800+ hours, ~10K species)
3. Local recordings with quality filtering

Supports data augmentation at the audio and spectrogram level.
"""

import json
import logging
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "data" / "training_datasets"


def build_from_xeno_canto(
    species_list: list[dict],
    output_dir: str | Path = DEFAULT_OUTPUT_DIR / "xeno_canto",
    max_per_species: int = 30,
    min_quality: str = "C",
    country: str = "China",
) -> dict:
    """Download training data from Xeno-canto for a list of target species.

    Args:
        species_list: List of dicts with keys 'scientific', 'chinese', 'english'.
        output_dir: Where to save downloaded audio files.
        max_per_species: Maximum recordings per species.
        min_quality: Minimum quality rating (A > B > C > D > E).
        country: Country filter for recordings.

    Returns:
        Dict with manifest path, statistics, and any errors.
    """
    from xeno_canto_client import (
        search_recordings,
        search_recordings_global,
        download_recording,
        get_api_key,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not get_api_key():
        return {"error": "Xeno-canto API key not configured"}

    quality_order = ["A", "B", "C", "D", "E"]
    quality_idx = quality_order.index(min_quality) if min_quality in quality_order else 2

    manifest = []
    stats = {"total_downloaded": 0, "species_counts": {}, "errors": []}

    for sp in species_list:
        scientific = sp.get("scientific", "")
        if not scientific:
            continue

        sp_dir = output_dir / scientific.replace(" ", "_")
        sp_dir.mkdir(parents=True, exist_ok=True)

        recordings = []
        for q in quality_order[: quality_idx + 1]:
            try:
                recs = search_recordings(scientific, quality=q, country=country)
                recordings.extend([r for r in recs if r.get("file_url")])
            except Exception as e:
                logger.warning("XC search failed for %s (q=%s): %s", scientific, q, e)

        if len(recordings) < max_per_species:
            try:
                global_recs = search_recordings_global(scientific)
                recordings.extend([r for r in global_recs if r.get("file_url")])
            except Exception:
                pass

        seen_ids = set()
        unique_recs = []
        for r in recordings:
            rid = r.get("id")
            if rid not in seen_ids:
                seen_ids.add(rid)
                unique_recs.append(r)

        unique_recs = unique_recs[:max_per_species]
        downloaded = 0

        for rec in unique_recs:
            try:
                filepath = download_recording(rec["file_url"], str(sp_dir), str(rec.get("id", "")))
                if filepath:
                    manifest.append({
                        "species_scientific": scientific,
                        "species_chinese": sp.get("chinese", ""),
                        "species_english": sp.get("english", ""),
                        "file_path": str(filepath),
                        "source": "xeno_canto",
                        "xc_id": rec.get("id", ""),
                        "quality": rec.get("quality", ""),
                    })
                    downloaded += 1
            except Exception as e:
                stats["errors"].append(f"{scientific}: {e}")

        stats["species_counts"][scientific] = downloaded
        stats["total_downloaded"] += downloaded
        logger.info("Downloaded %d/%d for %s", downloaded, max_per_species, scientific)
        time.sleep(0.5)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    stats["manifest_path"] = str(manifest_path)
    stats["total_species"] = len(stats["species_counts"])
    return stats


def build_from_birdset(
    target_species: list[str],
    output_dir: str | Path = DEFAULT_OUTPUT_DIR / "birdset",
    max_per_species: int = 50,
    dataset_name: str = "DBD",
) -> dict:
    """Download and prepare training data from BirdSet (HuggingFace).

    BirdSet provides 6800+ recording hours across ~10K bird species.
    This function filters for target species and exports audio segments.

    Args:
        target_species: List of scientific names to extract.
        output_dir: Output directory.
        max_per_species: Maximum samples per species.
        dataset_name: BirdSet subset (HSN, NBP, SSW, etc.).

    Returns:
        Dict with manifest path and statistics.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from datasets import load_dataset
    except ImportError:
        return {
            "error": "HuggingFace datasets not installed. Run: pip install datasets",
            "install_command": "pip install datasets soundfile",
        }

    stats = {"total_extracted": 0, "species_counts": {}, "errors": []}
    manifest = []

    try:
        logger.info("Loading BirdSet/%s from HuggingFace...", dataset_name)
        ds = load_dataset(
            "DBD-research-group/BirdSet",
            dataset_name,
            trust_remote_code=True,
        )
    except Exception as e:
        return {"error": f"Failed to load BirdSet: {e}"}

    train_split = ds.get("train")
    if train_split is None:
        return {"error": "No train split found in BirdSet"}

    target_set = {sp.lower().replace(" ", "_") for sp in target_species}

    if hasattr(train_split, "column_names"):
        cols = train_split.column_names
        has_ebird = "ebird_code" in cols
        has_labels = "labels" in cols or "label" in cols
    else:
        has_ebird = False
        has_labels = False

    species_counter = Counter()

    for i, example in enumerate(train_split):
        if has_labels:
            label_key = "labels" if "labels" in example else "label"
            label = example.get(label_key, "")
        elif has_ebird:
            label = example.get("ebird_code", "")
        else:
            continue

        label_normalized = str(label).lower().replace(" ", "_")
        if label_normalized not in target_set:
            continue

        if species_counter[label_normalized] >= max_per_species:
            continue

        try:
            audio = example.get("audio")
            if audio is None:
                continue

            sp_dir = output_dir / label_normalized
            sp_dir.mkdir(parents=True, exist_ok=True)

            import soundfile as sf
            filename = f"{label_normalized}_{species_counter[label_normalized]:04d}.wav"
            filepath = sp_dir / filename

            if isinstance(audio, dict):
                array = audio.get("array")
                sr = audio.get("sampling_rate", 22050)
                if array is not None:
                    sf.write(str(filepath), array, sr)
                else:
                    continue
            else:
                continue

            manifest.append({
                "species_scientific": label.replace("_", " ").title(),
                "file_path": str(filepath),
                "source": "birdset",
                "dataset": dataset_name,
                "sample_index": i,
            })
            species_counter[label_normalized] += 1
            stats["total_extracted"] += 1

        except Exception as e:
            stats["errors"].append(f"Sample {i}: {e}")

        if all(species_counter[sp] >= max_per_species for sp in target_set):
            break

    stats["species_counts"] = dict(species_counter)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    stats["manifest_path"] = str(manifest_path)
    return stats


def merge_manifests(
    manifest_paths: list[str | Path],
    output_path: str | Path,
    min_per_species: int = 3,
) -> dict:
    """Merge multiple manifest files into one unified training manifest.

    Filters species with fewer than min_per_species samples.
    """
    all_entries = []
    for mp in manifest_paths:
        mp = Path(mp)
        if mp.exists():
            entries = json.loads(mp.read_text(encoding="utf-8"))
            all_entries.extend(entries)

    species_counts = Counter(e.get("species_scientific", "") for e in all_entries)
    valid_species = {sp for sp, cnt in species_counts.items() if cnt >= min_per_species and sp}

    filtered = [e for e in all_entries if e.get("species_scientific", "") in valid_species]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(filtered, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    return {
        "total_entries": len(filtered),
        "total_species": len(valid_species),
        "removed_species": len(species_counts) - len(valid_species),
        "sources": dict(Counter(e.get("source", "unknown") for e in filtered)),
        "manifest_path": str(output_path),
    }


def augment_audio_dataset(
    manifest_path: str | Path,
    output_dir: str | Path,
    augmentations_per_file: int = 3,
    target_species: Optional[list[str]] = None,
) -> dict:
    """Apply audio augmentation to expand a training dataset.

    Generates augmented copies using noise injection, pitch shift,
    time stretch, and gain variation.
    """
    import librosa
    import soundfile as sf

    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rng = np.random.default_rng(42)

    new_entries = []
    augmented_count = 0

    for entry in manifest:
        sp = entry.get("species_scientific", "")
        if target_species and sp not in target_species:
            continue

        fp = Path(entry.get("file_path", ""))
        if not fp.exists():
            continue

        try:
            y, sr = librosa.load(str(fp), sr=22050, duration=10.0)
        except Exception:
            continue

        sp_dir = output_dir / sp.replace(" ", "_")
        sp_dir.mkdir(parents=True, exist_ok=True)

        for aug_idx in range(augmentations_per_file):
            y_aug = y.copy()

            if rng.random() < 0.5:
                noise_level = rng.uniform(0.001, 0.01)
                y_aug = y_aug + rng.normal(0, noise_level, len(y_aug)).astype(np.float32)

            if rng.random() < 0.4:
                n_steps = rng.uniform(-2, 2)
                y_aug = librosa.effects.pitch_shift(y_aug, sr=sr, n_steps=n_steps)

            if rng.random() < 0.4:
                rate = rng.uniform(0.85, 1.15)
                y_aug = librosa.effects.time_stretch(y_aug, rate=rate)

            if rng.random() < 0.5:
                gain = rng.uniform(0.7, 1.3)
                y_aug = y_aug * gain

            y_aug = np.clip(y_aug, -1.0, 1.0)

            aug_filename = f"{fp.stem}_aug{aug_idx:02d}.wav"
            aug_path = sp_dir / aug_filename
            sf.write(str(aug_path), y_aug, sr)

            new_entry = {**entry, "file_path": str(aug_path), "augmented": True}
            new_entries.append(new_entry)
            augmented_count += 1

    aug_manifest = manifest + new_entries
    aug_manifest_path = output_dir / "manifest_augmented.json"
    aug_manifest_path.write_text(
        json.dumps(aug_manifest, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    return {
        "original_count": len(manifest),
        "augmented_count": augmented_count,
        "total_count": len(aug_manifest),
        "manifest_path": str(aug_manifest_path),
    }
