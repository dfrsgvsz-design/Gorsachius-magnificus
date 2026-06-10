"""
BirdNET Integration Engine — Baseline species identification using BirdNET-Analyzer.

Provides a switchable inference backend using Cornell Lab's BirdNET model (~6000 species).
Used as:
1. Baseline comparison for our custom CNN models
2. Semi-automatic labeling tool for training data
3. Fallback when custom model is not trained

Requires: pip install birdnetlib
"""

import os
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional

_analyzer = None
_available = False


def _check_available():
    """Check if birdnetlib is installed and usable."""
    global _available
    try:
        from birdnetlib.analyzer import Analyzer

        _available = True
    except ImportError:
        _available = False
    return _available


def is_available():
    """Return True if BirdNET engine can be used."""
    if _analyzer is not None:
        return True
    return _check_available()


def init_analyzer():
    """Initialize BirdNET analyzer (downloads model on first run)."""
    global _analyzer
    if _analyzer is not None:
        return _analyzer
    if not _check_available():
        return None
    try:
        from birdnetlib.analyzer import Analyzer

        _analyzer = Analyzer()
        print("[BirdNET] Analyzer initialized successfully")
        return _analyzer
    except Exception as e:
        print(f"[BirdNET] Failed to initialize: {e}")
        return None


def predict_from_file(filepath, lat=None, lon=None, date=None, min_conf=0.1, top_k=10):
    """Run BirdNET prediction on an audio file.

    Args:
        filepath: Path to audio file (mp3/wav/ogg/flac)
        lat: Latitude for geographic filtering (optional)
        lon: Longitude for geographic filtering (optional)
        date: Date for seasonal filtering (optional, defaults to today)
        min_conf: Minimum confidence threshold
        top_k: Return top K results

    Returns:
        List of detection dicts with species info and confidence.
    """
    analyzer = init_analyzer()
    if analyzer is None:
        return [{"error": "BirdNET not available. Install: pip install birdnetlib"}]

    try:
        from birdnetlib import Recording

        if date is None:
            date = datetime.now()

        kwargs = {
            "min_conf": min_conf,
        }
        if lat is not None and lon is not None:
            kwargs["lat"] = float(lat)
            kwargs["lon"] = float(lon)
            kwargs["date"] = date

        recording = Recording(analyzer, str(filepath), **kwargs)
        recording.analyze()

        detections = recording.detections or []

        # Aggregate by species (BirdNET returns per-segment results)
        species_best = {}
        for det in detections:
            sci = det.get("scientific_name", "")
            conf = det.get("confidence", 0)
            if sci not in species_best or conf > species_best[sci]["confidence"]:
                species_best[sci] = {
                    "species_scientific": sci,
                    "species_common": det.get("common_name", ""),
                    "confidence": round(conf, 4),
                    "start_time": det.get("start_time", 0),
                    "end_time": det.get("end_time", 0),
                    "source": "birdnet",
                }

        results = sorted(
            species_best.values(), key=lambda x: x["confidence"], reverse=True
        )
        return results[:top_k]

    except Exception as e:
        return [{"error": f"BirdNET prediction failed: {str(e)}"}]


def predict_from_bytes(audio_bytes, filename="audio.wav", **kwargs):
    """Run BirdNET on in-memory audio bytes."""
    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        return predict_from_file(tmp_path, **kwargs)
    finally:
        os.unlink(tmp_path)


def batch_label(file_paths, lat=None, lon=None, min_conf=0.3):
    """Batch-label audio files for semi-automatic training data creation.

    Returns a manifest-compatible list of labels.
    """
    results = []
    for i, fp in enumerate(file_paths):
        preds = predict_from_file(fp, lat=lat, lon=lon, min_conf=min_conf, top_k=1)
        if preds and "error" not in preds[0]:
            top = preds[0]
            results.append(
                {
                    "file_path": str(fp),
                    "species_scientific": top["species_scientific"],
                    "species_common": top["species_common"],
                    "confidence": top["confidence"],
                    "auto_labeled": True,
                    "label_source": "birdnet",
                }
            )
        if (i + 1) % 50 == 0:
            print(f"  [BirdNET] Labeled {i+1}/{len(file_paths)} files")
    print(f"  [BirdNET] Labeling complete: {len(results)}/{len(file_paths)} labeled")
    return results
