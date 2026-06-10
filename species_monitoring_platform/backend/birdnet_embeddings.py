"""
BirdNET Embedding Extraction & Lightweight Classifier Integration

Uses the official BirdNET model (birdnet package) as a frozen feature
extractor. Extracts 1024-dim embedding vectors from audio, then trains
a lightweight classifier (logistic regression / MLP) on top.

This approach allows:
- 6,522 species coverage from day one (BirdNET's pre-trained knowledge)
- Custom species fine-tuning with just 3-5 recordings per species
- No GPU required for training the classifier layer
- Sub-second inference on CPU

Installation: pip install birdnet scikit-learn
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

CLASSIFIER_DIR = Path(__file__).parent / "data" / "birdnet_classifiers"
CLASSIFIER_DIR.mkdir(parents=True, exist_ok=True)


class BirdNETEmbeddingEngine:
    """Extract embeddings from audio using BirdNET's pre-trained model."""

    def __init__(self):
        self._model = None
        self._available = None

    @property
    def available(self) -> bool:
        if self._available is None:
            try:
                import birdnet
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def _ensure_model(self):
        if self._model is not None:
            return
        if not self.available:
            raise ImportError(
                "birdnet package not installed. Run: pip install birdnet"
            )
        import birdnet
        self._model = birdnet.load("acoustic", "2.4", "tf")
        logger.info(
            "BirdNET V2.4 loaded: %d species, %d-dim embeddings",
            self._model.n_species, self._model.get_embeddings_dim(),
        )

    def extract_embeddings(
        self,
        audio_path: str,
    ) -> list[dict]:
        """Extract 1024-dim embeddings from an audio file.

        Returns list of dicts with keys: embedding, time_start, time_end
        """
        self._ensure_model()

        results = []
        try:
            encoding_result = self._model.encode([audio_path])
            for chunk in encoding_result:
                emb = chunk["embedding"]
                results.append({
                    "embedding": np.array(emb, dtype=np.float32),
                    "time_start": float(chunk["start_time"]),
                    "time_end": float(chunk["end_time"]),
                })
        except Exception as e:
            logger.warning("BirdNET embedding extraction failed: %s", e)

        return results

    def extract_from_manifest(
        self,
        manifest_path: str,
        max_per_species: int = 50,
    ) -> dict:
        """Extract embeddings from all files in a training manifest.

        Returns dict with embeddings array, labels, species_map.
        """
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

        from collections import defaultdict
        species_files = defaultdict(list)
        for entry in manifest:
            sp = entry.get("species_scientific", "")
            fp = entry.get("file_path", "")
            if sp and fp and Path(fp).exists():
                species_files[sp].append(fp)

        species_list = sorted(species_files.keys())
        species_to_idx = {sp: i for i, sp in enumerate(species_list)}

        all_embeddings = []
        all_labels = []
        skipped = 0

        for sp in species_list:
            files = species_files[sp][:max_per_species]
            for fp in files:
                try:
                    chunks = self.extract_embeddings(fp)
                    if chunks:
                        emb = chunks[0]["embedding"]
                        all_embeddings.append(emb)
                        all_labels.append(species_to_idx[sp])
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1

        if not all_embeddings:
            return {"error": "No embeddings extracted", "skipped": skipped}

        return {
            "embeddings": np.stack(all_embeddings),
            "labels": np.array(all_labels),
            "species_map": {i: sp for sp, i in species_to_idx.items()},
            "species_list": species_list,
            "total_samples": len(all_embeddings),
            "embedding_dim": all_embeddings[0].shape[0],
            "skipped": skipped,
        }


