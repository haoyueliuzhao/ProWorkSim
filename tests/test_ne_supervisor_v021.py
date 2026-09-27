"""CPU process/world fixtures only; no model construction, GPU query or job launch."""

import signal
import sys
from types import SimpleNamespace

import pytest

from scripts import run_ne_v021 as supervisor
from scripts import evaluate_work_v021 as evaluation
from proworksim.storage import read_json


SOURCE = {"code_commit": "cpu-fixture", "code_dirty": False, "source_tree_sha256": "fixture"}


def sample(cards=(3,), processes="", free=80000):
    return {"gpus": {"returncode": 0, "stdout": "\n".join(
        f"{i}, GPU-{i}, NVIDIA A100-SXM4-80GB, {free}, 81920, 0" for i in cards), "stderr": ""},
        "processes": {"returncode": 0, "stdout": processes, "stderr": ""}}


def test_released_requires_empty_a100_and_query_evidence():
    assert supervisor.released_cards(sample((7, 3))) == [3, 7]
    assert supervisor.released_cards(sample((3, 7), "GPU-3, 44, 1, another-project")) == [7]
    assert supervisor.released_cards(sample(free=77999)) == []
    assert supervisor.released_cards(sample(processes="unparseable")) == []
    broken = sample()
    broken["gpus"]["returncode"] = None
    assert supervisor.released_cards(broken) == []
    non_a100 = sample()
    non_a100["gpus"]["stdout"] = non_a100["gpus"]["stdout"].replace("A100", "H100")
    assert supervisor.released_cards(non_a100) == []


def test_persistent_supervisor_runs_e_after_nonzero_n_on_same_first_card_once(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    supervisor.write(plan, {"fixture": True})
    out = tmp_path / "observer"
    monkeypatch.setattr(supervisor, "validate_plan", lambda plan: None)
    monkeypatch.setattr(supervisor, "code_identity", lambda: dict(SOURCE))
    samples = iter([sample((3,)), sample((3,)), sample((0, 3)), sample((0, 3))])
    monkeypatch.setattr(supervisor, "resources", lambda: next(samples))
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("No actual process"))
    called = []
    def run_line(plan, state, name, gpu, output):
        called.append((name, gpu))
        state["jobs"][name].update(attempted=True, status="stopped" if name == "N" else "complete",
            exit_code=2 if name == "N" else 0, elapsed_gpu_seconds=10)
        supervisor.write(output / "state.json", state)
    monkeypatch.setattr(supervisor, "run_line", run_line)
    monkeypatch.setattr(sys, "argv", ["supervisor", "--plan", str(plan), "--output", str(out)])
    supervisor.main()
    assert called == [("N", 3), ("E", 3)]
    state = read_json(out / "state.json")
    assert state["status"] == "closed" and state["selected_gpu"] == 3
    assert state["total_gpu_seconds"] == 20 and not state["automatic_training_started"]
    with pytest.raises(ValueError, match="attempted a line"):
        supervisor.main()
    assert len(called) == 2
    with supervisor.lock(out):
        with pytest.raises(RuntimeError, match="already owns"):
            with supervisor.lock(out):
                pass


@pytest.mark.parametrize("case", ["N_memory", "E_remaining_time"])
def test_limits_persist_intent_and_signal_only_own_session(tmp_path, monkeypatch, case):
    name = "N" if case == "N_memory" else "E"
    plan_path = tmp_path / "plan.json"
    supervisor.write(plan_path, {"fixture": True})
    plan = {"plan_path": str(plan_path)}
    state = {"source": SOURCE, "plan": supervisor.reference(plan_path),
             "jobs": {"N": {"attempted": False}, "E": {"attempted": False}}}
    if name == "E":
        state["jobs"]["N"].update(attempted=True, elapsed_gpu_seconds=1206)
    monkeypatch.setattr(supervisor, "code_identity", lambda: dict(SOURCE))
    monkeypatch.setattr(supervisor, "command", lambda *a: ["fixture-no-process"])
    times = iter([0, 1 if name == "N" else 2395])
    latest = [0]
    def now():
        latest[0] = next(times, latest[0])
        return latest[0]
    monkeypatch.setattr(supervisor.time, "time", now)
    monkeypatch.setattr(supervisor.time, "sleep", lambda _: pytest.fail("Extra supervision loop"))
    own_memory = 73729 if name == "N" else 100
    monkeypatch.setattr(supervisor, "resources", lambda: sample((3,),
        f"GPU-3, 123456789, {own_memory}, owned-child\nGPU-0, 99, 80000, other-project"))
    process = SimpleNamespace(pid=123456789, code=None)
    process.poll = lambda: process.code
    process.wait = lambda timeout=None: process.code
    def launch(*args, **kwargs):
        persisted = read_json(tmp_path / "state.json")
        assert persisted["jobs"][name]["attempted"] is True
        assert kwargs["start_new_session"] and kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "3"
        return process
    monkeypatch.setattr(supervisor.subprocess, "Popen", launch)
    signals = []
    def killpg(pid, sig):
        signals.append((pid, sig))
        process.code = -int(sig)
    monkeypatch.setattr(supervisor.os, "killpg", killpg)
    supervisor.run_line(plan, state, name, 3, tmp_path)
    assert signals == [(process.pid, signal.SIGTERM)]
    job = state["jobs"][name]
    assert job["stop_reason"] == ("own_gpu_memory_limit" if name == "N" else "line_time_limit")
    assert job["gpu_budget_seconds"] == (1200 if name == "N" else 2394)
    assert job["stop_after_seconds"] == job["gpu_budget_seconds"] - 30
    with pytest.raises(ValueError, match="never restarted"):
        supervisor.run_line(plan, state, name, 3, tmp_path)


