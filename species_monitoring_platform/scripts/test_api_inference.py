"""Test the /api/analyze endpoint with real audio files."""
import json
import requests
import random
from pathlib import Path

API_BASE = "http://localhost:8001"
MANIFEST = Path(__file__).parent.parent / "data" / "xc_expanded" / "manifest.json"

manifest = json.load(open(MANIFEST, "r", encoding="utf-8"))
random.shuffle(manifest)

# Test health
r = requests.get(f"{API_BASE}/api/health")
health = r.json()
print(f"Health: model={health['model_loaded']}, device={health['device']}, species={health['num_species_model']}")

# Test 5 random audio files
correct = 0
total = 0
for item in manifest[:5]:
    fp = Path(item["file_path"])
    true_species = item["species_scientific"]
    if not fp.exists():
        print(f"  SKIP {fp} (not found)")
        continue

    with open(fp, "rb") as f:
        r = requests.post(
            f"{API_BASE}/api/analyze",
            files={"file": (fp.name, f, "audio/mpeg")},
            params={"top_k": 5},
        )

    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:200]}")
        continue

    result = r.json()
    detections = result.get("detections", [])
    # Aggregate: find species with highest total confidence
    species_conf = {}
    for d in detections:
        sp = d.get("species", d.get("species_scientific", ""))
        species_conf[sp] = species_conf.get(sp, 0) + d["confidence"]
    top1_species = max(species_conf, key=species_conf.get) if species_conf else None

    total += 1
    match = top1_species == true_species
    if match:
        correct += 1

    status = "OK" if match else "MISS"
    print(f"  [{status}] True: {true_species}")
    if top1_species:
        top1_det = next((d for d in detections if d.get("species") == top1_species), {})
        print(f"         Pred: {top1_species} (agg_conf={species_conf[top1_species]:.2f})")
        print(f"         Chinese: {top1_det.get('species_chinese', '')}")
    if not match and species_conf:
        in_top5 = true_species in species_conf
        if in_top5:
            print(f"         (True species in detections)")

    print(f"         Duration: {result.get('duration_seconds', '?')}s, Segments: {result.get('num_segments', '?')}")
    print()

print(f"Results: {correct}/{total} correct ({correct/max(total,1)*100:.0f}%)")
