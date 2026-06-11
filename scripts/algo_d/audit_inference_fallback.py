"""Algo-D / P2-W3 audit: verify the inference_fallback module is wired up.

Runs four checks WITHOUT requiring birdnet / birdnetlib / actual GPU:

  F1 module imports cleanly
  F2 tiers_status() shape is correct
  F3 predict_species_fallback() returns canonical shape even when no tier
     is available (graceful degradation)
  F4 safe_predict_species() catches a faked OOM RuntimeError and routes
     through the fallback path

Exit codes:
  0 = all checks PASS
  2 = at least one check FAIL
  3 = module not importable at all
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "species_monitoring_platform" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

ARTIFACTS_DIR = Path(__file__).resolve().parent / "_artifacts"
REPORT_PATH = ARTIFACTS_DIR / "inference_fallback_report.json"


REQUIRED_CANONICAL_FIELDS = {"species_scientific", "species_chinese", "species_english",
                              "confidence", "reliable"}
REQUIRED_META_FIELDS = {"fallback_engine", "fallback_reason"}


def _check(name: str, condition: bool, detail: str = "") -> dict:
    status = "PASS" if condition else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f"  -- {detail}"
    print(msg)
    return {"name": name, "status": status, "detail": detail}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake-oom", action="store_true",
                    help="run an explicit OOM-simulation test via safe_predict_species")
    args = ap.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []

    print("=" * 72)
    print(" Algo-D / P2-W3 :: inference_fallback audit")
    print("=" * 72)

    # F1: module imports
    try:
        import inference_fallback as fb  # noqa: WPS433
    except Exception as exc:  # pragma: no cover
        print(f"[FATAL] cannot import inference_fallback: {exc}")
        return 3
    checks.append(_check("F1 module imports cleanly", True, "ok"))

    # F2: tiers_status shape
    status = fb.tiers_status()
    expected_keys = {"tier1_birdnet_embedding", "tier1_knn_index", "tier2_birdnet_classifier"}
    f2_ok = isinstance(status, dict) and set(status) == expected_keys
    checks.append(_check("F2 tiers_status() shape correct", f2_ok,
                         f"keys={sorted(status) if isinstance(status, dict) else status}"))

    # F3: predict_species_fallback graceful degradation on a non-existent path
    fake_path = str(Path(tempfile.gettempdir()) / "algo_d_no_such_file.wav")
    result = fb.predict_species_fallback(fake_path, top_k=3, reason="audit_smoke")
    f3_shape_ok = (
        isinstance(result, list)
        and len(result) >= 1
        and isinstance(result[0], dict)
        and REQUIRED_CANONICAL_FIELDS.issubset(set(result[0].keys()))
    )
    f3_meta_ok = (
        isinstance(result[0].get("_meta"), dict)
        and REQUIRED_META_FIELDS.issubset(set(result[0]["_meta"].keys()))
    )
    f3_engine = result[0].get("_meta", {}).get("fallback_engine")
    checks.append(_check("F3a predict_species_fallback returns canonical shape",
                         f3_shape_ok,
                         f"top1_keys={sorted(result[0].keys()) if result else '[]'}"))
    checks.append(_check("F3b _meta has fallback_engine and fallback_reason",
                         f3_meta_ok,
                         f"engine={f3_engine}"))

    # F4: safe_predict_species catches OOM-like RuntimeError and falls back
    def fake_primary_oom(**_kwargs):
        raise RuntimeError("CUDA out of memory. Tried to allocate 4.00 GiB")

    f4_result = fb.safe_predict_species(
        primary=fake_primary_oom,
        primary_kwargs={"mel": None, "top_k": 3},
        audio_path=fake_path,
        top_k=3,
    )
    f4_engine = (f4_result[0].get("_meta") or {}).get("fallback_engine") if f4_result else None
    f4_reason = (f4_result[0].get("_meta") or {}).get("fallback_reason") if f4_result else None
    f4_ok = (
        isinstance(f4_result, list)
        and len(f4_result) >= 1
        and (f4_result[0].get("_meta") or {}).get("fallback_reason") == "out_of_memory"
    )
    checks.append(_check("F4 safe_predict_species catches OOM-like exception",
                         f4_ok,
                         f"engine={f4_engine} reason={f4_reason}"))

    # Optional explicit fake-oom block (mostly an alias for F4, but with verbose output)
    if args.fake_oom:
        print("\n[debug] full F4 result:")
        print(json.dumps(f4_result, ensure_ascii=False, indent=2)[:1500])

    passes = sum(1 for c in checks if c["status"] == "PASS")
    fails = sum(1 for c in checks if c["status"] == "FAIL")
    print("=" * 72)
    print(f"  {passes} PASS / {fails} FAIL out of {len(checks)} checks")
    print(f"  tier status snapshot: {json.dumps(status, ensure_ascii=False)[:400]}")
    print("=" * 72)

    REPORT_PATH.write_text(json.dumps({
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "passes": passes,
        "fails": fails,
        "checks": checks,
        "tiers_status_snapshot": status,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  report: {REPORT_PATH}")
    return 0 if fails == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
