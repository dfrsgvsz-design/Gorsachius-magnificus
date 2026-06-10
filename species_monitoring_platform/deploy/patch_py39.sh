#!/usr/bin/env bash
# Patch backend code for Python 3.9 compatibility:
#   1. `from datetime import ... UTC` is 3.11+ only -> shim with timezone.utc
#   2. PEP 604 union types (X | Y) -> add `from __future__ import annotations`
set -e
ROOT=/opt/gm-backend
LOG=/var/log/gm-deploy/patch_py39.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="
echo "---- step 1: UTC import shim ----"

# Files using `from datetime import ... UTC ...`
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

for f in "${UTC_FILES[@]}"; do
  if [ ! -f "$f" ]; then
    echo "  SKIP missing $f"; continue
  fi
  if grep -q '^UTC = timezone.utc$' "$f"; then
    echo "  SKIP already patched $f"; continue
  fi
  echo "  PATCH $f"
  # 3 patterns: order varies
  sed -i \
    -e 's/^from datetime import datetime, UTC, timedelta$/from datetime import datetime, timedelta, timezone\nUTC = timezone.utc/' \
    -e 's/^from datetime import datetime, UTC$/from datetime import datetime, timezone\nUTC = timezone.utc/' \
    -e 's/^from datetime import UTC, datetime, timedelta$/from datetime import datetime, timedelta, timezone\nUTC = timezone.utc/' \
    -e 's/^from datetime import UTC, datetime$/from datetime import datetime, timezone\nUTC = timezone.utc/' \
    "$f"
  # Verify the line is now gone
  if grep -nE '^from datetime import.*\bUTC\b' "$f"; then
    echo "  WARN: still has UTC in datetime import: $f"
  fi
done

echo "---- step 2: PEP 604 union (X | Y) -> future annotations ----"

# Files using PEP 604 union types
PEP604_FILES=(
  "$ROOT/shared/backend/clients/ebird_client.py"
  "$ROOT/shared/backend/utils/runtime_paths.py"
  "$ROOT/backend/runtime_paths.py"
  "$ROOT/backend/routes/biodiversity_routes.py"
  "$ROOT/backend/routes/images.py"
  "$ROOT/backend/routes/taxonomy.py"
)

for f in "${PEP604_FILES[@]}"; do
  if [ ! -f "$f" ]; then
    echo "  SKIP missing $f"; continue
  fi
  if grep -q 'from __future__ import annotations' "$f"; then
    echo "  SKIP already has future annotations $f"; continue
  fi
  echo "  PATCH $f"
  sed -i '1i from __future__ import annotations' "$f"
done

echo "---- step 3: import verification ----"
cd "$ROOT"
.venv/bin/python -c 'import backend.main; print("backend.main OK")' 2>&1 | tail -20

echo "==== END $(date -Is) ===="
