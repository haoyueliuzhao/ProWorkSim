"""Only the GPU-scope delta: mocked telemetry/processes, no model/GPU calls."""
from types import SimpleNamespace

import pytest

from proworksim.storage import read_json
from scripts import software_learning_development_resume_v049r2g as adapter
from scripts.run_ne_v021 import reference, write


ALL = tuple(range(8))


def sample(*rows):
    return {"gpus": {"returncode": 0, "stdout": "\n".join(rows)},
            "processes": {"returncode": 0, "stdout": ""}}


def test_all_added_devices_keep_capacity_and_exclusion_gates():
    provider = adapter.resources(ALL)
    plan = {"gpu_preference": list(ALL), "limits": adapter.LIMITS}
    telemetry = sample(*(f"{i}, GPU-{i}, A100, 81920, 81920, 0" for i in ALL))
    assert [c["index"] for c in provider.available_cards(plan, telemetry)] == list(ALL)
    assert [c["index"] for c in provider.available_cards(plan, telemetry, [0, 2])] == [1, 3, 4, 5, 6, 7]
    bad = sample("0, GPU-0, A100, 57000, 81920, 0", "1, GPU-1, A100, 40000, 40960, 0")
    assert provider.available_cards(plan, bad) == []
    bad["processes"]["returncode"] = 1
    assert provider.available_cards(plan, bad) == []
    assert adapter.inherited.GPU_ORDER == (3, 4, 5, 7)
    assert adapter.inherited.available_cards.__globals__["GPU_ORDER"] == (3, 4, 5, 7)


@pytest.mark.parametrize("indices", [[], [0, 0], [1, 0], [-1], [True]])
def test_scope_is_an_explicit_unique_physical_inventory(indices):
    with pytest.raises(ValueError, match="physical GPU"):
        adapter.gpu_scope(indices)


def test_query_environment_and_nested_preload_use_same_scope(monkeypatch):
    queries = []
    monkeypatch.setattr(adapter.inherited, "target_resources",
                        lambda selector, **kwargs: queries.append(selector))
    provider = adapter.resources(ALL)
    provider.allowed_resources()
    assert queries == ["0,1,2,3,4,5,6,7"]
    plan = {"runtime_dependency_path": "/fixture/dependencies"}
    env = provider.worker_env(plan, 6)
    assert env["CUDA_VISIBLE_DEVICES"] == "6" and env["HF_HUB_OFFLINE"] == "1"
    assert env["PYTHONPATH"].split(":")[0] == "/fixture/dependencies"
    with pytest.raises(ValueError):
        provider.worker_env(plan, 8)
    worker = adapter.worker_function(ALL)
    loader = worker.__globals__["original"]._load_owner
    assert worker.__code__ is adapter.prior.run_worker.__code__
    assert loader.__code__ is adapter.prior.original._load_owner.__code__
    nested = loader.__globals__["inherited"]
    assert nested.available_cards.__globals__["GPU_ORDER"] == ALL
    assert nested.allowed_resources.__globals__["GPU_ORDER"] == ALL
    assert worker.__globals__["GPU_ORDER"] == ALL
    assert adapter.prior.GPU_ORDER == adapter.inherited.GPU_ORDER == (3, 4, 5, 7)


