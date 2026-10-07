"""CPU controls for immutable inheritance, exact work accounting and shared admission."""
import copy
import hashlib
import subprocess

import pytest

from proworksim.experience_allocation_v035 import development_receipt
from proworksim.storage import read_json
from scripts import software_allocation_v037 as runner
from scripts.run_ne_v021 import write
from test_software_allocation_v036 import allocation


def test_complete_update_counts_cache_application_separately_from_actual_backwards():
    material = {"admitted_decisions": 682, "admitted_own_output_tokens": 161827}
    report = {"status": "updated", "behavior_probability_passed": True,
        "actor_optimizer_steps": 1, "critic_optimizer_steps": 1,
        "backward_decisions_completed": 21, "cache_actual_backward_decisions": 21, "native_accumulation_exact_checks": 21,
        "cache_hit_decisions": 661, "cache_applied_decisions": 682,
        "admitted_decisions": 682, "admitted_output_tokens": 161827,
        "scheduled_slots": 16, "changed_actor_elements": 8}
    runner.require_actual_update(report, material)
    for mutation in ({"cache_applied_decisions": 681}, {"cache_hit_decisions": 660}, {"native_accumulation_exact_checks": 20},
                     {"backward_decisions_completed": 682}, {"admitted_output_tokens": 161826},
                     {"actor_optimizer_steps": 0}, {"critic_optimizer_steps": 0},
                     {"behavior_probability_passed": False}, {"changed_actor_elements": 0}):
        with pytest.raises(ValueError, match="No complete real"):
            runner.require_actual_update({**report, **mutation}, material)
    runner.require_actual_update({**report, "backward_decisions_completed": 0,
        "cache_actual_backward_decisions": 0, "cache_hit_decisions": 682, "native_accumulation_exact_checks": 0}, material)


def sample(gpus, processes=""):
    return {"gpus": {"returncode": 0, "stdout": gpus},
            "processes": {"returncode": 0, "stdout": processes}}


def test_shared_admission_prefers_empty_and_preserves_exclusions_and_capacity():
    plan = {"gpu_preference": [5, 3, 0], "limits": runner.LIMITS}
    rows = "5, g5, NVIDIA A100-SXM4-80GB, 62000, 81920, 99\n3, g3, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n0, g0, NVIDIA A100-SXM4-80GB, 57000, 81920, 0\n"
    reading = sample(rows, "g5, 999, 18000, other-job\n")
    cards = runner.available_cards(plan, reading)
    assert [c["index"] for c in cards] == [3, 5]
    assert [c["shared"] for c in cards] == [False, True]
    assert [c["index"] for c in runner.available_cards(plan, reading, excluded=[3])] == [5]
    assert runner.available_cards(plan, {**reading, "processes": {"returncode": 1}}) == []
    assert runner.available_cards(plan, sample(rows.replace("62000", "nan"))) == []
    assert runner.available_cards(plan, sample(rows, "malformed\n")) == []
    assert runner.LIMITS["minimum_free_gpu_mib"] == runner.LIMITS["own_gpu_memory_mib"] == 56 * 1024
    assert runner.LIMITS["task_seconds"]["cache_wait"] is None
    assert runner.LIMITS["max_parallel_model_instances"] == 4


def test_device_reserve_stops_only_current_bound_worker_without_targeting_other_pid():
    reading = sample("5, g5, NVIDIA A100-SXM4-80GB, 6143, 81920, 99\n", "g5, 999, 18000, other-job\n")
    assert runner.live_free_stop_reason(reading, 5) == "shared_device_free_memory_reserve"
    assert runner.live_free_stop_reason(reading, 3) is None
    reading["gpus"]["stdout"] = reading["gpus"]["stdout"].replace("6143", "6144")
    assert runner.live_free_stop_reason(reading, 5) is None
    assert runner.live_free_stop_reason({"gpus": {"returncode": 1}}, 5) is None


