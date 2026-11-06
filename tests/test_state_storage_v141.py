import json
from pathlib import Path

import pytest

from proworksim import scenarios, storage
from proworksim.core import journal
from proworksim.core.world import WorldSpec
from proworksim.software_benchmark_state_storage_v141 import (
    LowMemoryWorldCore, StreamCachedStore, StreamStore, atomic_json, build_scenario,
    clone_json, read_json, streamed_digest,
)


def test_json_clone_preserves_normalization_without_mutable_aliases():
    text = "汉字 and quotes \"\\\n" * 2000
    child = {"payload": text, "tuple": (1, None, False)}
    value = {7: child, "other": child, None: {True: -0.0}}
    copied = clone_json(value)
    assert copied == json.loads(json.dumps(value, allow_nan=False))
    assert copied["7"] is not copied["other"]
    assert copied["7"]["payload"] is text
    copied["7"]["tuple"].append(3)
    assert copied["other"]["tuple"] == [1, None, False]
    assert child["tuple"] == (1, None, False)


@pytest.mark.parametrize("value", [float("inf"), {"a": float("nan")}, {("a",): 1}, {1, 2}])
def test_json_clone_rejects_originally_invalid_values(value):
    with pytest.raises((TypeError, ValueError)):
        clone_json(value)


def test_json_cycle_rejected():
    value = []
    value.append(value)
    with pytest.raises(ValueError, match="Circular"):
        clone_json(value)


@pytest.mark.parametrize("chunk_size", [1, 7, 65536])
def test_incremental_reader_exact_values_and_shared_strings(tmp_path, chunk_size):
    long = '汉字 " \\\\ \n 🙂' * 400
    value = {"data": [long, long, {"x": "\\uD83D", "n": -1.25e-30}], "empty": [{}, []]}
    path = tmp_path / "value.json"
    atomic_json(path, value)
    assert path.read_bytes() == storage.json_bytes(value)
    loaded = read_json(path, chunk_size=chunk_size)
    assert loaded == value
    assert loaded["data"][0] is loaded["data"][1]
    assert streamed_digest(value) == storage.digest(storage.json_bytes(value))
    assert streamed_digest(value, canonical=True) == journal.canonical_digest(value)


@pytest.mark.parametrize("raw", ['{"a":1,}', '[1,]', '{"a" 1}', '"oops', 'true false', '01', '{"a":"\\q"}'])
def test_incremental_reader_rejects_corrupt_json(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_text(raw)
    with pytest.raises((ValueError, TypeError)):
        read_json(path, chunk_size=2)


def test_failed_atomic_save_preserves_committed_data(tmp_path):
    path = tmp_path / "state.json"
    atomic_json(path, {"old": 1})
    before = path.read_bytes()
    with pytest.raises(ValueError):
        atomic_json(path, {"payload": "x" * 8192, "bad": float("inf")})
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".tmp-v141-*"))


def test_cached_state_does_not_return_caller_mutations(tmp_path):
    store = StreamCachedStore(tmp_path)
    store.save({"rows": [{"data": "x" * 4096}]})
    first = store.load()
    first["rows"][0]["data"] = "changed"
    assert store.load()["rows"][0]["data"] == "x" * 4096
    store.save({"rows": []})
    assert store.load() == {"rows": []}


def test_new_world_uses_streamed_store_and_command_bound_digests(tmp_path):
    spec = WorldSpec(
        world_id="memory-control",
        actors=[{"actor_id": "operator", "kind": "operator"}],
        bootstrap_grants=[{"actor_id": "operator", "power": "install_project", "scope": "world"}],
    )
    world = LowMemoryWorldCore.create(tmp_path / "world", spec)
    assert isinstance(world.store, StreamStore)
    request = {"package": {"data": "汉" * 1000}}
    identity, digest = world._operation_identity("operator", "install_project", request, "control")
    assert identity == "command:operator:control"
    assert digest == journal.canonical_digest({"action": "install_project", "arguments": request})


def test_private_bindings_leave_frozen_modules_unchanged():
    assert scenarios.validate_scenario.__globals__["json"] is json
    assert scenarios.build_scenario.__globals__["WorldCore"] is not LowMemoryWorldCore
    assert build_scenario.__globals__["WorldCore"] is LowMemoryWorldCore
    assert storage.Store.save.__globals__["json_bytes"] is storage.json_bytes
    assert Path(build_scenario.__code__.co_filename).name == "scenarios.py"
