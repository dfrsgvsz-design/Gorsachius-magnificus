"""Debug: test constructing download URLs from recording IDs."""
import os
import sys
import requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

API_KEY = os.environ.get("XC_API_KEY", "").strip()
BASE_URL = "https://xeno-canto.org/api/3/recordings"

if not API_KEY:
    raise SystemExit("XC_API_KEY is required to run this script.")

# Test species WITHOUT file URLs: Garrulax canorus
query = 'sp:"Garrulax canorus" grp:birds'
params = {"query": query, "key": API_KEY}
resp = requests.get(BASE_URL, params=params, timeout=30)
data = resp.json()
recs = data.get("recordings", [])

print(f"Garrulax canorus: {len(recs)} returned")
if recs:
    rec = recs[0]
    rec_id = rec.get("id", "")
    file_field = rec.get("file", "")
    print(f"  rec[0] id={rec_id}, file='{file_field}'")
    print(f"  All keys: {sorted(rec.keys())}")
    
    # Try constructing URL from ID
    constructed_url = f"https://xeno-canto.org/{rec_id}/download"
    print(f"  Constructed URL: {constructed_url}")
    
    # Test if constructed URL works
    try:
        dl = requests.get(constructed_url, params={"key": API_KEY}, 
                         timeout=30, stream=True, allow_redirects=True)
        ct = dl.headers.get("content-type", "")
        cl = dl.headers.get("content-length", "?")
        print(f"  Download status: {dl.status_code}, content-type: {ct}, size: {cl}")
        
        # Read first 100 bytes to check
        chunk = next(dl.iter_content(100), b"")
        is_audio = not chunk.startswith(b"<") and not chunk.startswith(b"<!DOCTYPE")
        print(f"  Is audio data: {is_audio} (first bytes: {chunk[:20]})")
    except Exception as e:
        print(f"  Download error: {e}")

# Also test a species WITH file URLs for comparison
print()
query2 = 'sp:"Pycnonotus sinensis" grp:birds'
params2 = {"query": query2, "key": API_KEY}
resp2 = requests.get(BASE_URL, params=params2, timeout=30)
recs2 = resp2.json().get("recordings", [])
print(f"Pycnonotus sinensis: {len(recs2)} returned")
if recs2:
    rec2 = recs2[0]
    print(f"  rec[0] id={rec2.get('id')}, file='{rec2.get('file','')[:60]}'")
    
    # Also construct URL for comparison
    constructed2 = f"https://xeno-canto.org/{rec2.get('id')}/download"
    print(f"  API file URL: {rec2.get('file','')}")
    print(f"  Constructed:   {constructed2}")
    print(f"  Match: {rec2.get('file','').rstrip('/') == constructed2}")
