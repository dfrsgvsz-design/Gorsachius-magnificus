"""
Multimodal Wildlife Diversity Survey Module

Integrates infrared camera imagery and audio recordings into unified
survey sessions for comprehensive biodiversity assessment.

Data flow:
  IR Camera → Photos → EXIF extraction → AI species classification
  Audio Recorder → Recordings → Acoustic indices + species detection
  Manual → Field notes → Observer records
  ──────────────────→ Spatiotemporal correlation → Merged species list
"""

import json
import logging
import uuid
from collections import Counter, defaultdict
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data" / "multimodal_surveys"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class SurveySession:
    """Represents a multimodal survey at a specific site and time range."""

    def __init__(
        self,
        session_id: str = "",
        site_name: str = "",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        habitat_type: str = "",
        observer: str = "",
        notes: str = "",
    ):
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.site_name = site_name
        self.latitude = latitude
        self.longitude = longitude
        self.start_time = start_time or datetime.now(UTC).isoformat()
        self.end_time = end_time
        self.habitat_type = habitat_type
        self.observer = observer
        self.notes = notes
        self.image_records: list[dict] = []
        self.audio_records: list[dict] = []
        self.manual_records: list[dict] = []
        self.created_at = datetime.now(UTC).isoformat()

    def add_image_record(
        self,
        file_path: str,
        timestamp: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        camera_model: str = "",
        species_detected: Optional[list[dict]] = None,
        is_blank: bool = False,
        exif: Optional[dict] = None,
        thumbnail_path: str = "",
    ) -> dict:
        """Add an infrared camera image record to the survey."""
        record = {
            "record_id": str(uuid.uuid4())[:10],
            "type": "image",
            "file_path": file_path,
            "timestamp": timestamp or datetime.now(UTC).isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "camera_model": camera_model,
            "species_detected": species_detected or [],
            "is_blank": is_blank,
            "exif": exif or {},
            "thumbnail_path": thumbnail_path,
        }
        self.image_records.append(record)
        return record

    def add_audio_record(
        self,
        file_path: str,
        timestamp: Optional[str] = None,
        duration_seconds: float = 0,
        device_id: str = "",
        species_detected: Optional[list[dict]] = None,
        acoustic_indices: Optional[dict] = None,
        sample_rate: int = 0,
    ) -> dict:
        """Add an audio recording to the survey."""
        record = {
            "record_id": str(uuid.uuid4())[:10],
            "type": "audio",
            "file_path": file_path,
            "timestamp": timestamp or datetime.now(UTC).isoformat(),
            "duration_seconds": duration_seconds,
            "device_id": device_id,
            "species_detected": species_detected or [],
            "acoustic_indices": acoustic_indices or {},
            "sample_rate": sample_rate,
        }
        self.audio_records.append(record)
        return record

    def add_manual_record(
        self,
        species: str,
        count: int = 1,
        evidence_type: str = "visual",
        timestamp: Optional[str] = None,
        observer: str = "",
        confidence: str = "certain",
        behavior: str = "",
        habitat_notes: str = "",
    ) -> dict:
        """Add a manual field observation record."""
        record = {
            "record_id": str(uuid.uuid4())[:10],
            "type": "manual",
            "species": species,
            "count": count,
            "evidence_type": evidence_type,
            "timestamp": timestamp or datetime.now(UTC).isoformat(),
            "observer": observer or self.observer,
            "confidence": confidence,
            "behavior": behavior,
            "habitat_notes": habitat_notes,
        }
        self.manual_records.append(record)
        return record

    def get_merged_species_list(
        self,
        min_confidence: float = 0.3,
        time_window_minutes: int = 30,
    ) -> list[dict]:
        """Merge species detections from all modalities into a unified list.

        Combines image detections, audio detections, and manual records,
        deduplicating by species and aggregating evidence.
        """
        species_evidence = defaultdict(lambda: {
            "image_detections": 0,
            "audio_detections": 0,
            "manual_observations": 0,
            "max_confidence": 0.0,
            "evidence_types": set(),
            "first_seen": None,
            "last_seen": None,
            "total_count": 0,
        })

        for img in self.image_records:
            if img.get("is_blank"):
                continue
            for det in img.get("species_detected", []):
                sp = det.get("species", det.get("label", ""))
                conf = det.get("confidence", 0)
                if sp and conf >= min_confidence:
                    info = species_evidence[sp]
                    info["image_detections"] += 1
                    info["max_confidence"] = max(info["max_confidence"], conf)
                    info["evidence_types"].add("camera_trap")
                    ts = img.get("timestamp")
                    if ts:
                        if info["first_seen"] is None or ts < info["first_seen"]:
                            info["first_seen"] = ts
                        if info["last_seen"] is None or ts > info["last_seen"]:
                            info["last_seen"] = ts
                    info["total_count"] += det.get("count", 1)

        for aud in self.audio_records:
            for det in aud.get("species_detected", []):
                sp = det.get("species", det.get("species_scientific", ""))
                conf = det.get("confidence", 0)
                if sp and conf >= min_confidence:
                    info = species_evidence[sp]
                    info["audio_detections"] += 1
                    info["max_confidence"] = max(info["max_confidence"], conf)
                    info["evidence_types"].add("acoustic")
                    ts = aud.get("timestamp")
                    if ts:
                        if info["first_seen"] is None or ts < info["first_seen"]:
                            info["first_seen"] = ts
                        if info["last_seen"] is None or ts > info["last_seen"]:
                            info["last_seen"] = ts
                    info["total_count"] += 1

        for rec in self.manual_records:
            sp = rec.get("species", "")
            if sp:
                info = species_evidence[sp]
                info["manual_observations"] += 1
                info["evidence_types"].add(rec.get("evidence_type", "manual"))
                info["total_count"] += rec.get("count", 1)
                info["max_confidence"] = max(info["max_confidence"], 1.0)
                ts = rec.get("timestamp")
                if ts:
                    if info["first_seen"] is None or ts < info["first_seen"]:
                        info["first_seen"] = ts
                    if info["last_seen"] is None or ts > info["last_seen"]:
                        info["last_seen"] = ts

        merged = []
        for sp, info in sorted(species_evidence.items(), key=lambda x: -x[1]["total_count"]):
            merged.append({
                "species": sp,
                "total_detections": info["total_count"],
                "image_detections": info["image_detections"],
                "audio_detections": info["audio_detections"],
                "manual_observations": info["manual_observations"],
                "max_confidence": round(info["max_confidence"], 4),
                "evidence_types": sorted(info["evidence_types"]),
                "multimodal": len(info["evidence_types"]) > 1,
                "first_seen": info["first_seen"],
                "last_seen": info["last_seen"],
            })
        return merged

    def compute_diversity_indices(self, min_confidence: float = 0.3) -> dict:
        """Compute biodiversity indices from merged species data."""
        species_list = self.get_merged_species_list(min_confidence)
        if not species_list:
            return {"richness": 0, "shannon": 0, "simpson": 0, "evenness": 0}

        counts = [sp["total_detections"] for sp in species_list]
        total = sum(counts)
        richness = len(species_list)

        if total == 0:
            return {"richness": richness, "shannon": 0, "simpson": 0, "evenness": 0}

        import math
        proportions = [c / total for c in counts]

        shannon = -sum(p * math.log(p) for p in proportions if p > 0)
        simpson = 1 - sum(p ** 2 for p in proportions)
        max_shannon = math.log(richness) if richness > 1 else 1
        evenness = shannon / max_shannon if max_shannon > 0 else 0

        multimodal_species = sum(1 for sp in species_list if sp["multimodal"])

        return {
            "richness": richness,
            "shannon": round(shannon, 4),
            "simpson": round(simpson, 4),
            "evenness": round(evenness, 4),
            "total_individuals": total,
            "multimodal_species": multimodal_species,
            "image_only_species": sum(1 for sp in species_list if sp["image_detections"] > 0 and sp["audio_detections"] == 0 and sp["manual_observations"] == 0),
            "audio_only_species": sum(1 for sp in species_list if sp["audio_detections"] > 0 and sp["image_detections"] == 0 and sp["manual_observations"] == 0),
        }

    def get_summary(self) -> dict:
        """Get a summary of the survey session."""
        species_list = self.get_merged_species_list()
        diversity = self.compute_diversity_indices()

        return {
            "session_id": self.session_id,
            "site_name": self.site_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "habitat_type": self.habitat_type,
            "observer": self.observer,
            "total_images": len(self.image_records),
            "blank_images": sum(1 for r in self.image_records if r.get("is_blank")),
            "total_audio": len(self.audio_records),
            "total_manual": len(self.manual_records),
            "total_species": len(species_list),
            "diversity": diversity,
            "species_list": species_list,
        }

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "site_name": self.site_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "habitat_type": self.habitat_type,
            "observer": self.observer,
            "notes": self.notes,
            "created_at": self.created_at,
            "image_records": self.image_records,
            "audio_records": self.audio_records,
            "manual_records": self.manual_records,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SurveySession":
        session = cls(
            session_id=data.get("session_id", ""),
            site_name=data.get("site_name", ""),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            habitat_type=data.get("habitat_type", ""),
            observer=data.get("observer", ""),
            notes=data.get("notes", ""),
        )
        session.created_at = data.get("created_at", session.created_at)
        session.image_records = data.get("image_records", [])
        session.audio_records = data.get("audio_records", [])
        session.manual_records = data.get("manual_records", [])
        return session


