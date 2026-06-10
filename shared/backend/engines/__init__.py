"""Inference engines for species identification."""

from .birdnet_engine import predict_from_file, predict_from_bytes, is_available as birdnet_available
from .onnx_engine import ONNXInferenceEngine, get_onnx_engine
