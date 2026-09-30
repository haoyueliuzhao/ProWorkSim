"""Frozen C1 scheduling, immutable checkpoint migration and stop boundaries."""

import copy
import json
from types import SimpleNamespace
import sys

import pytest

from proworksim.storage import digest
from scripts import collaboration_carrier_v026 as worker
from scripts import run_collaboration_carrier_v026 as supervisor
from scripts.evaluate_work_v022 import reference, write


def catalog():
    cases = [{"case_id": f"case-{index}"} for index in range(4)]
    slots = []
    for repeat in range(2):
        for case in cases:
            for condition in ("normal", "single_pass"):
                slots.append(
                    {
                        "slot_id": f"{case['case_id']}-{repeat}-{condition}",
                        "case_id": case["case_id"],
                        "condition": condition,
                        "repeat_index": repeat,
                        "seed": 123 + repeat,
                        "sampling_seed": 123 + repeat,
                    }
                )
    return {"cases": cases, "slots": slots}


def test_fixed_partitions_preserve_pairs_without_moving_slots():
    declared = catalog()
    result = worker.assignments(declared)
    assert [len(slots) for slots in result.values()] == [8, 8]
    for slots in result.values():
        assert len({slot["case_id"] for slot in slots}) == 2
        assert slots == [
            slot
            for slot in declared["slots"]
            if slot["slot_id"] in {row["slot_id"] for row in slots}
        ]
        for case in {slot["case_id"] for slot in slots}:
            assert {
                (slot["condition"], slot["repeat_index"])
                for slot in slots
                if slot["case_id"] == case
            } == {("normal", 0), ("normal", 1), ("single_pass", 0), ("single_pass", 1)}
    broken = copy.deepcopy(declared)
    broken["slots"][1]["sampling_seed"] += 1
    broken["slots"][1]["seed"] += 1
    with pytest.raises(ValueError, match="same seed"):
        worker.assignments(broken)
    missing = copy.deepcopy(declared)
    missing["slots"].pop()
    with pytest.raises(ValueError, match="sixteen"):
        worker.assignments(missing)


def test_invariant_hash_binds_old_git_bytes_and_new_source(tmp_path, monkeypatch):
    relative = "src/model.py"
    current = tmp_path / relative
    current.parent.mkdir()
    current.write_bytes(b"original model path")
    monkeypatch.setattr(worker, "INVARIANT_MODULES", (relative,))
    monkeypatch.setattr(
        worker.subprocess, "check_output", lambda *args, **kwargs: b"original model path"
    )
    plan = {
        "invariant_module_sha256": {relative: digest(current.read_bytes())},
        "old_worker_source": {"code_commit": "a" * 40},
    }
    proof = worker.verify_invariant_source(plan, tmp_path)
    assert proof[relative]["old_sha256"] == proof[relative]["new_sha256"]
    current.write_bytes(b"changed actor code")
    with pytest.raises(ValueError, match="execution changed"):
        worker.verify_invariant_source(plan, tmp_path)


