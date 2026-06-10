"""Backward-compatible re-export from shared package.

Resolved drift: the species and acoustic platforms each used to ship a
~225-237 KB copy of this module that drifted ~12 KB apart. The species
copy was the superset (added audit logging, soft-delete trash management,
restore + purge workflow, and context-manager support), so it became the
canonical source. The shared module lives at
``shared/backend/stores/survey_store.py``.

Private helpers (``_load_vertebrate_export_profiles``,
``_taxonomy_entry_for_observation``) are re-exported explicitly because
``from ... import *`` does not pull names prefixed with ``_``; the
test suite reaches into these helpers for white-box coverage.
"""
from shared.backend.stores.survey_store import *  # noqa: F401, F403
from shared.backend.stores.survey_store import (  # noqa: F401
    _load_vertebrate_export_profiles,
    _taxonomy_entry_for_observation,
)
