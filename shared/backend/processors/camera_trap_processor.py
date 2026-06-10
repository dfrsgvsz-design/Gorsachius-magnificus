"""
Camera Trap (Infrared) Image Processing Module.
Handles IR camera images: preprocessing, animal detection, and sequence grouping.
Designed for PIR-triggered camera traps with IR illumination.
"""

import io
import json
import base64
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from PIL import Image, ImageFilter, ImageEnhance, ExifTags

    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import numpy as np

    _NP_OK = True
except ImportError:
    _NP_OK = False

try:
    import torch
    import torchvision.transforms as T
    import torchvision.models.detection as det_models

    _TORCH_OK = True
except ImportError:
    _TORCH_OK = False


def preprocess_ir_image(image_bytes: bytes) -> Optional[bytes]:
    """Enhance infrared camera images for better visibility and detection.

    IR images are typically grayscale with low contrast. This pipeline:
    1. Converts to grayscale if needed
    2. Applies CLAHE-like contrast enhancement
    3. Reduces IR noise
    """
    if not _PIL_OK:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes))
        gray = img.convert("L")
        enhanced = ImageEnhance.Contrast(gray).enhance(1.8)
        enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.3)
        enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
        buf = io.BytesIO()
        enhanced.save(buf, format="JPEG", quality=90)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def create_ir_thumbnail(image_bytes: bytes, max_size: int = 400) -> Optional[str]:
    """Create a base64 thumbnail from an IR camera image with enhancement."""
    processed = preprocess_ir_image(image_bytes)
    if processed is None:
        return None
    try:
        img = Image.open(io.BytesIO(processed))
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")
    except Exception:
        return None


def extract_trap_metadata(image_bytes: bytes) -> dict:
    """Extract metadata from camera trap images including timestamp and GPS."""
    if not _PIL_OK:
        return {"error": "Pillow not installed"}
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        return {"error": str(e)}

    meta = {
        "width": img.width,
        "height": img.height,
        "is_grayscale": img.mode in ("L", "LA"),
        "is_ir": False,
        "latitude": None,
        "longitude": None,
        "datetime": None,
        "camera_model": None,
        "temperature": None,
    }

    if _NP_OK and img.mode in ("RGB", "RGBA"):
        arr = np.array(img.convert("RGB"))
        r_mean, g_mean, b_mean = (
            arr[:, :, 0].mean(),
            arr[:, :, 1].mean(),
            arr[:, :, 2].mean(),
        )
        rg_diff = abs(float(r_mean) - float(g_mean))
        rb_diff = abs(float(r_mean) - float(b_mean))
        meta["is_ir"] = rg_diff < 10 and rb_diff < 10 and float(r_mean) > 30
    elif img.mode in ("L", "LA"):
        meta["is_ir"] = True

    exif_data = img.getexif() if hasattr(img, "getexif") else {}
    for tag_id, value in exif_data.items():
        tag_name = ExifTags.TAGS.get(tag_id, "")
        if tag_name in ("DateTime", "DateTimeOriginal"):
            meta["datetime"] = str(value)
        elif tag_name == "Model":
            meta["camera_model"] = str(value)

    try:
        gps_info = (
            exif_data.get_ifd(ExifTags.IFD.GPSInfo)
            if hasattr(exif_data, "get_ifd")
            else {}
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
    except Exception:
        pass

    return meta


def _dms_to_decimal(dms, ref):
    try:
        d, m, s = float(dms[0]), float(dms[1]), float(dms[2])
        dec = d + m / 60 + s / 3600
        return round(-dec if ref in ("S", "W") else dec, 6)
    except (TypeError, IndexError, ValueError):
        return None


def detect_animals_basic(image_bytes: bytes, conf_threshold: float = 0.5) -> list:
    """Basic animal detection using Faster R-CNN pretrained on COCO.

    COCO categories include: bird(16), cat(17), dog(18), horse(19),
    sheep(20), cow(21), elephant(22), bear(23), zebra(24), giraffe(25).
    """
    if not _TORCH_OK or not _PIL_OK:
        return [{"note": "torch/torchvision not available for detection"}]
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        transform = T.Compose([T.ToTensor()])
        tensor = transform(img).unsqueeze(0)

        model = det_models.fasterrcnn_mobilenet_v3_large_fpn(
            weights=det_models.FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1
        )
        model.eval()

        with torch.no_grad():
            outputs = model(tensor)[0]

        coco_animal_ids = {
            16: "bird",
            17: "cat",
            18: "dog",
            19: "horse",
            20: "sheep",
            21: "cow",
            22: "elephant",
            23: "bear",
            24: "zebra",
            25: "giraffe",
        }

        detections = []
        for score, label, box in zip(
            outputs["scores"], outputs["labels"], outputs["boxes"]
        ):
            s = score.item()
            l = label.item()
            if s >= conf_threshold and l in coco_animal_ids:
                x1, y1, x2, y2 = box.tolist()
                detections.append(
                    {
                        "category": coco_animal_ids[l],
                        "confidence": round(s, 3),
                        "bbox": [round(x1), round(y1), round(x2), round(y2)],
                    }
                )
        return detections
    except Exception as e:
        return [{"note": f"Detection failed: {e}"}]


def group_sequences(records: list, max_gap_seconds: int = 60) -> list:
    """Group camera trap images into event sequences based on timestamp proximity."""
    if not records:
        return []
    sorted_records = sorted(records, key=lambda r: r.get("datetime") or "")
    sequences = []
    current_seq = [sorted_records[0]]

    for record in sorted_records[1:]:
        try:
            prev_dt = datetime.fromisoformat(current_seq[-1].get("datetime", ""))
            curr_dt = datetime.fromisoformat(record.get("datetime", ""))
            gap = abs((curr_dt - prev_dt).total_seconds())
            if gap <= max_gap_seconds:
                current_seq.append(record)
            else:
                sequences.append(current_seq)
                current_seq = [record]
        except (ValueError, TypeError):
            sequences.append(current_seq)
            current_seq = [record]

    if current_seq:
        sequences.append(current_seq)

    return [
        {
            "sequence_id": i + 1,
            "count": len(seq),
            "start_time": seq[0].get("datetime"),
            "end_time": seq[-1].get("datetime"),
            "records": seq,
        }
        for i, seq in enumerate(sequences)
    ]
