"""Few-shot species detector using embedding similarity.

Creates detection pipelines for rare/endangered species using as few as
1-5 reference recordings, leveraging the embedding space from the main
CNN classifier for cosine-similarity matching.
"""

import json
import logging
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_DETECTORS_DIR = Path(__file__).parent / "data" / "fewshot_detectors"


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class FewShotDetector:
    """Manages few-shot detectors backed by embedding prototypes."""

    def __init__(self, embedding_engine=None, audio_processor=None):
        self.embedding_engine = embedding_engine
        self.audio_processor = audio_processor
        _DETECTORS_DIR.mkdir(parents=True, exist_ok=True)

    def create_detector(
        self,
        name: str,
        species: str,
        reference_embeddings: list[np.ndarray],
    ) -> dict:
        """Create a new few-shot detector from reference embeddings."""
        if not reference_embeddings:
            return {"error": "At least one reference embedding required"}

        prototype = np.mean(reference_embeddings, axis=0)
        detector_id = str(uuid.uuid4())[:12]

        meta = {
            "id": detector_id,
            "name": name,
            "species": species,
            "n_references": len(reference_embeddings),
            "created_at": datetime.now(UTC).isoformat(),
            "prototype_shape": list(prototype.shape),
        }

        det_dir = _DETECTORS_DIR / detector_id
        det_dir.mkdir(parents=True, exist_ok=True)
        np.save(det_dir / "prototype.npy", prototype)
        (det_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return meta

    def list_detectors(self) -> list:
        """List all saved few-shot detectors."""
        detectors = []
        for d in sorted(_DETECTORS_DIR.iterdir()):
            meta_path = d / "meta.json"
            if meta_path.exists():
                detectors.append(json.loads(meta_path.read_text(encoding="utf-8")))
        return detectors

    def get_detector(self, detector_id: str) -> Optional[dict]:
        meta_path = _DETECTORS_DIR / detector_id / "meta.json"
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def load_prototype(self, detector_id: str) -> Optional[np.ndarray]:
        path = _DETECTORS_DIR / detector_id / "prototype.npy"
        if not path.exists():
            return None
        return np.load(path)

    def delete_detector(self, detector_id: str) -> bool:
        det_dir = _DETECTORS_DIR / detector_id
        if not det_dir.exists():
            return False
        import shutil

        shutil.rmtree(det_dir)
        return True

    def scan_embeddings(
        self,
        detector_id: str,
        embeddings: list[dict],
        threshold: float = 0.85,
    ) -> list:
        """Scan a batch of embeddings against the detector prototype.

        Each item in *embeddings* should have keys:
          - "embedding": np.ndarray or list
          - "file": str (source file path)
          - "offset_sec": float (optional)
          - "detection_id": str (optional)
        """
        prototype = self.load_prototype(detector_id)
        if prototype is None:
            return []

        candidates = []
        for item in embeddings:
            emb = item.get("embedding")
            if emb is None:
                continue
            if isinstance(emb, list):
                emb = np.array(emb)
            sim = _cosine_similarity(prototype, emb)
            if sim >= threshold:
                candidates.append(
                    {
                        "file": item.get("file", ""),
                        "offset_sec": item.get("offset_sec", 0),
                        "detection_id": item.get("detection_id", ""),
                        "similarity": round(sim, 4),
                    }
                )

        candidates.sort(key=lambda c: c["similarity"], reverse=True)
        return candidates

    def extract_embedding_from_audio(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """Extract an embedding vector from raw audio bytes.

        Requires self.embedding_engine to be set (wraps the main CNN model's
        penultimate-layer output).
        """
        if self.embedding_engine is None:
            logger.warning("No embedding engine configured for few-shot detector")
            return None

        try:
            if self.audio_processor:
                import io

                wav = self.audio_processor.ensure_wav(io.BytesIO(audio_bytes))
                if wav is None:
                    return None
                audio_bytes = wav

            embedding = self.embedding_engine.extract_from_bytes(audio_bytes)
            return embedding
        except Exception:
            logger.warning("Failed to extract embedding from audio", exc_info=True)
            return None