def test_stage_order_retains_every_frozen_direction_and_unknown_blocks_formal(tmp_path, monkeypatch):
    plan = allocation()
    freeze = {"allocation": plan}
    reviews = []
    monkeypatch.setattr(runner, "shared_B_cost_review", lambda root, value: reviews.append(value))
    stage, names = runner.next_stage("shared_B", {"trial-B": {"status": "complete"}}, tmp_path, freeze)
    assert stage == "full_trials"
    assert names == ["trial-" + key for key in plan["candidates"] if key != "B"]
    assert reviews == [freeze]
    receipts = {"trial-" + key: development_receipt(plan, key, [0] * 16,
        provenance="current_model_development") for key in plan["candidates"]}
    monkeypatch.setattr(runner, "verified_receipt", lambda root, name, allocation: receipts[name])
    states = {name: {"status": "complete"} for name in names}
    receipts[names[-1]]["outcomes"][0]["utility"] = None
    with pytest.raises(ValueError, match="Incomplete or unknown"):
        runner.next_stage(stage, states, tmp_path, freeze)
    assert not (tmp_path / "selection.json").exists()
    receipts[names[-1]]["outcomes"][0]["utility"] = 0
    assert runner.next_stage(stage, states, tmp_path, freeze) == (
        "formal_and_independent_confirmation", ["formal-B", "formal-G-raw", "formal-I-P"])
    assert runner.next_stage(stage, {names[0]: {"status": "stopped"}}, tmp_path, freeze) == ("incomplete_execution", [])


def test_inherited_numerical_bytes_are_checked_against_real_parent_commit(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "src/pkg").mkdir(parents=True)
    (repo / "scripts").mkdir()
    old = {"src/pkg/model.py": b"precision = 'highest'\n", "scripts/run.py": b"state = 'original'\n"}
    for name, data in old.items():
        (repo / name).write_bytes(data)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=Control", "-c", "user.email=control@example.invalid",
                    "commit", "-qm", "original"], cwd=repo, check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    source_hash = hashlib.sha256()
    for name in sorted(old):
        if name.startswith("src/"):
            source_hash.update(name.encode())
            source_hash.update(old[name])
    source = {"code_commit": commit, "code_dirty": False, "source_tree_sha256": source_hash.hexdigest()}
    monkeypatch.setattr(runner, "SOURCE", repo)
    original = runner.inherited_source_manifest(source)
    (repo / "src/pkg/new_cache_v037.py").write_text("cache = True\n")
    assert runner.inherited_source_manifest(source) == original
    (repo / "src/pkg/model.py").write_text("precision = 'high'\n")
    with pytest.raises(ValueError, match="Inherited source bytes changed"):
        runner.inherited_source_manifest(source)


def test_immutable_refs_preserve_original_file_bytes_and_sizes(tmp_path):
    path = tmp_path / "original.json"
    path.write_text('{"original": true}\n')
    ref = {**runner.reference(path), "bytes": path.stat().st_size}
    runner._check_references({"nested": [ref, ref]})
    with pytest.raises(ValueError, match="size changed"):
        runner._check_references({**ref, "bytes": ref["bytes"] + 1})
    path.write_text('{"original": false}\n')
    with pytest.raises(ValueError, match="bytes changed"):
        runner._check_references(ref)


def test_receipt_requires_same_common_and_new_source(tmp_path):
    plan = allocation()
    source = {"code_commit": "v037-control", "code_dirty": False}
    inventory = [{"slot_id": r["unit_id"], "case_id": r["root_id"], "sampling_seed": r["seed"]}
                 for r in plan["development"]["units"]]
    write(tmp_path / "plan.json", {"source": source, "inventories": {"development": inventory}})
    folder = tmp_path / "trial-B/actual"
    rows = [{**r, "status": "closed", "record_validity": True, "training_eligible": False, "R": 0}
            for r in inventory]
    write(folder / "panel-summary.json", {"all_known": True, "rows": rows})
    original = {"status": "complete", "source_before": source, "source_after": source,
        "new_actor_steps": 1, "new_critic_steps": 1, "full_material_consumption_passed": True,
        "common_restored_exactly": True, "panel": runner.reference(folder / "panel-summary.json")}
    receipt = development_receipt(plan, "B", [0] * 16, provenance="current_model_development")
    write(folder / "development-receipt.json", receipt)
    write(folder / "report.json", original)
    assert runner.verified_receipt(tmp_path, "trial-B", plan) == receipt
    for mutation in ({"source_before": {"code_commit": "v036"}}, {"common_restored_exactly": False}):
        write(folder / "report.json", {**original, **mutation})
        with pytest.raises(ValueError, match="same-common"):
            runner.verified_receipt(tmp_path, "trial-B", plan)


