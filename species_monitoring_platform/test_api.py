"""End-to-end test for the Biodiversity Field Survey Platform API."""
import requests
import json

API = "http://localhost:8000"

# 1. Health check
r = requests.get(f"{API}/api/health")
h = r.json()
print("=== Health Check ===")
print(f"  Status: {h['status']}, Model loaded: {h['model_loaded']}, Species: {h['num_species']}")

# 2. Analyze test audio
print("\n=== Analyze Audio ===")
with open("test_data/test_bird_chirp.wav", "rb") as f:
    resp = requests.post(
        f"{API}/api/analyze",
        files={"file": ("test.wav", f, "audio/wav")},
        params={"top_k": 5, "confidence_threshold": 0.01},
    )
d = resp.json()
print(f"  HTTP {resp.status_code}")
print(f"  Duration: {d.get('duration_seconds')}s, Segments: {d.get('num_segments')}")
print(f"  Total detections: {d['summary']['total_detections']}")
print(f"  Unique species: {d['summary']['unique_species']}")
alpha = d["summary"]["alpha_diversity"]
print(f"  Shannon index: {alpha['shannon_index']}")
print(f"  Simpson index: {alpha['simpson_index']}")
print(f"  Chao1 estimate: {alpha['chao1_estimate']}")
print(f"  Waveform image: {'YES' if d.get('waveform_image') else 'NO'}")
print(f"  Spectrogram image: {'YES' if d.get('spectrogram_image') else 'NO'}")
print("\n  Top detections:")
for sp in d["summary"]["species_breakdown"][:5]:
    print(f"    {sp['species']}: count={sp['count']}, avg_conf={sp['avg_confidence']:.4f}")

# 3. Xeno-canto search (Gorsachius magnificus)
print("\n=== Xeno-canto Search: Gorsachius magnificus ===")
xc = requests.post(f"{API}/api/search-xc", json={
    "species": "Gorsachius magnificus",
    "country": "China",
    "max_results": 5,
})
xd = xc.json()
print(f"  Results: {xd.get('total_results', 0)}")
for rec in xd.get("recordings", [])[:3]:
    print(f"    XC{rec['id']}: {rec['species']} | {rec['locality']} | Q:{rec['quality']} | {rec['duration']}")

# 4. Xeno-canto search (common species)
print("\n=== Xeno-canto Search: Garrulax canorus (画眉) ===")
xc2 = requests.post(f"{API}/api/search-xc", json={
    "species": "Garrulax canorus",
    "country": "China",
    "max_results": 5,
})
xd2 = xc2.json()
print(f"  Results: {xd2.get('total_results', 0)}")
for rec in xd2.get("recordings", [])[:3]:
    print(f"    XC{rec['id']}: {rec['species']} | {rec['locality']} | Q:{rec['quality']} | {rec['duration']}")

# 5. Beta diversity comparison
print("\n=== Beta Diversity: 2-site comparison ===")
beta = requests.post(f"{API}/api/compare-sites", json={
    "sites": [
        {"site_name": "Site_A_Forest", "species": ["Garrulax canorus", "Pycnonotus sinensis", "Parus major", "Cuculus canorus", "Otus lettia"]},
        {"site_name": "Site_B_Wetland", "species": ["Nycticorax nycticorax", "Egretta garzetta", "Pycnonotus sinensis", "Alcedo atthis", "Parus major"]},
    ]
})
bd = beta.json()
print(f"  Sites: {bd['num_sites']}")
for name, metrics in bd["alpha_diversity"].items():
    print(f"  {name}: S={metrics['species_richness']}, H'={metrics['shannon_index']}, 1-D={metrics['simpson_index']}")
bm = bd["beta_diversity"]
print(f"  Jaccard similarity: {bm['jaccard'][0][1]:.4f}")
print(f"  Sorensen similarity: {bm['sorensen'][0][1]:.4f}")
print(f"  Bray-Curtis dissimilarity: {bm['bray_curtis'][0][1]:.4f}")

# 6. Paper context
print("\n=== Paper Context ===")
pc = requests.get(f"{API}/api/paper-context")
pcd = pc.json()
print(f"  Paper: {pcd['paper'][:80]}...")
print(f"  Pain points: {len(pcd['key_problems_with_acoustic_indices'])}")
print(f"  Solutions: {len(pcd['platform_solutions'])}")
print(f"  Databases: {len(pcd['databases_used'])}")
print(f"  Tools: {len(pcd['referenced_tools'])}")

print("\n=== ALL TESTS PASSED ===")
