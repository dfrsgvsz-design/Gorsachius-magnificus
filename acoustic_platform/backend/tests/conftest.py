"""Test path bootstrap for workspace-shared backend modules."""

import os
import sys
import tempfile
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[1]

for path in (WORKSPACE_ROOT, BACKEND_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

if "FRONTEND_DIST_DIR" not in os.environ:
    _stub_dist = Path(tempfile.mkdtemp(prefix="conftest_frontend_dist_"))
    (_stub_dist / "index.html").write_text(
        "<!doctype html><title>test-stub</title>", encoding="utf-8"
    )
    os.environ["FRONTEND_DIST_DIR"] = str(_stub_dist)