def waiting_fixture(tmp_path, monkeypatch):
    old = tmp_path / "waiting"
    original = tmp_path / "r1"
    scientific = dict.fromkeys(("inventory", "design", "declaration", "s0", "mapper_specification",
        "source_partition", "task_source_manifest", "training_reward", "development_F", "common", "model_references"), "UNCHANGED")
    write(original / "plan.json", scientific)
    source = {"code_dirty": False, "fixture": True}
    inventory = {"state_proof": {"path": "FIXTURE", "sha256": "FIXTURE"}}
    write(tmp_path / "old-controls.json", {})
    plan = {**scientific, "version": adapter.prior.VERSION, "workers": list(adapter.WORKERS),
        "limits": adapter.LIMITS, "new_budget_caps": adapter.prior.budget_caps(),
        "gpu_preference": list(adapter.prior.GPU_ORDER), "source": source, "source_files": {},
        "prior_artifact_roots": [], "original_root": str(original), "resume_of": reference(original / "plan.json"),
        "resume_inventory": inventory, "resume_cpu_controls": reference(tmp_path / "old-controls.json"),
        "automatic_retries": False, "automatic_successors": []}
    write(old / "plan.json", adapter.prior._seal(plan, "plan_sha256"))
    write(old / "supervisor.json", {"source": source, "status": "interrupted", "ended_at": 123,
        "closed_worker_gpu_seconds": 0, "running_worker_gpu_seconds": 0,
        "states": {name: {"status": "stopped", "attempted": False} for name in adapter.WORKERS}})
    monkeypatch.setattr(adapter.prior.previous, "original_source_agreement", lambda *args: {})
    monkeypatch.setattr(adapter, "code_identity", lambda: source)
    monkeypatch.setattr(adapter.prior, "code_identity", lambda: source)
    monkeypatch.setattr(adapter, "source_files", lambda: {})
    monkeypatch.setattr(adapter.prior, "derive_inventory", lambda *args, **kwargs: inventory)
    checked = adapter.prior.checked
    monkeypatch.setattr(adapter.prior, "checked", lambda ref: "FIXTURE" if ref.get("path") == "FIXTURE" else checked(ref))
    protocol = tmp_path / "protocol.md"
    protocol.write_text("FIXTURE")
    monkeypatch.setattr(adapter, "PROTOCOL", protocol)
    return old


@pytest.mark.parametrize("fault", [None, "attempted", "live_host", "prepared_directory", "worker_cost"])
def test_only_a_terminal_zero_worker_wait_may_be_moved(tmp_path, monkeypatch, fault):
    old = waiting_fixture(tmp_path, monkeypatch)
    supervisor = read_json(old / "supervisor.json")
    if fault == "attempted":
        supervisor["states"][adapter.WORKERS[0]]["attempted"] = True
    elif fault == "live_host":
        supervisor["observer_pid"] = 123
        monkeypatch.setattr(adapter, "worker_identity", lambda pid: {"alive": True})
    elif fault == "prepared_directory":
        (old / adapter.WORKERS[0]).mkdir()
    elif fault == "worker_cost":
        supervisor["closed_worker_gpu_seconds"] = 1
    write(old / "supervisor.json", supervisor)
    if fault:
        with pytest.raises(ValueError):
            adapter.waiting_receipt(old)
    else:
        receipt = adapter.waiting_receipt(old)
        assert receipt["new_model_workers"] == receipt["gpu_worker_seconds"] == 0


@pytest.mark.parametrize("fault", [None, "GPU_scope", "scientific_setting", "waiting_evidence"])
def test_resource_plan_seals_scope_and_preserves_every_other_setting(tmp_path, monkeypatch, fault):
    old = waiting_fixture(tmp_path, monkeypatch)
    controls = tmp_path / "controls.json"
    write(controls, adapter.prior._seal({"passed": True, "waiting_receipt": adapter.waiting_receipt(old),
        "gpu_preference": list(ALL), "new_model_calls": 0, "new_gpu_workers": 0, "new_backward_calls": 0}))
    root = tmp_path / "new"
    plan = adapter.prepare(root, waiting_root=old, controls=controls)
    if fault == "GPU_scope":
        plan["gpu_preference"] = [6]
    elif fault == "scientific_setting":
        plan["training_reward"] = "changed"
    elif fault == "waiting_evidence":
        write(old / "new-evidence.json", {"changed": True})
    plan.pop("plan_sha256")
    write(root / "plan.json", adapter.prior._seal(plan, "plan_sha256"))
    if fault:
        with pytest.raises(ValueError):
            adapter.frozen(root)
    else:
        assert adapter.frozen(root)["gpu_preference"] == list(ALL)
        with pytest.raises(FileExistsError):
            adapter.prepare(root, waiting_root=old, controls=controls)


