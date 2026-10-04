"""CPU plan/gate/worker controls; every process and model is an explicit fixture."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.storage import digest, json_bytes, read_json
from scripts import software_model_selection_v031 as module
from scripts.run_ne_v021 import reference, write


def fixture_profile(candidate):
    return {"candidate_id": candidate, "version": "declared-cpu-fixture-v031"}


def numeric_report(root, candidate, trace, report_path):
    return {"candidate_id": candidate, "passed": True, "status": "passed", "ended_at": 12.0,
            "profile_sha256": digest(json_bytes(fixture_profile(candidate))),
            "source": {"code_commit": "probe-old-commit", "cpu_fixture": True},
            "tested_files_sha256": {name: digest((root / name).read_bytes()) for name in module.NUMERIC_PROOF_FILES},
            "original_trace_refs": [reference(trace)], "all_full_tokens_retained": True,
            "all_behavior_and_gradient_probability_passed": True, "full_backward_completed": True,
            "optimizer_steps": 0, "new_model_calls": 0, "actual_worker_gpu_seconds": 4.0,
            "original_actor_identity_matched": True, "common_restored_exactly": True,
            "artifact_directory": str(Path(report_path).resolve().parent),
            "probe_ledger_directory": str(Path(report_path).resolve().parent.parent),
            "test_fixture_only_not_a_real_gpu_receipt": True}


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    code = tmp_path / "code"
    for name in module.NUMERIC_PROOF_FILES:
        path = code / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixed CPU file binding\n")
    monkeypatch.setattr(module, "SOURCE", code)
    monkeypatch.setattr(module, "backend_profile", fixture_profile)
    monkeypatch.setattr(module, "implementation_files", lambda: {"fixture": "f" * 64})
    monkeypatch.setattr(module, "comparison_proof", lambda prior: {"protected_fixture": True})
    monkeypatch.setattr(module.original, "reference", lambda path: {"path": str(Path(path)), "sha256": "1" * 64})
    old_plan = module.original.make_plan(tmp_path / "data", tmp_path / "cpu.json")
    old_plan["source"] = {"code_commit": "original", "code_dirty": False, "source_tree_sha256": "a" * 64}
    source = {"code_commit": "new-v031", "code_dirty": False, "source_tree_sha256": "c" * 64}
    monkeypatch.setattr(module, "code_identity", lambda: copy.deepcopy(source))
    old, recovered = tmp_path / "original", tmp_path / "recovery"
    proof = tmp_path / "retained-data.json"
    write(proof, {"cpu_fixture": True})
    first_states, second_states, probe_paths = {}, {}, {}
    for candidate in module.original.CANDIDATES:
        retained = candidate == module.RETAINED
        rows = [{**copy.deepcopy(row), "category": module.original.case_spec(row["case_id"])["category"],
            "status": "closed", "R": 0, "complete_work": False, "format_errors": 0,
            "entry": reference(proof), "assessment": reference(proof), "evaluation_guard": reference(proof)}
            for row in old_plan["inventories"][candidate]] if retained else []
        first = {"status": "complete" if retained else "interrupted_or_error", "rows": rows,
            "source_before": old_plan["source"], "source_after": old_plan["source"], "screening_optimizer_steps": 0,
            "qualification": {"inference_ready": retained, "training_ready": retained}}
        second = copy.deepcopy(first)
        if not retained:
            second.update(status="qualification_failed", source_before={"code_commit": "r1"})
        write(old / candidate / "actual/report.json", first)
        write(recovered / candidate / "actual/report.json", second)
        first_states[candidate] = {"status": "complete" if retained else "stopped", "elapsed_gpu_seconds": 100.0 if retained else 10.0}
        second_states[candidate] = ({**copy.deepcopy(first_states[candidate]), "retained_original": True} if retained else
            {"status": "qualification_failed", "elapsed_gpu_seconds": 30.0, "recovery_worker_gpu_seconds": 20.0})
        if not retained:
            number = 1 if candidate == module.EXECUTED[0] else 3
            trace = recovered / candidate / "actual/qualification" / f"native-call-{number}/response.json"
            write(trace, {"saved_original_trace_cpu_fixture": candidate})
            path = tmp_path / "numeric-probes" / candidate / "admission-proof.json"
            write(path, numeric_report(code, candidate, trace, path))
            probe_paths[candidate] = path
    for directory, states in ((old, first_states), (recovered, second_states)):
        write(directory / "plan.json", old_plan)
        write(directory / "supervisor.json", {"status": "finite_batch_no_qualified_candidate",
            "ended_at": 123.0, "running_gpu_seconds": 0, "states": states})
    plan = module.make_plan(tmp_path / "data", tmp_path / "cpu.json", old, recovered, probe_paths)
    return {"plan": plan, "old": old, "recovered": recovered, "code": code, "probes": probe_paths}


def test_new_batch_preserves_old_9b_and_exact_inventory_without_old_cost_double_count(frozen):
    plan = frozen["plan"]
    assert module.validate_plan(plan, check_files=False) is plan
    assert plan["execution_candidates"] == list(module.EXECUTED)
    assert plan["retained_candidates"] == [module.RETAINED]
    assert plan["new_screening_episodes_max"] == 24 and plan["cumulative_screening_episodes_max"] == 36
    assert plan["gpu_preference"] == [4, 6, 5, 0, 1, 2, 3, 7]
    assert sorted(plan["gpu_preference"]) == list(range(8))
    for candidate in module.EXECUTED:
        old = plan["prior"]["workers"][candidate]
        assert old["historical_gpu_seconds"] == 30
        assert old["historical_cost_components"] == {"original_worker_gpu_seconds": 10, "r1_worker_gpu_seconds": 20}
        assert plan["numeric_probes"][candidate]["elapsed_gpu_seconds"] == 4
        assert plan["numeric_probes"][candidate]["report"]["path"] == str(frozen["probes"][candidate])
    for field, value in (("new_screening_episodes_max", 25), ("automatic_retries", True),
                         ("gpu_preference", [5]), ("automatic_model_replacement", True)):
        changed = copy.deepcopy(plan)
        changed[field] = value
        with pytest.raises(ValueError, match="v031 batch"):
            module.validate_plan(changed, check_files=False)
    changed = copy.deepcopy(plan)
    changed["inventories"][module.EXECUTED[0]][0]["sampling_seed"] += 1
    with pytest.raises(ValueError, match="v031 batch"):
        module.validate_plan(changed, check_files=False)


@pytest.mark.parametrize("field,value", [
    ("passed", False), ("profile_sha256", "wrong"), ("new_model_calls", 1), ("optimizer_steps", 1),
    ("all_full_tokens_retained", False), ("all_behavior_and_gradient_probability_passed", False),
    ("full_backward_completed", False), ("common_restored_exactly", False),
])
def test_gpu_numerical_admission_cannot_be_substituted_by_flags_or_changed_protocol(frozen, field, value):
    candidate = module.EXECUTED[0]
    path = frozen["probes"][candidate]
    record = read_json(path)
    record[field] = value
    write(path, record)
    with pytest.raises(ValueError, match="GPU old-trace"):
        module.validate_numeric_proof(path, candidate, fixture_profile(candidate))


def test_old_trace_proof_binds_exact_failed_trace_and_actual_tested_files(frozen):
    candidate = module.EXECUTED[0]
    path = frozen["probes"][candidate]
    proof = module.validate_numeric_proof(path, candidate, fixture_profile(candidate))
    assert proof["source"]["code_commit"] == "probe-old-commit"
    changed = copy.deepcopy(proof)
    changed["original_trace_refs"] = frozen["plan"]["numeric_probes"][module.EXECUTED[1]]["original_trace_refs"]
    with pytest.raises(ValueError, match="original failing trace"):
        module._trace_binding(frozen["plan"]["prior"], candidate, changed)
    (frozen["code"] / "src/proworksim/functional_dense_v031.py").write_text("# unqualified numeric change\n")
    with pytest.raises(ValueError, match="implementation changed"):
        module.validate_numeric_proof(path, candidate, fixture_profile(candidate))


def test_prior_formal_work_or_double_counted_recovery_cost_is_rejected(frozen):
    old, recovered = frozen["old"], frozen["recovered"]
    before = (old / module.RETAINED / "actual/report.json").read_bytes()
    candidate = module.EXECUTED[0]
    path = recovered / "supervisor.json"
    state = read_json(path)
    state["states"][candidate]["elapsed_gpu_seconds"] = 40
    write(path, state)
    with pytest.raises(ValueError, match="exactly once"):
        module.prior_snapshot(old, recovered)
    state["states"][candidate]["elapsed_gpu_seconds"] = 30
    write(path, state)
    (recovered / candidate / "actual/screen-0-0").mkdir()
    with pytest.raises(ValueError, match="no prior formal"):
        module.prior_snapshot(old, recovered)
    assert (old / module.RETAINED / "actual/report.json").read_bytes() == before


def test_public_world_and_historical_9b_source_changes_prevent_retention(tmp_path, monkeypatch):
    old, current = tmp_path / "old", tmp_path / "current"
    paths = ("src/proworksim/harness_sdk.py", "src/proworksim/candidate_runtime_v015.py",
             "examples/software-sources-v030/case/contract.md")
    for root in (old, current):
        for name in paths:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("same frozen public behavior\n")
    plan_path = tmp_path / "old-plan.json"
    write(plan_path, {"source_root": str(old), "source": {"code_commit": "original"}})
    prior = {"original_plan": reference(plan_path)}
    monkeypatch.setattr(module, "SOURCE", current)
    monkeypatch.setattr(module.original, "_implementation_reference", lambda: {})
    proof = module.comparison_proof(prior)
    assert proof["protected_file_count"] == 3
    (current / paths[0]).write_text("different SDK behavior\n")
    with pytest.raises(ValueError, match="old path changed"):
        module.comparison_proof(prior)


def test_numeric_artifact_directory_binding_union_growth_and_model_exclusion(frozen, tmp_path):
    candidate = module.EXECUTED[0]
    path = frozen["probes"][candidate]
    proof = read_json(path)
    proof["artifact_directory"] = str(tmp_path / "wrong-candidate-directory")
    write(path, proof)
    with pytest.raises(ValueError, match="actual admission location"):
        module.validate_numeric_proof(path, candidate, fixture_profile(candidate))
    proof["artifact_directory"] = str(path.parent)
    write(path, proof)
    bound = module.validate_numeric_proof(path, candidate, fixture_profile(candidate))
    assert bound["probe_ledger_directory"] == str(path.parent.parent)

    old = tmp_path / "union/old"
    recovered = old / "nested-recovery"
    numerical = tmp_path / "union/numerical"
    nested_numeric = numerical / "nested"
    formal = numerical / "formal"
    for folder in (recovered, nested_numeric, formal):
        folder.mkdir(parents=True)
    (old / "original.log").write_bytes(b"a" * 11)
    (recovered / "recovery.log").write_bytes(b"b" * 13)
    (numerical / "controller.json").write_bytes(b"c" * 17)
    (nested_numeric / "gradients.bin").write_bytes(b"d" * 19)
    (formal / "initial.json").write_bytes(b"e" * 23)
    prior = {"original_root": str(old), "recovery_root": str(recovered), "prior_artifact_bytes": 37}
    probes = {"one": {"probe_ledger_directory": str(numerical)},
              "two": {"probe_ledger_directory": str(nested_numeric)},
              "duplicate": {"probe_ledger_directory": str(numerical)}}
    inventory = module.bind_artifact_inventory(prior, probes, tmp_path / "data")
    assert len(inventory["prior_artifact_roots"]) == 2
    assert inventory["numeric_probe_artifact_roots"] == [str(numerical)]
    assert inventory["prior_artifact_bytes"] == 83  # Each real file exactly once.
    plan = {"prior": inventory}
    assert module.artifact_usage(plan, formal) == 83  # Nested formal directory is not added again.
    (numerical / "controller.json").write_bytes(b"c" * 29)
    assert module.artifact_usage(plan, formal) == 95  # Include later driver-ledger growth.
    model_root = tmp_path / "data/runs/assets/models"
    for invalid in (model_root / "model", model_root.parent):
        with pytest.raises(ValueError, match="model assets"):
            module.bind_artifact_inventory(prior, {"bad": {"probe_ledger_directory": str(invalid)}}, tmp_path / "data")
    assert module.LIMITS["artifact_bytes"] == 128 * 1024**3


@pytest.mark.parametrize("ready", [True, False])
def test_only_new_candidate_loads_one_fresh_owner_and_screen_requires_strict_restore(frozen, tmp_path, monkeypatch, ready):
    import proworksim.model_qualification_v030 as qualification
    import proworksim.online_training as learning
    import proworksim.software_learning_v029 as software_learning

    plan = frozen["plan"]
    monkeypatch.setattr(module, "validate_plan", lambda value: value)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "5")
    monkeypatch.setattr(module, "resources", lambda: {})
    monkeypatch.setattr(module, "available_cards", lambda *args: [{"index": 5}])
    recipe_path = tmp_path / "owner-recipe.json"
    write(recipe_path, {"recipe": {"frozen_original": True}})
    plan["owner_recipe"] = reference(recipe_path)
    manifest = tmp_path / "download.json"
    write(manifest, {"fixture": True})
    monkeypatch.setattr(module.original, "download_state", lambda *args: {
        "status": "ready", "model_path": "fixture-model", "manifest": reference(manifest)})
    plan_path = tmp_path / "plan.json"
    write(plan_path, plan)
    calls = []

    class Owner:
        actor_steps = critic_steps = 0
        torch = object()
        recipe = {"members": ["member_a", "member_b", "software_inactive"]}

        def _state_bundle(self):
            return {"cpu_state": True}

        def freeze_identity(self):
            return {"new_fixture_actor": True}

        _make_identity = freeze_identity

        def save_checkpoint(self, path):
            calls.append("common")
            return {"state_tensor_digest": "common", "actor_identity": self.freeze_identity()}

    owner = Owner()

    def construct(*args, **kwargs):
        calls.append("load")
        assert kwargs["manifest"] == manifest
        assert kwargs["profile"] == fixture_profile(module.EXECUTED[0])
        return owner

    def qualify(actual, folder, *, common_dir, return_probe, on_stage):
        calls.append("qualify")
        assert calls.index("common") < calls.index("qualify")
        on_stage("qualification_update", "fixture")
        return {"inference_ready": True, "training_ready": ready, "common_restored_exactly": True}

    monkeypatch.setattr(module, "load_owner", construct)
    monkeypatch.setattr(software_learning, "migrate_software_owner", lambda actual, **kw: {"expected_steps": kw["expected_steps"]})
    monkeypatch.setattr(qualification, "qualify", qualify)
    monkeypatch.setattr(learning, "tensor_tree_digest", lambda *args: "common")
    monkeypatch.setattr(module.original, "collect", lambda actual, spec, folder, output: calls.append("screen") or [{}])
    monkeypatch.setattr(module.original, "_screen_row", lambda row, *args: copy.deepcopy(row))
    report = module.run_worker(plan_path, module.EXECUTED[0], tmp_path / "actual")
    assert calls.count("load") == calls.count("qualify") == 1
    assert calls.count("screen") == (12 if ready else 0)
    assert report["status"] == ("complete" if ready else "qualification_failed")
    with pytest.raises(ValueError, match="Only the two new"):
        module.run_worker(plan_path, module.RETAINED, tmp_path / "forbidden-retained")
    monkeypatch.setattr(learning, "tensor_tree_digest", lambda *args: "not-common")
    with pytest.raises(ValueError, match="full original common"):
        module.run_worker(plan_path, module.EXECUTED[0], tmp_path / "bad-restore")


@pytest.mark.parametrize("numeric_failure", [False, True])
def test_supervisor_uses_latest_gpu_priority_never_reexecutes_9b_and_preserves_all_costs(frozen, tmp_path, monkeypatch, numeric_failure):
    plan = frozen["plan"]
    if numeric_failure:
        candidate = module.EXECUTED[0]
        path = frozen["probes"][candidate]
        value = read_json(path)
        value.update(passed=False, status="failed", full_backward_completed=False,
                     all_behavior_and_gradient_probability_passed=False,
                     error={"message": "CPU fixture failed numerical preflight"})
        write(path, value)
        plan["numeric_probes"][candidate] = module.validate_numeric_proof(path, candidate, fixture_profile(candidate))
    plan_path = tmp_path / "plan.json"
    write(plan_path, plan)
    monkeypatch.setattr(module, "validate_plan", lambda value: value)
    clock = {"now": 100.0}
    monkeypatch.setattr(module.time, "time", lambda: clock["now"])
    monkeypatch.setattr(module.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + 60))
    monkeypatch.setattr(module, "resources", lambda: {})
    monkeypatch.setattr(module, "target_resources", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "worker_identity", lambda pid: {"start_ticks": pid})
    monkeypatch.setattr(module, "TelemetryGuard", lambda *args, **kwargs: SimpleNamespace(observe=lambda *a, **k: {}))
    monkeypatch.setattr(module, "available_cards", lambda plan, sample, excluded=(): [
        {"index": index, "uuid": "GPU-fixture-" + str(index)} for index in (4, 6) if index not in excluded])
    started = []

    class Process:
        returncode = 0

        def __init__(self, argv, **kwargs):
            candidate = argv[argv.index("--candidate") + 1]
            assert candidate in module.EXECUTED
            started.append((candidate, kwargs["env"]["CUDA_VISIBLE_DEVICES"]))
            self.pid = 1000 + len(started)
            write(Path(argv[argv.index("--output") + 1]) / "report.json", {
                "status": "qualification_failed", "qualification": {"inference_ready": False, "training_ready": False}, "rows": []})

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(module.subprocess, "Popen", Process)
    result = module.supervise(plan_path, tmp_path / "run")
    assert started == ([(module.EXECUTED[1], "4")] if numeric_failure else
                       [(module.EXECUTED[0], "4"), (module.EXECUTED[1], "6")])
    assert (tmp_path / "run" / module.RETAINED).resolve() == frozen["old"] / module.RETAINED
    assert result["states"][module.RETAINED]["elapsed_gpu_seconds"] == 100
    for candidate in module.EXECUTED:
        state = result["states"][candidate]
        assert state["cost_components"]["original_worker_gpu_seconds"] == 10
        assert state["cost_components"]["r1_worker_gpu_seconds"] == 20
        assert state["cost_components"]["v031_old_trace_gpu_proof_seconds"] == 4
        assert state["elapsed_gpu_seconds"] == 34 + state["cost_components"]["v031_worker_gpu_seconds"]
    if numeric_failure:
        failed = result["states"][module.EXECUTED[0]]
        assert failed["preflight_status"] == "numeric_preflight_failed"
        assert failed["native_calls"] == failed["formal_screening_episodes"] == 0
        assert not failed["attempted"]
        prior_bytes = (frozen["old"] / module.RETAINED / "actual/report.json").read_bytes()
        archived = module.report(tmp_path / "run", tmp_path / "reports")
        assert archived["candidates"][module.RETAINED]["retained_original"]
        assert archived["candidates"][module.EXECUTED[0]]["qualification"]["inference_ready"] is None
        assert all(row["R"] is None for row in archived["candidates"][module.EXECUTED[0]]["outcomes"])
        assert (tmp_path / "reports/software-model-selection-v031.md").exists()
        assert not (tmp_path / "reports/software-model-selection-v030.md").exists()
        assert (frozen["old"] / module.RETAINED / "actual/report.json").read_bytes() == prior_bytes
    assert result["status"] == "finite_batch_no_qualified_candidate"