def test_e_only_collects_work_and_frozen_guards_never_learning(tmp_path, monkeypatch):
    import proworksim.templates.retail_collaboration_v021 as template

    class Owner:
        phase = "idle"
        actor_steps = critic_steps = 0
        def freeze_identity(self): return {"actor": "fixed"}
        def capture_evaluation_state(self):
            assert self.phase == "idle"
            return {"cpu_fixture_snapshot": True}
        def begin_window(self, window):
            assert self.phase == "idle"
            self.phase = "collecting"
            return self.freeze_identity()
        def reseed(self, *args, **kwargs): pass
        def finish_evaluation(self, entries, output):
            assert self.phase == "collecting"
            self.phase = "idle"
        def finish_evaluation_guard(self, snapshot):
            assert self.phase == "idle" and snapshot["cpu_fixture_snapshot"]
            return {"learning_unchanged": True, "rng_restored_exactly": True}
        def learning_logprobs(self, *args): raise AssertionError("E invoked learner forward")
        def update_window(self, *args): raise AssertionError("E invoked update")
    def build(case, folder):
        folder.mkdir()
        return SimpleNamespace(world=object(), scenario={}, active_roles=["implementer"])
    runtime = SimpleNamespace(recorder=SimpleNamespace(snapshot=lambda: {}), policy_identities={}, snapshot=lambda: {})
    monkeypatch.setattr(template, "build_case", build)
    monkeypatch.setattr(template, "assess_episode", lambda _: {"eligible": True, "fixture": True})
    monkeypatch.setattr(evaluation, "_runtime", lambda *args: (runtime, [], {}))
    monkeypatch.setattr(evaluation, "begin_episode", lambda *a, **k: None)
    monkeypatch.setattr(evaluation, "finish_episode", lambda *a, **k: None)
    monkeypatch.setattr(evaluation, "run_fragment", lambda *a, **k: {"fixture_boundary": True})
    owner = Owner()
    result = evaluation.execute(owner, {"situations": [{"case_id": str(i)} for i in range(6)]}, tmp_path)
    assert result["status"] == "complete" and len(result["rows"]) == 6
    assert owner.phase == "idle" and owner.actor_steps == owner.critic_steps == 0
    assert all(row["evaluation_guard"]["learning_unchanged"] for row in result["rows"])


