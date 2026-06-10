"""Quick test of Xeno-canto API v3 query formats."""
import os
import requests

API_KEY = os.environ.get("XC_API_KEY", "").strip()
BASE = "https://xeno-canto.org/api/3/recordings"

if not API_KEY:
    raise SystemExit("XC_API_KEY is required to run this script.")

formats = [
    'sp:"Pycnonotus sinensis" grp:birds',
    'sp:Pycnonotus sinensis grp:birds',
    'Pycnonotus sinensis grp:birds',
    '"Pycnonotus sinensis" grp:birds',
    'Pycnonotus sinensis',
]

for q in formats:
    try:
        r = requests.get(BASE, params={"query": q, "key": API_KEY}, timeout=30)
        data = r.json() if r.status_code == 200 else {}
        recs = data.get("recordings", [])
        has_file = sum(1 for x in recs if x.get("file", ""))
        total = data.get("numRecordings", 0)
        print(f"[{r.status_code}] query='{q}' => total={total}, returned={len(recs)}, with_file={has_file}")
    except Exception as e:
        print(f"[ERR] query='{q}' => {e}")
