"""CPU-only controls for a single inherited-identity path recovery worker."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.storage import read_json
from scripts import software_path_recovery_v031r2 as module
from scripts.run_ne_v021 import reference, write


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    old = tmp_path / "v031"
    actual = old / module.CANDIDATE / "actual"
    source = {"code_commit": "new-cpu-fixture", "code_dirty": False, "source_tree_sha256": "new-source"}
    old_source = {**source, "code_commit": "old-cpu-fixture", "source_tree_sha256": "old-source"}
    def profile(name):
        return {"candidate_id": name, "version": "cpu-fixture"}
    monkeypatch.setattr(module.previous, "backend_profile", profile)
    monkeypatch.setattr(module, "code_identity", lambda: copy.deepcopy(source))
    monkeypatch.setattr(module, "implementation_files", lambda: {"fixture": "frozen"})
    monkeypatch.setattr(module, "unchanged_source", lambda plan: {"cpu_fixture": True})
    plan = {"version": module.previous.VERSION, "data_root": str(tmp_path), "source": old_source,
        "source_root": str(tmp_path / "old-source"), "candidates": list(module.original.CANDIDATES),
        "inventories": {name: module.original.inventory() for name in module.original.CANDIDATES},
        "candidate_profiles": {name: profile(name) for name in module.previous.EXECUTED},
        "selection_rule": copy.deepcopy(module.original.SELECTION_RULE), "limits": copy.deepcopy(module.LIMITS),
        "prior": {"prior_artifact_roots": [str(tmp_path / "v030"), str(tmp_path / "r1"), str(tmp_path / "probes")]}}
    for name in module.UNCHANGED:
        plan.setdefault(name, {"cpu_fixture": name})
    write(old / "plan.json", plan)
    identity = {"version": "explicit-cpu-fixture", "adapter_sha256": "original-common"}
    state_path = actual / "common-state/shared-state.pt"
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(b"explicit CPU fixture, not a model tensor")
    common = {"state": reference(state_path), "actor_identity": identity, "actor_steps": 0,
              "critic_steps": 0, "state_tensor_digest": "entire-original-common"}
    write(actual / "common-state/checkpoint.json", common)
    manifest = tmp_path / "manifest.json"
    write(manifest, {"cpu_fixture": True})
    owner = {"base_identity": {"path": str(tmp_path / "fixed-model"), "manifest": reference(manifest)},
             "inference_profile": profile(module.CANDIDATE), "recipe": {"cpu_fixture": "original-recipe"}}
    write(actual / "resident/owner.json", owner)
    calls = []
    for index in range(1, 5):
        directory = actual / "qualification" / f"native-call-{index}"
        response = {"body": {"choices": [{"message": {"tool_calls": [{"function": {
            "name": "read_public_note", "arguments": '{"path":"/public-note.json"}'}}]}}]}}
        write(directory / "request.json", {"cpu_fixture": index})
        write(directory / "response.json", response)
        calls.append({"actual_trace_complete": True, "interface_passed": index in (2, 3),
                      "response_path": str(directory / "response.json"),
                      "interface_error": {"message": "The first public operation must read the declared actual note"}})
    update = {"status": "one_aggregate_diagnostic_update_completed", "actor_optimizer_steps": 1,
              "critic_optimizer_steps": 1, "backward_decisions_completed": 4,
              "behavior_probability_checks": [{"passed": True} for _ in range(4)],
              "gradient_probability_checks": [{"passed": True} for _ in range(4)]}
    checkpoint = {"state": reference(state_path), "actor_steps": 1, "critic_steps": 1}
    returned = {"calls": 1, "explicit_cpu_fixture": True}
    qualification = {"inference_ready": False, "training_ready": False, "errors": [], "native_calls_executed": 4,
        "training_integration_ready": True, "near_16k_capacity_demonstrated": True,
        "common_restored_exactly": True, "updated_identity_return_passed": True, "diagnostic_gradients_cleared": True,
        "calls": calls, "update": update, "common_before": {"state_tensor_digest": common["state_tensor_digest"]},
        "common_after": {"state_tensor_digest": common["state_tensor_digest"]},
        "checkpoint_roundtrip": {"checkpoint": checkpoint, "common_reload_exact": True, "updated_reload_exact": True,
                                 "updated_identity_changed": True, "updated_optimizer_states_changed": True},
        "return_probe": returned}
    write(actual / "qualification/report.json", qualification)
    write(actual / "qualification-result.json", qualification)
    write(actual / "qualification/aggregate-update.json", update)
    write(actual / "qualification/updated-checkpoint/checkpoint.json", checkpoint)
    write(actual / "qualification/updated-return-probe/updated-identity-return.json", returned)
    write(actual / "qualification/updated-return-probe/evaluation-guard.json", {"cpu_fixture": True})
    worker = {"candidate_id": module.CANDIDATE, "status": "qualification_failed", "rows": [],
              "screening_optimizer_steps": 0, "source_before": old_source, "source_after": old_source,
              "qualification": qualification, "common_actor_identity": identity, "actor_steps": 0, "critic_steps": 0}
    write(actual / "report.json", worker)
    state = {"candidate_id": module.CANDIDATE, "status": "qualification_failed", "ended_at": 20.0,
             "exit_code": 0, "stop_reason": None, "elapsed_gpu_seconds": 30.0,
             "cost_components": {"v030": 2.0, "r1": 3.0, "v031_probe": 5.0, "v031_worker": 20.0}}
    write(old / module.CANDIDATE / "state.json", state)
    cpu = tmp_path / "cpu.json"
    write(cpu, {"passed": True, "model_calls": 0, "source": source})
    monkeypatch.setattr(module.original, "download_state", lambda plan, candidate: {
        "status": "ready", "model_path": owner["base_identity"]["path"], "manifest": reference(manifest)})
    new_plan = module.make_plan(tmp_path, cpu, old)
    return {"root": tmp_path, "old": old, "actual": actual, "plan": new_plan, "common": common,
            "owner": owner, "source": source, "qualification": qualification}


def test_plan_binds_closed_swe_only_and_preserves_all_old_cost_and_slots(frozen):
    plan = frozen["plan"]
    assert module.validate_plan(plan) is plan
    assert plan["execution_candidates"] == [module.CANDIDATE]
    assert plan["new_screening_episodes_max"] == 12
    assert plan["prior"]["historical_gpu_seconds"] == 30.0
    assert len(plan["prior"]["references"]) == 22
    assert plan["inventories"][module.CANDIDATE] == module.original.inventory()
    assert plan["final_model_selection"] is False
    before = copy.deepcopy(plan["prior"])
    write(frozen["old"] / "supervisor.json", {"states": {"devstral-small-2507": {"status": "running"}}})
    write(frozen["old"] / "devstral-small-2507/actual/report.json", {"rows": ["dynamic unrelated record"]})
    assert module.prior_snapshot(frozen["old"]) == before


@pytest.mark.parametrize("field,value", [
    ("execution_candidates", ["devstral-small-2507"]), ("max_new_model_instances", 2),
    ("new_screening_episodes_max", 13), ("automatic_retries", True), ("final_model_selection", True),
    ("worker_gpu_seconds", 999),
])
def test_plan_rejects_expanded_scope_or_cumulative_deadline(frozen, field, value):
    plan = copy.deepcopy(frozen["plan"])
    plan[field] = value
    with pytest.raises(ValueError, match="one fixed SWE"):
        module.validate_plan(plan, check_files=False)


@pytest.mark.parametrize("mutation", ["old_screening", "original_response", "capacity", "update_record"])
def test_inherited_artifacts_cannot_be_substituted(frozen, mutation):
    actual = frozen["actual"]
    if mutation == "old_screening":
        (actual / "screen-0-0").mkdir()
    elif mutation == "original_response":
        response_path = actual / "qualification/native-call-1/response.json"
        response = read_json(response_path)
        response["body"]["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"path":"public-note.json"}'
        write(response_path, response)
    elif mutation == "capacity":
        qualification = copy.deepcopy(frozen["qualification"])
        qualification["near_16k_capacity_demonstrated"] = False
        for path in (actual / "qualification/report.json", actual / "qualification-result.json"):
            write(path, qualification)
        worker = read_json(actual / "report.json")
        worker["qualification"] = qualification
        write(actual / "report.json", worker)
    else:
        write(actual / "qualification/aggregate-update.json", {"status": "not_a_completed_update"})
    with pytest.raises(ValueError):
        module.validate_plan(frozen["plan"])


@pytest.mark.parametrize("qualified", [True, False])
def test_worker_restores_original_common_before_admission_and_screens_exactly_once(frozen, monkeypatch, qualified):
    from proworksim import native_path_admission_v031r2 as admission
    from proworksim import online_training, software_learning_v029
    plan = frozen["plan"]
    plan_path = frozen["root"] / "new-plan.json"
    write(plan_path, plan)
    monkeypatch.setattr(module, "validate_plan", lambda value: value)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "4")
    monkeypatch.setattr(module, "resources", lambda: {"explicit_cpu_fixture": True})
    monkeypatch.setattr(module, "available_cards", lambda plan, sample: [{"index": 4}])
    events, slots = [], []
    identity = frozen["common"]["actor_identity"]
    def restore(directory):
        assert Path(directory) == frozen["actual"] / "common-state"
        events.append("restore_original_common")
        return frozen["common"]
    owner = SimpleNamespace(inference_profile=frozen["owner"]["inference_profile"],
        base_identity=frozen["owner"]["base_identity"], actor_steps=0, critic_steps=0,
        restore_checkpoint=restore, freeze_identity=lambda: identity, _make_identity=lambda: identity,
        _state_bundle=lambda: {}, torch=object())
    def load(model_path, *, manifest, profile, output, recipe):
        assert recipe == frozen["owner"]["recipe"]
        assert profile == frozen["plan"]["candidate_profiles"][module.CANDIDATE]
        events.append("load_original_recipe")
        return owner
    monkeypatch.setattr(module.previous, "load_owner", load)
    monkeypatch.setattr(software_learning_v029, "migrate_software_owner", lambda value, expected_steps: events.append("migrate") or {})
    monkeypatch.setattr(online_training, "tensor_tree_digest", lambda value, torch: frozen["common"]["state_tensor_digest"])
    def qualify(value, output, *, common_dir, prior_qualification, on_stage):
        assert events == ["load_original_recipe", "migrate", "restore_original_common"]
        assert prior_qualification == plan["prior"]["references"]["qualification"]
        events.append("path_admission")
        return {"inference_ready": qualified, "training_ready": qualified, "common_restored_exactly": True,
                "new_optimizer_steps": 0, "optimizer_steps": 0, "native_calls_executed": 3,
                "calls": [{}, {}, {}], "correction_calls_executed": 0, "near_16k_stress_rerun": False}
    monkeypatch.setattr(admission, "qualify_path", qualify)
    def collect(value, spec, folder, worker_output):
        assert events[-1] == "path_admission"
        slots.extend(spec["slots"])
        return [{}]
    monkeypatch.setattr(module.original, "collect", collect)
    monkeypatch.setattr(module.original, "_screen_row", lambda row, entry, folder: {**row, "status": "closed", "R": 0})
    output = frozen["root"] / "new-worker"
    result = module.run_worker(plan_path, output)
    assert result["status"] == ("complete" if qualified else "qualification_failed")
    assert slots == (plan["inventories"][module.CANDIDATE] if qualified else [])
    assert result["actor_steps"] == result["critic_steps"] == result["screening_optimizer_steps"] == 0
    assert read_json(frozen["actual"] / "qualification/report.json")["inference_ready"] is False


def test_report_has_own_filenames_and_never_runs_final_chooser(frozen, monkeypatch):
    root = frozen["root"] / "new-run"
    write(root / "plan.json", frozen["plan"])
    state = {"status": "qualification_failed", "elapsed_gpu_seconds": 35.0,
             "cost_components": {**frozen["plan"]["prior"]["historical_cost_components"], "v031r2_worker_gpu_seconds": 5.0}}
    write(root / "supervisor.json", {"status": "qualification_failed", "states": {module.CANDIDATE: state}})
    write(root / module.CANDIDATE / "actual/report.json", {"status": "qualification_failed", "rows": [],
        "qualification": {"inference_ready": False, "training_ready": False}})
    write(frozen["old"] / "supervisor.json", {"states": {"devstral-small-2507": {"status": "running"}}})
    monkeypatch.setattr(module.original, "select_candidate", lambda *args: pytest.fail("No final chooser is authorized"))
    output = frozen["root"] / "reports"
    result = module.report(root, output)
    assert sorted(path.name for path in output.iterdir()) == ["software-path-recovery-v031r2.json", "software-path-recovery-v031r2.md"]
    assert result["final_model_selection"] is None and result["selected_candidate"] is None
    assert result["reference_candidates"]["devstral-small-2507"]["status"] == "running"
    assert result["candidate_result"]["screening_rows_recorded"] == 0
    assert result["prior_path_failure"]["interface_passed"] is False


def test_supervisor_launches_only_one_swe_worker_and_keeps_historical_cost(frozen, monkeypatch):
    plan_path = frozen["root"] / "new-plan.json"
    write(plan_path, frozen["plan"])
    monkeypatch.setattr(module, "validate_plan", lambda value: value)
    limits = copy.deepcopy(module.LIMITS)
    limits["gpu_capacity_stability_seconds"] = 0
    monkeypatch.setattr(module, "LIMITS", limits)
    monkeypatch.setattr(module, "resources", lambda: {})
    monkeypatch.setattr(module, "available_cards", lambda plan, sample: [{"index": 4, "uuid": "GPU-own-fixture"}])
    monkeypatch.setattr(module, "artifact_usage", lambda plan, root: 1)
    monkeypatch.setattr(module, "target_resources", lambda gpu, worker_pid: {})
    monkeypatch.setattr(module, "worker_identity", lambda pid: {"pid": pid, "alive": True, "start_ticks": 123})
    monkeypatch.setattr(module, "TelemetryGuard", lambda *args, **kwargs: object())
    monkeypatch.setattr(module.original, "worker_env", lambda *args: {})
    monkeypatch.setattr(module.continuation, "_stop_worker", lambda process, state: None)
    launches = []
    class Process:
        pid, returncode = 919191, 0
        def poll(self):
            return 0
        def wait(self, timeout):
            return 0
    def launch(argv, **kwargs):
        launches.append(argv)
        output = Path(argv[argv.index("--output") + 1])
        write(output / "report.json", {"status": "qualification_failed", "source_before": frozen["source"],
              "source_after": frozen["source"], "rows": []})
        return Process()
    monkeypatch.setattr(module.subprocess, "Popen", launch)
    result = module.supervise(plan_path, frozen["root"] / "new-run")
    assert len(launches) == 1
    assert module.CANDIDATE in launches[0][-1]
    assert set(result["states"]) == {module.CANDIDATE}
    state = result["states"][module.CANDIDATE]
    assert state["status"] == "qualification_failed" and state["attempted"] is True
    assert state["elapsed_gpu_seconds"] == 30.0 + state["cost_components"]["v031r2_worker_gpu_seconds"]
    assert result["running_gpu_seconds"] == 0
    assert result["final_model_selection"] is False


def test_finish_publishes_only_the_two_new_reports(frozen, monkeypatch):
    root = frozen["root"] / "new-run"
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        if "supervise" in command:
            write(root / "supervisor.json", {"explicit_cpu_fixture": True})
        code = 1 if command[:3] == ["git", "diff", "--quiet"] else 0
        return SimpleNamespace(returncode=code, stdout="cpu fixture", stderr="")
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.subprocess, "check_output", lambda command, **kwargs: "main\n" if "branch" in command else "cpu-fixture-commit\n")
    reports = []
    monkeypatch.setattr(module, "report", lambda run_root, output: reports.append((run_root, output)))
    value = module.finish(frozen["root"] / "plan.json", root, frozen["root"], publish=True)
    assert value["publish_status"] == "pushed"
    assert len(reports) == 1
    commit = next(command for command in commands if command[:2] == ["git", "commit"])
    assert "--only" in commit
    assert commit[commit.index("--") + 1:] == module.REPORT_PATHS
    assert next(command for command in commands if command[:2] == ["git", "add"])[3:] == module.REPORT_PATHS
    assert not any("software-model-selection-v031.json" in argument for command in commands for argument in command)
