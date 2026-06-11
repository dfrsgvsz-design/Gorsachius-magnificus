"""Algo-D / P2-W3 :: CNN inference fallback (BirdNET embedding + KNN, then
BirdNET classifier, then graceful empty).

This module is intentionally side-effect-free at import time: nothing here
loads heavy models until the first ``predict_species_fallback`` call. That
means ``import inference_fallback`` is always safe in main.py at process
start, even on machines without the ``birdnet`` / ``birdnetlib`` packages.

Public surface
--------------
- :func:`tiers_status` -> dict             # which tiers are actually usable now
- :func:`is_available` -> bool             # True if any tier loaded
- :func:`predict_species_fallback`         # drop-in replacement for predict_species
- :func:`safe_predict_species`             # wrap the main CNN call with try/fallback

Tier-1 path (preferred): BirdNET 1024-dim embedding + cosine-kNN on our own
labeled audio. Index files live in ``backend/checkpoints/birdnet_knn/`` and
are produced by ``scripts/algo_d/build_birdnet_knn_index.py``.

Tier-2 path (fallback of fallback): ``shared.backend.engines.birdnet_engine``
``predict_from_file`` -- BirdNET's bundled 6522-class classifier.

If neither tier is wired, ``predict_species_fallback`` returns ``[]`` with
``_meta.fallback_engine = "none"`` so the caller can still distinguish "no
prediction" from "exception bubbled up".

Return shape: see docs/algo_d/2026-06-10_inference_fallback_design.md :: \xa74.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent
KNN_INDEX_DIR = _BACKEND_DIR / "checkpoints" / "birdnet_knn"
EXPLICIT_FALLBACK_PATH = _BACKEND_DIR / "checkpoints" / "explicit_fallback_species.json"

KNN_DEFAULT_K = 7
KNN_DEFAULT_DISTANCE = "cosine"
RELIABLE_CONFIDENCE_THRESHOLD = 0.30  # match main predict_species threshold
KNN_RELIABLE_TOP1_RATIO = 0.5         # top-1 must hold > half the votes


_explicit_fallback_cache: list[str] | None = None


def explicit_fallback_species() -> list[str]:
    """Read scripts/algo_d/trim_species_mapping_to_head.py output sidecar.

    Returns the list of scientific names that are *deliberately* not in
    the trimmed mapping (because the CNN head cannot output them) and
    therefore must be served via BirdNET when the audio actually contains
    them. Empty list if no sidecar exists (no proactive routing in effect).
    """
    global _explicit_fallback_cache
    if _explicit_fallback_cache is not None:
        return _explicit_fallback_cache
    if not EXPLICIT_FALLBACK_PATH.exists():
        _explicit_fallback_cache = []
        return _explicit_fallback_cache
    try:
        doc = json.loads(EXPLICIT_FALLBACK_PATH.read_text(encoding="utf-8"))
        species = [
            str(item.get("scientific_name", "")).strip()
            for item in doc.get("species", [])
            if isinstance(item, dict) and item.get("scientific_name")
        ]
        _explicit_fallback_cache = [s for s in species if s]
        logger.info(
            "[inference_fallback] explicit fallback species loaded: %d entries from %s",
            len(_explicit_fallback_cache), EXPLICIT_FALLBACK_PATH.name,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("[inference_fallback] failed to read explicit fallback sidecar: %s", exc)
        _explicit_fallback_cache = []
    return _explicit_fallback_cache


def proactive_predict_for_explicit_species(
    audio_path: str,
    *,
    top_k: int = 5,
    chinese_lookup=None,
    english_lookup=None,
) -> list[dict]:
    """Run a BirdNET-side prediction and filter to only the explicit-fallback
    species. Used by ``safe_predict_species`` after the main CNN runs so the
    6 species that were trimmed off the mapping can still be detected.

    Returns up to ``top_k`` rows in the same shape as ``predict_species``;
    ``_meta`` carries ``fallback_engine = "birdnet_*"`` and
    ``fallback_reason = "explicit_routing"``.
    Empty list if no explicit species were predicted.
    """
    allowed = set(explicit_fallback_species())
    if not allowed:
        return []
    raw = predict_species_fallback(
        audio_path,
        top_k=top_k * 4,   # over-request, then filter
        reason="explicit_routing",
        chinese_lookup=chinese_lookup,
        english_lookup=english_lookup,
    )
    if not raw or (raw and raw[0].get("_meta", {}).get("fallback_engine") == "none"):
        return []
    filtered = [r for r in raw if r.get("species_scientific") in allowed]
    if not filtered:
        return []
    # carry the _meta block from the first row, but mark explicit
    meta = dict(filtered[0].get("_meta", {})) if isinstance(filtered[0].get("_meta"), dict) else {}
    meta.update({"fallback_reason": "explicit_routing"})
    out = []
    for r in filtered[:top_k]:
        row = {k: v for k, v in r.items() if k != "_meta"}
        out.append(row)
    if out:
        out[0]["_meta"] = meta
    return out


# ─────────────────────────── KNN INDEX (Tier-1) ──────────────────────────

class _BirdnetKnnIndex:
    """Singleton lazy-loaded numpy-backed cosine KNN index."""

    _embeddings = None       # ndarray (N, 1024) float32, L2-normalized
    _labels = None           # ndarray (N,) int32 -> species idx
    _idx_to_species: dict[int, str] = {}
    _species_to_chinese: dict[str, str] = {}
    _species_to_english: dict[str, str] = {}
    _meta: dict[str, Any] = {}
    _load_attempted = False
    _load_error: str | None = None

    @classmethod
    def status(cls) -> dict[str, Any]:
        return {
            "available": cls._embeddings is not None,
            "load_attempted": cls._load_attempted,
            "load_error": cls._load_error,
            "n_embeddings": int(cls._embeddings.shape[0]) if cls._embeddings is not None else 0,
            "dim": int(cls._embeddings.shape[1]) if cls._embeddings is not None else 0,
            "n_species": len(cls._idx_to_species),
            "index_dir": str(KNN_INDEX_DIR),
            "meta": cls._meta,
        }

    @classmethod
    def is_available(cls) -> bool:
        cls._ensure_loaded()
        return cls._embeddings is not None

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._load_attempted:
            return
        cls._load_attempted = True
        emb_path = KNN_INDEX_DIR / "embeddings.npy"
        lbl_path = KNN_INDEX_DIR / "labels.npy"
        mapping_path = KNN_INDEX_DIR / "species_mapping.json"
        meta_path = KNN_INDEX_DIR / "index_meta.json"
        if not (emb_path.exists() and lbl_path.exists() and mapping_path.exists()):
            cls._load_error = (
                f"KNN index files missing under {KNN_INDEX_DIR}; "
                "run scripts/algo_d/build_birdnet_knn_index.py once."
            )
            logger.info("[inference_fallback] tier-1 KNN not loaded: %s", cls._load_error)
            return
        try:
            import numpy as np  # noqa: WPS433  (deferred import keeps module import cheap)

            cls._embeddings = np.load(emb_path).astype(np.float32, copy=False)
            cls._labels = np.load(lbl_path).astype(np.int32, copy=False)
            # L2-normalize so cosine sim = dot product.
            norms = np.linalg.norm(cls._embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            cls._embeddings = cls._embeddings / norms
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
            cls._idx_to_species = {int(k): v for k, v in mapping.get("idx_to_species", {}).items()}
            if meta_path.exists():
                cls._meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover (rare)
            cls._embeddings = None
            cls._labels = None
            cls._load_error = f"{type(exc).__name__}: {exc}"
            logger.warning("[inference_fallback] tier-1 KNN load failed: %s", cls._load_error)

    @classmethod
    def topk_species(cls, query_embeddings, *, k: int, top_k: int) -> list[dict]:
        """Aggregate KNN votes across all chunks in `query_embeddings`.

        Each chunk casts `k` weighted votes (weight = cosine similarity).
        Sum weights per species across all chunks, then return top_k.
        """
        cls._ensure_loaded()
        if cls._embeddings is None or cls._labels is None:
            return []
        import numpy as np

        # Normalize query (L2)
        q = np.asarray(query_embeddings, dtype=np.float32)
        if q.ndim == 1:
            q = q[None, :]
        q_norms = np.linalg.norm(q, axis=1, keepdims=True)
        q_norms[q_norms == 0] = 1.0
        q = q / q_norms

        # Cosine sims = q @ E.T  (Mx1024 @ 1024xN -> MxN)
        sims = q @ cls._embeddings.T  # type: ignore[operator]
        # Per-row top-k indices (argpartition then sort by similarity)
        votes: dict[int, list[float]] = {}
        for row in sims:
            if row.shape[0] <= k:
                top_idx = np.argsort(-row)
            else:
                top_idx_unsorted = np.argpartition(-row, k)[:k]
                top_idx = top_idx_unsorted[np.argsort(-row[top_idx_unsorted])]
            for j in top_idx[:k]:
                lbl = int(cls._labels[j])
                votes.setdefault(lbl, []).append(float(row[j]))

        # Aggregate per species: total weight and vote count
        scored = []
        total_votes = sum(len(v) for v in votes.values()) or 1
        for sp_idx, weights in votes.items():
            sp = cls._idx_to_species.get(sp_idx, "Unknown")
            scored.append({
                "species_idx": sp_idx,
                "species_scientific": sp,
                "confidence": float(sum(weights) / max(len(weights), 1)),
                "vote_count": len(weights),
                "vote_share": len(weights) / total_votes,
            })
        scored.sort(key=lambda r: (-r["confidence"], -r["vote_count"]))
        return scored[:top_k]


# ─────────────────────────── BirdNET EMBEDDING (Tier-1 input) ─────────────

class _BirdnetEmbedder:
    """Wraps backend.birdnet_embeddings.BirdNETEmbeddingEngine with safe defer."""

    _engine = None
    _attempted = False
    _error: str | None = None

    @classmethod
    def status(cls) -> dict[str, Any]:
        return {
            "loaded": cls._engine is not None,
            "load_attempted": cls._attempted,
            "load_error": cls._error,
        }

    @classmethod
    def ensure(cls):
        if cls._engine is not None or cls._attempted:
            return cls._engine
        cls._attempted = True
        try:
            from birdnet_embeddings import BirdNETEmbeddingEngine  # type: ignore

            cls._engine = BirdNETEmbeddingEngine()
            if not cls._engine.available:
                cls._error = "birdnet package not installed"
                cls._engine = None
        except Exception as exc:  # pragma: no cover
            cls._error = f"{type(exc).__name__}: {exc}"
        if cls._error:
            logger.info("[inference_fallback] tier-1 BirdNET embedder unavailable: %s", cls._error)
        return cls._engine

    @classmethod
    def extract(cls, audio_path: str):
        eng = cls.ensure()
        if eng is None:
            return []
        try:
            chunks = eng.extract_embeddings(audio_path)
        except Exception as exc:  # pragma: no cover
            logger.warning("[inference_fallback] BirdNET extract failed: %s", exc)
            return []
        return [c.get("embedding") for c in chunks if isinstance(c, dict) and "embedding" in c]


# ─────────────────────────── TIER-2 (BirdNET classifier) ───────────────────

class _BirdnetClassifier:
    """Wraps shared.backend.engines.birdnet_engine.predict_from_file."""

    @classmethod
    def status(cls) -> dict[str, Any]:
        try:
            from shared.backend.engines import birdnet_engine  # type: ignore

            return {"available": bool(birdnet_engine.is_available())}
        except Exception as exc:  # pragma: no cover
            return {"available": False, "load_error": str(exc)}

    @classmethod
    def predict(cls, audio_path: str, *, top_k: int, min_conf: float = 0.1) -> list[dict]:
        try:
            from shared.backend.engines import birdnet_engine  # type: ignore

            return birdnet_engine.predict_from_file(audio_path, top_k=top_k, min_conf=min_conf) or []
        except Exception as exc:  # pragma: no cover
            logger.warning("[inference_fallback] tier-2 BirdNET classifier failed: %s", exc)
            return []


# ─────────────────────────── PUBLIC SURFACE ──────────────────────────────

def tiers_status() -> dict[str, Any]:
    """Snapshot of what each fallback tier looks like right now (lazy probe)."""
    return {
        "tier1_birdnet_embedding": _BirdnetEmbedder.status(),
        "tier1_knn_index": _BirdnetKnnIndex.status(),
        "tier2_birdnet_classifier": _BirdnetClassifier.status(),
    }


def is_available() -> bool:
    s = tiers_status()
    return bool(
        (s["tier1_birdnet_embedding"]["loaded"] and s["tier1_knn_index"]["available"])
        or s["tier2_birdnet_classifier"].get("available")
    )


def _canonical_row(
    *,
    scientific: str,
    confidence: float,
    reliable: bool,
    chinese_lookup: Callable[[str], str] | None = None,
    english_lookup: Callable[[str], str] | None = None,
) -> dict:
    return {
        "species_scientific": scientific,
        "species_chinese": chinese_lookup(scientific) if chinese_lookup else "",
        "species_english": english_lookup(scientific) if english_lookup else "",
        "confidence": float(round(confidence, 4)),
        "reliable": bool(reliable),
    }


def predict_species_fallback(
    audio_path: str,
    *,
    top_k: int = 5,
    reason: str = "unknown",
    knn_k: int = KNN_DEFAULT_K,
    chinese_lookup: Callable[[str], str] | None = None,
    english_lookup: Callable[[str], str] | None = None,
) -> list[dict]:
    """Drop-in replacement for predict_species. Returns same shape (see doc \xa74)."""
    # ---- Tier 1: BirdNET embedding + KNN ----
    embeddings = _BirdnetEmbedder.extract(audio_path)
    if embeddings and _BirdnetKnnIndex.is_available():
        scored = _BirdnetKnnIndex.topk_species(embeddings, k=knn_k, top_k=top_k)
        if scored:
            results = []
            total_chunks = max(len(embeddings), 1)
            for row in scored:
                conf = row["confidence"]
                # KNN-side reliability: confidence above threshold AND vote share dominant
                reliable = (
                    conf > RELIABLE_CONFIDENCE_THRESHOLD
                    and row["vote_share"] > (KNN_RELIABLE_TOP1_RATIO / total_chunks)
                )
                results.append(_canonical_row(
                    scientific=row["species_scientific"],
                    confidence=conf,
                    reliable=reliable,
                    chinese_lookup=chinese_lookup,
                    english_lookup=english_lookup,
                ))
            if results:
                results[0]["_meta"] = {
                    "fallback_engine": "birdnet_embedding_knn",
                    "fallback_reason": reason,
                    "knn_k": knn_k,
                    "voting": "weighted_cosine",
                    "n_chunks": total_chunks,
                    "model_version": "birdnet-2.4-knn",
                    "temperature": None,
                    "ensemble": False,
                    "write_back": False,
                }
            logger.warning(
                "[inference_fallback] tier-1 served prediction for %s (reason=%s, top1=%s, conf=%.3f)",
                audio_path, reason, results[0]["species_scientific"], results[0]["confidence"],
            )
            return results

    # ---- Tier 2: BirdNET bundled classifier ----
    tier2_results = _BirdnetClassifier.predict(audio_path, top_k=top_k)
    if tier2_results:
        normalized = []
        for det in tier2_results:
            sci = det.get("scientific_name") or det.get("species_scientific") or ""
            if not sci:
                continue
            normalized.append(_canonical_row(
                scientific=sci,
                confidence=float(det.get("confidence", 0.0) or 0.0),
                reliable=bool(det.get("confidence", 0.0) and det["confidence"] > 0.5),
                chinese_lookup=chinese_lookup,
                english_lookup=english_lookup,
            ))
        if normalized:
            normalized[0]["_meta"] = {
                "fallback_engine": "birdnet_classifier",
                "fallback_reason": reason,
                "model_version": "birdnetlib",
                "temperature": None,
                "ensemble": False,
                "write_back": False,
            }
            logger.warning(
                "[inference_fallback] tier-2 served prediction for %s (reason=%s, top1=%s)",
                audio_path, reason, normalized[0]["species_scientific"],
            )
            return normalized

    # ---- No tier could serve ----
    logger.error(
        "[inference_fallback] no fallback tier could serve %s (reason=%s, status=%s)",
        audio_path, reason, tiers_status(),
    )
    return [{
        "species_scientific": "",
        "species_chinese": "",
        "species_english": "",
        "confidence": 0.0,
        "reliable": False,
        "_meta": {
            "fallback_engine": "none",
            "fallback_reason": reason,
            "model_version": None,
            "temperature": None,
            "ensemble": False,
            "write_back": False,
        },
    }]


# ─────────────────────────── safe_predict_species wrapper ────────────────

def _is_oom_error(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "outofmemory" in name or "outofmemoryerror" in name:
        return True
    return any(token in msg for token in ("out of memory", "oom", "cuda error", "cudnn"))


def safe_predict_species(
    *,
    primary: Callable[..., list[dict]],
    primary_kwargs: dict[str, Any],
    audio_path: str,
    top_k: int = 5,
    chinese_lookup: Callable[[str], str] | None = None,
    english_lookup: Callable[[str], str] | None = None,
) -> list[dict]:
    """Run the CNN primary; on failure fall back to BirdNET-based path."""
    try:
        return primary(**primary_kwargs)
    except Exception as exc:  # noqa: BLE001 - intentional broad catch for safety
        reason = "out_of_memory" if _is_oom_error(exc) else "runtime_error"
        if isinstance(exc, FileNotFoundError):
            reason = "no_model"
        logger.warning(
            "[inference_fallback] primary CNN failed (%s: %s); reason=%s; falling back",
            type(exc).__name__, exc, reason,
        )
        return predict_species_fallback(
            audio_path,
            top_k=top_k,
            reason=reason,
            chinese_lookup=chinese_lookup,
            english_lookup=english_lookup,
        )
