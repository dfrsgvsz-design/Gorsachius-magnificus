"""Algo-D / P0-W1 CI gate: thin wrapper around audit_species_head_gap.py.

Returns a single-line PASS/FAIL summary and the exit code from the audit
(0 = PASS, 2 = FAIL gap, 3 = inputs missing). Intended for use in CI
where you only care about the gate decision, not the full report.

Usage:
  python scripts/algo_d/validate_head_consistency.py
  python scripts/algo_d/validate_head_consistency.py --strict   # also runs the backend loader path-check in STRICT mode
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

HERE = Path(__file__).resolve().parent
AUDIT_PATH = HERE / "audit_species_head_gap.py"
REPO_ROOT = HERE.parents[1]
BACKEND_DIR = REPO_ROOT / "species_monitoring_platform" / "backend"


def run_audit() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(AUDIT_PATH)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout + proc.stderr


def run_loader_dry_check() -> tuple[int, str]:
    """Smoke-test that the loader patch in main.py would fail-fast under STRICT."""
    code = (
        "import os, sys, json\n"
        f"sys.path.insert(0, r'{BACKEND_DIR}')\n"
        "os.environ['ALGO_D_STRICT_HEAD_MATCH'] = '1'\n"
        "from pathlib import Path\n"
        "from main import _align_species_mapping_to_checkpoint\n"
        "import main as _m\n"
        "# fabricate a mapping > head; we only test the function logic, no torch needed\n"
        "_m.species_mapping = {f'sp_{i}': i for i in range(10)}\n"
        "_m.idx_to_species  = {i: f'sp_{i}' for i in range(10)}\n"
        "try:\n"
        "    _align_species_mapping_to_checkpoint(7)\n"
        "    print('LOADER_DRY: FAIL  (strict mode did not raise)')\n"
        "    sys.exit(2)\n"
        "except RuntimeError as e:\n"
        "    print(f'LOADER_DRY: PASS  (strict mode raised: {e})')\n"
        "    sys.exit(0)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="also dry-run the loader fail-fast path")
    args = ap.parse_args()

    audit_exit, audit_out = run_audit()
    last_line = audit_out.strip().splitlines()[-1] if audit_out.strip() else "(no output)"
    if audit_exit == 0:
        print(f"G1  audit          : PASS  ({last_line})")
    elif audit_exit == 2:
        print(f"G1  audit          : FAIL  ({last_line})")
        print(audit_out)
    else:
        print(f"G1  audit          : ERROR (exit={audit_exit}) ({last_line})")
        print(audit_out)

    overall = audit_exit
    if args.strict:
        loader_exit, loader_out = run_loader_dry_check()
        last = loader_out.strip().splitlines()[-1] if loader_out.strip() else "(no output)"
        if loader_exit == 0:
            print(f"G1b loader STRICT  : PASS  ({last})")
        else:
            print(f"G1b loader STRICT  : FAIL  ({last})")
            print(loader_out)
            overall = overall or loader_exit
    return overall


if __name__ == "__main__":
    sys.exit(main())