def test_new_cost_reports_actual_misses_and_does_not_fill_unknown_effects(tmp_path):
    write(tmp_path / "plan.json", {"source": {"code_commit": "control"},
        "parent_root": "original-v036", "parent_freeze": {}, "inventories": {"confirmation": []}})
    write(tmp_path / "p3-supervisor.json", {"status": "running", "states": {
        "trial-B": {"status": "running"}, "trial-G0": {"status": "running"}}})
    counts = [(682, 0), (20, 662)]
    for name, (misses, hits) in zip(("trial-B", "trial-G0"), counts):
        write(tmp_path / name / "actual/update/report.json", {
            "cache_actual_backward_decisions": misses, "cache_hit_decisions": hits,
            "cache_applied_decisions": misses + hits})
    value = runner.results(tmp_path)
    assert value["cost"]["gradient_work"]["cache_actual_backward_decisions"] == 702
    assert value["cost"]["gradient_work"]["cache_hit_decisions"] == 662
    assert value["cost"]["gradient_work"]["cache_applied_decisions"] == 1364
    assert value["I_minus_B"] is value["I_minus_G_raw"] is None
    assert value["independent_paired_units"] == []
    assert value["support"]["reused_without_sampling"] is True


def test_finish_preserves_execution_error_if_reporting_also_fails(tmp_path, monkeypatch):
    root = tmp_path / "run"
    def fail_execution(root):
        raise RuntimeError("original execution failure")
    def fail_reporting(*args):
        raise ValueError("secondary reporting failure")
    monkeypatch.setattr(runner, "supervise", fail_execution)
    monkeypatch.setattr(runner, "report", fail_reporting)
    with pytest.raises(RuntimeError, match="original execution"):
        runner.finish(root, tmp_path)
    value = read_json(root / "finish.json")
    assert value["error"]["message"] == "original execution failure"
    assert value["reporting_error"]["message"] == "secondary reporting failure"
    assert value["ended_at"] >= value["started_at"]


def test_finish_publishes_only_declared_v037_reports(tmp_path, monkeypatch):
    publication = []
    monkeypatch.setattr(runner, "supervise", lambda root: {"status": "complete"})
    monkeypatch.setattr(runner, "report", lambda *args: {"status": "complete"})
    monkeypatch.setattr(runner.support, "publish_report_paths",
        lambda repo, paths, message: publication.append((repo, copy.deepcopy(paths))) or {"status": "pushed"})
    value = runner.finish(tmp_path / "run", tmp_path)
    assert value["publication"]["status"] == "pushed"
    assert publication == [(tmp_path, runner.REPORT_PATHS)]
    assert all("v037" in path for path in runner.REPORT_PATHS)


