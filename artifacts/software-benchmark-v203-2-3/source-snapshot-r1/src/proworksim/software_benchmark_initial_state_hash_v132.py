"""The exact legacy initial-business-state JSON digest, emitted in bounded chunks.

The persistent world and every immutable version retain their original bytes.
Only the audit hash calculation changes: no complete hex string or complete
serialized JSON is retained. This code performs no model or world operation.
"""
from __future__ import annotations

import hashlib
import json
from json.encoder import encode_basestring
import os


VERSION = "v132-exact-streamed-initial-business-state-hash-r1"
TEXT_CHUNK = 8192
FILE_CHUNK = 1024 * 1024


def _string(value):
    yield '"'
    for offset in range(0, len(value), TEXT_CHUNK):
        yield encode_basestring(value[offset:offset + TEXT_CHUNK])[1:-1]
    yield '"'


def _excluded(key, path):
    return ((not path and key in {"instance_id", "branch_id", "parent_branch_id"})
            or (key == "wall_seconds" and len(path) == 2 and path[0] == "interactions")
            or (key == "state_digests" and path and path[-1] in {"receipt", "transition"}))


def _key(value):
    if isinstance(value, str):
        return value
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return json.dumps(value, allow_nan=False)
    raise TypeError("Only the legacy JSON dictionary key types are supported")


def _parts(value, level, *, path=(), normalize=False):
    if isinstance(value, dict):
        yield "{"
        first = True
        for key, item in value.items():
            if normalize and _excluded(key, path):
                continue
            yield ("\n" if first else ",\n") + "  " * (level + 1)
            first = False
            yield from _string(_key(key))
            yield ": "
            yield from _parts(item, level + 1, path=path + (key,), normalize=normalize)
        if not first:
            yield "\n" + "  " * level
        yield "}"
    elif isinstance(value, (list, tuple)):
        yield "["
        for index, item in enumerate(value):
            yield ("\n" if index == 0 else ",\n") + "  " * (level + 1)
            # Legacy normalize traverses lists, but leaves tuples untouched.
            yield from _parts(item, level + 1, path=path + (index,),
                              normalize=normalize and isinstance(value, list))
        if value:
            yield "\n" + "  " * level
        yield "]"
    elif isinstance(value, str):
        yield from _string(value)
    else:
        yield json.dumps(value, ensure_ascii=False, allow_nan=False)


def measure_initial_business_state(world):
    """Hash exactly json_bytes(initial_business_state(world)), under its lock.

    The old normalization exclusions, insertion order, indentation, Unicode,
    full immutable-file bytes encoded as lowercase hex and final newline are
    all preserved. Holding the world lock prevents a concurrent operation from
    changing the source while its serialization is streamed.
    """
    sha = hashlib.sha256()
    emitted = immutable_bytes = versions = 0
    def emit(value):
        nonlocal emitted
        raw = value.encode("utf-8") if isinstance(value, str) else value
        sha.update(raw)
        emitted += len(raw)
    with world.store.lock():
        state = world.state
        emit('{\n  "state": ')
        for part in _parts(state, 1, normalize=True):
            emit(part)
        emit(',\n  "immutable_files": {')
        first = True
        for oid, artifact in state["artifacts"].items():
            for version in artifact["versions"]:
                emit("\n    " if first else ",\n    ")
                first = False
                for part in _string(oid + ":" + version):
                    emit(part)
                emit(': "')
                with world.store.version_path(artifact, version).open("rb") as source:
                    before = os.fstat(source.fileno())
                    for chunk in iter(lambda: source.read(FILE_CHUNK), b""):
                        immutable_bytes += len(chunk)
                        emit(chunk.hex())
                    after = os.fstat(source.fileno())
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError("An immutable version changed while its audit hash was read")
                emit('"')
                versions += 1
        if not first:
            emit("\n  ")
        emit("}\n}\n")
    return {"version": VERSION, "sha256": sha.hexdigest(), "hashed_bytes": emitted,
            "immutable_bytes": immutable_bytes, "immutable_versions": versions,
            "whole_file_hex_materialized": False, "whole_JSON_materialized": False,
            "world_modified": False}


def initial_business_state_digest(world):
    return measure_initial_business_state(world)["sha256"]
