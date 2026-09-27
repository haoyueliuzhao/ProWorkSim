"""CPU-only P1 launch guards; no candidate load, CUDA call or subprocess launch."""

import copy
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import p1_v020 as p1
from proworksim.storage import read_json


@pytest.fixture
def plan(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    p1.write(manifest, {"fixture": True})
    requests = []
    for index in range(3):
        path = tmp_path / f"request-{index}.json"
        p1.write(path, {"request": {"messages": [{"role": "user", "content": str(index)}]}})
        requests.append({"record": p1.ref(path), "purpose": f"fixture-{index}"})
    inventory = {"candidates": {"qwen35-9b": requests}}
    frozen = tmp_path / "frozen-inventory.json"
    p1.write(frozen, inventory)
    monkeypatch.setattr(p1, "PROBE_INVENTORY", frozen)
    monkeypatch.setattr(p1, "code_identity", lambda: {"code_commit": "fixture", "code_dirty": False})
    return p1.build_plan(tmp_path / "unloaded-model", manifest, inventory)


def test_fixed_plan_rejects_prompt_substitution_recipe_slots_and_replicas(plan, tmp_path):
    p1.validate_plan(plan)
    assert plan["limits"] == p1.LIMITS
    assert p1.LIMITS == {"gpu_count": 1, "gpu_seconds": 3600, "task_seconds": 900,
        "host_rss_bytes": 64 * 1024**3, "output_bytes": 5 * 1024**3, "model_api_calls": 0,
        "minimum_free_gpu_mib": 40960, "gpu_process_memory_limit_mib": 40960}
    other = tmp_path / "different-prompt.json"
    p1.write(other, {"request": {"messages": []}})
    changes = [
        lambda p: p["numerical_requests"][0].update(request=p1.ref(other)),
        lambda p: p["recipe"].update(max_output_tokens=1024),
        lambda p: p["work_window"]["slots"].pop(),
        lambda p: p.update(sampling_replicas=1),
        lambda p: p["recipe"].update(diagnostic_max_groups=1),
    ]
    for change in changes:
        altered = copy.deepcopy(plan)
        change(altered)
        with pytest.raises(ValueError):
            p1.validate_plan(altered)


def test_failed_numeric_gate_never_collects_business_or_runs_successor(plan, tmp_path, monkeypatch):
    import proworksim.candidate_runtime_v020 as candidate
    import proworksim.online_training as online
    import proworksim.harness_collection as collection

    out = tmp_path / "child"
    out.mkdir()
    p1.write(out / "plan.json", plan)
    owner = SimpleNamespace(actor_steps=0, critic_steps=0)
    calls = []
    monkeypatch.setattr(candidate, "CandidateActor", SimpleNamespace(
        from_candidate=lambda *args, **kwargs: calls.append("fixture_loader") or owner,
        profile_factory=candidate.CandidateActor.profile_factory))
    monkeypatch.setattr(p1, "numerical", lambda *args: calls.append("numeric_failure") or False)
    monkeypatch.setattr(p1.importlib.metadata, "version", lambda name: "1.5.5")
    def forbidden(*args, **kwargs):
        raise AssertionError("Business ran after failed numeric gate")
    monkeypatch.setattr(online, "run_online_windows", forbidden)
    monkeypatch.setattr(collection, "collect_window", forbidden)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2")
    assert p1.child(plan, out) == 2
    report = read_json(out / "report.json")
    assert calls == ["fixture_loader", "numeric_failure"]
    assert report["status"] == "stopped_numeric_gate"
    assert not report["numeric_completed"] and report["work_episodes_started"] == 0
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    with pytest.raises(ValueError, match="Exactly one physical GPU"):
        p1.child(plan, out)
    assert calls == ["fixture_loader", "numeric_failure"]


def test_numeric_first_request_failure_does_not_claim_learning_forward(plan, tmp_path):
    pytest.importorskip("torch")
    class Owner:
        def __init__(self):
            self.actor_steps = self.critic_steps = 0
            self.actor_optimizer = SimpleNamespace(zero_grad=lambda **kw: None)
            self.model = SimpleNamespace(eval=lambda: None)
        def begin_window(self, name): self.phase = "collecting"
        def freeze_identity(self): return {"fixture": True}
        def _make_identity(self): return self.freeze_identity()
        def reseed(self, *args, **kwargs): pass
        def clear_generation_cache(self): pass
        def complete(self, request, **kwargs): return {"http_status": 503, "body": {"error": "fixture"}}
        def finish_evaluation(self, *args): raise AssertionError("Wrong diagnostic closure")
    owner = Owner()
    out = tmp_path / "numeric"
    out.mkdir()
    assert p1.numerical(owner, plan, out) is False
    result = read_json(out / "numerical.json")
    assert result["status"] == "failed" and owner.phase == "idle"
    assert not result["diagnostic_learning_forward_and_backward"]
    assert result["learning_forward_calls_attempted"] == result["backward_calls_completed"] == 0


@pytest.mark.parametrize("failure", ["total", "task", "rss", "storage", "gpu", "query"])
def test_watchdog_enforces_limits_and_signals_only_owned_child(plan, tmp_path, monkeypatch, failure):
    out = tmp_path / failure
    # Do not validate fixture-modified thresholds as a different real experiment.
    monkeypatch.setattr(p1, "validate_plan", lambda _: None)
    monkeypatch.setattr(p1, "query_gpus", lambda: [
        {"index": 2, "uuid": "fixture-a100", "free_mib": 50000, "name": "NVIDIA A100"}])
    times = iter([0, 3601 if failure == "total" else 901 if failure == "task" else 1])
    last = [0]
    def now():
        last[0] = next(times, last[0])
        return last[0]
    monkeypatch.setattr(p1.time, "time", now)
    monkeypatch.setattr(p1.time, "sleep", lambda _: (_ for _ in ()).throw(AssertionError("Unexpected extra loop")))
    original_read_text = Path.read_text
    def read_text(path, *args, **kwargs):
        if str(path) == "/proc/123456789/statm":
            return "0 " + str((p1.LIMITS["host_rss_bytes"] // 4096 + 1) if failure == "rss" else 1)
        return original_read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(p1.os, "sysconf", lambda _: 4096)
    if failure == "storage":
        monkeypatch.setattr(p1, "LIMITS", {**p1.LIMITS, "output_bytes": 1})
    memory = 40961 if failure == "gpu" else 100
    monkeypatch.setattr(p1.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=1 if failure == "query" else 0,
        stdout=f"fixture-a100, 123456789, {memory}, fixture-owned-child\nother, 999, 70000, unrelated\n",
        stderr="fixture query failure" if failure == "query" else ""))
    class Process:
        pid = 123456789
        code = None
        def poll(self): return self.code
        def wait(self, timeout=None):
            assert self.code is not None
            return self.code
    process = Process()
    def launch(*args, **kwargs):
        assert kwargs["start_new_session"] is True
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "2"
        return process
    monkeypatch.setattr(p1.subprocess, "Popen", launch)
    signals = []
    def killpg(pid, sig):
        signals.append((pid, sig))
        process.code = -int(sig)
    monkeypatch.setattr(p1.os, "killpg", killpg)
    assert p1.parent(plan, out) == -signal.SIGTERM
    assert signals == [(process.pid, signal.SIGTERM)]
    expected = {"total": "total_gpu_time_limit", "task": "single_task_time_limit",
        "rss": "host_memory_limit", "storage": "artifact_size_limit",
        "gpu": "gpu_process_memory_limit", "query": "gpu_resource_query_failed"}
    result = read_json(out / "launch.json")
    assert result["limit_reason"] == expected[failure]
    assert result["no_retry"] and not result["downstream_started"]


def test_no_free_authorized_a100_creates_no_process_or_output(plan, tmp_path, monkeypatch):
    monkeypatch.setattr(p1, "query_gpus", lambda: [
        {"index": 2, "free_mib": 40959, "name": "NVIDIA A100"},
        {"index": 3, "free_mib": 80000, "name": "not-the-declared-model"},
        {"index": 0, "free_mib": 80000, "name": "NVIDIA A100"}])
    monkeypatch.setattr(p1.subprocess, "Popen", lambda *a, **k: pytest.fail("Unexpected process"))
    out = tmp_path / "unstarted"
    with pytest.raises(RuntimeError, match="No authorized GPU"):
        p1.parent(plan, out)
    assert not out.exists()


def test_owned_child_escalation_is_bounded_and_exited_child_is_untouched(monkeypatch):
    class Process:
        pid = 123456789
        exited = False
        def poll(self): return -9 if self.exited else None
        def wait(self, timeout=None):
            assert timeout == 5
            raise p1.subprocess.TimeoutExpired("fixture", timeout)
    process = Process()
    signals = []
    monkeypatch.setattr(p1.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    p1.stop_owned_child(process)
    assert signals == [(process.pid, signal.SIGTERM), (process.pid, signal.SIGKILL)]
    process.exited = True
    p1.stop_owned_child(process)
    assert len(signals) == 2


def test_explicit_head_followup_binds_closed_prior_and_subtracts_actual_time(plan, tmp_path):
    prior = tmp_path / "closed-prior"
    prior.mkdir()
    p1.write(prior / "plan.json", plan)
    p1.write(prior / "report.json", {"plan": p1.ref(prior / "plan.json"),
        "status": "stopped_numeric_gate", "source_unchanged": True,
        "actor_steps": 0, "critic_steps": 0, "work_episodes_started": 0})
    elapsed = 46.31456899642944
    p1.write(prior / "launch.json", {"version": p1.VERSION, "status": "stopped", "exit_code": 2,
        "downstream_started": False, "limits": p1.LIMITS, "elapsed_seconds": elapsed,
        "ended_at": 100})
    inventory = read_json(p1.PROBE_INVENTORY)
    followup = p1.build_plan(plan["model"], plan["manifest"]["path"], inventory,
        execution_profile="v0.20.1", prior_attempt_ref=p1.ref(prior / "launch.json"))
    p1.validate_plan(followup)
    assert followup["remaining_gpu_seconds"] == 3600 - elapsed
    assert followup["prior_output_bytes"] > 0
    assert followup["runtime_profile"]["lm_head_storage_dtype"] == "float32"
    assert followup["work_window"] == plan["work_window"]
    assert followup["numerical_requests"] == plan["numerical_requests"]
    altered = copy.deepcopy(followup)
    altered["remaining_gpu_seconds"] = 3600
    with pytest.raises(ValueError):
        p1.validate_plan(altered)
    with pytest.raises(ValueError, match="closed original"):
        p1.build_plan(plan["model"], plan["manifest"]["path"], inventory, execution_profile="v0.20.1")
    with pytest.raises(ValueError, match="two explicitly"):
        p1.build_plan(plan["model"], plan["manifest"]["path"], inventory, execution_profile="v0.20.2")
