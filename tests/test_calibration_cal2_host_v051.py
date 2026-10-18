"""New host-only CPU controls. No model, shell, repository pytest or tokenizer."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.storage import digest, json_bytes, read_json
from scripts import software_calibration_v051_cal2 as host


def static_rows():
    return host.inventory(read_json(host.INVENTORY))


def closed_values(condition="P"):
    row = next(row for row in static_rows() if row["condition"] == condition)
    values = {"result": {"R_code": 0, "R_joint": None if condition == "R" else 0},
        "accounting": {"all_started_settled": True, "integrity_errors": [], "known_actual_tokens": 100},
        "guard": {"passed": True},
        "episode_guard": {"learning_unchanged": True, "rng_restored_exactly": True},
        "measurement": {"decision": "continue", "safe_local_context_rejection": True}}
    return row, values


def test_original_inventory_retains_all18_and_order():
    original = read_json(host.INVENTORY)
    rows = host.inventory(original)
    assert len(rows) == 18 and {row["partition"] for row in rows} == {"CAL2"}
    assert sum(row["generation_tokens"] for row in rows) == 9000000
    altered = copy.deepcopy(original)
    altered["rows"][0]["seed"] += 1
    with pytest.raises(ValueError):
        host.inventory(altered)


def test_real_relative_evidence_normalization_without_mutating_old_receipt(tmp_path):
    source = read_json(host.SOURCE_QUALIFIED)
    before = copy.deepcopy(source)
    release = read_json(host.RELEASE)
    control = tmp_path / "fake-control.json"
    host.write(control, {"passed": True, "fixture_only": True})
    references = host._evidence_refs(release, source, {"control_references": [host.ref(control)]})
    assert references and all(Path(item["path"]).is_absolute() for item in references)
    assert source == before
    state = read_json(host.INVENTORY)["states"]["S_star"]
    assert Path(state["state_file_reference_from_original_metadata"]["path"]).is_absolute()


def test_independent_compound_release_required_without_score_threshold():
    release = read_json(host.RELEASE)
    source = read_json(host.SOURCE_QUALIFIED)
    references = {"release_ref": host.ref(host.RELEASE), "source_ref": host.ref(host.SOURCE_QUALIFIED),
                  "policy_ref": host.ref(host.RESOURCE_POLICY)}
    admission = {"version": "v051-cal2-compound-admission-v1", "stage": "CAL2", "released": True,
        "unresolved_blockers": [], "cal1_release": references["release_ref"],
        "source_qualified": references["source_ref"], "resource_policy": references["policy_ref"],
        "checks": dict.fromkeys(host.COMPOUND_CHECKS, True), "control_references": [references["source_ref"]]}
    assert host.gate_records(release, source, admission, **references)
    admission["released"] = False
    with pytest.raises(ValueError):
        host.gate_records(release, source, admission, **references)
    admission["released"] = True
    for record, key in ((release, "original48_uniquely_accounted_for"),
                        (source, "new_initial_inputs_bound"), (admission, "host_controls")):
        saved = record["checks"].pop(key)
        with pytest.raises(ValueError):
            host.gate_records(release, source, admission, **references)
        record["checks"][key] = saved
    bad = copy.deepcopy(release)
    bad["resources"]["allowed_gpu_indices"] = [0, 1, 3, 4, 6, 7]
    with pytest.raises(ValueError):
        host.gate_records(bad, source, admission, **references)
    assert release["legacy_limitations"]["formal_full_mean_and_difference"] is None


@pytest.mark.parametrize("condition", ["R", "P", "U"])
def test_known_code_failure_and_local_stop_continue_but_unknown_never_does(condition):
    row, values = closed_values(condition)
    assert host.classify_closed(row, **values)["decision"] == "continue"
    values["result"]["R_code"] = 1
    assert host.classify_closed(row, **values)["decision"] == "continue"
    values["result"]["R_code"] = None
    assert host.classify_closed(row, **values)["reasons"] == ["terminal_code_unknown"]
    values["result"]["R_code"] = 0
    values["episode_guard"]["rng_restored_exactly"] = False
    assert host.classify_closed(row, **values)["decision"] == "global_pause"


def test_only_zero_model_startup_failure_can_requeue():
    row = static_rows()[0]
    plan_ref = {"path": "/fixture/plan", "sha256": "fixture", "bytes": 1}
    report = {"status": "pre_model_resource_unavailable", "model_loader_entered": False,
        "generation_calls": 0, "slot_id": row["slot_id"], "source_plan": plan_ref}
    attempt = {"exit_code": 75, "reason": None}
    arguments = {"plan_ref": plan_ref, "slot_started": False, "cleanup_passed": True}
    assert host.worker_completion(row, attempt, report, **arguments) == "not_started"
    arguments["slot_started"] = True
    assert host.worker_completion(row, attempt, report, **arguments) == "stopped"
    arguments.update(slot_started=False, cleanup_passed=False)
    assert host.worker_completion(row, attempt, report, **arguments) == "stopped"


def test_actual_receipts_and_uncertain_reservation_counted_once(tmp_path):
    calls = tmp_path / "calls"
    calls.mkdir()
    identity = {"test_actor": True}
    native = {"input_ids": [1, 2, 3]}
    for name in ("one", "two"):
        prepared = {"attempt_id": name, "native_input": native, "actor_identity": identity,
            "reserved_maximum_tokens": 2051, "generation_started": False}
        host.write(calls / (name + "-prepared.json"), prepared)
        host.write(calls / (name + "-started.json"), {**prepared, "generation_started": True})
    result = {"attempt_id": "one", "input": native, "actor_identity": identity, "output_ids": [4],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}
    host.write(calls / "one-complete.json", result)
    receipt = host.native_accounting(tmp_path)
    assert receipt["known_actual_tokens"] == 4
    assert receipt["uncertain_reservation_tokens"] == 2051
    assert receipt["complete_actual_tokens"] is None
    result["usage"]["total_tokens"] = 5
    host.write(calls / "one-complete.json", result)
    assert host.native_accounting(tmp_path)["integrity_errors"]


def test_episode_deadline_cannot_reset_at_request_boundaries():
    current = {"kind": "generation", "started_at": 5950, "episode_started_at": 0, "episode_closed_at": None}
    assert host.deadline_reason(current, 6001) == "episode_hard_deadline"
    current.update(kind="measurement", episode_closed_at=5990)
    assert host.deadline_reason(current, 6001) is None
    assert host.deadline_reason(current, 6550) == "task_deadline"


def test_native_local_refusal_requires_exact_source_and_remaining_budget(tmp_path):
    from proworksim.software_calibration_runtime_v051 import VERSION

    row = static_rows()[0]
    identity = {"fixture_actor": True}
    ids = [1] * 16385
    native = host.sealed({"version": VERSION, "contract_sha256": digest(json_bytes(host.CONTRACT)),
        "input_ids": ids, "input_ids_sha256": digest(json_bytes(ids)), "prompt_tokens": len(ids),
        "rendered_prompt": "programmed CPU fixture", "rendered_prompt_sha256": digest(b"programmed CPU fixture"),
        "context_limit": 18432, "requested_output_tokens": 2048, "fits": False})
    binding = {"task_id": row["task_id"], "condition": "R", "seed": row["seed"], "initial_files_sha256": "fixture"}
    rejection = {"native_input": native, "P": len(ids), "O": 2048, "C": 18432, "fits": False,
        "reason": "full_native_context_preexecution_rejection", "generation_started": False,
        "new_side_effect": False, "actor_identity": identity, "episode_binding": binding,
        "actual_tokens": 0, "remaining_tokens": 500000, "decisions": 1, "attempts": 0}
    path = tmp_path / "rejection.json"
    host.write(path, rejection)
    ledger = {"inflight": None, "reserved_unknown_tokens": 0, "attempts": 0,
        "complete_responses": 0, "known_actual_tokens": 0, "decisions": 1, "calls": [],
        "episode_binding": binding, "stop_reason": rejection["reason"],
        "preexecution_rejections": [host.ref(path)]}
    result = {"status": "bounded_native_episode_closed", "task_id": row["task_id"],
        "seed": row["seed"], "initial_files_sha256": "fixture", "actions": 0, "ledger": ledger}
    accounting = {"started_generations": 0, "complete_generations": 0, "known_actual_tokens": 0, "actual_calls": []}
    assert host.measure_native(result, row=row, owner_identity=identity, accounting=accounting)["decision"] == "continue"
    rejection["remaining_tokens"] -= 1
    host.write(path, rejection)
    ledger["preexecution_rejections"] = [host.ref(path)]
    assert host.measure_native(result, row=row, owner_identity=identity, accounting=accounting)["decision"] == "global_pause"


@pytest.mark.parametrize("condition", ["R", "P", "U"])
def test_worker_real_orchestration_with_programmed_components(monkeypatch, tmp_path, condition):
    from proworksim import repository_sources_v051 as sources
    from proworksim import software_calibration_runtime_v051 as runtime
    from proworksim import software_calibration_v051_mini as mini
    from proworksim import software_calibration_collector_v051 as collector
    from proworksim import software_calibration_world_v051 as world
    from proworksim import software_calibration_measurement_v051 as measurement
    from proworksim import software_calibration_native_grade_v051 as native_grade

    row = next(row for row in static_rows() if row["condition"] == condition)
    root, attempt = tmp_path / "run", tmp_path / "run/workers/attempt-001"
    root.mkdir()
    host.write(root / "plan.json", {"fixture": True})
    plan = {"rows": [row], "native_python": __import__("sys").executable,
        "gpu_preference": list(range(8)), "model_path": "not_loaded",
        "model_manifest": {"path": "not_read"}, "S_star": {"checkpoint": {"path": "S_star4/4"}},
        "repository_source_root": "not_read", "adapter_manifest": {"sha256": "fixture"},
        "mini_manifest": {"path": "not_read"}}
    monkeypatch.setattr(host, "frozen", lambda _: plan)
    startup = SimpleNamespace(acquire_startup_cache=lambda *a, **k: {}, StartupResourceUnavailable=RuntimeError)
    resource = SimpleNamespace(binding_from_env=lambda: {"gpu_index": 2})
    monkeypatch.setattr(host, "resource_modules", lambda _: (resource, startup))
    files = {"parse.py": "pass\n", "tests/test.py": "pass\n"}
    source_sha = digest(json_bytes(files))
    load_calls = []

    def load(*args, **kwargs):
        load_calls.append(kwargs)
        (kwargs["output"] / "calls").mkdir(parents=True)
        return SimpleNamespace(generate_native=lambda _: pytest.fail("No actual generation allowed"),
            freeze_identity=lambda: {"fixture_actor": True}, verify_evaluation_guard=lambda: {"passed": True})

    monkeypatch.setattr(runtime, "load_actor", load)
    provider = SimpleNamespace(build_case=lambda _: {"files": files, "root_goal": "fixture issue"},
        runner_spec=lambda _: {"task_id": row["task_id"], "module": "parse"})
    monkeypatch.setattr(sources, "RepositorySources", lambda *a, **k: provider)

    def episode_guard(folder):
        folder.mkdir(parents=True, exist_ok=True)
        host.write(folder / "evaluation-guard.json", {"learning_unchanged": True, "rng_restored_exactly": True})

    def native_run(owner, **kwargs):
        folder = kwargs["output"]
        episode_guard(folder)
        host.write(folder / "candidate-files.json", files)
        return {"status": "bounded_native_episode_closed", "task_id": row["task_id"], "seed": row["seed"],
            "candidate_files": str(folder / "candidate-files.json"), "initial_files_sha256": source_sha,
            "actions": 0, "ledger": {"inflight": None, "reserved_unknown_tokens": 0,
                "attempts": 0, "complete_responses": 0, "known_actual_tokens": 0, "decisions": 0,
                "episode_binding": {"task_id": row["task_id"], "condition": "R", "seed": row["seed"],
                    "initial_files_sha256": source_sha}, "preexecution_rejections": []}}

    monkeypatch.setattr(mini, "prepare_buggy_worktree", lambda *a, **k: {"fixture": True})
    monkeypatch.setattr(mini, "run_native_case", native_run)
    monkeypatch.setattr(native_grade, "grade_native_candidate", lambda **kwargs: {"R_code": 0, "Q_task": 0.})

    def prepare(case_id, destination, **kwargs):
        assert destination.is_relative_to(attempt)
        assert kwargs["provider"] is provider
        return SimpleNamespace(fixture=True)

    def collect(owner, prepared, folder, **kwargs):
        episode_guard(folder)
        assert kwargs["calibration_condition"] == condition
        return {"R_code": 0, "R_joint": 0, "usage": {"total_tokens": 0}}

    monkeypatch.setattr(world, "build_software_collaboration_case", prepare)
    monkeypatch.setattr(collector, "collect_episode", collect)
    monkeypatch.setattr(measurement, "measure_slot", lambda *a, **k: {"decision": "continue"})
    assert host.worker(root, row["slot_id"], attempt) == 0
    assert len(load_calls) == 1 and load_calls[0]["path"] == "project"
    assert load_calls[0]["checkpoint"] == ("S_star4/4" if condition == "U" else None)
    report = read_json(attempt / "report.json")
    assert report["verdict"]["decision"] == "continue" and report["result"]["R_code"] == 0
    assert report["accounting"]["started_generations"] == 0


@pytest.mark.parametrize("mode", ["complete", "unknown_code", "host_stop"])
def test_scheduler_fresh_residents_limit_pause_and_child_cleanup(monkeypatch, tmp_path, mode):
    from proworksim import software_calibration_process_v051 as cleanup

    rows = static_rows()[:6]
    root = tmp_path / mode
    root.mkdir()
    host.write(root / "plan.json", {"fixture": True})
    plan = {"rows": rows, "gpu_preference": list(range(8)), "native_python": "never_executed",
        "source_root": str(root), "runtime_dependency_path": str(root)}
    monkeypatch.setattr(host, "frozen", lambda _: plan)
    cards = [{"index": index, "uuid": "GPU-" + str(index)} for index in (2, 5, 0, 7)]
    resource = SimpleNamespace(available_cards=lambda plan, sample, excluded: [c for c in cards if c["index"] not in excluded],
        launch_target=lambda card: card, worker_env=lambda env, binding: env)
    monkeypatch.setattr(host, "resource_modules", lambda _: (resource, None))
    monkeypatch.setattr(host, "target_resources", lambda *a, **k: {"fixture": True})
    monkeypatch.setattr(host, "artifact_bytes", lambda _: 0)
    monkeypatch.setattr(host, "rss", lambda _: 0)
    monkeypatch.setattr(host.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**15))
    monkeypatch.setattr(host.signal, "signal", lambda *a: None)
    monkeypatch.setattr(host.time, "sleep", lambda _: None)
    monkeypatch.setattr(host, "worker_identity", lambda pid: {"pid": pid, "start_ticks": pid + 1})
    monkeypatch.setattr(host, "TelemetryGuard", lambda *a, **k: SimpleNamespace(
        observe=lambda *a, **k: {"stop_reason": "fixture_integrity_stop" if mode == "host_stop" else None}))
    processes, cleanups, commands = {}, [], []

    def clean(output, pid, ticks, *, reason):
        cleanups.append((pid, ticks, reason))
        return {"passed": True, "fixture_only": True}

    monkeypatch.setattr(cleanup, "cleanup_registered_children", clean)

    class Process:
        def __init__(self, command, **kwargs):
            self.pid = 10000 + len(processes)
            self.returncode = None
            processes[self.pid] = self
            commands.append(command)
            output = Path(command[command.index("--attempt") + 1])
            output.mkdir(parents=True)
            slot_id = command[command.index("--slot") + 1]
            row = next(r for r in rows if r["slot_id"] == slot_id)
            _, values = closed_values(row["condition"])
            if mode == "unknown_code" and len(processes) == 1:
                values["result"]["R_code"] = None
            verdict = host.classify_closed(row, **values)
            host.write(output / "report.json", {"status": "closed", "row": row,
                "source_plan": host.ref(root / "plan.json"), "verdict": verdict, **values})

        def poll(self):
            if mode != "host_stop":
                self.returncode = 0
            return self.returncode

        def wait(self, timeout):
            assert self.returncode is not None
            return self.returncode

    monkeypatch.setattr(host.subprocess, "Popen", Process)
    monkeypatch.setattr(host.os, "killpg", lambda pid, signum: setattr(processes[pid], "returncode", -int(signum)))
    result = host.supervise(root)
    assert len(commands) == (6 if mode == "complete" else 4)
    assert [cmd[cmd.index("--slot") + 1] for cmd in commands] == [r["slot_id"] for r in rows[:len(commands)]]
    assert result["status"] == ("complete" if mode == "complete" else "paused")
    assert all(pid + 1 == ticks for pid, ticks, reason in cleanups)
    if mode == "host_stop":
        for pid in processes:
            reasons = [reason for target, _, reason in cleanups if target == pid]
            assert len(reasons) == 2 and reasons[0].startswith("before_") and reasons[1].startswith("after_")
    else:
        assert len(cleanups) == len(commands)
