"""Fail-closed future binding of the verified v175 public-test bundle.

This module only validates/stages ordinary files and returns new namespaces.
It never deploys an actor, changes an archived module, or starts a service.
The v141 result schema is retained because v175 explicitly retains that schema;
deployment identity is separately pinned so that schema equality cannot admit
the older execution/observer files again.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v203.2.2-pinned-v175-public-test-bundle-r1"
MANIFEST = ROOT / "config/v203-2-2-public-test-bundle.json"
MANIFEST_SHA256 = "c087080adca04f8f50d5baeaa82613ccf302c584b58c815a8b180ad1dd4ee603"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest():
    raw = MANIFEST.read_bytes()
    if digest(raw) != MANIFEST_SHA256:
        raise ValueError("The v203.2.2 public-test admission manifest changed")
    value = json.loads(raw)
    if value["version"] != VERSION:
        raise ValueError("Unsupported public-test deployment binding")
    for item in [*value["files"].values(), value["managed_entry"]]:
        if digest((ROOT / item["source"]).read_bytes()) != item["sha256"]:
            raise ValueError(f"Pinned public-test source differs: {item['source']}")
    return value


def public_files():
    return {item["config_key"]: ROOT / item["source"]
            for item in manifest()["files"].values()}


def admit_loaded_hashes(loaded):
    expected = {item["config_key"]: item["sha256"]
                for item in manifest()["files"].values()}
    if loaded != expected:
        raise ValueError("The actor did not load the exact pinned v175 public-test bundle")
    return {"version": VERSION, "manifest_sha256": MANIFEST_SHA256,
            "deployment_revision": manifest()["deployment_revision"], "loaded_files": expected}


def admit_staged_bundle(folder):
    folder = Path(folder)
    value = manifest()
    loaded = {}
    for target, item in value["files"].items():
        raw = (folder / target).read_bytes()
        if len(raw) != item["bytes"]:
            raise ValueError(f"Public-test staged file size differs: {target}")
        loaded[item["config_key"]] = digest(raw)
    return admit_loaded_hashes(loaded)


def stage_bundle(folder):
    """Write only to a new ordinary-user directory; no installation or root."""
    value = manifest()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    for target, item in value["files"].items():
        destination = folder / target
        destination.write_bytes((ROOT / item["source"]).read_bytes())
        destination.chmod(0o444)
    (folder / "public-test-bundle-manifest.json").write_bytes(MANIFEST.read_bytes())
    return admit_staged_bundle(folder)


def staged_execution(folder):
    """Load the admitted execution alias and its admitted sibling observer."""
    admit_staged_bundle(folder)
    path = Path(folder) / "public-test-execution.py"
    spec = importlib.util.spec_from_file_location("_pws_public_test_execution_v203_2_2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.DEPLOYMENT_REVISION != manifest()["deployment_revision"]:
        raise ValueError("Admitted public-test deployment marker differs")
    return module


def run_public_entry(*args, **kwargs):
    """Guard the actual managed adapter, including packaged execution/evidence."""
    value = manifest()
    from . import software_benchmark_public_test_evidence_v175 as evidence
    for actual, expected in [
        (Path(evidence.__file__), value["managed_entry"]),
        (evidence._source, value["files"]["public-test-execution.py"]),
        (evidence._module.helper_path(), value["files"]["public-test-evidence.py"]),
    ]:
        if digest(actual.read_bytes()) != expected["sha256"]:
            raise ValueError("Managed public-test adapter resolves an unadmitted implementation")
    return evidence.run_public_entry(*args, **kwargs)


def managed_actor():
    """Return an isolated v143/v141 namespace with the guarded repaired entry."""
    manifest()
    from . import software_benchmark_managed_actor_v143 as original
    old = original.ManagedOperationSession.execute
    namespace = {**old.__globals__, "run_public_entry": run_public_entry}

    class ManagedOperationSession(original.ManagedOperationSession):
        execute = FunctionType(old.__code__, namespace, old.__name__, old.__defaults__, old.__closure__)

    return SimpleNamespace(**{**vars(original), "ManagedOperationSession": ManagedOperationSession,
                              "run_public_entry": run_public_entry, "DEPLOYMENT_VERSION": VERSION})
