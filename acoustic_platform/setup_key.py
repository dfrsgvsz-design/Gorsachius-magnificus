"""Check file URL availability rate across species."""
import os
import sys, requests
sys.path.insert(0, "backend")

KEY = os.environ.get("XC_API_KEY", "").strip()
BASE = "https://xeno-canto.org/api/3/recordings"

from xeno_canto_client import CHINA_BIRD_SPECIES

if not KEY:
    raise SystemExit("XC_API_KEY is required to run this script.")

print("Species | Total | WithFile | Rate")
print("-" * 60)
total_all, total_with = 0, 0
for sp in CHINA_BIRD_SPECIES[:10]:
    query = f'sp:"{sp["scientific"]}" grp:birds cnt:China'
    resp = requests.get(BASE, params={"query": query, "key": KEY}, timeout=15)
    if resp.status_code != 200:
        print(f'{sp["chinese"]:8s} | ERROR {resp.status_code}')
        continue
    data = resp.json()
    recs = data.get("recordings", [])
    n_total = len(recs)
    n_file = sum(1 for r in recs if r.get("file"))
    total_all += n_total
    total_with += n_file
    rate = f"{n_file/n_total*100:.0f}%" if n_total > 0 else "N/A"
    print(f'{sp["chinese"]:8s} | {n_total:5d} | {n_file:8d} | {rate}')

print(f"\nTotal: {total_all} recordings, {total_with} with file URLs ({total_with/max(total_all,1)*100:.0f}%)")
