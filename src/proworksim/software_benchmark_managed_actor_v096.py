"""Original private actor protocol with the separately qualified tree-sync fix."""
from __future__ import annotations

from . import software_benchmark_managed_actor_v064 as original
from .software_benchmark_managed_sync_v095 import synchronize_tree as repaired_sync

# This module exports the original wire and validators without changing that
# frozen module's dictionary. The actor entrypoint selects this module explicitly.
globals().update({key: value for key, value in vars(original).items() if not key.startswith('__')})
synchronize_tree = repaired_sync
SYNC_REVISION = 'v095-private-managed-atomic-tree-sync-r1'