class BirdNETClassifier:
    """Lightweight classifier trained on BirdNET embeddings."""

    def __init__(self, embedding_engine: Optional[BirdNETEmbeddingEngine] = None):
        self.engine = embedding_engine or BirdNETEmbeddingEngine()

    def train(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray,
        species_map: dict,
        name: str = "birdnet_default",
        method: str = "logistic",
    ) -> dict:
        """Train a classifier on pre-extracted embeddings.

        Args:
            method: 'logistic' or 'mlp'
        """
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import cross_val_score

        scaler = StandardScaler()
        X = scaler.fit_transform(embeddings)

        if method == "mlp":
            from sklearn.neural_network import MLPClassifier
            clf = MLPClassifier(
                hidden_layer_sizes=(256, 128),
                max_iter=500,
                early_stopping=True,
                random_state=42,
            )
        else:
            from sklearn.linear_model import LogisticRegression
            clf = LogisticRegression(
                C=1.0,
                max_iter=1000,
                multi_class="multinomial",
                class_weight="balanced",
                random_state=42,
            )

        n_classes = len(set(labels))
        cv_acc = None
        if len(labels) >= 10 and n_classes >= 2:
            folds = min(5, min(np.bincount(labels)))
            folds = max(2, folds)
            scores = cross_val_score(clf, X, labels, cv=folds)
            cv_acc = float(scores.mean())

        clf.fit(X, labels)
        train_acc = float(clf.score(X, labels))

        save_dir = CLASSIFIER_DIR / name
        save_dir.mkdir(parents=True, exist_ok=True)
        with open(save_dir / "classifier.pkl", "wb") as f:
            pickle.dump(clf, f)
        with open(save_dir / "scaler.pkl", "wb") as f:
            pickle.dump(scaler, f)

        meta = {
            "name": name,
            "method": method,
            "n_species": n_classes,
            "n_samples": len(labels),
            "embedding_dim": int(embeddings.shape[1]),
            "train_accuracy": train_acc,
            "cv_accuracy": cv_acc,
            "species_map": {str(k): v for k, v in species_map.items()},
        }
        (save_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8",
        )

        logger.info(
            "BirdNET classifier '%s' trained: train=%.3f, cv=%s, species=%d",
            name, train_acc, f"{cv_acc:.3f}" if cv_acc else "N/A", n_classes,
        )
        return meta

    def predict(
        self,
        audio_path: str,
        classifier_name: str = "birdnet_default",
        top_k: int = 5,
    ) -> list[dict]:
        """Predict species from audio using BirdNET embeddings + trained classifier."""
        save_dir = CLASSIFIER_DIR / classifier_name
        if not save_dir.exists():
            return []

        with open(save_dir / "classifier.pkl", "rb") as f:
            clf = pickle.load(f)
        with open(save_dir / "scaler.pkl", "rb") as f:
            scaler = pickle.load(f)
        meta = json.loads((save_dir / "meta.json").read_text(encoding="utf-8"))
        species_map = meta.get("species_map", {})

        chunks = self.engine.extract_embeddings(audio_path)
        if not chunks:
            return []

        all_predictions = []
        for chunk in chunks:
            emb = chunk["embedding"].reshape(1, -1)
            X = scaler.transform(emb)
            probas = clf.predict_proba(X)[0]

            top_indices = np.argsort(probas)[::-1][:top_k]
            for idx in top_indices:
                sp = species_map.get(str(idx), f"class_{idx}")
                all_predictions.append({
                    "species": sp,
                    "confidence": float(probas[idx]),
                    "time_start": chunk.get("time_start", 0),
                    "time_end": chunk.get("time_end", 3.0),
                    "birdnet_species": chunk.get("top_species"),
                    "birdnet_confidence": chunk.get("top_confidence", 0),
                })

        all_predictions.sort(key=lambda x: -x["confidence"])
        return all_predictions[:top_k * 3]

    def list_classifiers(self) -> list[dict]:
        classifiers = []
        for d in sorted(CLASSIFIER_DIR.iterdir()):
            meta_path = d / "meta.json"
            if meta_path.exists():
                classifiers.append(json.loads(meta_path.read_text(encoding="utf-8")))
        return classifiers


def quick_setup_pipeline(
    manifest_path: str,
    classifier_name: str = "birdnet_v1",
    method: str = "logistic",
    max_per_species: int = 30,
) -> dict:
    """One-call pipeline: manifest → BirdNET embeddings → trained classifier.

    Usage:
        result = quick_setup_pipeline("data/training/manifest.json")
        # result contains classifier metadata and accuracy metrics
    """
    engine = BirdNETEmbeddingEngine()

    if not engine.available:
        return {
            "error": "BirdNET not installed",
            "install": "pip install birdnet",
        }

    logger.info("Step 1: Extracting BirdNET embeddings from manifest...")
    data = engine.extract_from_manifest(manifest_path, max_per_species)
    if "error" in data:
        return data

    logger.info(
        "Step 2: Training %s classifier on %d embeddings (%d species)...",
        method, data["total_samples"], len(data["species_list"]),
    )
    classifier = BirdNETClassifier(engine)
    meta = classifier.train(
        data["embeddings"],
        data["labels"],
        data["species_map"],
        name=classifier_name,
        method=method,
    )

    return {
        "status": "success",
        "classifier": meta,
        "data_summary": {
            "total_samples": data["total_samples"],
            "species_count": len(data["species_list"]),
            "embedding_dim": data["embedding_dim"],
            "skipped_files": data["skipped"],
        },
    }
