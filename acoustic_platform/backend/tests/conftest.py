"""Test path bootstrap for workspace-shared backend modules."""

import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[1]

for path in (WORKSPACE_ROOT, BACKEND_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)
