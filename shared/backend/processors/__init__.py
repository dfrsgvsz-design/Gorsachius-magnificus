"""Audio, image, and camera trap data processors."""

from .audio_processor import load_audio, audio_to_mel_spectrogram, normalize_spectrogram, process_audio_for_inference
from .image_processor import extract_exif, classify_image, create_thumbnail
from .camera_trap_processor import preprocess_ir_image, detect_animals_basic, extract_trap_metadata
from .batch_import import scan_directory, create_import_manifest