def test_imported_B_keeps_original_source_and_is_not_counted_as_new_work(tmp_path):
    old = tmp_path / "old/trial-B/actual"
    root = tmp_path / "new"
    imported = {"folder": str(old), "source": {"code_commit": "old"}, "original_worker_gpu_seconds": 999}
    write(root / "plan.json", {"source": {"code_commit": "new"}, "parent_root": str(tmp_path / "old"),
        "parent_freeze": {}, "imported_B": imported, "inventories": {"confirmation": []}})
    write(root / "p3-supervisor.json", {"status": "running", "states": {
        "trial-B": {"status": "complete", "imported": True, "attempted": False},
        "trial-other": {"status": "running"}}})
    write(old / "report.json", {"new_actor_steps": 1, "new_critic_steps": 1})
    write(old / "update/report.json", {"backward_decisions_completed": 682})
    write(old / "panel-summary.json", {"rows": [{"actual_usage": {
        "decisions": 100, "attempts": 100, "charged_tokens": 1000, "test_runs": 20}}]})
    write(root / "trial-other/actual/report.json", {"new_actor_steps": 1, "new_critic_steps": 1})
    write(root / "trial-other/actual/update/report.json", {"cache_actual_backward_decisions": 20,
        "cache_hit_decisions": 662, "cache_applied_decisions": 682})
    value = runner.results(root)
    assert value["workers"]["trial-B"]["imported"] is True
    assert value["cost"]["new_v037_optimizer_steps"] == {"actor": 1, "critic": 1}
    assert value["cost"]["gradient_work"]["cache_actual_backward_decisions"] == 20
    assert value["cost"]["sampling_usage"]["decisions"] == 0
    assert value["cost"]["closed_P3_worker_gpu_seconds"] == 0
    assert value["cost"]["imported_B"]["original_worker_gpu_seconds"] == 999


def test_import_requires_original_B_exit_archive_and_complete_numerical_gate(tmp_path, monkeypatch):
    old = tmp_path / "old"
    folder = old / "trial-B/actual"
    source = {"code_commit": "original", "code_dirty": False}
    write(old / "plan.json", {"source": source})
    required = ["panel-summary.json", "development-receipt.json", "common-restore.json",
        "update/gradients-before-clip.pt", "update/software-consumption.json",
        "updated-state/checkpoint.json", "cold-archive-receipt.json"]
    for name in required:
        write(folder / name, {})
    write(folder / "update/report.json", {"backward_decisions_completed": 682})
    write(folder / "report.json", {"update": runner.reference(folder / "update/report.json")})
    write(old / "material.json", {"admitted_decisions": 682})
    state = {"status": "complete", "exit_code": 0, "stop_reason": None, "ended_at": 100,
        "elapsed_gpu_seconds": 90, "archive": {"receipt": runner.reference(folder / "cold-archive-receipt.json")}}
    write(old / "p3-supervisor.json", {"states": {"trial-B": state}})
    freeze = {"allocation": {}, "training_material_binding": runner.reference(old / "material.json")}
    controls = []
    monkeypatch.setattr(runner.original_allocation, "verified_receipt", lambda *args: {"valid": True})
    monkeypatch.setattr(runner.original_allocation, "require_actual_update", lambda *args: controls.append(args))
    imported = runner.import_shared_B(old, folder, freeze)
    assert len(controls) == 1
    assert imported["original_actual_backward_decisions"] == 682
    assert imported["new_backward_decisions"] == 0
    assert imported["source"] == source
    for mutation in ({"exit_code": 1}, {"status": "archiving"}, {"archive": None}, {"stop_reason": "error"}):
        write(old / "p3-supervisor.json", {"states": {"trial-B": {**state, **mutation}}})
        with pytest.raises(ValueError, match="exited and losslessly archived"):
            runner.import_shared_B(old, folder, freeze)


def test_handoff_signal_rejects_pid_reuse_before_any_signal(monkeypatch):
    identity = {"pid": 101, "start_ticks": 555}
    process = {"identity": identity, "command": ["original"], "cwd": "/frozen"}
    changed = {**process, "identity": {**identity, "start_ticks": 556}}
    signals, closed = [], []
    monkeypatch.setattr(runner.os, "pidfd_open", lambda pid: 77, raising=False)
    monkeypatch.setattr(runner.os, "close", closed.append)
    monkeypatch.setattr(runner.signal, "pidfd_send_signal", lambda *args: signals.append(args), raising=False)
    monkeypatch.setattr(runner, "process_binding", lambda pid: changed)
    with pytest.raises(ValueError, match="identity changed"):
        runner.stop_verified_parent_observer({"observer": process})
    assert signals == [] and closed == [77]
    monkeypatch.setattr(runner, "process_binding", lambda pid: process)
    runner.stop_verified_parent_observer({"observer": process})
    assert signals == [(77, runner.signal.SIGTERM)]


