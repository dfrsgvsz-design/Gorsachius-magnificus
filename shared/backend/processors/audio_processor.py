"""
Audio Processing Module for Bird Sound Platform.
Converts raw audio to mel-spectrograms for CNN input.
Implements data augmentation techniques for training robustness.
"""

import numpy as np
import io
import os
import base64
import subprocess
import tempfile

try:
    import librosa
    import librosa.display
except ImportError:
    librosa = None

try:
    import soundfile as sf
except ImportError:
    sf = None

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None


def _get_ffmpeg_path():
    """Locate ffmpeg binary: PATH first, then imageio-ffmpeg bundle."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return "ffmpeg"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        pass
    return None


_FFMPEG_PATH = _get_ffmpeg_path()


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
DEFAULT_SR = 22050  # Sample rate (Hz)
N_FFT = 2048  # FFT window size
HOP_LENGTH = 512  # Hop length for STFT
N_MELS = 128  # Number of mel bands
FMIN = 150  # Min frequency (Hz) - filters low-freq noise
FMAX = 10000  # Max frequency (Hz) - covers most bird vocalizations
SEGMENT_DURATION = 3.0  # Seconds per analysis segment
OVERLAP = 0.5  # Overlap ratio between segments


def _ffmpeg_bytes_to_wav(raw_bytes: bytes, target_sr: int) -> bytes:
    """Use ffmpeg to transcode arbitrary audio bytes to WAV in memory."""
    if _FFMPEG_PATH is None:
        raise RuntimeError("ffmpeg not available; install ffmpeg or imageio-ffmpeg")
    with tempfile.NamedTemporaryFile(suffix=".input", delete=False) as tmp_in:
        tmp_in.write(raw_bytes)
        tmp_in_path = tmp_in.name
    tmp_out_path = tmp_in_path + ".wav"
    try:
        subprocess.run(
            [
                _FFMPEG_PATH,
                "-y",
                "-i",
                tmp_in_path,
                "-ar",
                str(target_sr),
                "-ac",
                "1",
                "-f",
                "wav",
                tmp_out_path,
            ],
            capture_output=True,
            check=True,
            timeout=60,
        )
        with open(tmp_out_path, "rb") as f:
            return f.read()
    finally:
        for p in (tmp_in_path, tmp_out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def load_audio(file_path_or_bytes, sr=DEFAULT_SR, duration=None):
    """Load audio from file path or bytes, resample to target sr.

    Strategy for byte input:
      1. soundfile (fast, WAV/FLAC/AIFF)
      2. librosa via audioread (MP3 if ffmpeg on PATH)
      3. ffmpeg transcode to WAV then soundfile
    """
    if isinstance(file_path_or_bytes, (bytes, bytearray)):
        audio_io = io.BytesIO(file_path_or_bytes)

        if sf is not None:
            try:
                y, orig_sr = sf.read(audio_io, dtype="float32")
                if len(y.shape) > 1:
                    y = np.mean(y, axis=1)
                if orig_sr != sr:
                    y = librosa.resample(y, orig_sr=orig_sr, target_sr=sr)
                return y, sr
            except Exception:
                audio_io.seek(0)

        if librosa is not None:
            try:
                y, _ = librosa.load(audio_io, sr=sr, duration=duration, mono=True)
                return y, sr
            except Exception:
                pass

        if _FFMPEG_PATH is not None and sf is not None:
            wav_bytes = _ffmpeg_bytes_to_wav(file_path_or_bytes, sr)
            y, orig_sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
            if len(y.shape) > 1:
                y = np.mean(y, axis=1)
            return y, sr

        raise RuntimeError(
            "Cannot decode audio: install ffmpeg (or imageio-ffmpeg) "
            "to support MP3/M4A/OGG formats"
        )
    else:
        y, _ = librosa.load(file_path_or_bytes, sr=sr, duration=duration, mono=True)
    return y, sr


def audio_to_mel_spectrogram(
    y,
    sr=DEFAULT_SR,
    n_mels=N_MELS,
    n_fft=N_FFT,
    hop_length=HOP_LENGTH,
    fmin=FMIN,
    fmax=FMAX,
):
    """Convert audio waveform to log-mel spectrogram."""
    S = librosa.feature.melspectrogram(
        y=y,
        sr=sr,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=n_mels,
        fmin=fmin,
        fmax=fmax,
    )
    S_db = librosa.power_to_db(S, ref=np.max)
    return S_db


def normalize_spectrogram(S_db):
    """Normalize spectrogram to [0, 1] range."""
    s_min = S_db.min()
    s_max = S_db.max()
    if s_max - s_min < 1e-6:
        return np.zeros_like(S_db)
    return (S_db - s_min) / (s_max - s_min)


def segment_audio(y, sr=DEFAULT_SR, segment_duration=SEGMENT_DURATION, overlap=OVERLAP):
    """Split audio into overlapping segments."""
    segment_samples = int(segment_duration * sr)
    hop_samples = int(segment_samples * (1 - overlap))
    segments = []
    start = 0
    while start + segment_samples <= len(y):
        segments.append(y[start : start + segment_samples])
        start += hop_samples
    # Pad last segment if needed
    if start < len(y):
        last_segment = np.zeros(segment_samples)
        remaining = len(y) - start
        last_segment[:remaining] = y[start:]
        segments.append(last_segment)
    return segments


def process_audio_for_inference(audio_bytes, sr=DEFAULT_SR):
    """
    Full pipeline: audio bytes -> list of normalized mel-spectrogram tensors.
    Returns list of (spectrogram_array, time_offset) tuples.
    """
    y, sr = load_audio(audio_bytes, sr=sr)
    segments = segment_audio(y, sr=sr)
    results = []
    for i, seg in enumerate(segments):
        mel = audio_to_mel_spectrogram(seg, sr=sr)
        mel_norm = normalize_spectrogram(mel)
        time_offset = i * SEGMENT_DURATION * (1 - OVERLAP)
        results.append((mel_norm, time_offset))
    return results, sr, y


def spectrogram_to_base64_image(
    S_db, sr=DEFAULT_SR, hop_length=HOP_LENGTH, fmin=FMIN, fmax=FMAX, figsize=(10, 4)
):
    """Render mel-spectrogram as base64-encoded PNG image."""
    if plt is None:
        return None
    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=100)
    img = librosa.display.specshow(
        S_db,
        sr=sr,
        hop_length=hop_length,
        x_axis="time",
        y_axis="mel",
        fmin=fmin,
        fmax=fmax,
        ax=ax,
        cmap="magma",
    )
    fig.colorbar(img, ax=ax, format="%+2.0f dB")
    ax.set_title("Mel Spectrogram", fontsize=12)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def waveform_to_base64_image(y, sr=DEFAULT_SR, figsize=(10, 2)):
    """Render waveform as base64-encoded PNG."""
    if plt is None:
        return None
    fig, ax = plt.subplots(1, 1, figsize=figsize, dpi=100)
    t = np.arange(len(y)) / sr
    ax.plot(t, y, linewidth=0.5, color="#2563eb")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title("Waveform", fontsize=12)
    ax.set_xlim(0, t[-1])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ──────────────────────────────────────────────
# Data Augmentation (for training)
# ──────────────────────────────────────────────
class AudioAugmentor:
    """Audio-level augmentation for training data."""

    @staticmethod
    def add_noise(y, noise_level=0.005):
        noise = np.random.randn(len(y)) * noise_level
        return y + noise

    @staticmethod
    def time_shift(y, shift_max=0.2):
        shift = int(len(y) * np.random.uniform(-shift_max, shift_max))
        return np.roll(y, shift)

    @staticmethod
    def pitch_shift(y, sr=DEFAULT_SR, n_steps=None):
        if n_steps is None:
            n_steps = np.random.uniform(-2, 2)
        return librosa.effects.pitch_shift(y=y, sr=sr, n_steps=n_steps)

    @staticmethod
    def time_stretch(y, rate=None):
        if rate is None:
            rate = np.random.uniform(0.8, 1.2)
        return librosa.effects.time_stretch(y=y, rate=rate)

    @staticmethod
    def random_gain(y, min_gain=0.7, max_gain=1.3):
        gain = np.random.uniform(min_gain, max_gain)
        return y * gain


class SpectrogramAugmentor:
    """Spectrogram-level augmentation (SpecAugment-style)."""

    @staticmethod
    def freq_mask(S, num_masks=1, max_width=20):
        S = S.copy()
        n_mels = S.shape[0]
        for _ in range(num_masks):
            f = np.random.randint(0, max_width)
            f0 = np.random.randint(0, max(1, n_mels - f))
            S[f0 : f0 + f, :] = 0
        return S

    @staticmethod
    def time_mask(S, num_masks=1, max_width=30):
        S = S.copy()
        n_frames = S.shape[1]
        for _ in range(num_masks):
            t = np.random.randint(0, max_width)
            t0 = np.random.randint(0, max(1, n_frames - t))
            S[:, t0 : t0 + t] = 0
        return S

    @staticmethod
    def mixup(S1, S2, alpha=0.3):
        lam = np.random.beta(alpha, alpha)
        return lam * S1 + (1 - lam) * S2