def test_e_rejects_empty_device_before_model_constructor(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    supervisor.write(plan, {})
    monkeypatch.setattr(supervisor, "validate_plan", lambda _: None)
    monkeypatch.setattr(evaluation, "code_identity", lambda: dict(SOURCE))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    monkeypatch.setattr(sys, "argv", ["E", "--plan", str(plan), "--output", str(tmp_path / "no-output")])
    with pytest.raises(ValueError, match="exactly one GPU"):
        evaluation.main()
    assert not (tmp_path / "no-output").exists()


def test_prelaunch_shared_caps_and_changed_plan_never_start_model(tmp_path, monkeypatch):
    plan_path = tmp_path / "plan.json"
    supervisor.write(plan_path, {"fixture": True})
    state = {"source": SOURCE, "plan": supervisor.reference(plan_path),
             "jobs": {"N": {"attempted": True, "elapsed_gpu_seconds": 3600},
                      "E": {"attempted": False}}}
    monkeypatch.setattr(supervisor, "code_identity", lambda: dict(SOURCE))
    monkeypatch.setattr(supervisor, "command", lambda *a: ["fixture"])
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **k: pytest.fail("No budget; model must not launch"))
    plan = {"plan_path": str(plan_path)}
    supervisor.run_line(plan, state, "E", 3, tmp_path)
    assert state["jobs"]["E"]["status"] == "not_started_total_budget_exhausted"
    state["jobs"]["N"]["elapsed_gpu_seconds"] = 10
    monkeypatch.setattr(supervisor, "LIMITS", {**supervisor.LIMITS, "artifact_bytes": 1})
    supervisor.run_line(plan, state, "E", 3, tmp_path)
    assert state["jobs"]["E"]["status"] == "not_started_total_artifact_limit"
    supervisor.write(plan_path, {"fixture": "changed-after-wait"})
    with pytest.raises(ValueError, match="plan changed while waiting"):
        supervisor.run_line(plan, state, "E", 3, tmp_path)


def test_n_refs_must_be_the_unique_response_in_the_bound_prior_run(tmp_path, monkeypatch):
    import proworksim.templates.retail_collaboration_v021 as template

    prior = tmp_path / "prior"
    prior.mkdir()
    supervisor.write(prior / "plan.json", {"runtime_profile": {"version": "candidate-runtime-v0.20.1"}})
    supervisor.write(prior / "numerical.json", {"rows": [{"response_id": "fixture-call"}]})
    supervisor.write(prior / "resident/calls/fixture-call.json", {"fixture": True})
    catalog = {"situations": [{"case_id": str(i)} for i in range(6)]}
    monkeypatch.setattr(template, "registry", lambda: catalog)
    supervisor.write(tmp_path / "catalog.json", catalog)
    plan = {"version": supervisor.VERSION, "limits": supervisor.LIMITS,
        "gpu_pool": supervisor.GPU_POOL, "order": ["N", "E"], "runtime": "candidate-runtime-v0.20.1",
        "allow_parameter_updates": False, "automatic_successors": [],
        "N_prior_plan": supervisor.reference(prior / "plan.json"),
        "N_saved_numeric": supervisor.reference(prior / "numerical.json"),
        "N_saved_response": supervisor.reference(prior / "resident/calls/fixture-call.json"),
        "E_catalog": supervisor.reference(tmp_path / "catalog.json")}
    supervisor.validate_plan(plan)
    supervisor.write(tmp_path / "unrelated-response.json", {"fixture": True})
    changed = {**plan, "N_saved_response": supervisor.reference(tmp_path / "unrelated-response.json")}
    with pytest.raises(ValueError, match="does not belong"):
        supervisor.validate_plan(changed)


def test_terminal_accounting_preserves_partial_n_and_known_e_zero(tmp_path):
    from scripts.run_ne_v021 import write
    from scripts.summarize_ne_v021 import summarize
    (tmp_path / 'N').mkdir()
    (tmp_path / 'E').mkdir()
    write(tmp_path / 'state.json', {'status': 'closed', 'source': {'code_commit': 'cpu-fixture'},
        'jobs': {'N': {'attempted': True, 'exit_code': 1, 'elapsed_gpu_seconds': 2},
                 'E': {'attempted': True, 'exit_code': 0, 'elapsed_gpu_seconds': 3}}})
    write(tmp_path / 'N/report.json', {'status': 'interrupted_or_error'})
    write(tmp_path / 'N/paths.json', {'paths': {'cache_no_grad': {'status': 'complete',
        'comparison_to_original_sampling': {'max_abs_delta': .2, 'mean_abs_delta': .01, 'passed': False}}}})
    write(tmp_path / 'E/report.json', {'status': 'complete', 'planned_episodes': 6, 'rows': [
        {'case_id': 'fixture', 'status': 'closed', 'assessment': {'eligible': True, 'reward': 0, 'completed': False}}],
        'actor_steps': 0, 'critic_steps': 0})
    result = summarize(tmp_path)
    assert result['N']['paths']['cache_no_grad']['original_gate_passed'] is False
    assert result['E']['known'] == 1 and result['E']['rows'][0]['reward'] == 0
    assert result['E']['started'] == 1 and result['E']['planned'] == 6
    assert result['gpu_seconds'] == 5 and result['training_started'] is False
