"""
Feature Embedding Engine — 基于 Sugai et al. (2026) Section 4.5 的推荐方向。

提取 CNN 特征嵌入用于:
- 无监督声学事件聚类（发现未知声音模式）
- 物种间声学相似度分析
- 个体识别基础（Lakdari et al., 2024; McGinn et al., 2023）
- 声学多样性的连续度量（区别于离散声学指数）

架构:
1. 使用训练好的 SE-ResNet backbone 提取 feature embeddings
2. UMAP/t-SNE 降维可视化
3. HDBSCAN 密度聚类发现未知声学模式
"""

import numpy as np
import torch
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmbeddingRecord:
    embedding: np.ndarray
    species_prediction: str
    confidence: float
    time_offset: float
    session_id: str
    device_id: str = ""
    cluster_id: int = -1
    is_verified: bool = False
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


class EmbeddingEngine:
    """Extract and manage feature embeddings from trained models."""

    def __init__(self, model=None, device=None):
        self._model = model
        self._device = device or torch.device("cpu")
        self._records: List[EmbeddingRecord] = []
        self._session_records: Dict[str, List[int]] = defaultdict(list)

    def set_model(self, model, device=None):
        self._model = model
        if device:
            self._device = device

    def extract_embedding(
        self, mel_spectrogram: np.ndarray, is_dual_channel: bool = False
    ) -> Optional[np.ndarray]:
        """Extract feature embedding from mel spectrogram using model backbone."""
        if self._model is None:
            return None

        if not hasattr(self._model, "extract_features"):
            return None

        if is_dual_channel:
            tensor = torch.FloatTensor(mel_spectrogram).unsqueeze(0).to(self._device)
        else:
            tensor = (
                torch.FloatTensor(mel_spectrogram)
                .unsqueeze(0)
                .unsqueeze(0)
                .to(self._device)
            )

        with torch.no_grad():
            features = self._model.extract_features(tensor)

        return features.cpu().numpy().flatten()

    def add_record(
        self,
        embedding: np.ndarray,
        species_prediction: str,
        confidence: float,
        time_offset: float,
        session_id: str,
        device_id: str = "",
    ) -> int:
        """Store an embedding record. Returns record index."""
        record = EmbeddingRecord(
            embedding=embedding,
            species_prediction=species_prediction,
            confidence=confidence,
            time_offset=time_offset,
            session_id=session_id,
            device_id=device_id,
        )
        idx = len(self._records)
        self._records.append(record)
        self._session_records[session_id].append(idx)
        return idx

    def get_session_embeddings(self, session_id: str) -> Tuple[np.ndarray, List[str]]:
        """Get all embeddings and labels for a session."""
        indices = self._session_records.get(session_id, [])
        if not indices:
            return np.array([]), []
        embeddings = np.stack([self._records[i].embedding for i in indices])
        labels = [self._records[i].species_prediction for i in indices]
        return embeddings, labels

    def cluster_embeddings(
        self, embeddings: np.ndarray, min_cluster_size: int = 5
    ) -> np.ndarray:
        """Cluster embeddings using HDBSCAN for discovering unknown sound patterns.

        Falls back to KMeans if HDBSCAN is unavailable.
        """
        if len(embeddings) < min_cluster_size:
            return np.full(len(embeddings), -1, dtype=int)

        try:
            from sklearn.cluster import HDBSCAN as HDBSCANCls

            clusterer = HDBSCANCls(
                min_cluster_size=min_cluster_size,
                min_samples=2,
                metric="euclidean",
            )
            return clusterer.fit_predict(embeddings)
        except (ImportError, Exception):
            from sklearn.cluster import KMeans

            n_clusters = max(2, min(len(embeddings) // min_cluster_size, 20))
            return KMeans(
                n_clusters=n_clusters, n_init=10, random_state=42
            ).fit_predict(embeddings)

    def reduce_dimensions(
        self, embeddings: np.ndarray, n_components: int = 2, method: str = "pca"
    ) -> np.ndarray:
        """Reduce embedding dimensions for visualization.

        Uses PCA (always available), or UMAP if installed.
        """
        if len(embeddings) < 2:
            return (
                embeddings[:, :n_components]
                if embeddings.shape[1] >= n_components
                else embeddings
            )

        if method == "umap":
            try:
                import umap

                reducer = umap.UMAP(n_components=n_components, random_state=42)
                return reducer.fit_transform(embeddings)
            except ImportError:
                method = "pca"

        from sklearn.decomposition import PCA

        n_components = min(n_components, embeddings.shape[1], len(embeddings))
        return PCA(n_components=n_components, random_state=42).fit_transform(embeddings)

    def compute_acoustic_similarity_matrix(
        self, embeddings: np.ndarray, labels: List[str]
    ) -> Dict:
        """Compute species-level acoustic similarity from embeddings."""
        species_embeddings = defaultdict(list)
        for emb, label in zip(embeddings, labels):
            species_embeddings[label].append(emb)

        species_names = sorted(species_embeddings.keys())
        centroids = {}
        for sp in species_names:
            centroids[sp] = np.mean(species_embeddings[sp], axis=0)

        n = len(species_names)
        similarity_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                ci = centroids[species_names[i]]
                cj = centroids[species_names[j]]
                cos_sim = np.dot(ci, cj) / (
                    np.linalg.norm(ci) * np.linalg.norm(cj) + 1e-10
                )
                similarity_matrix[i][j] = float(cos_sim)

        return {
            "species": species_names,
            "similarity_matrix": similarity_matrix.tolist(),
        }

    def find_novel_sounds(
        self, session_id: str, novelty_threshold: float = 0.3
    ) -> List[Dict]:
        """Identify potentially novel or unrecognized sound events.

        Finds embeddings that are far from all known species cluster centroids —
        candidates for new species or unknown biophony/geophony.
        """
        embeddings, labels = self.get_session_embeddings(session_id)
        if len(embeddings) < 5:
            return []

        species_centroids = defaultdict(list)
        for emb, label in zip(embeddings, labels):
            species_centroids[label].append(emb)
        centroids = {
            sp: np.mean(embs, axis=0) for sp, embs in species_centroids.items()
        }

        novel = []
        indices = self._session_records.get(session_id, [])
        for i, (emb, label) in enumerate(zip(embeddings, labels)):
            min_dist = min(np.linalg.norm(emb - c) for c in centroids.values())
            if min_dist > novelty_threshold:
                record = self._records[indices[i]]
                novel.append(
                    {
                        "record_index": indices[i],
                        "time_offset": record.time_offset,
                        "predicted_species": label,
                        "confidence": record.confidence,
                        "novelty_score": float(min_dist),
                    }
                )
        return sorted(novel, key=lambda x: -x["novelty_score"])

    def extract_from_bytes(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """Extract embedding from raw audio bytes.

        Loads audio, computes mel spectrogram, and extracts features through
        the model backbone. Used by FewShotDetector and EmbeddingClassifier.
        """
        try:
            from audio_processor import process_audio_for_inference
            segments = process_audio_for_inference(audio_bytes)
            if not segments:
                return None
            mel, _ = segments[0]
            is_dual = mel.ndim == 3 and mel.shape[0] == 2
            return self.extract_embedding(mel, is_dual_channel=is_dual)
        except Exception:
            return None

    def get_stats(self) -> Dict:
        return {
            "total_records": len(self._records),
            "sessions": len(self._session_records),
            "unique_species": len(set(r.species_prediction for r in self._records)),
        }


import threading

_engine: Optional[EmbeddingEngine] = None
_engine_lock = threading.Lock()


def get_embedding_engine() -> EmbeddingEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = EmbeddingEngine()
    return _engine
