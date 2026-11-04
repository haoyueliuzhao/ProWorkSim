"""Exact digest and actual preparation binding controls, without model activity."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import subprocess
from types import FunctionType, SimpleNamespace

import pytest

from proworksim.scenarios import initial_business_state
from proworksim.storage import Store, digest, json_bytes
from proworksim.software_benchmark_initial_state_hash_v132 import (
    initial_business_state_digest, measure_initial_business_state,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def deny(*a, **kw):
        raise AssertionError("The streaming-state CPU control cannot use external resources")
    for name in ("connect", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, name, deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(subprocess, "Popen", deny)


def test_stream_is_exact_legacy_JSON_including_hex_unicode_exclusions_and_empty_values(tmp_path):
    store = Store(tmp_path)
    store.control.mkdir(parents=True)
    artifact = {"artifact_id": "obj-fixture", "filename": "payload.bin", "versions": {"v1": {}, "v2": {}}}
    raws = [bytes(range(256)) * 5000, b"\x00\xff\r\n"]
    for version, raw in zip(artifact["versions"], raws, strict=True):
        path = store.version_path(artifact, version)
        path.parent.mkdir(parents=True)
        path.write_bytes(raw)
    state = {"instance_id": "excluded", "branch_id": "excluded", "parent_branch_id": None,
        "artifacts": {"obj-fixture": artifact}, "interactions": [{"wall_seconds": 1.5,
            "receipt": {"state_digests": ["excluded"], "kept": True}, "state_digests": "keep"}],
        "unicode": ("汉字\\\n\t\"" * 3000), "empty": [[], {}, ""], "number": [None, False, True, 1.0, -5, 2e30],
        "nested": {"transition": {"state_digests": "excluded", "ordering": [2, 1]}}}
    world = SimpleNamespace(state=state, store=store)
    original = json_bytes(initial_business_state(world))
    measured = measure_initial_business_state(world)
    assert measured["sha256"] == digest(original)
    assert measured["hashed_bytes"] == len(original)
    assert measured["immutable_bytes"] == sum(map(len, raws))
    assert measured["immutable_versions"] == 2
    state["instance_id"] = "changed-but-excluded"
    state["interactions"][0]["wall_seconds"] = 999.0
    assert initial_business_state_digest(world) == measured["sha256"]
    state["nested"]["transition"]["ordering"] = [1, 2]
    assert initial_business_state_digest(world) != measured["sha256"]


def test_actual_MATRIX_preparation_keeps_prefix_world_and_all17_wire_schemas(tmp_path):
    from proworksim import software_fixed_organization_world_v132 as repaired_world
    from proworksim import software_fixed_organization_runtime_v132 as repaired_runtime
    from proworksim import software_benchmark_sdk_bundle_v132 as bundle
    from proworksim.software_benchmark_episode_v132 import build_episode
    from proworksim import software_benchmark_scope_v131 as old_scope
    from proworksim.software_benchmark_alignment_contract_v131 import VERSION
    spec = importlib.util.spec_from_file_location("CPU_original_world_fixture",
        ROOT / "tests/test_fixed_organization_v131.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    new_fixture = FunctionType(fixture.fixture.__code__, {**fixture.fixture.__globals__, "world": repaired_world},
                              fixture.fixture.__name__, fixture.fixture.__defaults__)
    prepared, _, calls = new_fixture(tmp_path, group="MATRIX")
    assert calls == []
    assert prepared.case["active_roles"] == ["member_001", "member_002", "member_003", "member_004"]
    expected = digest(json_bytes(initial_business_state(prepared.world)))
    assert prepared.prefix["prepared_business_state_sha256"] == expected
    stored = json.loads((tmp_path / "prepared/preparation.json").read_bytes())
    assert stored["prepared_business_state_sha256"] == expected
    schemas = repaired_runtime.prepare_schema_inventory()["schemas"]
    original = json.loads((ROOT / "runs/software-benchmark-v131/fixed-organization-50-r1/api-coordinator/api-runtime/member-tool-schemas-r2.json").read_bytes())
    assert schemas == original["schemas"]
    assert sum(len(members) for members in schemas.values()) == 17
    actual = build_episode(scope=old_scope, guard=lambda *a, **kw: {
        "status": "approved", "execution_alignment_version": VERSION, "source_index": {"CPU_only": True}})
    assert actual.runtime is bundle and actual._run.__globals__["runtime"] is bundle
    assert bundle.ALIASES["project-controller.py"] == "run_fixed_organization_controller_v132.py"
    assert bundle.ALIASES["managed-worker.py"] == "run_managed_worker_docker_v131.py"
    actual.host_memory.close()