def test_restore_proves_full_state_without_relabeling_old_marker(tmp_path, monkeypatch):
    from proworksim import online_training

    old_source = {"code_commit": "a" * 40, "code_dirty": False, "source_tree_sha256": "old"}
    new_source = {"code_commit": "b" * 40, "code_dirty": False, "source_tree_sha256": "new"}
    actor_identity = {"adapter_sha256": "original adapter"}
    checkpoint = tmp_path / "old-checkpoint.json"
    saved = {
        "state_tensor_digest": "complete state",
        "actor_identity": actor_identity,
        "state": {"sha256": "old bytes"},
    }
    write(checkpoint, saved)
    marker_path = tmp_path / "old-marker.json"
    write(
        marker_path,
        {
            "source": old_source,
            "checkpoint": reference(checkpoint),
            "directory": str(tmp_path / "original"),
            "actor_identity": actor_identity,
        },
    )
    original_bytes = marker_path.read_bytes()
    plan = {"checkpoint_marker": reference(marker_path), "old_worker_source": old_source}
    monkeypatch.setattr(worker, "code_identity", lambda: new_source)
    monkeypatch.setattr(worker, "verify_invariant_source", lambda _: {"model.py": "same"})
    monkeypatch.setattr(online_training, "tensor_tree_digest", lambda state, torch: state["digest"])

    class Owner:
        torch = None
        actor_steps = critic_steps = 3
        state_digest = "complete state"
        restores = []

        def restore_checkpoint(self, directory):
            self.restores.append(directory)
            return saved

        def _state_bundle(self):
            return {"digest": self.state_digest}

        def freeze_identity(self):
            return actor_identity

    owner = Owner()
    proof = worker.restore_original_endpoint(owner, plan, tmp_path / "new")
    assert owner.restores == [str(tmp_path / "original")]
    assert proof["old_worker_source"] == old_source
    assert proof["new_worker_source"] == new_source
    assert marker_path.read_bytes() == original_bytes
    owner.state_digest = "altered critic/optimizer state"
    with pytest.raises(ValueError, match="Exact actor/critic"):
        worker.restore_original_endpoint(owner, plan, tmp_path / "bad")
    assert not (tmp_path / "bad/cross-source-restore-proof.json").exists()


def test_worker_keeps_known_business_failures_and_stops_only_unknown(tmp_path, monkeypatch):
    boundaries = []

    def build(case, folder, **kwargs):
        folder.mkdir(parents=True)
        return SimpleNamespace(
            deployment=SimpleNamespace(status="ready"),
            case={"role_decision_limits": {"maintainer": 24, "consumer": 24}},
            scenario={"variation": {}},
            active_roles=["maintainer", "consumer"],
            world=SimpleNamespace(
                state={"work_items": {"a": {"node_id": "supply"}, "b": {"node_id": "consume"}}}
            ),
        )

    runtime = SimpleNamespace(
        recorder=SimpleNamespace(snapshot=lambda: {"events": []}),
        policy_identities={},
        snapshot=lambda: {"events": []},
    )
    template = SimpleNamespace(
        build_case=build, assess_episode=lambda _: {"eligible": True, "completed": False}
    )
    monkeypatch.setitem(sys.modules, "proworksim.templates.reciprocal_data_v026", template)
    monkeypatch.setitem(
        sys.modules,
        "proworksim.reciprocal_runtime_v026",
        SimpleNamespace(runtime=lambda *args, **kwargs: (runtime, {}, {})),
    )
    monkeypatch.setattr(
        worker, "begin_episode", lambda *args, **kwargs: boundaries.append(kwargs["work_nodes"])
    )
    monkeypatch.setattr(worker, "finish_episode", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker,
        "run_fragment",
        lambda *args, **kwargs: {
            "status": "finite_task_deadline",
            "role_stops": {"consumer": "model_budget_exhausted"},
        },
    )
    owner = SimpleNamespace(
        freeze_identity=lambda: {"actor": "same"},
        capture_evaluation_state=lambda: {},
        begin_window=lambda _: {"actor": "same"},
        reseed=lambda *args, **kwargs: None,
        finish_evaluation=lambda *args: None,
        finish_evaluation_guard=lambda _: {
            "learning_unchanged": True,
            "rng_restored_exactly": True,
        },
    )
    slots = worker.assignments(catalog())["worker-0"]
    result = worker.collect(owner, {"assets_root": "source"}, slots, tmp_path / "known")
    assert result["status"] == "complete" and len(result["rows"]) == 8
    assert all(row["assessment"]["completed"] is False for row in result["rows"])
    assert boundaries == [["consume", "supply"]] * 8
    template.assess_episode = lambda _: {"eligible": False, "completed": None}
    result = worker.collect(owner, {"assets_root": "source"}, slots, tmp_path / "unknown")
    assert result["status"] == "stopped_unknown" and len(result["rows"]) == 1
    assert result["not_started"] == slots[1:]
    assert (
        json.loads((tmp_path / "unknown/progress.json").read_text())[0]["status"] == "unassessable"
    )


