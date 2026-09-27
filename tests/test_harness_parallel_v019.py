"""Real subprocesses/worlds with explicit CPU response fixtures; no GPU claims."""

import copy
import json
import os
from pathlib import Path
import sys

import pytest

from proworksim import harness_collection
from proworksim import harness_parallel_v019 as parallel
from proworksim.member_views import member_view
from proworksim.online_training import prepare_window
from proworksim.storage import read_json
from test_online_collection_v013 import FakeOwner

SOURCE = {"code_commit": "explicit-cpu-fixture", "code_dirty": True, "source_tree_sha256": "fixture"}


class ParallelFakeOwner(FakeOwner):
    def __init__(self, window_id="cpu-window"):
        super().__init__(window_id)
        self.busy = False
        self.actor_steps = self.critic_steps = 0
        self.recipe.update(members=["provider", "implementer", "reviewer"], credit_assignment="terminal_mc")
        self.barrier = None
        self.child = False

    def _make_identity(self):
        return self.freeze_identity()

    def _resource_guard(self):
        return {"fixture": True, "seeds": copy.deepcopy(self.seeds), "calls": len(self.requests)}

    def verify_sampling_identity(self):
        return {"passed": True, "actor_identity": self.freeze_identity(),
                "actual_actor_identity": self.freeze_identity(), "optimizer_absent": True,
                "local_optimizer_updates": 0}

    def export_sampling_snapshot(self, path):
        path.mkdir()
        self.barrier = path.parent.parent / "declaration.json"
        payload = {"window_id": self.window_id, "actor_identity": self.freeze_identity(), "barrier": str(self.barrier)}
        parallel.write(path / "manifest.json", payload)
        return payload

    def complete(self, request, **kwargs):
        assert self.barrier and self.barrier.exists(), "No sampling before the full declaration"
        if self.child and os.environ.get("PROWORKSIM_TEST_CHILD_EXIT") == "1":
            os._exit(17)
        response = super().complete(request, **kwargs)
        call = response["body"]["choices"][0]["message"]["tool_calls"][0]
        call["function"] = {"name": "staff_done", "arguments": json.dumps({"reason": "Explicit CPU fixture"})}
        response["raw_body"] = json.dumps(response["body"])
        return response


def fake_load(snapshot, output):
    value = read_json(Path(snapshot) / "manifest.json")
    owner = ParallelFakeOwner(value["window_id"])
    owner.identity = value["actor_identity"]
    owner.barrier = Path(value["barrier"])
    owner.child = True
    if os.environ.get("PROWORKSIM_TEST_WRONG_ACTOR") == "1":
        owner.identity["policy_version"] = "wrong-fixture-policy"
    Path(output).mkdir()
    return owner


