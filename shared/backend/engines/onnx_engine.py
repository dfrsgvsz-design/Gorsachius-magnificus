"""
ONNX Runtime Inference Engine — 轻量推理后端

用于替代 PyTorch 的桌面/CLI 部署场景，极大缩小安装包体积：
- onnxruntime (~20MB) vs torch (~500MB+)
- 支持 CPU/GPU/DirectML/CoreML 多后端
- INT8 量化后模型 <15MB

使用流程:
1. 训练时用 PyTorch (cnn_model_v7.py)
2. 导出 ONNX: python -c "from cnn_model_v7 import export_to_onnx, create_model_v7; m=create_model_v7(223,'student'); export_to_onnx(m,'model.onnx',223)"
3. 推理时用本模块 (无需安装 PyTorch)

兼容 V7 ConvNeXt 的双通道 mel 输入。
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("bird_platform")

try:
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:
    ort = None
    ONNX_AVAILABLE = False


class ONNXInferenceEngine:
    """ONNX Runtime inference engine for bird sound classification.

    Drop-in replacement for PyTorch model inference, compatible with
    the same dual-channel mel spectrogram inputs.
    """

    def __init__(self):
        self._session: Optional["ort.InferenceSession"] = None
        self._species_mapping: Optional[Dict[str, int]] = None
        self._idx_to_species: Optional[Dict[int, str]] = None
        self._num_species: int = 0
        self._providers: List[str] = []

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    @property
    def num_species(self) -> int:
        return self._num_species

    def load(
        self, model_path: str, mapping_path: str, prefer_gpu: bool = False
    ) -> bool:
        """Load ONNX model and species mapping.

        Args:
            model_path: Path to .onnx model file
            mapping_path: Path to species_mapping.json
            prefer_gpu: Try GPU providers first (CUDA, DirectML, CoreML)
        """
        if not ONNX_AVAILABLE:
            logger.error("onnxruntime not installed. Run: pip install onnxruntime")
            return False

        model_path = Path(model_path)
        mapping_path = Path(mapping_path)

        if not model_path.exists():
            logger.error("ONNX model not found: %s", model_path)
            return False
        if not mapping_path.exists():
            logger.error("Species mapping not found: %s", mapping_path)
            return False

        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._species_mapping = data["species_to_idx"]
        self._idx_to_species = {int(k): v for k, v in data["idx_to_species"].items()}
        self._num_species = len(self._species_mapping)

        providers = []
        if prefer_gpu:
            available = ort.get_available_providers()
            for gpu_provider in [
                "CUDAExecutionProvider",
                "DmlExecutionProvider",
                "CoreMLExecutionProvider",
            ]:
                if gpu_provider in available:
                    providers.append(gpu_provider)
        providers.append("CPUExecutionProvider")

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        sess_options.intra_op_num_threads = 4

        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=sess_options,
            providers=providers,
        )
        self._providers = self._session.get_providers()
        logger.info(
            "ONNX model loaded: %s (%d species, providers=%s)",
            model_path.name,
            self._num_species,
            self._providers,
        )
        return True

    def predict(self, mel_input: np.ndarray, top_k: int = 5) -> List[Dict]:
        """Run inference on a dual-channel mel spectrogram.

        Args:
            mel_input: Shape (2, 96, 512) or (n_mels, frames) float32 array
            top_k: Number of top predictions to return

        Returns:
            List of {species_scientific, confidence, reliable} dicts
        """
        if not self.is_loaded:
            return []

        if mel_input.ndim == 2:
            inp = mel_input[np.newaxis, np.newaxis, :, :].astype(np.float32)
        elif mel_input.ndim == 3:
            inp = mel_input[np.newaxis, :, :, :].astype(np.float32)
        else:
            inp = mel_input.astype(np.float32)

        input_name = self._session.get_inputs()[0].name
        logits = self._session.run(None, {input_name: inp})[0]

        probs = _softmax(logits[0])
        top_indices = np.argsort(probs)[::-1][:top_k]

        results = []
        for idx in top_indices:
            species = self._idx_to_species.get(int(idx), "Unknown")
            conf = float(probs[idx])
            results.append(
                {
                    "species_scientific": species,
                    "confidence": round(conf, 4),
                    "reliable": conf > 0.3,
                }
            )
        return results

    def predict_batch(
        self, mel_inputs: List[np.ndarray], top_k: int = 5
    ) -> List[List[Dict]]:
        """Batch inference for multiple mel spectrograms."""
        if not self.is_loaded or not mel_inputs:
            return []

        batch = np.stack(
            [m[np.newaxis] if m.ndim == 2 else m for m in mel_inputs]
        ).astype(np.float32)

        input_name = self._session.get_inputs()[0].name
        logits = self._session.run(None, {input_name: batch})[0]

        all_results = []
        for i in range(len(logits)):
            probs = _softmax(logits[i])
            top_indices = np.argsort(probs)[::-1][:top_k]
            results = []
            for idx in top_indices:
                species = self._idx_to_species.get(int(idx), "Unknown")
                conf = float(probs[idx])
                results.append(
                    {
                        "species_scientific": species,
                        "confidence": round(conf, 4),
                        "reliable": conf > 0.3,
                    }
                )
            all_results.append(results)
        return all_results

    def get_info(self) -> Dict:
        """Get model info."""
        if not self.is_loaded:
            return {"loaded": False}
        inp = self._session.get_inputs()[0]
        return {
            "loaded": True,
            "num_species": self._num_species,
            "input_name": inp.name,
            "input_shape": inp.shape,
            "providers": self._providers,
        }


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


def quantize_onnx_model(input_path: str, output_path: str, quant_type: str = "dynamic"):
    """Quantize an ONNX model to reduce size and improve CPU inference speed.

    Args:
        input_path: Path to FP32 ONNX model
        output_path: Path to save quantized model
        quant_type: "dynamic" (INT8, ~2x smaller) or "static" (needs calibration data)
    """
    try:
        from onnxruntime.quantization import quantize_dynamic, QuantType

        quantize_dynamic(
            input_path,
            output_path,
            weight_type=QuantType.QInt8,
        )
        original_size = Path(input_path).stat().st_size / (1024 * 1024)
        quantized_size = Path(output_path).stat().st_size / (1024 * 1024)
        logger.info(
            "Quantized: %.1fMB → %.1fMB (%.0f%% reduction)",
            original_size,
            quantized_size,
            (1 - quantized_size / original_size) * 100,
        )
    except ImportError:
        logger.error("Install: pip install onnxruntime[quantization]")


_engine: Optional[ONNXInferenceEngine] = None


def get_onnx_engine() -> ONNXInferenceEngine:
    global _engine
    if _engine is None:
        _engine = ONNXInferenceEngine()
    return _engine