def test_supervisor_caps_loading_episode_and_per_worker_memory():
    plan = worker.FIXED_LIMITS
    state = {"started_at": 0, "budget_seconds": 7200}
    task = {"kind": "episode", "started_at": 0}
    kwargs = {
        "now": 100,
        "root_started": 0,
        "own_rss": 0,
        "all_rss": 0,
        "size": 0,
        "free_bytes": 2 * 1024**3,
    }
    assert supervisor.stop_reason(plan, state, task, **kwargs) is None
    assert (
        supervisor.stop_reason(plan, state, task, **{**kwargs, "now": 1140}) == "task_time_budget"
    )
    assert (
        supervisor.stop_reason(plan, state, task, **{**kwargs, "own_rss": 65 * 1024**3})
        == "host_rss_limit"
    )
    assert (
        supervisor.stop_reason(plan, state, task, **{**kwargs, "all_rss": 129 * 1024**3})
        == "host_rss_limit"
    )
    assert (
        supervisor.stop_reason(plan, state, task, **{**kwargs, "size": 12 * 1024**3})
        == "artifact_limit"
    )
    assert (
        supervisor.stop_reason(plan, state, task, **{**kwargs, "free_bytes": 0})
        == "temporary_volume_reserve"
    )


def qualification_fixture(tmp_path):
    """Synthetic metadata to test admission boundaries, not CPU work evidence."""
    declared = catalog()
    for case in declared["cases"]:
        case["role_decision_limits"] = {"maintainer": 24, "consumer": 24}
    write(tmp_path / "catalog.json", declared)
    write(tmp_path / "source-pin.json", {"scope": "explicit unit fixture"})
    write(
        tmp_path / "prior.json",
        {
            "model": str(tmp_path / "model"),
            "runtime_profile": {"max_context_tokens": 16384, "max_output_tokens": 2048},
        },
    )
    write(tmp_path / "episode.json", {"scope": "explicit metadata fixture, no work"})
    write(tmp_path / "requests.json", {"scope": "explicit metadata fixture, no model"})
    hashes = {}
    for relative in worker.QUALIFICATION_SOURCE_MODULES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# explicit test source\n")
        hashes[relative] = digest(path.read_bytes())
    choices = [
        ("normal", "constraint_first"),
        ("normal", "query_first"),
        ("single_pass", "constraint_first"),
    ]
    controls = []
    for case in declared["cases"]:
        for condition, route in choices:
            controls.append(
                {
                    "case_id": case["case_id"],
                    "condition": condition,
                    "route": route,
                    "negative_control": None,
                    "passed": True,
                    "assessment": {"eligible": True, "completed": True},
                    "tokenizer_checked": True,
                    "within_role_budgets": True,
                    "role_limits": {"maintainer": 24, "consumer": 24},
                    "context_limit": 16384,
                    "reserved_output": 2048,
                    "token_failures": [],
                    "tool_refusals": [],
                    "model_calls": 0,
                    "parameter_updates": 0,
                    "program_requests": {"maintainer": 1, "consumer": 1},
                    "tokens": [
                        {
                            "fits_prompt_and_reserved_output": True,
                            "program_output_within_limit": True,
                            "prompt_tokens": 100,
                            "program_output_tokens": 10,
                        }
                    ]
                    * 2,
                    "episode_manifest": reference(tmp_path / "episode.json"),
                    "requests_reference": reference(tmp_path / "requests.json"),
                }
            )
    for index, condition, negative in (
        (1, "normal", "ignore_demand_distinction"),
        (2, "single_pass", "ignore_unit_distinction"),
    ):
        row = copy.deepcopy(controls[0])
        row.update(
            case_id=declared["cases"][index]["case_id"],
            condition=condition,
            negative_control=negative,
            passed=False,
            assessment={"eligible": True, "completed": False},
        )
        controls.append(row)
    report = {
        "version": worker.QUALIFICATION_VERSION,
        "passed": True,
        "gpu_launch_qualified": True,
        "code_unchanged_during_qualification": True,
        "source_tree_unchanged_during_qualification": True,
        "source_tree_sha256": "fixture tree",
        "negative_controls_passed": True,
        "model_calls": 0,
        "gpu_calls": 0,
        "parameter_updates": 0,
        "model_training_eligible": False,
        "code_identity": hashes,
        "catalog_reference": reference(tmp_path / "catalog.json"),
        "catalog_sha256": digest(worker.json_bytes(declared)),
        "source_manifest_sha256": reference(tmp_path / "source-pin.json")["sha256"],
        "limits": copy.deepcopy(worker.QUALIFICATION_LIMITS),
        "tokenizer_path": str(tmp_path / "model"),
        "controls": controls,
        "counterfactual_checks": [
            {
                "case_indices": list(indices),
                "condition": condition,
                "route": route,
                "passed": True,
                "first_request_bytes_identical": True,
                "first_request_sha256": ["same", "same"],
            }
            for indices in ((0, 1), (2, 3))
            for condition, route in choices
        ],
        "fairness_checks": [
            {
                "case_index": index,
                "passed": True,
                "business_tool_definitions_equal": True,
                "same_decision_context_output_budgets": True,
                "exactly_one_legal_demand_forward": True,
                "both_conditions_reachable": True,
            }
            for index in range(4)
        ],
    }
    write(tmp_path / "qualification.json", report)
    plan = {
        "qualification": reference(tmp_path / "qualification.json"),
        "catalog": reference(tmp_path / "catalog.json"),
        "source_pin": reference(tmp_path / "source-pin.json"),
        "prior_model_plan": reference(tmp_path / "prior.json"),
    }
    return plan, declared, report


