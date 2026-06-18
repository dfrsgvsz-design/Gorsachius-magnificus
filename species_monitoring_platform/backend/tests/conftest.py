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

# CI runners execute backend tests without building the SPA first, but main.py
# only registers the "/" route when the frontend dist exists at import time,
# and test_api_smoke's rate-limit spec asserts "/" responds 200. When neither
# a real build output nor an explicit override is available, stage a one-page
# stub via FRONTEND_DIST_DIR before main.py gets imported.
if not os.environ.get("FRONTEND_DIST_DIR"):
    _real_dist = BACKEND_ROOT.parent / "frontend" / "dist"
    if not (_real_dist / "index.html").exists():
        _stub_dist = Path(tempfile.mkdtemp(prefix="stub_frontend_dist_"))
        (_stub_dist / "index.html").write_text(
            "<!doctype html><html><head><title>stub shell</title></head>"
            '<body><div id="root"></div></body></html>',
            encoding="utf-8",
        )
        os.environ["FRONTEND_DIST_DIR"] = str(_stub_dist)
