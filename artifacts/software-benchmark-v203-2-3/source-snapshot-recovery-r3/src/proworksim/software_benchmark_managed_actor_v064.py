"""Whole-tree-bound deltas and fixed public tests inside a private actor.

No command comes from a model/tool argument. Runtime callers must supply the
already isolated actor root; importing this module does not perform operations.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import uuid

from .repository_sources_v054 import (
    decode_entry, is_readonly, normalize_policy, snapshot_repository, tree_manifest, validate_tree,
)
from .software_benchmark_gitlinks_v054 import check_gitlink_payload, checked_gitlinks
from .storage import digest

VERSION = "v064-managed-actor-rpc-r1"
PUBLIC_ENTRY_VERSION = "v064-repository-public-test-entry-r1"
MAX_RPC_BYTES = 32 * 1024**2
MAX_OUTPUT_BYTES = 32 * 1024**2
UPLOAD_VERSION = "v064-managed-internal-chunked-upload-r1"
UPLOAD_CHUNK_BYTES = 1024**2
MAX_UPLOAD_BYTES = 2 * 1024**3
UPLOAD_BEGIN = "managed_upload_begin"
UPLOAD_CHUNK = "managed_upload_chunk"
UPLOAD_COMMIT = "managed_upload_commit"
MANAGED_OPERATIONS = frozenset(("managed_public_test", "sync_terminal"))


class ManagedInterfaceLimit(ValueError):
    classification = "interface_coverage_limit"


class ManagedTransferError(ValueError):
    """Internal transport is unknown; this is never a model repair verdict."""
    classification = "interface_unknown"


def upload_protocol():
    return {"version": UPLOAD_VERSION, "chunk_bytes": UPLOAD_CHUNK_BYTES,
            "maximum_payload_bytes": MAX_UPLOAD_BYTES, "maximum_pending_uploads": 1,
            "per_frame_bytes": MAX_RPC_BYTES, "model_tools_added": False}


def _hex(value, length):
    return isinstance(value, str) and len(value) == length and all(c in "0123456789abcdef" for c in value)


def _check_deadline(deadline, clock):
    if (type(deadline) not in (int, float) or not math.isfinite(deadline)
            or not clock() < deadline):
        raise ManagedTransferError("Managed upload exceeded its original episode deadline")


def _json_parts(value):
    """Encode large strings in bounded pieces instead of allocating a whole wire."""
    if isinstance(value, str):
        yield b'"'
        for start in range(0, len(value), 65536):
            yield json.dumps(value[start:start + 65536], ensure_ascii=False,
                             allow_nan=False)[1:-1].encode("utf-8")
        yield b'"'
    elif isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ManagedTransferError("Internal payload object keys must be strings")
        yield b"{"
        # Existing source/tree bindings preserve object insertion order; sorting
        # metadata keys here would change their strict JSON-based identities.
        for index, key in enumerate(value):
            if index:
                yield b","
            yield from _json_parts(key)
            yield b":"
            yield from _json_parts(value[key])
        yield b"}"
    elif isinstance(value, list):
        yield b"["
        for index, item in enumerate(value):
            if index:
                yield b","
            yield from _json_parts(item)
        yield b"]"
    elif value is None or type(value) in (bool, int, float):
        yield json.dumps(value, allow_nan=False).encode("ascii")
    else:
        raise ManagedTransferError("Unsupported non-JSON internal payload value")


@contextmanager
def prepare_payload_upload(payload, operation, *, directory, hard_at, clock=time.monotonic):
    """Only an ephemeral owned file holds the complete transport serialization."""
    _check_deadline(hard_at, clock)
    if (operation not in MANAGED_OPERATIONS or not isinstance(payload, dict)
            or not isinstance(payload.get("request"), dict)
            or payload["request"].get("hard_deadline_monotonic") != hard_at):
        raise ManagedTransferError("Upload must bind one permitted operation and its exact episode deadline")
    directory = Path(directory)
    if directory.is_symlink():
        raise ManagedTransferError("Managed upload storage cannot follow a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=directory) as stream:
        sha, size = hashlib.sha256(), 0
        try:
            for part in _json_parts(payload):
                _check_deadline(hard_at, clock)
                if size + len(part) > MAX_UPLOAD_BYTES:
                    raise ManagedTransferError("Complete managed payload exceeds the 2-GiB upload bound")
                stream.write(part)
                sha.update(part)
                size += len(part)
            stream.flush()
            stream.seek(0)
            manifest = {"version": UPLOAD_VERSION, "upload_id": uuid.uuid4().hex,
                        "operation": operation, "payload_bytes": size, "payload_sha256": sha.hexdigest(),
                        "chunk_bytes": UPLOAD_CHUNK_BYTES,
                        "chunks": (size + UPLOAD_CHUNK_BYTES - 1) // UPLOAD_CHUNK_BYTES,
                        "hard_deadline_monotonic": hard_at, "request": copy.deepcopy(payload["request"]),
                        "baseline_tree_sha256": payload.get("baseline_tree_sha256"),
                        "candidate_tree_sha256": payload.get("candidate_tree_sha256")}
            yield manifest, stream
        except ManagedTransferError:
            raise
        except Exception as error:
            raise ManagedTransferError("Managed upload preparation or transport failed: " + str(error)) from error


def upload_chunks(manifest, stream, *, clock=time.monotonic):
    offset = 0
    for index in range(manifest["chunks"]):
        _check_deadline(manifest["hard_deadline_monotonic"], clock)
        raw = stream.read(manifest["chunk_bytes"])
        expected = min(manifest["chunk_bytes"], manifest["payload_bytes"] - offset)
        if len(raw) != expected:
            raise ManagedTransferError("Prepared upload bytes disappeared before transfer")
        yield {"version": UPLOAD_VERSION, "upload_id": manifest["upload_id"], "index": index,
               "offset": offset, "bytes": len(raw), "sha256": digest(raw),
               "data_base64": base64.b64encode(raw).decode("ascii")}
        offset += len(raw)
    if offset != manifest["payload_bytes"] or stream.read(1):
        raise ManagedTransferError("Prepared upload length changed")


class ManagedUploadReceiver:
    """One sequential, hash-verified pending payload in this private actor only."""
    def __init__(self, directory, *, hard_at, clock=time.monotonic):
        _check_deadline(hard_at, clock)
        self.directory, self.hard_at, self.clock = Path(directory), hard_at, clock
        if self.directory.is_symlink():
            raise ManagedTransferError("Actor upload storage cannot be a symlink")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.pending, self.used_ids, self.failed = None, set(), False

    def abort(self):
        self.failed = True
        if self.pending is not None:
            self.pending["stream"].close()
            self.pending = None

    def _guard(self):
        if self.failed:
            raise ManagedTransferError("An uncertain upload cannot be replayed in this actor")
        _check_deadline(self.hard_at, self.clock)

    def begin(self, manifest):
        try:
            self._guard()
            fields = {"version", "upload_id", "operation", "payload_bytes", "payload_sha256", "chunk_bytes",
                      "chunks", "hard_deadline_monotonic", "request", "baseline_tree_sha256", "candidate_tree_sha256"}
            if (not isinstance(manifest, dict) or set(manifest) != fields or self.pending is not None
                    or manifest["version"] != UPLOAD_VERSION or not _hex(manifest["upload_id"], 32)
                    or manifest["upload_id"] in self.used_ids or manifest["operation"] not in MANAGED_OPERATIONS
                    or type(manifest["payload_bytes"]) is not int or not 0 < manifest["payload_bytes"] <= MAX_UPLOAD_BYTES
                    or not _hex(manifest["payload_sha256"], 64) or manifest["chunk_bytes"] != UPLOAD_CHUNK_BYTES
                    or type(manifest["chunks"]) is not int
                    or manifest["chunks"] != (manifest["payload_bytes"] + UPLOAD_CHUNK_BYTES - 1) // UPLOAD_CHUNK_BYTES
                    or not isinstance(manifest["request"], dict)
                    or manifest["request"].get("hard_deadline_monotonic") != manifest["hard_deadline_monotonic"]
                    or manifest["hard_deadline_monotonic"] > self.hard_at):
                raise ManagedTransferError("Invalid, reused or concurrent managed upload manifest")
            _check_deadline(manifest["hard_deadline_monotonic"], self.clock)
            if self.directory.is_symlink():
                raise ManagedTransferError("Actor upload storage identity changed")
            self.pending = {"manifest": copy.deepcopy(manifest),
                            "stream": tempfile.TemporaryFile(dir=self.directory),
                            "sha": hashlib.sha256(), "received": 0, "next_index": 0}
            self.used_ids.add(manifest["upload_id"])
            return {"upload_id": manifest["upload_id"], "accepted": True, "received_bytes": 0,
                    "next_index": 0, "operation_executed": False}
        except Exception as error:
            self.abort()
            if isinstance(error, ManagedTransferError):
                raise
            raise ManagedTransferError("Managed upload begin failed: " + str(error)) from error

    def chunk(self, value):
        try:
            self._guard()
            pending = self.pending
            if pending is None:
                raise ManagedTransferError("No pending upload accepts this chunk")
            manifest = pending["manifest"]
            _check_deadline(manifest["hard_deadline_monotonic"], self.clock)
            if (not isinstance(value, dict) or set(value) != {"version", "upload_id", "index", "offset", "bytes", "sha256", "data_base64"}
                    or value["version"] != UPLOAD_VERSION or value["upload_id"] != manifest["upload_id"]
                    or type(value["index"]) is not int or value["index"] != pending["next_index"]
                    or value["index"] >= manifest["chunks"] or type(value["offset"]) is not int
                    or value["offset"] != pending["received"] or type(value["bytes"]) is not int
                    or value["bytes"] != min(UPLOAD_CHUNK_BYTES, manifest["payload_bytes"] - pending["received"])
                    or not _hex(value["sha256"], 64) or not isinstance(value["data_base64"], str)
                    or len(value["data_base64"]) > ((UPLOAD_CHUNK_BYTES + 2) // 3) * 4):
                raise ManagedTransferError("Managed upload chunk order, identity or length differs")
            try:
                raw = base64.b64decode(value["data_base64"], validate=True)
            except (ValueError, binascii.Error) as error:
                raise ManagedTransferError("Invalid chunk base64") from error
            if (len(raw) != value["bytes"] or digest(raw) != value["sha256"]
                    or base64.b64encode(raw).decode("ascii") != value["data_base64"]):
                raise ManagedTransferError("Managed upload chunk content does not match its exact hash")
            pending["stream"].write(raw)
            pending["sha"].update(raw)
            pending["received"] += len(raw)
            pending["next_index"] += 1
            return {"upload_id": manifest["upload_id"], "received_bytes": pending["received"],
                    "next_index": pending["next_index"], "operation_executed": False}
        except Exception as error:
            self.abort()
            if isinstance(error, ManagedTransferError):
                raise
            raise ManagedTransferError("Managed upload chunk failed: " + str(error)) from error

    def commit(self, value):
        try:
            self._guard()
            pending = self.pending
            if pending is None:
                raise ManagedTransferError("No complete pending upload may commit")
            manifest = pending["manifest"]
            _check_deadline(manifest["hard_deadline_monotonic"], self.clock)
            if (not isinstance(value, dict) or set(value) != {"version", "upload_id", "payload_bytes", "payload_sha256"}
                    or any(value.get(key) != manifest[key] for key in value)
                    or pending["received"] != manifest["payload_bytes"]
                    or pending["next_index"] != manifest["chunks"]
                    or pending["sha"].hexdigest() != manifest["payload_sha256"]):
                raise ManagedTransferError("Managed upload is incomplete or its complete SHA/length changed")
            pending["stream"].flush()
            pending["stream"].seek(0)
            def unique_object(pairs):
                result = {}
                for key, item in pairs:
                    if key in result:
                        raise ManagedTransferError("Duplicate JSON key in complete upload")
                    result[key] = item
                return result
            payload = json.load(pending["stream"], object_pairs_hook=unique_object)
            _check_deadline(manifest["hard_deadline_monotonic"], self.clock)
            if (not isinstance(payload, dict) or payload.get("version") != VERSION
                    or any(payload.get(key) != manifest[key] for key in
                           ("request", "baseline_tree_sha256", "candidate_tree_sha256"))):
                raise ManagedTransferError("Complete upload differs from its frozen operation provenance")
            pending["stream"].close()
            self.pending = None
            receipt = {key: manifest[key] for key in
                       ("version", "upload_id", "operation", "payload_bytes", "payload_sha256", "chunks")}
            receipt.update(complete_payload_verified=True, operation_executed=False)
            return manifest["operation"], payload, receipt
        except Exception as error:
            self.abort()
            if isinstance(error, ManagedTransferError):
                raise
            raise ManagedTransferError("Managed upload commit failed: " + str(error)) from error


def validate_public_entry(entry, *, instance_id, public_python):
    fields = {"version", "instance_id", "argv", "cwd", "timeout_seconds", "hidden_material_used"}
    if (not isinstance(entry, dict) or set(entry) != fields or entry["version"] != PUBLIC_ENTRY_VERSION
            or entry["instance_id"] != instance_id or entry["cwd"] != "/testbed"
            or entry["hidden_material_used"] is not False
            or type(entry["timeout_seconds"]) is not int or not 0 < entry["timeout_seconds"] <= 1800):
        raise ValueError("Only the frozen task's repository-wide public entrypoint is allowed")
    argv = entry["argv"]
    if (not isinstance(argv, list) or not argv or len(argv) > 20 or argv[0] != public_python
            or any(not isinstance(arg, str) or not arg or "\0" in arg or "\n" in arg for arg in argv)):
        raise ValueError("Public tests must use the frozen original interpreter and argv")
    return copy.deepcopy(entry)


def make_delta(baseline, files, entry_metadata, *, request):
    """Mechanical transfer encoding; baseline and complete candidate stay bound."""
    policy = normalize_policy(baseline.get("file_policy"))
    validate_tree(files, entry_metadata, policy)
    changed = [path for path in files if path not in baseline["files"]
               or files[path] != baseline["files"][path]
               or entry_metadata[path] != baseline["entry_metadata"][path]]
    value = {"version": VERSION, "request": copy.deepcopy(request),
             "baseline_tree_sha256": tree_manifest(baseline["files"], baseline["entry_metadata"])["tree_sha256"],
             "changed_files": {path: files[path] for path in changed},
             "changed_metadata": {path: entry_metadata[path] for path in changed},
             "deleted_paths": sorted(set(baseline["files"]) - set(files)),
             "candidate_tree_sha256": tree_manifest(files, entry_metadata)["tree_sha256"]}
    return value


def reconstruct_delta(baseline, payload, *, gitlinks=()):
    if (set(payload) != {"version", "request", "baseline_tree_sha256", "changed_files",
                         "changed_metadata", "deleted_paths", "candidate_tree_sha256"}
            or payload["version"] != VERSION
            or payload["baseline_tree_sha256"] != tree_manifest(baseline["files"], baseline["entry_metadata"])["tree_sha256"]
            or set(payload["changed_files"]) != set(payload["changed_metadata"])
            or not isinstance(payload["deleted_paths"], list)
            or len(set(payload["deleted_paths"])) != len(payload["deleted_paths"])
            or set(payload["deleted_paths"]) & set(payload["changed_files"])
            or not set(payload["deleted_paths"]) <= set(baseline["files"])):
        raise ValueError("Delta does not bind the complete original baseline")
    files, metadata = dict(baseline["files"]), dict(baseline["entry_metadata"])
    for path in payload["deleted_paths"]:
        del files[path]
        del metadata[path]
    files.update(payload["changed_files"])
    metadata.update(payload["changed_metadata"])
    policy = normalize_policy(baseline.get("file_policy"))
    validate_tree(files, metadata, policy)
    check_gitlink_payload(files, list(gitlinks))
    for path in set(files) | set(baseline["files"]):
        if is_readonly(path, policy) and (files.get(path) != baseline["files"].get(path)
                                        or metadata.get(path) != baseline["entry_metadata"].get(path)):
            raise ValueError("Delta changed protected baseline content or metadata")
    tree = tree_manifest(files, metadata)["tree_sha256"]
    if tree != payload["candidate_tree_sha256"] or payload["request"].get("tree_sha256") != tree:
        raise ValueError("Reconstructed complete tree differs from the requested source version")
    return {"files": files, "entry_metadata": metadata, "file_policy": policy, "tree_sha256": tree}


def synchronize_tree(root, candidate, *, gitlinks=()):
    """Refresh one quiescent private checkout, retaining original Git controls."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("The actor checkout must be an existing real directory")
    root = root.resolve()
    links = checked_gitlinks(list(gitlinks))
    files, metadata = candidate["files"], candidate["entry_metadata"]
    validate_tree(files, metadata, candidate["file_policy"])
    check_gitlink_payload(files, links)
    controls = {".git", *(link["path"] + "/.git" for link in links)}
    directories = []
    for folder, dirs, leaves in os.walk(root, followlinks=False):
        parent = Path(folder)
        directories.append(parent)
        for name in list(dirs):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if relative in controls:
                dirs.remove(name)
            elif path.is_symlink():
                dirs.remove(name)
                leaves.append(name)
        for name in leaves:
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if relative in controls:
                continue
            if relative not in files:
                path.unlink()
    for directory in reversed(directories):
        if directory != root and not any(directory.iterdir()):
            directory.rmdir()
    for relative in sorted(files):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if any(parent.is_symlink() for parent in target.parents if parent != root and root in parent.parents):
            raise ValueError("A candidate ancestor unexpectedly became a symlink")
        raw = decode_entry(relative, files[relative], metadata[relative])
        if target.is_dir() and not target.is_symlink():
            # Only already-empty ordinary directories may become files.
            target.rmdir()
        if metadata[relative]["kind"] == "symlink":
            if target.is_symlink() and os.readlink(target) == files[relative]:
                continue
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(files[relative])
        else:
            if target.is_symlink():
                target.unlink()
            if not target.exists() or target.read_bytes() != raw:
                target.write_bytes(raw)
            target.chmod(0o755 if metadata[relative]["mode"] == "100755" else 0o644)
    observed = snapshot_repository(root, file_policy=candidate["file_policy"], gitlinks=links)
    if observed["tree"]["tree_sha256"] != candidate["tree_sha256"]:
        raise ValueError("Actual actor checkout failed the complete synchronized-tree comparison")
    return {"tree_sha256": candidate["tree_sha256"], "exact_complete_tree": True,
            "git_control_preserved": True, "source_file_count": len(files)}