def test_cpu_qualification_accepts_complete_bound_record_and_rejects_missing_ref(tmp_path):
    plan, declared, _ = qualification_fixture(tmp_path)
    proof = worker.validate_cpu_qualification(
        plan, declared, source_root=tmp_path, current_source={"source_tree_sha256": "fixture tree"}
    )
    assert (
        proof["passed"] is True
        and proof["positive_routes"] == 12
        and proof["negative_controls"] == 2
    )
    with pytest.raises(ValueError, match="qualification reference"):
        worker.validate_cpu_qualification({}, declared)
    with pytest.raises(ValueError, match="qualification reference"):
        worker.validate_plan({"version": worker.VERSION, **worker.FIXED_LIMITS})


@pytest.mark.parametrize(
    "failure",
    [
        "failed",
        "stale_source",
        "changed_catalog",
        "token_overflow",
        "missing_route",
        "unequal_budgets",
    ],
)
def test_cpu_qualification_rejects_incomplete_or_stale_admission(tmp_path, failure):
    plan, declared, report = qualification_fixture(tmp_path)
    if failure == "failed":
        report["passed"] = False
    elif failure == "stale_source":
        report["source_tree_sha256"] = "old tree"
    elif failure == "changed_catalog":
        report["catalog_sha256"] = "old catalog"
    elif failure == "token_overflow":
        report["controls"][0]["tokens"][0]["prompt_tokens"] = 14337
    elif failure == "missing_route":
        report["controls"].pop(0)
    elif failure == "unequal_budgets":
        report["fairness_checks"][0]["same_decision_context_output_budgets"] = False
    write(tmp_path / "qualification.json", report)
    plan["qualification"] = reference(tmp_path / "qualification.json")
    with pytest.raises(ValueError):
        worker.validate_cpu_qualification(
            plan,
            declared,
            source_root=tmp_path,
            current_source={"source_tree_sha256": "fixture tree"},
        )


def test_cpu_qualification_does_not_trust_changed_script_or_overwritten_report(tmp_path):
    plan, declared, report = qualification_fixture(tmp_path)
    current = {"source_tree_sha256": "fixture tree"}
    path = tmp_path / worker.QUALIFICATION_SOURCE_MODULES[0]
    path.write_text("# altered witness after qualification\n")
    with pytest.raises(ValueError, match="source bytes changed"):
        worker.validate_cpu_qualification(
            plan, declared, source_root=tmp_path, current_source=current
        )
    path.write_text("# explicit test source\n")
    report["passed"] = False
    write(tmp_path / "qualification.json", report)
    with pytest.raises(ValueError, match="Frozen input changed"):
        worker.validate_cpu_qualification(
            plan, declared, source_root=tmp_path, current_source=current
        )
