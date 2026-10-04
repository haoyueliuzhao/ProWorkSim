"""CPU supervisor/selection controls; no GPU, checkpoint weights or model calls."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.storage import read_json
from scripts import software_model_selection_v030 as module
from scripts.run_ne_v021 import reference, write


@pytest.fixture
def plan(tmp_path, monkeypatch):
    # Only the independent plan-shape tests omit file qualification. Worker and
    # queue tests explicitly mock their stage boundaries, never real models.
    monkeypatch.setattr(module, "reference", lambda path: {"path": str(Path(path)), "sha256": "1" * 64})
    return module.make_plan(tmp_path, tmp_path / "cpu-qualification.json")


def result_rows(plan, candidate, *, successes=None, errors=0):
    successes = set(range(12)) if successes is None else set(successes)
    return [{**copy.deepcopy(row), "category": module.case_spec(row["case_id"])["category"],
             "status": "closed", "R": int(index in successes), "complete_work": index in successes,
             "format_errors": errors if index == 0 else 0}
            for index, row in enumerate(plan["inventories"][candidate])]


def reports_and_states(plan):
    reports = {candidate: {"status": "complete", "qualification": {"inference_ready": True, "training_ready": True},
                           "rows": result_rows(plan, candidate)} for candidate in module.CANDIDATES}
    states = {candidate: {"status": "complete", "elapsed_gpu_seconds": 100.0} for candidate in module.CANDIDATES}
    return reports, states


def test_fixed_inventory_caps_and_no_automatic_extension(plan):
    assert module.validate_plan(plan, check_files=False) is plan
    assert list(plan["inventories"]) == list(module.CANDIDATES)
    rows = plan["inventories"][module.CANDIDATES[0]]
    assert len(rows) == 12 and [row["sampling_seed"] for row in rows] == [module.SEEDS[0]] * 6 + [module.SEEDS[1]] * 6
    assert [len(row["role_decision_limits"]) for row in rows] == [1, 1, 1, 1, 2, 2] * 2
    assert all(set(row["role_decision_limits"].values()) == {64} for row in rows)
    assert sum(sum(row["role_decision_limits"].values()) for row in rows) == 1024
    assert plan["qualification_limits"]["development_cases_used_for_update"] is False
    assert plan["automatic_successors"] == [] and plan["max_screening_episodes"] == 36
    for key, value in (("max_screening_episodes", 37), ("automatic_retries", True), ("automatic_model_replacement", True)):
        changed = copy.deepcopy(plan)
        changed[key] = value
        with pytest.raises(ValueError, match="Fixed v030"):
            module.validate_plan(changed, check_files=False)
    changed = copy.deepcopy(plan)
    changed["candidates"].append("one-more-model")
    with pytest.raises(ValueError, match="Fixed v030"):
        module.validate_plan(changed, check_files=False)


def test_download_pending_complete_and_wrong_source_are_separate(plan, tmp_path):
    candidate = module.CANDIDATES[1]
    path = Path(plan["download_manifests"][candidate])
    assert module.download_state(plan, candidate)["status"] == "waiting_download"
    base = {"candidate_id": candidate, "repo_id": module.MODELS[candidate]["repo_id"],
            "declared_hf_revision": module.MODELS[candidate]["revision"], "source_metadata_sha256": "1" * 64,
            "model_path": str(tmp_path / "model"), "status": "downloading_weights"}
    write(path, base)
    assert module.download_state(plan, candidate)["status"] == "waiting_download"
    write(path, {**base, "status": "complete"})
    assert module.download_state(plan, candidate)["status"] == "ready"
    write(path, {**base, "status": "download_or_verification_failed"})
    assert module.download_state(plan, candidate)["status"] == "download_failed"
    write(path, {**base, "status": "complete", "declared_hf_revision": "different"})
    assert module.download_state(plan, candidate)["status"] == "download_failed"


def test_selection_is_category_stratified_known_and_qualified(plan):
    reports, states = reports_and_states(plan)
    # Eight successes cannot conceal 0/4 on the root-goal team category.
    first = module.CANDIDATES[0]
    reports[first]["rows"] = result_rows(plan, first, successes={0, 1, 2, 3, 6, 7, 8, 9})
    second, third = module.CANDIDATES[1:]
    reports[second]["rows"][0].update(status="execution_unknown", R=None, complete_work=None)
    reports[third]["qualification"]["training_ready"] = False
    selection = module.select_candidate(plan, states, reports)
    assert selection["status"] == "finite_batch_no_qualified_candidate"
    assert selection["selected_candidate"] is None and selection["automatic_successors"] == []
    assert not selection["candidate_results"][first]["selection_eligible"]
    assert selection["candidate_results"][first]["categories"]["o1_root_goal"]["successful_complete_deliveries"] == 0
    assert not selection["candidate_results"][second]["all_12_known"]
    states[third]["status"] = "running"
    with pytest.raises(ValueError, match="terminal"):
        module.select_candidate(plan, states, reports)


def test_selection_order_uses_team_repair_api_consistency_format_cost_then_declared_order(plan):
    reports, states = reports_and_states(plan)
    a, b, c = module.CANDIDATES
    assert module.select_candidate(plan, states, reports)["selected_candidate"] == a
    states[c]["elapsed_gpu_seconds"] = 80
    assert module.select_candidate(plan, states, reports)["selected_candidate"] == c
    reports[c]["rows"][0]["format_errors"] = 1
    assert module.select_candidate(plan, states, reports)["selected_candidate"] == a
    reports[a]["rows"][0]["format_errors"] = 2
    assert module.select_candidate(plan, states, reports)["selected_candidate"] == b
    # A greater team success count outranks cost and formats.
    reports[a]["rows"][4].update(R=0, complete_work=False)
    reports[b]["rows"][4].update(R=0, complete_work=False)
    assert module.select_candidate(plan, states, reports)["selected_candidate"] == c
    reports[c]["qualification"]["training_ready"] = False
    reports[a]["rows"] = result_rows(plan, a, successes={0, 1, 2, 4, 5, 6, 7, 8, 10, 11})
    reports[b]["rows"] = result_rows(plan, b, successes=set(range(12)) - {0})
    assert module.select_candidate(plan, states, reports)["selected_candidate"] == b  # More repair, less API.
    reports[a]["rows"] = result_rows(plan, a, successes=set(range(12)) - {0})
    reports[b]["rows"] = result_rows(plan, b, successes=set(range(12)) - {0, 1})
    assert module.select_candidate(plan, states, reports)["selected_candidate"] == a  # Equal team/repair, more API.
    reports[a]["rows"] = result_rows(plan, a, successes={0, 6, 2, 8, 4, 10}, errors=3)
    reports[b]["rows"] = result_rows(plan, b, successes={0, 1, 2, 3, 4, 5})
    assert module.select_candidate(plan, states, reports)["selected_candidate"] == a  # Equal categories, greater seed consistency.
    # Changing a seed cannot turn a rerun into the missing scheduled result.
    reports[a]["rows"][0]["sampling_seed"] = 999
    with pytest.raises(ValueError, match="inventory prefix"):
        module.select_candidate(plan, states, reports)


@pytest.mark.parametrize("candidate,ready", [(module.CANDIDATES[0], True), (module.CANDIDATES[1], True), (module.CANDIDATES[2], False)])
def test_worker_loads_one_owner_qualifies_restores_then_screens_once(plan, tmp_path, monkeypatch, candidate, ready):
    import proworksim.candidate_runtime_v030 as dense
    import proworksim.deterministic_work_v024 as previous
    import proworksim.model_qualification_v030 as qualification
    import proworksim.online_training as learning
    import proworksim.software_learning_v029 as software_learning

    monkeypatch.setattr(module, "validate_plan", lambda value: value)
    monkeypatch.setattr(module, "reference", reference)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(module, "resources", lambda: {})
    monkeypatch.setattr(module, "available_cards", lambda *args: [{"index": 0}])
    owner_json = tmp_path / "owner.json"
    write(owner_json, {"recipe": {"frozen-original": True}})
    plan["owner_recipe"] = reference(owner_json)
    manifest = tmp_path / "download.json"
    write(manifest, {"status": "complete", "test_only": True})
    prior = tmp_path / "prior.json"
    write(prior, {"model": "fixture-model", "manifest": reference(manifest), "runtime_profile": {"fixture": True}})
    plan["prior_model_plan"] = reference(prior)
    plan_path = tmp_path / "plan.json"
    write(plan_path, plan)
    monkeypatch.setattr(module, "download_state", lambda *args: {"status": "ready", "manifest": reference(manifest), "model_path": "fixture-model"})
    calls = []

    class Owner:
        actor_steps = critic_steps = 0
        torch = object()
        recipe = {"members": ["member_a", "member_b", "software_inactive"]}

        def _state_bundle(self):
            return {"actor_steps": self.actor_steps}

        def freeze_identity(self):
            return {"cpu_fixture": candidate}

        _make_identity = freeze_identity

        def save_checkpoint(self, path):
            calls.append("save-common")
            return {"state_tensor_digest": "common-exact", "actor_identity": self.freeze_identity()}

    owner = Owner()

    def construct(*args, **kwargs):
        calls.append("construct")
        assert kwargs["recipe"] == {"frozen-original": True}
        assert Path(kwargs["manifest"]) == manifest  # Global stable identity, not the per-worker archival copy.
        return owner

    def restore(*args):
        calls.append("strict-old-restore")
        owner.actor_steps = owner.critic_steps = 3

    def migrate(actual, output=None, *, expected_steps=(3, 3)):
        calls.append(("migrate", expected_steps))
        assert (actual.actor_steps, actual.critic_steps) == ((3, 3) if candidate == module.CANDIDATES[0] else (0, 0))
        return {"cpu_fixture": True}

    def qualify(actual, folder, *, common_dir, return_probe, on_stage):
        calls.append("qualify")
        assert calls.index("save-common") < calls.index("qualify")
        on_stage("qualification_inference", "fixture-native-stage")
        on_stage("qualification_update", "fixture-update-stage")
        return {"inference_ready": True, "training_ready": ready, "common_restored_exactly": True}

    def collect(actual, spec, folder, output):
        calls.append(("screen", spec["window_id"]))
        return [{"slot_id": spec["slots"][0]["slot_id"]}]

    monkeypatch.setattr(dense.DenseCandidateActor, "from_candidate", construct)
    monkeypatch.setattr(previous.DeterministicCandidateActor, "from_candidate", construct)
    monkeypatch.setattr(module, "restore", restore)
    monkeypatch.setattr(software_learning, "migrate_software_owner", migrate)
    monkeypatch.setattr(qualification, "qualify", qualify)
    monkeypatch.setattr(learning, "tensor_tree_digest", lambda *args: "common-exact")
    monkeypatch.setattr(module, "collect", collect)
    monkeypatch.setattr(module, "_screen_row", lambda row, *args: copy.deepcopy(row))
    result = module.run_worker(plan_path, tmp_path / "unused", candidate, tmp_path / "actual")
    assert calls.count("construct") == 1 and calls.count("qualify") == 1
    assert len([call for call in calls if isinstance(call, tuple) and call[0] == "screen"]) == (12 if ready else 0)
    assert result["status"] == ("complete" if ready else "qualification_failed")
    assert ("strict-old-restore" in calls) == (candidate == module.CANDIDATES[0])
    assert ("migrate", (3, 3) if candidate == module.CANDIDATES[0] else None) in calls
    assert result["screening_optimizer_steps"] == 0
    if candidate != module.CANDIDATES[0]:
        assert read_json(tmp_path / "actual/model-download-manifest.json") == read_json(manifest)


def test_supervisor_waits_without_gpu_then_continues_independent_candidates(plan, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "validate_plan", lambda value: value)
    plan_path = tmp_path / "plan.json"
    write(plan_path, plan)
    clock = {"now": 100.0}
    monkeypatch.setattr(module.time, "time", lambda: clock["now"])
    monkeypatch.setattr(module.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + 60))
    monkeypatch.setattr(module, "resources", lambda: {"fixture": True})
    monkeypatch.setattr(module, "target_resources", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "artifact_bytes", lambda root: 0)
    monkeypatch.setattr(module, "rss", lambda pid: 0)
    monkeypatch.setattr(module, "available_cards", lambda plan, sample, excluded=(): [
        {"index": index, "uuid": "fixture-" + str(index)} for index in range(3) if index not in excluded])
    monkeypatch.setattr(module, "worker_identity", lambda pid: {"start_ticks": pid})
    monkeypatch.setattr(module, "TelemetryGuard", lambda *args, **kwargs: SimpleNamespace(observe=lambda *a, **k: {}))
    monkeypatch.setattr(module, "download_state", lambda plan, candidate: {
        "status": "ready" if candidate == module.CANDIDATES[0] or clock["now"] >= 220 else "waiting_download"})
    starts = []

    class Process:
        returncode = 0

        def __init__(self, argv, **kwargs):
            candidate = argv[argv.index("--worker") + 1]
            starts.append((candidate, clock["now"]))
            self.pid = 1000 + len(starts)
            output = Path(argv[argv.index("--output") + 1])
            if candidate == module.CANDIDATES[0]:
                report = {"status": "qualification_failed", "qualification": {"inference_ready": False, "training_ready": False}, "rows": []}
            else:
                report = {"status": "complete", "qualification": {"inference_ready": True, "training_ready": True},
                          "rows": result_rows(plan, candidate)}
            write(output / "report.json", report)

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(module.subprocess, "Popen", Process)
    monkeypatch.setattr(module, "code_identity", lambda: plan["source"])
    monkeypatch.setattr(module, "_implementation_reference", lambda: plan["implementation_files_sha256"])
    result = module.supervise(plan_path, tmp_path / "run")
    assert len(starts) == 3 and len({candidate for candidate, _ in starts}) == 3
    assert all(start >= 220 for candidate, start in starts if candidate != module.CANDIDATES[0])
    assert result["states"][module.CANDIDATES[0]]["status"] == "qualification_failed"
    assert result["status"] == "selected"
    selection = read_json(tmp_path / "run/selection.json")
    assert selection["selected_candidate"] in module.CANDIDATES[1:]
    assert selection["automatic_successors"] == [] and not selection["allocation_experiment_started"]
