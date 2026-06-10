"""Diagnose why training fails: check manifest paths and data loading."""
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

manifest_path = Path(__file__).parent.parent / "data" / "xc_china" / "manifest.json"
m = json.load(open(manifest_path, "r", encoding="utf-8"))

print(f"Total items: {len(m)}")
print(f"\nFirst 3 file_path values:")
for item in m[:3]:
    fp = item["file_path"]
    p = Path(fp)
    print(f"  {fp}")
    print(f"    exists={p.exists()}, is_absolute={p.is_absolute()}")

# Check how many files actually exist
exist_count = sum(1 for item in m if Path(item["file_path"]).exists())
print(f"\nFiles that exist: {exist_count}/{len(m)}")

if exist_count == 0:
    # Try relative to different bases
    for base in [Path(__file__).parent.parent, 
                 Path(__file__).parent.parent / "backend",
                 Path(".")]:
        test_path = base / m[0]["file_path"]
        print(f"  Try {base}/path: {test_path} -> exists={test_path.exists()}")

# Try loading one audio file
if exist_count > 0:
    from audio_processor import load_audio, audio_to_mel_spectrogram, normalize_spectrogram, DEFAULT_SR, SEGMENT_DURATION
    
    test_item = m[0]
    fp = test_item["file_path"]
    print(f"\nTest loading: {fp}")
    try:
        y, sr = load_audio(fp, sr=DEFAULT_SR, duration=SEGMENT_DURATION + 1)
        print(f"  Loaded: shape={y.shape}, sr={sr}, duration={len(y)/sr:.2f}s")
        print(f"  Min={y.min():.4f}, Max={y.max():.4f}, Std={y.std():.4f}")
        
        mel = audio_to_mel_spectrogram(y, sr=sr)
        print(f"  Mel shape: {mel.shape}")
        
        mel_norm = normalize_spectrogram(mel)
        print(f"  Normalized: min={mel_norm.min():.4f}, max={mel_norm.max():.4f}")
        
        # Check if all zeros
        if mel_norm.max() == mel_norm.min():
            print("  WARNING: Normalized mel is constant (all same value)!")
    except Exception as e:
        print(f"  ERROR: {e}")
else:
    print("\nNo files found! Check paths.")