def _handoff_fixture(tmp_path, monkeypatch, *, parent_stops=False):
    old, new, repo = tmp_path / "old", tmp_path / "new", tmp_path / "repo"
    source = {"code_commit": "new", "code_dirty": False, "source_tree_sha256": "abc"}
    parent = {"source": {"code_commit": "old"}}
    for name in runner.OPTIMIZATION_SOURCES:
        write(repo / name, {"source": name})
    write(old / "plan.json", parent)
    write(old / "postcollection-freeze.json", {})
    _qualified_control(new.parent / "v037-controls/qualification.json", repo)
    summary = {"stage": "shared_B", "status": "running", "states": {"trial-B": {"status": "running"}}}
    write(old / "p3-supervisor.json", summary)
    processes = {name: {"identity": {"pid": pid, "start_ticks": pid * 10}} for name, pid in (("observer", 101), ("finisher", 102))}
    monkeypatch.setattr(runner, "SOURCE", repo)
    monkeypatch.setattr(runner, "code_identity", lambda: source)
    monkeypatch.setattr(runner, "verify_parent", lambda root: (parent, {}))
    monkeypatch.setattr(runner, "inherited_source_manifest", lambda source: {})
    monkeypatch.setattr(runner, "parent_observer_binding", lambda *args: processes)
    monkeypatch.setattr(runner, "import_shared_B", lambda *args: {"folder": str(old / "trial-B/actual")})
    actions = []
    def advance(_):
        assert not actions
        summary["states"]["trial-B"]["status"] = "stopped" if parent_stops else "complete"
        write(old / "p3-supervisor.json", summary)
    monkeypatch.setattr(runner.time, "sleep", advance)
    monkeypatch.setattr(runner, "_bound_process_alive", lambda process: not actions)
    def stop(processes):
        control = new.parent / (new.name + "-handoff")
        assert (control / "request.json").exists()
        assert read_json(old / "p3-supervisor.json")["states"]["trial-B"]["status"] == "complete"
        actions.append("signal")
        write(old.parent / (old.name + "-finish.json"), {"status": "reported_P3_terminal", "ended_at": 123})
    monkeypatch.setattr(runner, "stop_verified_parent_observer", stop)
    def prepare(parent_root, root, *, imported_B, qualification):
        assert actions == ["signal"]
        assert imported_B == old / "trial-B/actual"
        root.mkdir()
        actions.append("prepare")
    monkeypatch.setattr(runner, "prepare", prepare)
    monkeypatch.setattr(runner, "finish", lambda *args: actions.append("finish") or {"status": "complete"})
    return old, new, repo, actions


def test_handoff_durably_waits_for_B_before_signal_prepare_and_finish(tmp_path, monkeypatch):
    old, new, repo, actions = _handoff_fixture(tmp_path, monkeypatch)
    value = runner.handoff(old, new, repo)
    assert actions == ["signal", "prepare", "finish"]
    assert value["status"] == "complete" and value["parent_signal_sent"] is True
    request = read_json(new.parent / (new.name + "-handoff/request.json"))
    assert request["initial_parent_snapshot"]["states"]["trial-B"]["status"] == "running"
    assert request["signal_before_B_complete"] is False
    assert read_json(new / "handoff.json")["original_B_preserved"] is True


def test_handoff_stops_without_signal_or_new_run_if_parent_B_fails(tmp_path, monkeypatch):
    old, new, repo, actions = _handoff_fixture(tmp_path, monkeypatch, parent_stops=True)
    value = runner.handoff(old, new, repo)
    assert actions == [] and not new.exists()
    assert value["status"] == "parent_stopped_before_complete_B"
    assert value["parent_signal_sent"] is False


