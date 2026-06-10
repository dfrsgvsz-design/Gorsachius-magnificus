"""
Bird Image Processing Module.
Extracts EXIF metadata (GPS, timestamp, camera) from uploaded photos
and provides a framework for visual species identification.
"""

import io
import json
import base64
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ExifTags

    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import torch
    import torchvision.transforms as T
    import torchvision.models as models

    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False


def _dms_to_decimal(dms, ref):
    """Convert EXIF GPS DMS tuple to decimal degrees."""
    try:
        degrees = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])
        decimal = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, IndexError, ValueError):
        return None


def extract_exif(image_bytes: bytes) -> dict:
    """Extract useful EXIF metadata from image bytes."""
    if not _PIL_OK:
        return {"error": "Pillow not installed"}
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        return {"error": f"Cannot open image: {e}"}

    meta = {
        "width": img.width,
        "height": img.height,
        "format": img.format,
        "mode": img.mode,
        "latitude": None,
        "longitude": None,
        "altitude": None,
        "datetime": None,
        "camera_make": None,
        "camera_model": None,
    }

    exif_data = img.getexif() if hasattr(img, "getexif") else {}
    tag_names = {v: k for k, v in ExifTags.TAGS.items()} if ExifTags else {}

    for tag_id, value in exif_data.items():
        tag_name = ExifTags.TAGS.get(tag_id, "")
        if tag_name == "DateTime":
            meta["datetime"] = str(value)
        elif tag_name == "Make":
            meta["camera_make"] = str(value)
        elif tag_name == "Model":
            meta["camera_model"] = str(value)
        elif tag_name == "DateTimeOriginal":
            meta["datetime"] = str(value)

    gps_info = (
        exif_data.get_ifd(ExifTags.IFD.GPSInfo) if hasattr(exif_data, "get_ifd") else {}
    )
    if gps_info:
        gps_tags = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_info.items()}
        lat_dms = gps_tags.get("GPSLatitude")
        lat_ref = gps_tags.get("GPSLatitudeRef", "N")
        lon_dms = gps_tags.get("GPSLongitude")
        lon_ref = gps_tags.get("GPSLongitudeRef", "E")
        if lat_dms and lon_dms:
            meta["latitude"] = _dms_to_decimal(lat_dms, lat_ref)
            meta["longitude"] = _dms_to_decimal(lon_dms, lon_ref)
        alt = gps_tags.get("GPSAltitude")
        if alt is not None:
            try:
                meta["altitude"] = round(float(alt), 1)
            except (TypeError, ValueError):
                pass

    return meta


def create_thumbnail(image_bytes: bytes, max_size: int = 400) -> Optional[str]:
    """Create a base64-encoded thumbnail from image bytes."""
    if not _PIL_OK:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")
    except Exception:
        return None


_IMAGE_TRANSFORMS = None
_IMAGE_MODEL = None
_IMAGENET_LABELS = None


def _ensure_classifier():
    """Lazily load a MobileNetV3 classifier for basic image classification."""
    global _IMAGE_MODEL, _IMAGE_TRANSFORMS, _IMAGENET_LABELS
    if _IMAGE_MODEL is not None:
        return True
    if not _TORCH_OK:
        return False
    try:
        weights = models.MobileNet_V3_Small_Weights.IMAGENET1K_V1
        _IMAGE_MODEL = models.mobilenet_v3_small(weights=weights)
        _IMAGE_MODEL.eval()
        _IMAGE_TRANSFORMS = weights.transforms()
        _IMAGENET_LABELS = weights.meta["categories"]
        return True
    except Exception:
        return False


def classify_image(image_bytes: bytes, top_k: int = 5) -> list:
    """Run ImageNet classification on an image (general-purpose, not bird-specific).

    Returns top-k predictions with labels and confidence scores.
    For dedicated bird classification, a fine-tuned model should replace this.
    """
    if not _ensure_classifier():
        return [
            {
                "label": "classifier_unavailable",
                "confidence": 0,
                "note": "Install torch + torchvision for image classification",
            }
        ]
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = _IMAGE_TRANSFORMS(img).unsqueeze(0)
        with torch.no_grad():
            logits = _IMAGE_MODEL(tensor)
        probs = torch.nn.functional.softmax(logits[0], dim=0)
        top_probs, top_indices = torch.topk(probs, min(top_k, len(probs)))
        results = []
        for prob, idx in zip(top_probs, top_indices):
            label = (
                _IMAGENET_LABELS[idx.item()]
                if _IMAGENET_LABELS
                else f"class_{idx.item()}"
            )
            results.append(
                {
                    "label": label,
                    "confidence": round(prob.item(), 4),
                    "is_bird_related": any(
                        kw in label.lower()
                        for kw in [
                            "bird",
                            "hen",
                            "rooster",
                            "cock",
                            "eagle",
                            "hawk",
                            "owl",
                            "parrot",
                            "penguin",
                            "flamingo",
                            "heron",
                            "crane",
                            "duck",
                            "goose",
                            "swan",
                            "robin",
                            "jay",
                            "magpie",
                            "finch",
                            "sparrow",
                            "warbler",
                            "woodpecker",
                            "kingfisher",
                            "pelican",
                            "albatross",
                            "quail",
                            "ostrich",
                            "vulture",
                            "kite",
                        ]
                    ),
                }
            )
        return results
    except Exception as e:
        return [{"label": "error", "confidence": 0, "note": str(e)}]