@pytest.fixture
def subprocess_control(tmp_path, monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    monkeypatch.setenv("PROWORKSIM_REPLICA_GPUS", "2,3")
    monkeypatch.setattr(parallel, "code_identity", lambda: SOURCE)
    monkeypatch.setattr(harness_collection, "code_identity", lambda: SOURCE)
    root = Path(__file__).resolve().parents[1]
    env = {"PYTHONPATH": os.pathsep.join([str(root / "src"), str(root / "tests"), str(root)])}
    script = tmp_path / "explicit_cpu_replica.py"
    script.write_text('''import sys
import types
from test_harness_parallel_v019 import fake_load, SOURCE
from proworksim import harness_collection, harness_parallel_v019
harness_collection.code_identity = lambda: SOURCE
harness_parallel_v019.code_identity = lambda: SOURCE
sys.modules['proworksim.sampling_replica_v019'] = types.SimpleNamespace(load_replica=fake_load)
from scripts import sampling_replica_v019
sampling_replica_v019.code_identity = lambda: SOURCE
sampling_replica_v019.main()
''')
    return {"replica_command": [sys.executable, str(script)], "replica_environment": env}


def window(owner):
    return {"window_id": owner.window_id, "harness": "native_v15", "stage": "CPU_parallel_fixture",
            "template": "retail_work", "mode": "online", "slots": [
                {"slot_id": f"slot-{i}", "case_id": f"uci-train-f{i}-implement", "sampling_seed": 501 + i}
                for i in range(2)]}


def test_real_process_barrier_original_seed_order_and_own_tokens(tmp_path, subprocess_control):
    owner = ParallelFakeOwner()
    spec = window(owner)
    output = tmp_path / "parallel"
    entries = parallel.collect_window(owner, spec, output, **subprocess_control)
    assert [e["slot_id"] for e in entries] == ["slot-0", "slot-1"]
    assert [e["reward"]["reward"] for e in entries] == [0, 0]
    assert owner.seeds == [(502, "slot-1")]
    report = read_json(output / "parallel/report.json")
    assert report["passed"] and report["child_finished_before_update"]
    assert report["partition"] == [1, 0]
    assert report["child"]["resource_after"]["seeds"] == [[501, "slot-0"]]
    assert owner.actor_steps == owner.critic_steps == 0
    declared = read_json(output / "declaration.json")
    assert len(declared["slots"]) == 2
    assert {e["rollout"]["window"]["gamma_fingerprint"] for e in entries} == {declared["gamma_fingerprint"]}
    for entry in entries:
        view = member_view(entry["rollout"], "implementer")
        assert view["complete_actor_trajectory"]
        assert view["decisions"][0]["tokens"]["output_ids"] == [3]
    targets = prepare_window(entries, owner.freeze_identity(), owner.window_id, owner.recipe)
    assert targets["slot_count"] == 2
    assert len(targets["decisions"]) == 2
    assert {r["actor_denominator"] for r in targets["decisions"]} == {2}
    # Evidence cannot be reassigned to another global slot after closure.
    path = output / "slot-0/parallel-result.json"
    result = read_json(path)
    result["entry"]["slot_id"] = "slot-1"
    parallel.write(path, result)
    with pytest.raises(ValueError, match="another slot"):
        parallel.read_slot_result(output, 0, 1, spec["slots"][0], declared["slots"][0], declared)


def test_child_crash_keeps_unknown_slot_no_reassignment_or_update(tmp_path, subprocess_control, monkeypatch):
    monkeypatch.setenv("PROWORKSIM_TEST_CHILD_EXIT", "1")
    owner = ParallelFakeOwner()
    output = tmp_path / "crashed"
    with pytest.raises(RuntimeError, match="no learner update"):
        parallel.collect_window(owner, window(owner), output, **subprocess_control)
    summary = read_json(output / "summary.json")
    assert len(summary["slots"]) == 2
    assert summary["slots"][0]["status"] == "interrupted"
    assert summary["slots"][1]["reward"]["reward"] == 0
    assert owner.seeds == [(502, "slot-1")]
    assert owner.actor_steps == owner.critic_steps == 0
    report = read_json(output / "parallel/report.json")
    assert not report["passed"] and report["child_exit_code"] == 17
    assert read_json(output / "replica-1/launch.json")["launch_attempt_count"] == 1


def test_wrong_child_actor_stops_before_any_parent_sampling(tmp_path, subprocess_control, monkeypatch):
    monkeypatch.setenv("PROWORKSIM_TEST_WRONG_ACTOR", "1")
    owner = ParallelFakeOwner()
    output = tmp_path / "wrong-actor"
    with pytest.raises(RuntimeError, match="no slot sampled"):
        parallel.collect_window(owner, window(owner), output, **subprocess_control)
    assert owner.requests == owner.seeds == []
    assert not (output / "declaration.json").exists()
    assert read_json(output / "parallel/report.json")["declaration_barrier_reached"] is False


@pytest.mark.parametrize("count", [2, 4, 8, 16, 27])
def test_fixed_partition_has_last_slot_on_parent_and_preserves_all(count):
    ranks = parallel.assignment(count)
    assert ranks[-1] == 0 and set(ranks) == {0, 1}
    assert abs(ranks.count(0) - ranks.count(1)) <= 1


def test_gpu_environment_requires_disjoint_equal_physical_lists(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    monkeypatch.setenv("PROWORKSIM_REPLICA_GPUS", "1,2")
    with pytest.raises(ValueError, match="disjoint"):
        parallel.resolve_replica_environment()
    assert parallel.resolve_replica_environment({"PROWORKSIM_REPLICA_GPUS": "2,3"})["CUDA_VISIBLE_DEVICES"] == "2,3"
