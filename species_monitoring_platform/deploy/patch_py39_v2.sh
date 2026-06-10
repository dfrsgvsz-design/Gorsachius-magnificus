#!/usr/bin/env bash
# v2: handle CRLF + use Python for reliable UTC import patching.
set -e
ROOT=/opt/gm-backend
LOG=/var/log/gm-deploy/patch_py39_v2.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="

UTC_FILES=(
  "$ROOT/shared/backend/export/darwin_core_exporter.py"
  "$ROOT/shared/backend/analysis/fewshot_detector.py"
  "$ROOT/backend/survey_store.py"
  "$ROOT/backend/survey_report.py"
  "$ROOT/backend/realtime.py"
  "$ROOT/backend/multimodal_survey.py"
  "$ROOT/backend/device_manager.py"
  "$ROOT/backend/detection_store.py"
)

echo "---- step 0: strip CRLF ----"
for f in "${UTC_FILES[@]}"; do
  if [ -f "$f" ]; then
    sed -i 's/\r$//' "$f"
  fi
done

echo "---- step 1: Python-based UTC patcher ----"
"$ROOT/.venv/bin/python" - <<'PY'
import re, sys
files = [
  "/opt/gm-backend/shared/backend/export/darwin_core_exporter.py",
  "/opt/gm-backend/shared/backend/analysis/fewshot_detector.py",
  "/opt/gm-backend/backend/survey_store.py",
  "/opt/gm-backend/backend/survey_report.py",
  "/opt/gm-backend/backend/realtime.py",
  "/opt/gm-backend/backend/multimodal_survey.py",
  "/opt/gm-backend/backend/device_manager.py",
  "/opt/gm-backend/backend/detection_store.py",
]
import_re = re.compile(r"^from datetime import (.+)$", re.MULTILINE)
for f in files:
    try:
        src = open(f, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"  SKIP missing {f}")
        continue
    if "UTC = timezone.utc" in src:
        print(f"  SKIP already patched {f}")
        continue
    m = import_re.search(src)
    if not m:
        print(f"  WARN: no datetime import found in {f}")
        continue
    parts_orig = m.group(1)
    parts = [p.strip() for p in parts_orig.split(",")]
    if "UTC" not in parts:
        print(f"  SKIP no UTC in import {f}")
        continue
    parts = [p for p in parts if p != "UTC"]
    if "timezone" not in parts:
        parts.append("timezone")
    new_import = "from datetime import " + ", ".join(parts) + "\nUTC = timezone.utc"
    new_src = src.replace(m.group(0), new_import, 1)
    open(f, "w", encoding="utf-8").write(new_src)
    print(f"  PATCH {f}")
    print(f"    old: {m.group(0)}")
    print(f"    new (line 1): {new_import.splitlines()[0]}")
PY

echo "---- step 2: PEP 604 future annotations ----"
PEP604_FILES=(
  "$ROOT/shared/backend/clients/ebird_client.py"
  "$ROOT/shared/backend/utils/runtime_paths.py"
  "$ROOT/backend/runtime_paths.py"
  "$ROOT/backend/routes/biodiversity_routes.py"
  "$ROOT/backend/routes/images.py"
  "$ROOT/backend/routes/taxonomy.py"
)
for f in "${PEP604_FILES[@]}"; do
  if [ -f "$f" ] && ! grep -q 'from __future__ import annotations' "$f"; then
    sed -i 's/\r$//' "$f"
    sed -i '1i from __future__ import annotations' "$f"
    echo "  PATCH $f"
  fi
done

echo "---- step 3: backend.main import verification ----"
cd "$ROOT"
.venv/bin/python -c 'import backend.main; print("backend.main OK")' 2>&1 | tail -25

echo "==== END $(date -Is) ===="
