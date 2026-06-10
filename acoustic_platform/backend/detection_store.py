"""Backward-compatible re-export from shared package.

Resolved drift: the species and acoustic platforms each used to ship a
~15.5 KB copy of this module. The acoustic copy was the refactored
version that extracted ``_add_detection_no_commit`` as a private helper
so that ``add_detection`` and ``batch_add`` can share insertion logic
without re-acquiring the connection lock; species was the older inline
version. We picked the acoustic refactor as the canonical baseline.
The shared module lives at ``shared/backend/stores/detection_store.py``.
"""
from shared.backend.stores.detection_store import *  # noqa: F401, F403