def _reap_private_children():
    """Only PID1 in the owned actor may stop descendants from its public test."""
    if os.getpid() != 1:
        raise ValueError("Child cleanup is only valid inside the private actor PID namespace")
    ended = time.monotonic() + 10
    while True:
        while True:
            try:
                if os.waitpid(-1, os.WNOHANG)[0] == 0:
                    break
            except ChildProcessError:
                break
        pending = [int(p.name) for p in Path("/proc").iterdir()
                   if p.name.isdigit() and int(p.name) != 1]
        if not pending:
            return True
        for pid in pending:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if time.monotonic() >= ended:
            raise RuntimeError("Owned public-test descendants did not quiesce")
        time.sleep(.05)


def run_public_entry(entry, *, root, environment, request, candidate_tree_sha256):
    remaining = request["hard_deadline_monotonic"] - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("The episode ended before the accepted public test could start")
    timeout = min(entry["timeout_seconds"], remaining)
    began = time.monotonic()
    timed_out = False
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(entry["argv"], cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        finally:
            _reap_private_children()
        log.seek(0, os.SEEK_END)
        length = log.tell()
        log.seek(0)
        raw = log.read(MAX_OUTPUT_BYTES + 1)
        if length > MAX_OUTPUT_BYTES:
            raise ManagedInterfaceLimit("Public-test output exceeds the 32-MiB exact feedback bound")
    output = raw.decode("utf-8", "backslashreplace")
    passed = process.returncode == 0 and not timed_out
    return {"passed": passed, "execution": {
                "executed": True, "input_tree_sha256": candidate_tree_sha256,
                "source_reference": request["source_reference"], "argv": entry["argv"],
                "cwd": "/testbed", "returncode": process.returncode, "timed_out": timed_out,
                "wall_seconds": time.monotonic() - began, "descendants_quiescent": True,
                "stdout_sha256": digest(raw), "stdout_bytes": length,
                "stdout_utf8_strict": output.encode("utf-8") == raw,
                "hidden_evaluator": False, "model_supplied_command": False},
            "groups": {"public_repository_tests": {"status": "passed" if passed else "failed",
                       "executed": True, "passed": passed, "output": output,
                       "tests": [{"test_id": "repository-wide-public-entrypoint", "passed": passed}]}},
            "repository_collection_errors": []}
