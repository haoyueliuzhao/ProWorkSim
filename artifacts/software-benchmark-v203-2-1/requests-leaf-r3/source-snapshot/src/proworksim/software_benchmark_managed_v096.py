"""Original aligned managed runtime with exact nullable-cursor restoration."""
from __future__ import annotations

from functools import cache

from . import software_benchmark_managed_v064 as original
from .software_benchmark_nullable_cursor_v090 import install_project_nullable_cursors

globals().update({key: value for key, value in vars(original).items() if not key.startswith('__')})
REPAIR_REVISION = 'v096-aligned-managed-nullable-cursor-r1'


@cache
def worker_type():
    class RepairedAlignedManagedWorker(original.worker_type()):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            try:
                install_project_nullable_cursors(self)
            except BaseException:
                self.close()
                raise
    return RepairedAlignedManagedWorker


def build_runtime(*args, worker_factory=None, **kwargs):
    return original.build_runtime(*args, worker_factory=worker_factory or worker_type(), **kwargs)