def test_inherited_supervisor_dispatches_two_added_cards_after_original_stability(tmp_path, monkeypatch):
    supervisor = adapter.prior_supervisor
    root = tmp_path / "new"
    root.mkdir()
    units = read_json(adapter.prior.original.DESIGN)["development_units_shared_by_branches"][2:]
    source = {"fixture": True}
    plan = {"source": source, "resume_inventory": {"remaining_development_units": units,
        "original_supervisor": {}}, "prior_artifact_roots": [], "limits": adapter.LIMITS,
        "gpu_preference": list(ALL), "native_python": "FIXTURE-NO-REAL-PROCESS", "runtime_dependency_path": "/fixture"}
    monkeypatch.setattr(adapter, "frozen", lambda path: plan)
    monkeypatch.setattr(adapter, "code_identity", lambda: source)
    class Clock:
        now = 1000
        def time(self):
            return self.now
        def sleep(self, seconds):
            self.now += seconds
    clock = Clock()
    monkeypatch.setattr(supervisor, "time", clock)
    telemetry = sample("0, GPU-0, A100, 81920, 81920, 0", "6, GPU-6, A100, 81920, 81920, 0")
    monkeypatch.setattr(adapter.inherited, "target_resources", lambda *args, **kwargs: telemetry)
    monkeypatch.setattr(supervisor, "target_resources", lambda *args, **kwargs: telemetry)
    monkeypatch.setattr(supervisor, "worker_identity", lambda pid: {"start_ticks": pid, "alive": True})
    monkeypatch.setattr(supervisor, "rss", lambda pid: 0)
    monkeypatch.setattr(supervisor, "artifact_bytes", lambda path: 0)
    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda path: SimpleNamespace(free=1024**4))
    class Guard:
        def __init__(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            return {"stop_reason": None}
    monkeypatch.setattr(supervisor, "TelemetryGuard", Guard)
    launched = []
    class FakeProcess:
        def __init__(self, argv, **kwargs):
            self.pid = 900 + len(launched)
            self.returncode = None
            self.started = clock.now
            assert argv[2] == adapter.MODULE
            self.name = argv[argv.index("--worker") + 1]
            self.gpu = int(kwargs["env"]["CUDA_VISIBLE_DEVICES"])
            launched.append(self)
            write(root / self.name / "actual/report.json", {"status": "complete", "source_before": source,
                "source_after": source, "success_boundary": True})
        def poll(self):
            if clock.now > self.started:
                self.returncode = 0
            return self.returncode
        def wait(self, timeout):
            return self.returncode
    monkeypatch.setattr(supervisor.subprocess, "Popen", FakeProcess)
    function = adapter.supervisor_function(ALL)
    assert function.__code__ is supervisor.supervise.__code__
    result = function(root)
    assert result["status"] == "complete" and result["original_F_B"] is None
    assert [p.gpu for p in launched] == [0, 6]
    assert launched[0].started == launched[1].started >= 1000 + adapter.LIMITS["gpu_capacity_stability_seconds"]
    assert adapter.prior.GPU_ORDER == (3, 4, 5, 7)


def test_process_translation_rejects_nonworker_commands():
    with pytest.raises(ValueError, match="inherited DB worker"):
        adapter.launch(["python", "-m", "arbitrary.module", "worker"])


@pytest.mark.parametrize("receipt_failure", [False, True])
def test_launch_receipt_precedes_process_and_records_actual_supervisor_command(tmp_path, monkeypatch, receipt_failure):
    folder = tmp_path / "DB"
    folder.mkdir()
    argv = ["FIXTURE-PYTHON", "-m", "scripts.software_learning_development_resume_v049r2", "worker",
            "--run-root", str(tmp_path), "--worker", adapter.WORKERS[0], "--output", str(folder / "actual")]
    requested = list(argv)
    state = {"command": argv}
    source = {"fixture": "no-model"}
    monkeypatch.setattr(adapter, "code_identity", lambda: source)
    launched = []
    def spawn(actual, **kwargs):
        receipt = read_json(folder / "worker-launch.json")
        assert receipt["phase"] == "before_popen" and receipt["source"] == source
        assert receipt["requested_command"] == requested
        assert receipt["actual_command"] == actual == state["command"]
        assert actual[2] == adapter.MODULE and receipt["physical_gpu"] == "6"
        launched.append(list(actual))
        return "FIXTURE-PROCESS"
    monkeypatch.setattr(adapter.prior_supervisor.subprocess, "Popen", spawn)
    if receipt_failure:
        def failed_write(*args):
            raise OSError("CPU-injected launch receipt failure")
        monkeypatch.setattr(adapter, "write", failed_write)
        with pytest.raises(OSError, match="launch receipt failure"):
            adapter.launch(argv, env={"CUDA_VISIBLE_DEVICES": "6"})
        assert launched == [] and state["command"] == requested
    else:
        assert adapter.launch(argv, env={"CUDA_VISIBLE_DEVICES": "6"}) == "FIXTURE-PROCESS"
        assert len(launched) == 1
