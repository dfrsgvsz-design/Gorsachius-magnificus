"""Quick test: verify backend can load v3 model with calibration."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import numpy as np

# Simulate the critical parts of main.py
from cnn_model import create_model, BirdSoundCNN
from cnn_model_v2 import SEResNet50, SEResNet18
import torch, json

MODEL_DIR = Path(__file__).parent.parent / "backend" / "checkpoints"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Load model
model_path = MODEL_DIR / "best_model.pth"
mapping_path = MODEL_DIR / "species_mapping.json"

with open(mapping_path, "r", encoding="utf-8") as f:
    data = json.load(f)
species_to_idx = data["species_to_idx"]
idx_to_species = {int(k): v for k, v in data["idx_to_species"].items()}
num_species = len(species_to_idx)

checkpoint = torch.load(model_path, map_location=DEVICE, weights_only=False)
version = checkpoint.get("version", "v1")
model_type = checkpoint.get("model_type", "")

print(f"Version: {version}, Type: {model_type}, Species: {num_species}")

if "v3" in str(version) or model_type in ("student", "teacher"):
    if model_type == "teacher":
        model = SEResNet50(num_species=num_species).to(DEVICE)
    else:
        model = SEResNet18(num_species=num_species).to(DEVICE)
    print(f"Created {type(model).__name__}")
else:
    lite = checkpoint.get("lite", False)
    model = create_model(num_species=num_species, lite=lite).to(DEVICE)

model.load_state_dict(checkpoint["model_state_dict"])
model.eval()
print(f"Model loaded OK: {type(model).__name__}")

# Load calibration
CALIBRATION_T = 1.0
calib_path = MODEL_DIR / "calibration.json"
if calib_path.exists():
    calib = json.load(open(calib_path))
    CALIBRATION_T = calib.get("temperature", 1.0)
    print(f"Calibration: T={CALIBRATION_T:.4f}")

# Test inference
mel = np.random.randn(128, 256).astype(np.float32)
tensor = torch.FloatTensor(mel).unsqueeze(0).unsqueeze(0).to(DEVICE)

with torch.no_grad():
    logits = model(tensor)
    # TTA
    logits_flip = model(torch.flip(tensor, dims=[-1]))
    logits = (logits + logits_flip) / 2.0
    # Temperature scaling
    calibrated = logits / CALIBRATION_T
    probs = torch.softmax(calibrated, dim=1)[0]
    top3_probs, top3_idx = probs.topk(3)

print(f"\nInference test (random noise input):")
for p, i in zip(top3_probs.cpu().numpy(), top3_idx.cpu().numpy()):
    sp = idx_to_species.get(int(i), "?")
    print(f"  {sp}: {p:.4f}")

# Entropy
entropy = float(-(probs * torch.log(probs + 1e-10)).sum().cpu())
max_entropy = np.log(num_species)
print(f"\nEntropy: {entropy:.2f} / {max_entropy:.2f} = {entropy/max_entropy:.4f} normalized")
print(f"(Random noise should have high entropy ~1.0)")
print(f"\n✅ Backend v3 model loading + calibration + inference: ALL OK")
