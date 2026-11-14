"""One committed-state cache for the v054 managed world only.

The writer, canonical JSON bytes, durability and world lock remain Store's.
Only repeated reads of the same committed file avoid decoding it again.
"""
from __future__ import annotations

import copy

from .storage import Store


def _identity(path):
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class CachedStateStore(Store):
    """Cache at most one decoded on-disk state, never a caller's working state.

    Callers retain the existing single-writer flock discipline. A cache hit
    copies all mutable descendants; large immutable strings may be shared.
    Stat before/after a copy or read detects a foreign atomic replacement and
    any observable metadata change. As with Store.save, all world writers must
    use atomic replacement; metadata-identical in-place writes are outside
    this cache protocol. A changed read is returned without installing a cache, as
    the original Store also returns its one actual read under the world lock.
    """

    def __init__(self, root):
        super().__init__(root)
        self._state_cache = None

    def load(self):
        path = self.control / "state.json"
        try:
            before = _identity(path)
            cached = self._state_cache
            if cached is not None and cached[0] == before:
                result = copy.deepcopy(cached[1])
                if _identity(path) == before:
                    return result
                # Never publish a cached value after detecting a newer file.
                del result
                before = _identity(path)
            self._state_cache = None
            state = super().load()
            if _identity(path) == before:
                # This value has passed the original JSON round trip. In
                # particular it has no caller aliases, tuples or non-str keys.
                self._state_cache = (before, state)
                return copy.deepcopy(state)
            return state
        except BaseException:
            self._state_cache = None
            raise

    def save(self, state):
        # Invalidating also on failure keeps unsaved mutations out of load.
        # Do not deepcopy the input into the cache: JSON normalizes tuples,
        # keys and aliases, and may reject values before any commit occurs.
        self._state_cache = None
        try:
            return super().save(state)
        finally:
            self._state_cache = None
