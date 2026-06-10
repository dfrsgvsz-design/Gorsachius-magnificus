"""
Embedding-based lightweight classifier for bioacoustic species identification.

Uses pre-trained CNN backbone (or BirdNET / Perch) as a feature extractor,
then trains a lightweight classifier (logistic regression or MLP) on the
extracted embeddings. This approach achieves strong performance with very
limited labeled data (as few as 3-5 samples per species).

References:
- Ghani et al. (2025): 1-shot pipeline using BirdNET/Perch embeddings
- Lostanlen et al. (2024): Embedding-based bird sound retrieval
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

CLASSIFIER_DIR = Path(__file__).parent / "data" / "embedding_classifiers"


class EmbeddingClassifier:
    """Train and run lightweight classifiers on pre-extracted embeddings."""

    def __init__(self, embedding_engine=None, audio_processor=None):
        self.embedding_engine = embedding_engine
        self.audio_processor = audio_processor
        CLASSIFIER_DIR.mkdir(parents=True, exist_ok=True)

    def extract_embeddings_from_manifest(
        self,
        manifest_path: str,
        max_per_species: int = 50,
    ) -> dict:
        """Extract embeddings from a training manifest.

        Returns dict with 'embeddings' (N x D), 'labels' (N,), 'species_map'.
        """
        manifest_path = Path(manifest_path)
        if not manifest_path.exists():
            return {"error": f"Manifest not found: {manifest_path}"}

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        from collections import Counter, defaultdict
        species_files = defaultdict(list)
        for entry in manifest:
            sp = entry.get("species_scientific", "")
            fp = entry.get("file_path", "")
            if sp and fp:
                species_files[sp].append(fp)

        all_embeddings = []
        all_labels = []
        species_list = sorted(species_files.keys())
        species_to_idx = {sp: i for i, sp in enumerate(species_list)}
        skipped = 0

        for sp in species_list:
            files = species_files[sp][:max_per_species]
            for fp in files:
                emb = self._extract_from_file(fp)
                if emb is not None:
                    all_embeddings.append(emb)
                    all_labels.append(species_to_idx[sp])
                else:
                    skipped += 1

        if not all_embeddings:
            return {"error": "No embeddings extracted", "skipped": skipped}

        embeddings = np.stack(all_embeddings)
        labels = np.array(all_labels)

        logger.info(
            "Extracted %d embeddings for %d species (skipped %d files)",
            len(embeddings), len(species_list), skipped,
        )

        return {
            "embeddings": embeddings,
            "labels": labels,
            "species_map": {i: sp for sp, i in species_to_idx.items()},
            "species_list": species_list,
            "total_samples": len(embeddings),
            "skipped": skipped,
        }

    def train_logistic(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray,
        species_map: dict,
        classifier_name: str = "default",
        C: float = 1.0,
        max_iter: int = 1000,
    ) -> dict:
        """Train a logistic regression classifier on embeddings."""
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(embeddings)

        clf = LogisticRegression(
            C=C,
            max_iter=max_iter,
            solver="lbfgs",
            multi_class="multinomial",
            class_weight="balanced",
            random_state=42,
        )

        n_classes = len(set(labels))
        if len(labels) >= 10 and n_classes >= 2:
            cv_folds = min(5, min(np.bincount(labels)))
            cv_folds = max(2, cv_folds)
            scores = cross_val_score(clf, X_scaled, labels, cv=cv_folds, scoring="accuracy")
            cv_accuracy = float(scores.mean())
            cv_std = float(scores.std())
        else:
            cv_accuracy = None
            cv_std = None

        clf.fit(X_scaled, labels)
        train_accuracy = float(clf.score(X_scaled, labels))

        save_dir = CLASSIFIER_DIR / classifier_name
        save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / "classifier.pkl", "wb") as f:
            pickle.dump(clf, f)
        with open(save_dir / "scaler.pkl", "wb") as f:
            pickle.dump(scaler, f)

        meta = {
            "name": classifier_name,
            "type": "logistic_regression",
            "n_species": n_classes,
            "n_samples": len(labels),
            "embedding_dim": embeddings.shape[1],
            "train_accuracy": train_accuracy,
            "cv_accuracy": cv_accuracy,
            "cv_std": cv_std,
            "species_map": {str(k): v for k, v in species_map.items()},
            "C": C,
        }
        (save_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8",
        )

        logger.info(
            "Trained logistic classifier '%s': train_acc=%.3f, cv_acc=%s",
            classifier_name, train_accuracy,
            f"{cv_accuracy:.3f}±{cv_std:.3f}" if cv_accuracy else "N/A",
        )
        return meta

    def train_mlp(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray,
        species_map: dict,
        classifier_name: str = "default_mlp",
        hidden_layers: tuple = (256, 128),
        max_iter: int = 500,
    ) -> dict:
        """Train a small MLP classifier on embeddings."""
        from sklearn.neural_network import MLPClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(embeddings)

        clf = MLPClassifier(
            hidden_layer_sizes=hidden_layers,
            activation="relu",
            solver="adam",
            max_iter=max_iter,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
        )

        n_classes = len(set(labels))
        if len(labels) >= 10 and n_classes >= 2:
            cv_folds = min(5, min(np.bincount(labels)))
            cv_folds = max(2, cv_folds)
            scores = cross_val_score(clf, X_scaled, labels, cv=cv_folds, scoring="accuracy")
            cv_accuracy = float(scores.mean())
            cv_std = float(scores.std())
        else:
            cv_accuracy = None
            cv_std = None

        clf.fit(X_scaled, labels)
        train_accuracy = float(clf.score(X_scaled, labels))

        save_dir = CLASSIFIER_DIR / classifier_name
        save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / "classifier.pkl", "wb") as f:
            pickle.dump(clf, f)
        with open(save_dir / "scaler.pkl", "wb") as f:
            pickle.dump(scaler, f)

        meta = {
            "name": classifier_name,
            "type": "mlp",
            "n_species": n_classes,
            "n_samples": len(labels),
            "embedding_dim": embeddings.shape[1],
            "hidden_layers": list(hidden_layers),
            "train_accuracy": train_accuracy,
            "cv_accuracy": cv_accuracy,
            "cv_std": cv_std,
            "species_map": {str(k): v for k, v in species_map.items()},
        }
        (save_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8",
        )

        logger.info(
            "Trained MLP classifier '%s': train_acc=%.3f, cv_acc=%s",
            classifier_name, train_accuracy,
            f"{cv_accuracy:.3f}±{cv_std:.3f}" if cv_accuracy else "N/A",
        )
        return meta

    def predict(
        self,
        embedding: np.ndarray,
        classifier_name: str = "default",
        top_k: int = 5,
    ) -> list[dict]:
        """Predict species from a single embedding vector."""
        save_dir = CLASSIFIER_DIR / classifier_name
        if not save_dir.exists():
            return []

        with open(save_dir / "classifier.pkl", "rb") as f:
            clf = pickle.load(f)
        with open(save_dir / "scaler.pkl", "rb") as f:
            scaler = pickle.load(f)
        meta = json.loads((save_dir / "meta.json").read_text(encoding="utf-8"))
        species_map = meta.get("species_map", {})

        X = scaler.transform(embedding.reshape(1, -1))
        probas = clf.predict_proba(X)[0]

        top_indices = np.argsort(probas)[::-1][:top_k]
        results = []
        for idx in top_indices:
            sp = species_map.get(str(idx), f"class_{idx}")
            results.append({
                "species": sp,
                "confidence": float(probas[idx]),
                "class_index": int(idx),
            })
        return results

    def predict_from_audio(
        self,
        audio_bytes: bytes,
        classifier_name: str = "default",
        top_k: int = 5,
    ) -> list[dict]:
        """Full pipeline: audio bytes → embedding → prediction."""
        emb = self._extract_from_bytes(audio_bytes)
        if emb is None:
            return []
        return self.predict(emb, classifier_name, top_k)

    def list_classifiers(self) -> list[dict]:
        """List all saved classifiers."""
        classifiers = []
        if not CLASSIFIER_DIR.exists():
            return classifiers
        for d in sorted(CLASSIFIER_DIR.iterdir()):
            meta_path = d / "meta.json"
            if meta_path.exists():
                classifiers.append(json.loads(meta_path.read_text(encoding="utf-8")))
        return classifiers

    def _extract_from_file(self, file_path: str) -> Optional[np.ndarray]:
        """Extract embedding from an audio file."""
        fp = Path(file_path)
        if not fp.exists():
            return None
        try:
            audio_bytes = fp.read_bytes()
            return self._extract_from_bytes(audio_bytes)
        except Exception:
            logger.debug("Failed to extract embedding from %s", file_path, exc_info=True)
            return None

    def _extract_from_bytes(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """Extract embedding from raw audio bytes using the CNN backbone."""
        if self.embedding_engine is None:
            return None

        try:
            from audio_processor import process_audio_for_inference
            segments = process_audio_for_inference(audio_bytes)
            if not segments:
                return None

            mel, _ = segments[0]
            is_dual = mel.ndim == 3 and mel.shape[0] == 2
            emb = self.embedding_engine.extract_embedding(mel, is_dual_channel=is_dual)
            return emb
        except Exception:
            logger.debug("Embedding extraction failed", exc_info=True)
            return None