class SurveyStore:
    """Persistent storage for multimodal survey sessions."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: SurveySession) -> str:
        path = self.data_dir / f"{session.session_id}.json"
        path.write_text(
            json.dumps(session.to_dict(), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return str(path)

    def load(self, session_id: str) -> Optional[SurveySession]:
        path = self.data_dir / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return SurveySession.from_dict(data)

    def list_sessions(self) -> list[dict]:
        sessions = []
        for f in sorted(self.data_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append({
                    "session_id": data.get("session_id"),
                    "site_name": data.get("site_name"),
                    "start_time": data.get("start_time"),
                    "end_time": data.get("end_time"),
                    "total_images": len(data.get("image_records", [])),
                    "total_audio": len(data.get("audio_records", [])),
                    "total_manual": len(data.get("manual_records", [])),
                    "observer": data.get("observer"),
                })
            except Exception:
                continue
        return sessions

    def delete(self, session_id: str) -> bool:
        path = self.data_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False


def batch_import_camera_trap(
    directory: str,
    session: SurveySession,
    analyze_fn=None,
    extensions: tuple = (".jpg", ".jpeg", ".png", ".heic"),
) -> dict:
    """Batch import camera trap photos from a directory.

    Scans for image files, extracts EXIF metadata, and optionally runs
    AI classification on each image.

    Args:
        directory: Path to directory with camera trap photos.
        session: SurveySession to add records to.
        analyze_fn: Optional callable(file_path) -> dict with classification.
        extensions: Image file extensions to scan.

    Returns:
        Import statistics.
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return {"error": f"Directory not found: {directory}"}

    stats = {"scanned": 0, "imported": 0, "blank": 0, "errors": 0}

    image_files = sorted(
        f for f in dir_path.rglob("*")
        if f.suffix.lower() in extensions and not f.name.startswith(".")
    )
    stats["scanned"] = len(image_files)

    for img_path in image_files:
        try:
            exif = _extract_exif(img_path)

            species_detected = []
            is_blank = False

            if analyze_fn:
                try:
                    result = analyze_fn(str(img_path))
                    species_detected = result.get("classification", [])
                    is_blank = result.get("is_blank", False)
                except Exception:
                    pass

            session.add_image_record(
                file_path=str(img_path),
                timestamp=exif.get("datetime"),
                latitude=exif.get("latitude"),
                longitude=exif.get("longitude"),
                camera_model=exif.get("camera_model", ""),
                species_detected=species_detected,
                is_blank=is_blank,
                exif=exif,
            )
            stats["imported"] += 1
            if is_blank:
                stats["blank"] += 1

        except Exception as e:
            logger.warning("Failed to import %s: %s", img_path, e)
            stats["errors"] += 1

    return stats