def _qualified_control(path, source):
    receipt = path.parent / "exploratory-cuda.json"
    write(receipt, {"passed": False, "declared_production_passed": True,
                    "nonproduction_fp32_negative_control_passed": False})
    value = {"version": "gradient-cache-qualification-v0.37", "passed_for_declared_production": True,
        "declared_profile": "original-v0201-mixed-bf16-efficient-only",
        "required_checks": dict.fromkeys(runner.OPTIMIZATION_CHECKS, True),
        "source_files": {name: runner.digest((source / name).read_bytes()) for name in runner.OPTIMIZATION_SOURCES},
        "evidence": {"cuda_original": runner.reference(receipt)}}
    write(path, value)
    return value


def test_optimization_qualification_binds_declared_profile_sources_and_original_receipts(tmp_path, monkeypatch):
    source = tmp_path / "source"
    for name in runner.OPTIMIZATION_SOURCES:
        write(source / name, {"module": name})
    monkeypatch.setattr(runner, "SOURCE", source)
    path = tmp_path / "controls/qualification.json"
    original = _qualified_control(path, source)
    # An exploratory all-FP32 negative result is preserved, not promoted or hidden.
    assert runner.validate_optimization_controls(path) == original
    assert read_json(path.parent / "exploratory-cuda.json")["passed"] is False
    for name in runner.OPTIMIZATION_CHECKS:
        failed = copy.deepcopy(original)
        failed["required_checks"][name] = False
        write(path, failed)
        with pytest.raises(ValueError, match="declared-production"):
            runner.validate_optimization_controls(path)
    for mutation in ({"passed_for_declared_production": False}, {"declared_profile": "fp32-exploration"},
                     {"source_files": {}}, {"evidence": {"not_a_receipt": "text"}}):
        write(path, {**original, **mutation})
        with pytest.raises(ValueError):
            runner.validate_optimization_controls(path)
    write(path, original)
    changed = source / runner.OPTIMIZATION_SOURCES[0]
    changed.write_text("changed implementation\n")
    with pytest.raises(ValueError, match="source bytes changed"):
        runner.validate_optimization_controls(path)


def test_optimization_receipt_tamper_and_absolute_source_paths_are_rejected(tmp_path, monkeypatch):
    source = tmp_path / "source"
    for name in runner.OPTIMIZATION_SOURCES:
        write(source / name, {"module": name})
    monkeypatch.setattr(runner, "SOURCE", source)
    path = tmp_path / "controls/qualification.json"
    original = _qualified_control(path, source)
    bad = copy.deepcopy(original)
    bad["source_files"][str(source / runner.OPTIMIZATION_SOURCES[0])] = "0" * 64
    write(path, bad)
    with pytest.raises(ValueError, match="relative Python paths"):
        runner.validate_optimization_controls(path)
    write(path, original)
    write(path.parent / "exploratory-cuda.json", {"passed": True})
    with pytest.raises(ValueError, match="artifact bytes changed"):
        runner.validate_optimization_controls(path)


def test_handoff_rechecks_qualification_before_stopping_parent(tmp_path, monkeypatch):
    old, new, repo, actions = _handoff_fixture(tmp_path, monkeypatch)
    advance = runner.time.sleep
    def changed_qualification(seconds):
        advance(seconds)
        path = new.parent / "v037-controls/qualification.json"
        value = read_json(path)
        value["passed_for_declared_production"] = False
        write(path, value)
    monkeypatch.setattr(runner.time, "sleep", changed_qualification)
    with pytest.raises(ValueError):
        runner.handoff(old, new, repo)
    assert actions == [] and not new.exists()
    state = read_json(new.parent / (new.name + "-handoff/status.json"))
    assert state["parent_signal_sent"] is False


def test_handoff_rechecks_exact_execution_source_before_stopping_parent(tmp_path, monkeypatch):
    old, new, repo, actions = _handoff_fixture(tmp_path, monkeypatch)
    advance = runner.time.sleep
    original = copy.deepcopy(runner.code_identity())
    def changed_source(seconds):
        advance(seconds)
        monkeypatch.setattr(runner, "code_identity", lambda: {**original, "code_commit": "changed"})
    monkeypatch.setattr(runner.time, "sleep", changed_source)
    with pytest.raises(ValueError, match="do not stop the original supervisor"):
        runner.handoff(old, new, repo)
    assert actions == [] and not new.exists()
