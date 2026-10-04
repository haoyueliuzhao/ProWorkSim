"""CPU-only terminal proof controls; no worker or GPU is started."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.storage import digest, json_bytes, read_json
from scripts import continue_model_selection_v031 as driver
from scripts import software_model_selection_v031 as selection
from scripts.run_ne_v021 import reference, write


@pytest.fixture
def proof_case(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    fingerprints = {}
    for name in selection.NUMERIC_PROOF_FILES:
        path = source_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# explicit CPU fixture for frozen file binding\n")
        fingerprints[name] = digest(path.read_bytes())
    monkeypatch.setattr(selection, "SOURCE", source_root)
    trace = tmp_path / "original-trace.json"
    write(trace, {"explicit_cpu_fixture": True, "complete_original_tokens": [1, 2, 3]})
    candidate = selection.EXECUTED[0]
    profile = {"candidate_id": candidate, "version": "cpu-terminal-proof-fixture"}
    binding = {
        "candidate_id": candidate,
        "profile_sha256": digest(json_bytes(profile)),
        "source": {"code_commit": "frozen-cpu-fixture", "cpu_fixture": True},
        "tested_files_sha256": fingerprints,
        "original_trace_refs": [reference(trace)],
    }
    state = {
        "exit_code": 0,
        "stop_reason": None,
        "started_at": 100.0,
        "ended_at": 108.0,
        "actual_worker_gpu_seconds": 8.0,
    }
    worker = {
        **copy.deepcopy(binding),
        "passed": True,
        "status": "passed",
        "started_at": 102.0,
        "ended_at": 105.0,
        "actual_worker_gpu_seconds": 3.0,
        "new_model_calls": 0,
        "optimizer_steps": 0,
        "source_unchanged": True,
        "original_trace_files_unchanged": True,
        "all_full_tokens_retained": True,
        "all_behavior_and_gradient_probability_passed": True,
        "full_backward_completed": True,
        "original_actor_identity_matched": True,
        "common_restored_exactly": True,
    }
    probe_root = tmp_path / "probes"
    worker_path = probe_root / candidate / "actual/report.json"
    worker_path.parent.mkdir(parents=True)
    return {"root": probe_root, "binding": binding, "state": state,
            "worker": worker, "path": worker_path, "profile": profile}


def validate_terminal(case, report):
    path = case["path"].parent.parent / "admission-proof.json"
    write(path, report)
    return selection.validate_numeric_proof(path, case["binding"]["candidate_id"], case["profile"])


def test_terminal_proof_binds_normal_success_and_keeps_worker_cost_separate(proof_case):
    case = proof_case
    write(case["path"], case["worker"])
    original_bytes = case["path"].read_bytes()
    inputs = copy.deepcopy((case["binding"], case["state"]))

    report = driver.terminal_proof(case["binding"], case["state"], case["path"])

    assert report["passed"] is True and report["status"] == "passed"
    assert report["actual_worker_gpu_seconds"] == 8.0
    assert report["worker_body_seconds"] == 3.0
    assert report["worker_report"] == reference(case["path"])
    assert report["artifact_directory"] == str(case["path"].parent.parent)
    assert report["probe_ledger_directory"] == str(case["root"])
    assert report["new_model_calls"] == report["optimizer_steps"] == 0
    assert validate_terminal(case, report)["passed"] is True
    assert case["path"].read_bytes() == original_bytes
    assert (case["binding"], case["state"]) == inputs


@pytest.mark.parametrize("change", [
    {"exit_code": 1},
    {"exit_code": -15},
    {"stop_reason": "single_task_budget"},
])
def test_abnormal_controller_end_cannot_promote_a_passing_worker(proof_case, change):
    case = proof_case
    write(case["path"], case["worker"])
    before = reference(case["path"])
    case["state"].update(change)

    report = driver.terminal_proof(case["binding"], case["state"], case["path"])

    assert report["passed"] is False and report["status"] == "failed"
    assert report["controller_reason"]
    assert report["worker_report"] == before == reference(case["path"])
    assert read_json(case["path"])["passed"] is True
    assert report["actual_worker_gpu_seconds"] == 8.0
    assert report["worker_body_seconds"] == 3.0
    assert validate_terminal(case, report)["passed"] is False


@pytest.mark.parametrize("field,value", [
    ("passed", False),
    ("status", "replaying"),
    ("candidate_id", "another-candidate"),
    ("profile_sha256", "another-profile"),
    ("source", {"code_commit": "another-source"}),
    ("tested_files_sha256", {}),
    ("original_trace_refs", []),
    ("source_unchanged", False),
    ("original_trace_files_unchanged", False),
    ("all_full_tokens_retained", False),
    ("all_behavior_and_gradient_probability_passed", False),
    ("full_backward_completed", False),
    ("original_actor_identity_matched", False),
    ("common_restored_exactly", False),
])
def test_worker_success_requires_each_bound_identity_and_numerical_gate(proof_case, field, value):
    case = proof_case
    case["worker"][field] = value
    write(case["path"], case["worker"])
    before = reference(case["path"])

    report = driver.terminal_proof(case["binding"], case["state"], case["path"])

    assert report["passed"] is False and report["status"] == "failed"
    assert report["controller_reason"]
    assert report["worker_report"] == before == reference(case["path"])
    for key, expected in case["binding"].items():
        assert report[key] == expected
    assert validate_terminal(case, report)["passed"] is False


@pytest.mark.parametrize("contents", [None, "{unfinished-json", "[]", "null"])
def test_unavailable_worker_report_closes_false_with_frozen_contract_evidence(proof_case, contents):
    case = proof_case
    if contents is not None:
        case["path"].write_text(contents)
    before = reference(case["path"]) if contents is not None else None
    case["state"].update(exit_code=-9, stop_reason="host_memory_budget")

    report = driver.terminal_proof(case["binding"], case["state"], case["path"])

    assert report["passed"] is False and report["status"] == "failed"
    assert report["controller_reason"]
    assert report["worker_report"] == before
    assert report["worker_body_seconds"] is None
    assert report["counter_evidence"] == "frozen_probe_contract"
    assert report["new_model_calls"] == report["optimizer_steps"] == 0
    assert report["actual_worker_gpu_seconds"] == 8.0
    assert validate_terminal(case, report)["passed"] is False
    if contents is None:
        assert not case["path"].exists()
    else:
        assert case["path"].read_text() == contents


@pytest.mark.parametrize("field", ["new_model_calls", "optimizer_steps"])
def test_explicit_nonzero_counter_is_preserved_and_rejected(proof_case, field):
    case = proof_case
    case["worker"][field] = 1
    write(case["path"], case["worker"])
    before = reference(case["path"])

    report = driver.terminal_proof(case["binding"], case["state"], case["path"])

    assert report["passed"] is False and report["status"] == "failed"
    assert report[field] == 1 and report["counter_evidence"] == "worker_report"
    assert report["worker_report"] == before == reference(case["path"])
    with pytest.raises(ValueError, match="bound GPU"):
        validate_terminal(case, report)


def gpu_sample(*, utilization, pids=(), index=5):
    return {
        "gpus": {"returncode": 0, "stdout":
                 f"{index}, GPU-fixture, NVIDIA A100-SXM4-80GB, 81151, 81920, {utilization}\n"},
        "processes": {"returncode": 0, "stdout": "".join(
            f"GPU-fixture, {pid}, 100, fixture\n" for pid in pids)},
    }


@pytest.mark.parametrize("gpu", [4, 6])
def test_reservation_ready_binds_declared_gpu_and_live_process_identity(tmp_path, monkeypatch, gpu):
    directory = tmp_path / "reservation"
    launch = {"pid": 120, "start_ticks": 456, "physical_gpu": gpu,
              "gpu_uuid": f"GPU-fixture-{gpu}", "user_authorization": "Explicit CPU test fixture"}
    state = {**launch, "status": "reserved", "model_calls": 0,
             "ready_at": 100.0, "heartbeat_at": 164.0}
    write(directory / "launch.json", launch)
    write(directory / "state.json", state)
    observations = [{"observed_at": float(now), "uuid": launch["gpu_uuid"], "pids": [120]}
                    for now in range(100, 165, 2)]
    (directory / "observations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in observations))
    identity = {"alive": True, "start_ticks": 456}
    monkeypatch.setattr(driver.time, "time", lambda: 164.0)
    monkeypatch.setattr(driver, "worker_identity", lambda pid: identity)

    proof = driver.reservation_ready(directory)

    assert proof["continuous_exclusive_seconds"] == 64.0
    assert proof["launch"]["physical_gpu"] == gpu
    assert proof["launch_reference"] == reference(directory / "launch.json")
    identity["start_ticks"] = 789
    assert driver.reservation_ready(directory) is None
    identity["start_ticks"] = 456
    state["physical_gpu"] = 6 if gpu == 4 else 4
    write(directory / "state.json", state)
    with pytest.raises(ValueError, match="same authorized physical GPU"):
        driver.reservation_ready(directory)


@pytest.mark.parametrize("gpu", [4, 6])
def test_release_reobserves_transient_utilization_without_second_stability_wait(monkeypatch, gpu):
    samples = iter([gpu_sample(utilization=100, index=gpu), gpu_sample(utilization=0, index=gpu)])
    deadlines, sleeps = [], []
    monkeypatch.setattr(driver.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(driver.time, "sleep", sleeps.append)

    def sample(deadline):
        deadlines.append(deadline)
        return next(samples)

    monkeypatch.setattr(driver, "_bounded_resources", sample)
    plan = {"limits": selection.LIMITS, "gpu_preference": selection.GPU_ORDER}

    card, receipt = driver.released_capacity(plan, {"gpu_uuid": "GPU-fixture", "physical_gpu": gpu})

    assert card["index"] == gpu and card["uuid"] == "GPU-fixture"
    assert len(receipt["observations"]) == 2 and deadlines == [15.0, 15.0]
    assert receipt["reason"] is None
    assert receipt["immediate_capacity_available"] is True
    assert receipt["second_empty_card_stability_wait_required"] is False
    assert sleeps == [0.1]


@pytest.mark.parametrize("gpu", [4, 6])
def test_release_returns_to_queue_immediately_when_competitor_appears(monkeypatch, gpu):
    observations = []
    monkeypatch.setattr(driver.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(driver.time, "sleep", lambda _: pytest.fail("Do not wait through competition"))
    monkeypatch.setattr(driver, "_release_reservation_pid",
                        lambda *_: pytest.fail("Never signal a competing process"))

    def sample(deadline):
        observations.append(deadline)
        assert len(observations) == 1
        return gpu_sample(utilization=0, pids=[999], index=gpu)

    monkeypatch.setattr(driver, "_bounded_resources", sample)
    plan = {"limits": selection.LIMITS, "gpu_preference": selection.GPU_ORDER}

    card, receipt = driver.released_capacity(plan, {"gpu_uuid": "GPU-fixture", "physical_gpu": gpu})

    assert card is None and observations == [15.0]
    assert receipt["reason"] == "competing_process_after_release"
    assert receipt["second_empty_card_stability_wait_required"] is True


def test_probe_supervisor_closes_two_failed_workers_once_without_retry(proof_case, tmp_path, monkeypatch):
    case = proof_case
    root = tmp_path / "supervised-probes"
    root.mkdir()
    qualification = tmp_path / "cpu-qualification.json"
    write(qualification, {"cpu_fixture": True})
    bindings = {candidate: {**copy.deepcopy(case["binding"]), "candidate_id": candidate}
                for candidate in driver.EXECUTED}
    plan = {"source": case["binding"]["source"], "qualification": reference(qualification),
            "data_root": str(tmp_path), "gpu_preference": selection.GPU_ORDER, "limits": selection.LIMITS}
    clock = {"now": 100.0}
    launched, live, concurrent = [], set(), []

    class Process:
        def __init__(self, argv, **kwargs):
            candidate = argv[argv.index("--candidate") + 1]
            output = Path(argv[argv.index("--output") + 1])
            self.pid, self.returncode, self.polls = 1000 + len(launched), None, 0
            launched.append(candidate)
            live.add(self.pid)
            concurrent.append(len(live))
            write(output / "report.json", {**copy.deepcopy(case["worker"]), **bindings[candidate],
                                           "status": "failed", "passed": False})

        def poll(self):
            self.polls += 1
            if self.polls >= 2:
                self.returncode = 0
            return self.returncode

        def wait(self, timeout=None):
            assert self.returncode == 0
            live.discard(self.pid)
            return 0

    def sleep(_):
        clock["now"] += 60.0

    sample = gpu_sample(utilization=0)
    sample["gpus"]["stdout"] += "0, GPU-second, NVIDIA A100-SXM4-80GB, 81151, 81920, 0\n"
    monkeypatch.setattr(driver.time, "time", lambda: clock["now"])
    monkeypatch.setattr(driver.time, "sleep", sleep)
    monkeypatch.setattr(driver.subprocess, "Popen", Process)
    monkeypatch.setattr(driver, "code_identity", lambda: case["binding"]["source"])
    monkeypatch.setattr(driver.probe, "implementation_hashes", lambda: case["binding"]["tested_files_sha256"])
    monkeypatch.setattr(driver.original, "worker_env", lambda *args: {})
    monkeypatch.setattr(driver, "worker_identity", lambda pid: {"pid": pid, "alive": True, "start_ticks": pid + 1})
    monkeypatch.setattr(driver, "resources", lambda: copy.deepcopy(sample))
    monkeypatch.setattr(driver, "target_resources", lambda *args, **kwargs: {})
    monkeypatch.setattr(driver, "TelemetryGuard", lambda *args, **kwargs: SimpleNamespace(
        observe=lambda *args, **kwargs: {"stop_reason": None}))
    monkeypatch.setattr(driver, "artifact_bytes", lambda path: 0)
    monkeypatch.setattr(driver, "rss", lambda pid: 0)
    monkeypatch.setattr(driver.shutil, "disk_usage", lambda path: SimpleNamespace(free=100 * 1024**3))
    monkeypatch.setattr(driver, "stop_owned", lambda process: pytest.fail("Finished workers need no signal"))

    proofs = driver.supervise_probes(plan, {"prior_artifact_bytes": 0}, bindings, root,
                                     tmp_path / "old-recovery", None)

    assert launched == list(driver.EXECUTED) and max(concurrent) == 2 and not live
    summary = read_json(root / "supervisor.json")
    assert summary["status"] == "completed" and summary["automatic_retries"] is False
    assert set(proofs) == set(driver.EXECUTED)
    for candidate, proof_path in proofs.items():
        state, report = summary["states"][candidate], read_json(Path(proof_path))
        assert state["status"] == "failed" and state["attempted"] is True
        assert state["exit_code"] == 0 and state["actual_worker_gpu_seconds"] == 60.0
        assert report["passed"] is False and report["status"] == "failed"
        assert report["worker_body_seconds"] == 3.0
        assert report["new_model_calls"] == report["optimizer_steps"] == 0
        assert read_json(root / candidate / "actual/report.json")["actual_worker_gpu_seconds"] == 3.0