def batch_import_audio(
    directory: str,
    session: SurveySession,
    analyze_fn=None,
    soundscape_fn=None,
    extensions: tuple = (".wav", ".mp3", ".flac", ".ogg"),
) -> dict:
    """Batch import audio recordings from a directory.

    Args:
        directory: Path to directory with audio files.
        session: SurveySession to add records to.
        analyze_fn: Optional callable(file_path) -> dict with species detections.
        soundscape_fn: Optional callable(file_path) -> dict with acoustic indices.
        extensions: Audio file extensions to scan.

    Returns:
        Import statistics.
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return {"error": f"Directory not found: {directory}"}

    stats = {"scanned": 0, "imported": 0, "errors": 0}

    audio_files = sorted(
        f for f in dir_path.rglob("*")
        if f.suffix.lower() in extensions and not f.name.startswith(".")
    )
    stats["scanned"] = len(audio_files)

    for audio_path in audio_files:
        try:
            species_detected = []
            acoustic_indices = {}
            duration = 0

            try:
                import librosa
                y, sr = librosa.load(str(audio_path), sr=None, duration=300)
                duration = len(y) / sr
            except Exception:
                pass

            if analyze_fn:
                try:
                    result = analyze_fn(str(audio_path))
                    species_detected = result.get("detections", [])
                except Exception:
                    pass

            if soundscape_fn:
                try:
                    indices = soundscape_fn(str(audio_path))
                    acoustic_indices = indices.get("indices", {})
                except Exception:
                    pass

            timestamp = _extract_audio_timestamp(audio_path)

            session.add_audio_record(
                file_path=str(audio_path),
                timestamp=timestamp,
                duration_seconds=duration,
                species_detected=species_detected,
                acoustic_indices=acoustic_indices,
            )
            stats["imported"] += 1

        except Exception as e:
            logger.warning("Failed to import %s: %s", audio_path, e)
            stats["errors"] += 1

    return stats


def _extract_exif(image_path: Path) -> dict:
    """Extract EXIF metadata from an image file."""
    exif = {}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        img = Image.open(image_path)
        exif_data = img._getexif()
        if not exif_data:
            exif["width"], exif["height"] = img.size
            exif["format"] = img.format
            return exif

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, str(tag_id))
            if tag == "GPSInfo":
                gps = {}
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                    gps[gps_tag] = gps_value

                if "GPSLatitude" in gps and "GPSLongitude" in gps:
                    lat = _gps_to_decimal(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
                    lon = _gps_to_decimal(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))
                    exif["latitude"] = lat
                    exif["longitude"] = lon

                if "GPSAltitude" in gps:
                    try:
                        alt = float(gps["GPSAltitude"])
                        exif["altitude"] = alt
                    except (TypeError, ValueError):
                        pass

            elif tag == "DateTimeOriginal":
                exif["datetime"] = str(value)
            elif tag == "Model":
                exif["camera_model"] = str(value)
            elif tag == "Make":
                exif["camera_make"] = str(value)

        exif["width"], exif["height"] = img.size
        exif["format"] = img.format

    except Exception:
        pass

    return exif


def _gps_to_decimal(coord, ref) -> float:
    """Convert GPS coordinates from degrees/minutes/seconds to decimal."""
    try:
        degrees = float(coord[0])
        minutes = float(coord[1])
        seconds = float(coord[2])
        decimal = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, ValueError, IndexError):
        return 0.0


def _extract_audio_timestamp(audio_path: Path) -> Optional[str]:
    """Try to extract recording timestamp from filename or file metadata."""
    name = audio_path.stem
    import re
    patterns = [
        r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_]?(\d{2})",
        r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, name)
        if match:
            groups = match.groups()
            try:
                dt = datetime(
                    int(groups[0]), int(groups[1]), int(groups[2]),
                    int(groups[3]), int(groups[4]), int(groups[5]),
                )
                return dt.isoformat()
            except (ValueError, IndexError):
                pass

    import os
    mtime = os.path.getmtime(audio_path)
    return datetime.fromtimestamp(mtime, tz=UTC).isoformat()
