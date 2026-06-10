"""
Batch Import Module for Camera Trap and Audio Recorder SD Cards.
Scans directories, auto-classifies files, and links to device/site metadata.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

try:
    from PIL import Image, ExifTags

    _PIL_OK = True
except ImportError:
    _PIL_OK = False

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".heic", ".heif"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}


def scan_directory(root_path: str, recursive: bool = True) -> dict:
    """Scan a directory and classify files by type.

    Returns a summary with file counts and organized file lists.
    """
    root = Path(root_path)
    if not root.exists():
        return {"error": f"Directory not found: {root_path}"}

    result = {
        "root": str(root),
        "audio_files": [],
        "image_files": [],
        "video_files": [],
        "other_files": [],
        "total_size_mb": 0,
        "subdirectories": [],
    }

    iterator = root.rglob("*") if recursive else root.glob("*")
    for path in iterator:
        if path.is_dir():
            result["subdirectories"].append(str(path.relative_to(root)))
            continue
        if not path.is_file():
            continue

        ext = path.suffix.lower()
        size_mb = path.stat().st_size / (1024 * 1024)
        result["total_size_mb"] += size_mb

        entry = {
            "path": str(path),
            "name": path.name,
            "size_mb": round(size_mb, 2),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            "relative_path": str(path.relative_to(root)),
        }

        if ext in AUDIO_EXTENSIONS:
            entry["type"] = "audio"
            entry["format"] = ext[1:]
            result["audio_files"].append(entry)
        elif ext in IMAGE_EXTENSIONS:
            entry["type"] = "image"
            entry["format"] = ext[1:]
            if _PIL_OK:
                try:
                    with Image.open(path) as img:
                        entry["dimensions"] = f"{img.width}x{img.height}"
                        exif = img.getexif()
                        for tag_id, val in exif.items():
                            name = ExifTags.TAGS.get(tag_id, "")
                            if name == "Model":
                                entry["camera_model"] = str(val)
                            elif name in ("DateTime", "DateTimeOriginal"):
                                entry["capture_time"] = str(val)
                except Exception:
                    pass
            result["image_files"].append(entry)
        elif ext in VIDEO_EXTENSIONS:
            entry["type"] = "video"
            entry["format"] = ext[1:]
            result["video_files"].append(entry)
        else:
            entry["type"] = "other"
            result["other_files"].append(entry)

    result["total_size_mb"] = round(result["total_size_mb"], 1)
    result["summary"] = {
        "audio": len(result["audio_files"]),
        "image": len(result["image_files"]),
        "video": len(result["video_files"]),
        "other": len(result["other_files"]),
        "total": (
            len(result["audio_files"])
            + len(result["image_files"])
            + len(result["video_files"])
            + len(result["other_files"])
        ),
    }

    return result


def group_by_camera(files: List[dict]) -> Dict[str, list]:
    """Group files by camera model extracted from EXIF."""
    groups = {}
    for f in files:
        camera = f.get("camera_model", "unknown")
        groups.setdefault(camera, []).append(f)
    return groups


def group_by_date(files: List[dict]) -> Dict[str, list]:
    """Group files by date (from capture_time or modified)."""
    groups = {}
    for f in files:
        dt_str = f.get("capture_time") or f.get("modified", "")
        try:
            date = dt_str[:10]
        except (TypeError, IndexError):
            date = "unknown"
        groups.setdefault(date, []).append(f)
    return groups


def create_import_manifest(
    scan_result: dict,
    device_id: Optional[str] = None,
    site_name: Optional[str] = None,
    camera_serial: Optional[str] = None,
) -> dict:
    """Create an import manifest that can be used to batch-process files."""
    manifest = {
        "created_at": datetime.now().isoformat(),
        "device_id": device_id,
        "site_name": site_name,
        "camera_serial": camera_serial,
        "root_directory": scan_result.get("root", ""),
        "summary": scan_result.get("summary", {}),
        "total_size_mb": scan_result.get("total_size_mb", 0),
        "files_to_process": [],
    }

    for file_list in [
        scan_result.get("audio_files", []),
        scan_result.get("image_files", []),
    ]:
        for f in file_list:
            manifest["files_to_process"].append(
                {
                    "path": f["path"],
                    "type": f["type"],
                    "format": f.get("format", ""),
                    "size_mb": f.get("size_mb", 0),
                    "device_id": device_id,
                    "site_name": site_name,
                    "camera_serial": camera_serial or f.get("camera_model"),
                }
            )

    return manifest
