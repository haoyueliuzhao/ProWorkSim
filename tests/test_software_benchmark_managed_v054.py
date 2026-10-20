"""Cross-component S1 gateway controls; synthetic source, no model or GPU."""
import copy
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_managed_v054 as managed
from proworksim import software_benchmark_world_v054 as world
from proworksim.repository_sources_v054 import RepositorySources, capture_repository
from proworksim.software_benchmark_candidates_v054 import (
    lock_episode_candidates, read_episode_candidates,
)
from proworksim.storage import json_bytes


def prepared_case(tmp_path):
    source = tmp_path / "public"
    source.mkdir()
    for index in range(205):
        (source / f"part-{index:03}.py").write_text(f"index = {index}\n")
    (source / "large.txt").write_text("start\n" + "z" * 350_000 + "\nend")
    (source / "data.bin").write_bytes(b"\0\xffdata")
    identity = {"instance_id": "fixture__repo-054", "repo": "fixture/repo",
                "base_commit": "a" * 40, "dataset_revision": "b" * 40}
    manifest = capture_repository(
        source, tmp_path / "source-snapshot", task_id=identity["instance_id"],
        problem_statement="This is a synthetic public issue, not a benchmark task.",
        source_identity=identity)

    def forbidden_runner(**_):
        pytest.fail("Opening or editing an S1 world must not automatically run tests")

    provider = RepositorySources(manifest, runner=forbidden_runner)
    return world.build_software_collaboration_case(
        identity["instance_id"], tmp_path / "managed-world", provider=provider)


def test_real_gateway_versions_full_tree_and_exports_without_implicit_delivery(tmp_path):
    prepared = prepared_case(tmp_path)
    events = []
    port = managed.managed_port(
        prepared, public_sink=lambda kind, value: events.append((kind, value)),
        world_sink=lambda value, association: events.append(("world", value)))
    tools = {item["name"] for item in port.tools()}
    assert {"create_file", "delete_file", "rename_file", "read_file"} <= tools
    assert not {"bash", "terminal", "execute_bash"} & tools
    observation = port.observe()
    assert observation["file_count"] == 207
    assert 0 < len(observation["file_directory"]["files"]) <= 40
    assert observation["file_directory"]["next_cursor"] is not None
    assert len(json_bytes(observation)) < 25_000
    original = observation["workspace_reference"]

    def call(name, key, **arguments):
        return port.call(name, request_key=key, association={}, **arguments)

    created = call("create_file", "create", path="new/config.toml", text="enabled=true\n")
    assert created["ok"]
    assert call("create_file", "create", path="new/config.toml",
                text="enabled=true\n") == created
    renamed = call("rename_file", "rename", path="data.bin", new_path="assets/renamed.bin")
    assert renamed["ok"]
    assert call("delete_file", "delete", path="part-000.py")["ok"]
    assert call("replace_file", "edit-large", path="large.txt", old="start\n", new="changed\n")["ok"]
    assert not call("submit_integration", "no-test-submit", message="Premature")["ok"]
    assert port.observe()["workspace_reference"] != original
    _, _, current = prepared.world._bundle("member_001")
    assert "part-000.py" not in current["files"] and "data.bin" not in current["files"]
    assert current["entry_metadata"]["assets/renamed.bin"]["encoding"] == "base64"

    # No submission still has one terminal-code candidate; it must not be
    # replaced by the unchanged baseline or disappear from the code endpoint.
    lock = lock_episode_candidates(prepared, run_root=tmp_path / "closed")
    pair = read_episode_candidates(lock)
    assert pair["last_legal_delivery"] is None
    assert pair["terminal_code"]["files"]["new/config.toml"] == "enabled=true\n"
    assert pair["terminal_code"]["files"]["large.txt"].startswith("changed\n")
    assert pair["terminal_code"]["entry_metadata"]["assets/renamed.bin"]["encoding"] == "base64"
    assert "part-000.py" not in pair["terminal_code"]["files"]
    assert prepared.world.test_budget.snapshot()["used"] == 0
    assert any(kind == "world" for kind, _ in events)


def test_runtime_factory_binds_repaired_tools_without_sampling_or_ungated_execution(tmp_path):
    prepared = prepared_case(tmp_path)
    before = copy.deepcopy(prepared.world.store.load())
    workers = []

    class InertWorker:
        def __init__(self, member, definitions, config, **kwargs):
            self.member = member
            self.definitions, self.config = copy.deepcopy(definitions), copy.deepcopy(config)
            self.kwargs = kwargs
            workers.append(self)

        def step(self, *_args, **_kwargs):
            pytest.fail("Runtime assembly may not perform model work")

        def snapshot(self):
            return {"synthetic_inert_worker": True}

    owner = SimpleNamespace(
        window_id="synthetic-v054",
        recipe={"temperature": 0.7, "max_output_tokens": 2048, "max_length": 18432},
        transport=SimpleNamespace(),
        freeze_identity=lambda: {"policy_version": "synthetic-raw", "checkpoint": None})
    runtime, _, interfaces = managed.build_runtime(
        owner, prepared, tmp_path / "runtime", worker_factory=InertWorker)
    assert runtime.labels == ["member_001"] and len(workers) == 1
    assert set(interfaces) == {"member_001"}
    assert {"create_file", "delete_file", "rename_file"} <= {
        item["name"] for item in workers[0].definitions}
    assert workers[0].config["action_protocol"] == "native_tools"
    assert workers[0].config["budget"]["max_total_tokens"] == 500000
    assert prepared.world.store.load() == before
    assert runtime.opportunities == runtime.actions == 0
    assert runtime.team_budget.snapshot()["attempts"] == 0
    with pytest.raises(ValueError, match="outside its scheduled"):
        runtime.execute("member_001", "create_file", {"path": "bad", "text": "bad"},
                        {"model_call_id": "not-a-real-call", "decision_id": "not-scheduled"})
