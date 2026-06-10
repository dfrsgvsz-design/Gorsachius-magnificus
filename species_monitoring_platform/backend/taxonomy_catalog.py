"""Backward-compatible re-export from shared package.

Resolved drift: the species and acoustic platforms each used to ship a
~108 KB copy of this module that had drifted ~770 bytes apart. The
species copy was the superset (newer SQL escape helper, extra search
result fields, stricter release-activation validation), so it became the
canonical source. The shared module lives at
``shared/backend/stores/taxonomy_catalog.py`` and respects
``BIRD_PLATFORM_BACKEND_DIR`` / ``SURVEY_DATA_DIR`` for storage paths
(see ``runtime_paths.py``).
"""
from shared.backend.stores.taxonomy_catalog import *  # noqa: F401, F403
