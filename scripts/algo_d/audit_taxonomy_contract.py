"""Algo-D / P0-W2 audit: validate the 5-tuple taxonomy API contract.

For each of the 16 documented legal `(program, jurisdiction, protocol,
submodule, taxon_group)` combinations in
``docs/taxonomy_api_contract.md`` :: §5, hit the running backend at:

  GET /api/surveys/taxonomy/search
  GET /api/surveys/taxonomy/packages
  GET /api/surveys/protocols

and assert HTTP 200. Also probe the `limit` boundary:
  limit=200 -> 200 OK
  limit=201 -> 422 Unprocessable Entity   (current contract)
  taxon_group=birds vs submodule=birds returns the same total

Writes a JSON gate report to ``scripts/algo_d/_artifacts/taxonomy_contract_report.json``.

Exit codes:
  0 = all checks PASS
  2 = at least one check FAIL
  3 = backend unreachable

Usage:
  python scripts/algo_d/audit_taxonomy_contract.py --base http://127.0.0.1:8000
  python scripts/algo_d/audit_taxonomy_contract.py            # default base
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    print("[FATAL] 'requests' not installed; pip install requests")
    sys.exit(3)

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

ARTIFACTS_DIR = Path(__file__).resolve().parent / "_artifacts"
REPORT_PATH = ARTIFACTS_DIR / "taxonomy_contract_report.json"

LEGAL_FIVE_TUPLES: list[dict[str, str]] = [
    # terrestrial_vertebrates × mainland_china
    {"program": "terrestrial_vertebrates", "jurisdiction": "mainland_china", "protocol": "bird_line_transect", "submodule": "birds"},
    {"program": "terrestrial_vertebrates", "jurisdiction": "mainland_china", "protocol": "bird_point_count", "submodule": "birds"},
    {"program": "terrestrial_vertebrates", "jurisdiction": "mainland_china", "protocol": "mammal_trap_net", "submodule": "mammals"},
    {"program": "terrestrial_vertebrates", "jurisdiction": "mainland_china", "protocol": "herp_infrared_camera", "submodule": "reptiles"},
    {"program": "terrestrial_vertebrates", "jurisdiction": "mainland_china", "protocol": "herp_infrared_camera", "submodule": "amphibians"},
    # terrestrial_vertebrates × taiwan
    {"program": "terrestrial_vertebrates", "jurisdiction": "taiwan", "protocol": "bird_line_transect", "submodule": "birds"},
    {"program": "terrestrial_vertebrates", "jurisdiction": "taiwan", "protocol": "bird_point_count", "submodule": "birds"},
    {"program": "terrestrial_vertebrates", "jurisdiction": "taiwan", "protocol": "mammal_trap_net", "submodule": "mammals"},
    {"program": "terrestrial_vertebrates", "jurisdiction": "taiwan", "protocol": "herp_infrared_camera", "submodule": "reptiles"},
    {"program": "terrestrial_vertebrates", "jurisdiction": "taiwan", "protocol": "herp_infrared_camera", "submodule": "amphibians"},
    # plants × both
    {"program": "plants", "jurisdiction": "mainland_china", "protocol": "plant_quadrat", "submodule": "plants"},
    {"program": "plants", "jurisdiction": "mainland_china", "protocol": "plant_transect", "submodule": "plants"},
    {"program": "plants", "jurisdiction": "taiwan", "protocol": "plant_quadrat", "submodule": "plants"},
    {"program": "plants", "jurisdiction": "taiwan", "protocol": "plant_transect", "submodule": "plants"},
    # insects × both
    {"program": "insects", "jurisdiction": "mainland_china", "protocol": "insect_transect", "submodule": "insects"},
    {"program": "insects", "jurisdiction": "taiwan", "protocol": "insect_transect", "submodule": "insects"},
    # aquatic_vertebrates (v1.1) × both
    {"program": "aquatic_vertebrates", "jurisdiction": "mainland_china", "protocol": "fish_electrofishing", "submodule": "freshwater_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "mainland_china", "protocol": "fish_electrofishing", "submodule": "estuarine_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "mainland_china", "protocol": "fish_visual_count", "submodule": "freshwater_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "mainland_china", "protocol": "fish_visual_count", "submodule": "estuarine_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "mainland_china", "protocol": "fish_visual_count", "submodule": "marine_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "taiwan", "protocol": "fish_electrofishing", "submodule": "freshwater_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "taiwan", "protocol": "fish_electrofishing", "submodule": "estuarine_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "taiwan", "protocol": "fish_visual_count", "submodule": "freshwater_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "taiwan", "protocol": "fish_visual_count", "submodule": "estuarine_fish"},
    {"program": "aquatic_vertebrates", "jurisdiction": "taiwan", "protocol": "fish_visual_count", "submodule": "marine_fish"},
    # fungi (v1.1) × both
    {"program": "fungi", "jurisdiction": "mainland_china", "protocol": "fungi_transect", "submodule": "macrofungi"},
    {"program": "fungi", "jurisdiction": "mainland_china", "protocol": "fungi_transect", "submodule": "lichens"},
    {"program": "fungi", "jurisdiction": "mainland_china", "protocol": "fungi_quadrat", "submodule": "macrofungi"},
    {"program": "fungi", "jurisdiction": "mainland_china", "protocol": "fungi_quadrat", "submodule": "lichens"},
    {"program": "fungi", "jurisdiction": "taiwan", "protocol": "fungi_transect", "submodule": "macrofungi"},
    {"program": "fungi", "jurisdiction": "taiwan", "protocol": "fungi_transect", "submodule": "lichens"},
    {"program": "fungi", "jurisdiction": "taiwan", "protocol": "fungi_quadrat", "submodule": "macrofungi"},
    {"program": "fungi", "jurisdiction": "taiwan", "protocol": "fungi_quadrat", "submodule": "lichens"},
]


def _get(base: str, path: str, params: dict[str, Any]) -> tuple[int, dict | None, str]:
    url = f"{base.rstrip('/')}{path}"
    try:
        r = requests.get(url, params=params, timeout=15)
    except requests.RequestException as exc:
        return 0, None, f"{type(exc).__name__}: {exc}"
    body = None
    try:
        body = r.json()
    except ValueError:
        pass
    return r.status_code, body, ""


def _check(name: str, condition: bool, detail: str = "") -> dict:
    status = "PASS" if condition else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f"  -- {detail}"
    print(msg)
    return {"name": name, "status": status, "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000",
                    help="backend base URL (default http://127.0.0.1:8000)")
    ap.add_argument("--limit", type=int, default=25,
                    help="limit value used in the 16-tuple sanity loop (default 25)")
    args = ap.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print(f" Algo-D / P0-W2 :: taxonomy API contract audit")
    print(f"  base    = {args.base}")
    print(f"  tuples  = {len(LEGAL_FIVE_TUPLES)}")
    print("=" * 72)

    # Reachability probe
    code, body, err = _get(args.base, "/api/health", {})
    if code == 0:
        print(f"[FATAL] backend unreachable at {args.base} :: {err}")
        return 3
    print(f"  /api/health -> HTTP {code}")

    checks: list[dict] = []

    # C1: 16-tuple sanity
    print("\n[C1] 16 legal 5-tuples -> 200 OK on /api/surveys/taxonomy/search")
    for tup in LEGAL_FIVE_TUPLES:
        params = dict(tup, limit=args.limit, q="")
        code, body, err = _get(args.base, "/api/surveys/taxonomy/search", params)
        cond = (code == 200)
        detail = f"{tup}  -> HTTP {code}" + (f"  err={err}" if err else "")
        if cond and isinstance(body, dict):
            detail += f"  total={body.get('total')}"
        checks.append(_check(f"5tuple {tup['program']}/{tup['jurisdiction']}/{tup['protocol']}/{tup['submodule']}", cond, detail))

    # C2a: limit=200 -> 200
    code, body, err = _get(args.base, "/api/surveys/taxonomy/search",
                            {"program": "terrestrial_vertebrates",
                             "jurisdiction": "mainland_china",
                             "protocol": "bird_line_transect",
                             "submodule": "birds",
                             "limit": 200})
    checks.append(_check("limit=200 returns 200", code == 200, f"HTTP {code}"))

    # C2b: limit=201 -> 422
    code, body, err = _get(args.base, "/api/surveys/taxonomy/search",
                            {"program": "terrestrial_vertebrates",
                             "jurisdiction": "mainland_china",
                             "protocol": "bird_line_transect",
                             "submodule": "birds",
                             "limit": 201})
    checks.append(_check("limit=201 returns 422", code == 422, f"HTTP {code} (contract says 422)"))

    # C2c: limit=250 -> 422 (reproduces backend_run.log)
    code, body, err = _get(args.base, "/api/surveys/taxonomy/search",
                            {"program": "terrestrial_vertebrates",
                             "jurisdiction": "mainland_china",
                             "protocol": "bird_line_transect",
                             "submodule": "birds",
                             "taxon_group": "birds",
                             "limit": 250})
    checks.append(_check("limit=250 returns 422 (backend_run.log reproduction)", code == 422,
                         f"HTTP {code}"))

    # C3: taxon_group vs submodule equivalence
    code_a, body_a, _ = _get(args.base, "/api/surveys/taxonomy/search",
                              {"program": "terrestrial_vertebrates",
                               "jurisdiction": "mainland_china",
                               "protocol": "bird_line_transect",
                               "taxon_group": "birds",
                               "limit": 25})
    code_b, body_b, _ = _get(args.base, "/api/surveys/taxonomy/search",
                              {"program": "terrestrial_vertebrates",
                               "jurisdiction": "mainland_china",
                               "protocol": "bird_line_transect",
                               "submodule": "birds",
                               "limit": 25})
    if isinstance(body_a, dict) and isinstance(body_b, dict):
        equal = (body_a.get("total") == body_b.get("total"))
        checks.append(_check("taxon_group=birds <=> submodule=birds (same total)",
                             equal, f"taxon_group total={body_a.get('total')} vs submodule total={body_b.get('total')}"))
    else:
        checks.append(_check("taxon_group=birds <=> submodule=birds (same total)", False,
                             f"http codes a={code_a} b={code_b}"))

    # C4: /packages and /protocols smoke
    code, body, _ = _get(args.base, "/api/surveys/taxonomy/packages",
                          {"jurisdiction": "mainland_china", "program": "terrestrial_vertebrates"})
    checks.append(_check("/packages returns 200", code == 200, f"HTTP {code}"))
    code, body, _ = _get(args.base, "/api/surveys/protocols", {"program": "terrestrial_vertebrates"})
    checks.append(_check("/protocols returns 200", code == 200, f"HTTP {code}"))

    # Summary
    passes = sum(1 for c in checks if c["status"] == "PASS")
    fails = sum(1 for c in checks if c["status"] == "FAIL")
    print("=" * 72)
    print(f"  {passes} PASS / {fails} FAIL out of {len(checks)} checks")
    print("=" * 72)

    REPORT_PATH.write_text(json.dumps({
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "base": args.base,
        "passes": passes,
        "fails": fails,
        "checks": checks,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  report: {REPORT_PATH}")

    return 0 if fails == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
