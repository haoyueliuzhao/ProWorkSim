"""Opt-in CPU/deployment adapter retaining the pinned v175 command journal.

This is not installed in the frozen actor bundle. Callers must supply an owned
durable directory and a candidate/source binding before executing a command.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import secrets
from functools import lru_cache
from types import SimpleNamespace

VERSION = "v203.2.3-canonical-preload-retention-r5"
BASE_SHA256 = "511577e7dd203186f8874b111cf72e2022faa187ec9e2aa0b3be592e3a4385bb"


def load_base(root=None):
    # Normalize before caching: load_base() and load_base(None) must share the
    # same preload, including after private runtime sources have been sealed.
    key = str((Path(root) if root is not None else Path(__file__).resolve().parents[2]).resolve())
    return _load_base_cached(key)


@lru_cache(maxsize=2)
def _load_base_cached(key):
    root = Path(key)
    path = root / "tools/public_test_execution_v175.py"
    if hashlib.sha256(path.read_bytes()).hexdigest() != BASE_SHA256:
        raise ValueError("Retaining adapter requires the pinned v175 implementation")
    spec = importlib.util.spec_from_file_location("_pws_retention_base_v175", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Managed actor sealing deletes private project files after preload. Capture
    # executable source and observer bytes before that boundary, never reopen it.
    module._retention_source = inspect.getsource(module.execute_public_entry)
    observer = module.helper_path().read_bytes()
    module.helper_path = lambda: SimpleNamespace(read_bytes=lambda: observer)
    return module


def retaining_executor(retention_root, *, binding, root=None):
    """Return a v175 executor with a mandatory journal copy before tmp cleanup.

    The original parser, command, timeout, process group cleanup, and outcome
    rules remain unchanged. Failed and unknown parses retain the original bytes
    too. This adds durable copies; it does not repair an incomplete journal.
    """
    retention_root = Path(retention_root).resolve()
    if not isinstance(binding, dict) or not binding.get("source_reference") or not binding.get("candidate_tree_sha256"):
        raise ValueError("Journal evidence requires source_reference and candidate_tree_sha256")
    binding = json.loads(json.dumps(binding))
    base = load_base(root)
    source = base._retention_source
    anchor = "    validation = parse_test_evidence(evidence, framework=kind, token=token,"
    # Copy while the original temporary journal exists, even if validation fails.
    seam = "        log.seek(0, os.SEEK_END)"
    if source.count(seam) != 1 or source.count(anchor) != 1:
        raise ValueError("Pinned command journal retention seam changed")

    def retain(report, log, *, entry, root, token, process, timed_out):
        folder = retention_root / ("command-" + secrets.token_hex(16))
        folder.mkdir(parents=True, exist_ok=False)
        journal = folder / "framework-journal.jsonl"
        digest, size = hashlib.sha256(), 0
        with Path(report).open("rb") as src, journal.open("xb") as dst:
            while block := src.read(1024 * 1024):
                dst.write(block)
                digest.update(block)
                size += len(block)
            dst.flush()
            import os
            os.fsync(dst.fileno())
        stdout = folder / "stdout.bin"
        output_digest, output_size = hashlib.sha256(), 0
        log.seek(0)
        with stdout.open("xb") as stream:
            while block := log.read(1024 * 1024):
                stream.write(block)
                output_digest.update(block)
                output_size += len(block)
            stream.flush()
            os.fsync(stream.fileno())
        value = {"version": VERSION, "binding": binding, "argv": entry["argv"],
                 "cwd": str(root), "observer_token": token, "process_group": process.pid,
                 "returncode": process.returncode, "timed_out": timed_out,
                 "base_execution_sha256": BASE_SHA256,
                 "journal": {"path": str(journal), "sha256": digest.hexdigest(), "bytes": size},
                 "stdout": {"path": str(stdout), "sha256": output_digest.hexdigest(), "bytes": output_size},
                 "full_original_bytes_retained": True,
                 "same_uid_anti_forgery_boundary": False}
        from .storage import atomic_write, json_bytes
        receipt = folder / "command-binding.json"
        atomic_write(receipt, json_bytes(value))
        return {"binding_receipt": str(receipt), "journal_sha256": digest.hexdigest(),
                "journal_bytes": size, "version": VERSION}

    source = source.replace(seam, "        retained = _retain(report, log, entry=entry, root=root, token=token, process=process, timed_out=timed_out)\n" + seam)
    source = source.replace("    return {**validation, 'version': VERSION,", "    validation['test_evidence']['retained_journal'] = retained\n    return {**validation, 'version': VERSION,")
    namespace = {**base.__dict__, "_retain": retain}
    exec(compile(source, str(Path(__file__).resolve()) + ":v175-retaining-executor", "exec"), namespace)
    return namespace["execute_public_entry"]
