"""New panel seams only: actual accounting, independent repeats and pause policy."""
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from proworksim import software_panel_native_v053 as native


IDENTITY = {"raw_release": True, "checkpoint": None, "adapter_sha256": None}


def native_input(prompt=100):
    return {"prompt_tokens": prompt, "fits": True, "sha256": "f" * 64}


def response(record, *, attempt="first", output=3):
    return {
        "attempt_id": attempt, "actor_identity": copy.deepcopy(IDENTITY),
        "input": copy.deepcopy(record), "output_ids": [7] * output,
        "usage": {"prompt_tokens": record["prompt_tokens"], "completion_tokens": output,
                  "total_tokens": record["prompt_tokens"] + output},
    }


def test_actual_usage_settles_once_and_uncertain_usage_never_becomes_zero():
    ledger = native.EpisodeLedger(IDENTITY, {"slot_id": "main-000"})
    record = native_input()
    reservation = ledger.decide(record)
    ledger.reserve(record, {"path": "/synthetic/request"}, reservation)
    assert ledger.snapshot()["complete_actual_tokens"] is None
    assert ledger.snapshot()["uncertain_reservation_tokens"] == 2148
    with pytest.raises(native.PublicSystemFault, match="cannot be replayed"):
        ledger.decide(record)
    ledger.settle(record, response(record), {"path": "/synthetic/response"})
    assert ledger.snapshot()["known_actual_tokens"] == 103
    assert ledger.snapshot()["uncertain_reservation_tokens"] == 0
    assert ledger.snapshot()["complete_responses"] == 1
    ledger.reserve(record, {"path": "/synthetic/request2"}, ledger.decide(record))
    with pytest.raises(native.PublicSystemFault, match="cannot settle"):
        ledger.settle(record, response(record), {"path": "/synthetic/response2"})
    assert ledger.snapshot()["known_actual_tokens"] == 103
    assert ledger.snapshot()["complete_actual_tokens"] is None


def test_budget_and_context_reject_before_dispatch():
    ledger = native.EpisodeLedger(IDENTITY, {})
    ledger.prompt_tokens = 499000
    with pytest.raises(native.LocalStop) as stopped:
        ledger.decide(native_input())
    assert stopped.value.reason == "full_request_token_reservation_insufficient"
    assert ledger.attempts == 0 and ledger.inflight is None
    ledger = native.EpisodeLedger(IDENTITY, {})
    record = {**native_input(), "fits": False}
    with pytest.raises(native.LocalStop) as stopped:
        ledger.decide(record)
    assert stopped.value.reason == "full_native_context_preexecution_rejection"
    assert ledger.decisions == 1 and ledger.attempts == 0


def test_local_model_failure_is_scored_but_public_fault_and_unknown_pause():
    guard = {k: True for k in (
        "learning_unchanged", "rng_restored_exactly",
        "actor_identity_unchanged", "software_binding_unchanged")}
    common = dict(ledger={"inflight": None}, guard=guard, sdk_status="error", error=None)
    verdict = native.classify_episode(
        **common, status="safe_local_stop",
        stop_reason="full_native_context_preexecution_rejection", grade={"R_code": 0})
    assert verdict["decision"] == "continue" and verdict["R_code"] == 0
    verdict = native.classify_episode(
        **common, status="execution_fault", stop_reason=None, grade={"R_code": 1})
    assert verdict["decision"] == "global_pause" and verdict["R_code"] is None
    verdict = native.classify_episode(
        **common, status="closed", stop_reason=None, grade={"R_code": None})
    assert verdict["status"] == "technical_unknown" and verdict["R_code"] is None
    verdict = native.classify_episode(
        **common, status="closed", stop_reason=None,
        grade={"R_code": 0, "technical_error": "original harness did not complete"})
    assert verdict["decision"] == "global_pause" and verdict["R_code"] is None


def test_fixed_queue_and_fresh_repeat_binding():
    rows = [{"slot_id": str(i), "task_id": "task", "seed": 100 + i,
             "repeat_index": 1 if i == 0 else 2} for i in range(8)]
    assert native.next_pending_rows(
        rows, started_slot_ids={"0", "1"}, active_count=2, paused=False) == rows[2:4]
    assert native.next_pending_rows(
        rows, started_slot_ids={"0", "1"}, active_count=2, paused=True) == []
    with pytest.raises(ValueError, match="four"):
        native.next_pending_rows(rows, started_slot_ids=set(), active_count=5, paused=False)
    backend = {"task_id": "task", "fresh_initial_state": True, "container_id": "fresh-1"}
    first = native.assert_episode_binding(rows[0], panel_sha256="a" * 64, backend_identity=backend)
    second = native.assert_episode_binding(
        rows[1], panel_sha256="a" * 64, backend_identity={**backend, "container_id": "fresh-2"})
    assert first["window_id"] != second["window_id"]
    assert first["backend_identity"]["container_id"] != second["backend_identity"]["container_id"]
    with pytest.raises(ValueError, match="independent"):
        native.assert_episode_binding(
            rows[1], panel_sha256="a" * 64,
            backend_identity={**backend, "fresh_initial_state": False})


def test_server_uuid_binding_preserves_real_cuda_mapping():
    from proworksim.software_calibration_runtime_v051 import (
        single_gpu_binding, verify_single_gpu_uuid,
    )
    gpu_uuid = "GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    environment = {"CUDA_VISIBLE_DEVICES": gpu_uuid, "PROWORKSIM_HOST_GPU_DEVICES": "3"}
    binding = single_gpu_binding(environment)
    assert binding["physical_index"] == 3 and binding["uuid"] == gpu_uuid
    verify_single_gpu_uuid(binding, SimpleNamespace(uuid=gpu_uuid))
    assert environment["CUDA_VISIBLE_DEVICES"] == gpu_uuid
    with pytest.raises(ValueError, match="differs"):
        verify_single_gpu_uuid(binding, SimpleNamespace(uuid="GPU-other"))
    for invalid in (
            {"CUDA_VISIBLE_DEVICES": gpu_uuid},
            {"CUDA_VISIBLE_DEVICES": gpu_uuid, "PROWORKSIM_HOST_GPU_DEVICES": "3,4"},
            {"CUDA_VISIBLE_DEVICES": "GPU-aaaa", "PROWORKSIM_HOST_GPU_DEVICES": "3"},
            {"CUDA_VISIBLE_DEVICES": "3,4"}):
        with pytest.raises(ValueError, match="exactly one"):
            single_gpu_binding(invalid)


@pytest.mark.parametrize("drift", ["weight_stat", "manifest", "receipt"])
def test_model_hash_audit_reuse_requires_unchanged_stat_manifest_and_receipt(tmp_path, monkeypatch, drift):
    from proworksim import software_calibration_runtime_v051 as runtime
    model = tmp_path / "model"
    model.mkdir()
    weight = model / "model.safetensors"
    weight.write_bytes(b"small synthetic content, not model weights")
    manifest = model / "manifest.json"
    native.write_new(manifest, {"files": {
        weight.name: {"bytes": weight.stat().st_size, "sha256": native.digest(weight.read_bytes())}}})
    receipt = runtime.prepare_model_source_receipt(
        model, manifest=manifest, output=tmp_path / "audit.json")

    def unexpected_weight_rehash(path):
        raise AssertionError("Verified model weights must not be hashed again per episode")

    monkeypatch.setattr(runtime, "sha_file", unexpected_weight_rehash)
    runtime.verify_model_source(model, manifest, verified_source_receipt=receipt)
    if drift == "weight_stat":
        # Equal bytes still cannot silently refresh a changed identity.
        replacement = model / "replacement"
        replacement.write_bytes(weight.read_bytes())
        replacement.replace(weight)
    elif drift == "manifest":
        manifest.write_bytes(manifest.read_bytes() + b" ")
    else:
        Path(receipt["path"]).write_bytes(Path(receipt["path"]).read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        runtime.verify_model_source(model, manifest, verified_source_receipt=receipt)


def test_preload_resource_wait_never_enters_model_or_environment(tmp_path, monkeypatch):
    from scripts import software_panel_run_v053 as runner
    from proworksim import software_calibration_runtime_v051 as runtime
    from proworksim import software_panel_docker_v053 as docker
    from proworksim import software_panel_resources_v053 as resources
    row = {"slot_id": "queued", "task_id": "fixture", "seed": 123, "repeat_index": 1}
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}")
    monkeypatch.setattr(runner, "validate_plan", lambda *a, **k: (
        {"native_python": sys.executable, "environment_admission_ref": {}}, {"slots": [row]}))
    monkeypatch.setattr(runner, "task_for", lambda *a: {"instance_id": "fixture"})
    monkeypatch.setattr(runner, "validate_task_qualification", lambda *a: {})
    monkeypatch.setattr(resources, "binding_from_environment", lambda: {"gpu_index": 3})

    class ResourceWait(Exception):
        receipt = {"retryable": True, "loader_not_entered": True}

    def unavailable(*args, **kwargs):
        raise ResourceWait()

    def forbidden(*args, **kwargs):
        raise AssertionError("No backend, weights or numerical provider may be entered")

    monkeypatch.setattr(resources, "acquire_startup", unavailable)
    monkeypatch.setattr(resources, "is_preload_resource_wait", lambda error: isinstance(error, ResourceWait))
    monkeypatch.setattr(runtime, "load_actor", forbidden)
    monkeypatch.setattr(docker, "DockerBackend", forbidden)
    monkeypatch.setattr(runner, "provider_accounting", forbidden)
    output = tmp_path / "attempt"
    assert runner.worker(plan_path, "queued", output) == 75
    report = json.loads((output / "report.json").read_bytes())
    assert report["status"] == "resource_wait" and report["loader_not_entered"] is True
    assert report["model_calls"] == 0 and report["known_actual_tokens"] == 0
    assert not (output / "resident").exists() and not (output / "model-entered.json").exists()


@pytest.mark.parametrize("drift", ["backend_config", "task_receipt"])
def test_environment_config_and_own_frozen_receipt_reject_drift_without_hashing_other_tasks(tmp_path, drift):
    from scripts import software_panel_run_v053 as runner
    from proworksim.software_panel_v053 import canonical_bytes
    environment_root = tmp_path / "environment"
    own_path = environment_root / "tasks" / "fixture" / "qualification.json"
    own_ref = native.write_new(own_path, {"admitted": True, "image": "original-image"})
    backend = {"environment_root": str(environment_root), "docker_host": "unix:///frozen"}
    environment = {
        "config_sha256": native.digest(canonical_bytes(backend)),
        "repositories": [{"admitted": True, "qualified_task_ids": ["fixture", "other"],
                          "task_receipts": [own_ref, {
                              "path": str(environment_root / "tasks/other/qualification.json"),
                              "sha256": "a" * 64, "bytes": 999}]}],
    }
    plan = {
        "backend_config": backend,
        "environment_admission_ref": native.write_new(tmp_path / "admission.json", environment),
    }
    panel = {"admission_sha256": native.digest(canonical_bytes(environment))}
    verified = runner.validate_environment_binding(plan, panel)
    # The other receipt deliberately does not exist. Only the selected task is read.
    assert runner.validate_task_qualification(plan, "fixture", environment=verified) == own_ref
    if drift == "backend_config":
        plan["backend_config"] = {**backend, "docker_host": "unix:///changed"}
        with pytest.raises(ValueError, match="backend configuration differs"):
            runner.validate_environment_binding(plan, panel)
    else:
        native.write(own_path, {"admitted": True, "image": "replacement-image"})
        with pytest.raises(ValueError, match="evidence reference changed"):
            runner.validate_task_qualification(plan, "fixture", environment=verified)


class ProgrammedOwner:
    path = "project"
    contract = native.CONTRACT

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.generated = 0
        self.identity = {**IDENTITY, "fixture_only": True}

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def prepare_request(self, request):
        record = native_input()
        record["sha256"] = native.digest(native.json_bytes(request))
        record["rendered_prompt"] = json.dumps(request)
        return record["rendered_prompt"], request["messages"], record

    def generate_native(self, record):
        self.generated += 1
        return {
            **response(record, attempt=str(self.generated), output=1),
            "actor_identity": self.freeze_identity(),
            "raw_generated_text": self.replies.pop(0), "finish_reason": "stop",
        }

    def capture_evaluation_state(self):
        return {}

    def begin_window(self, window):
        self.window = window

    def reseed(self, seed, *, label):
        self.seed = seed

    def finish_evaluation(self, entries, output):
        Path(output).mkdir()

    def finish_evaluation_guard(self, before):
        return {"learning_unchanged": True, "rng_restored_exactly": True}


class FixtureBackend:
    working_dir = "/testbed"

    def __init__(self):
        self.identity = {"task_id": "fixture", "fresh_initial_state": True}
        self.commands = []
        self.exports = 0

    def execute(self, command, *, timeout_seconds):
        self.commands.append(command)
        return {"output": "Executed synthetic command.", "returncode": 0, "exception_info": None}

    def run_public_tests(self):
        self.commands.append(native.PUBLIC_TEST_COMMAND)
        return {"output": "Synthetic test passed.", "returncode": 0, "exception_info": None}

    def export_candidate(self, run_root):
        assert self.exports == 0
        self.exports += 1
        return native.write_new(Path(run_root) / "lock.json", {
            "candidate": "synthetic", "export_count": 1, "selection_after_scoring": False})


def tool(name, **params):
    return "<tool_call><function=" + name + ">" + "".join(
        "<parameter=" + key + ">" + str(value) + "</parameter>" for key, value in params.items()
    ) + "</function></tool_call>"


def sdk_collect(tmp_path, owner, backend, **kwargs):
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    pytest.importorskip("openhands.sdk")
    manifest = native.write_new(tmp_path / "sdk.json", native.sdk_provenance())
    return native.collect_episode(
        owner=owner, row={"slot_id": "v053-fixture-r1", "task_id": "fixture",
                         "seed": 1234, "repeat_index": 1},
        panel_sha256="a" * 64, task={"instance_id": "fixture", "problem_statement": "Fix fixture."},
        backend=backend, reference_runtime=manifest, episode_folder=tmp_path / "episode",
        allow_cpu_fixture=True, **kwargs)


def test_original_sdk_owns_terminal_history_finish_and_single_export(tmp_path):
    backend = FixtureBackend()
    owner = ProgrammedOwner([
        tool("terminal", command="echo should_not_run", is_input="true"),
        tool("terminal", command="echo synthetic"),
        tool("terminal", command=native.PUBLIC_TEST_COMMAND),
        tool("finish", message="Synthetic repair complete."),
    ])
    result = sdk_collect(tmp_path, owner, backend)
    assert result["status"] == "closed" and result["sdk_execution_status"] == "finished"
    assert result["ledger"]["known_actual_tokens"] == 404
    assert result["ledger"]["attempts"] == 4 and result["ledger"]["inflight"] is None
    assert backend.commands == ["echo synthetic", native.PUBLIC_TEST_COMMAND]
    assert backend.exports == 1 and result["candidate_lock"]
    assert result["episode_guard"]["software_binding_unchanged"] is True
    request = json.loads(native.checked(result["ledger"]["calls"][1]["request"]).read_bytes())
    assert any(message["role"] == "tool" for message in request["request"]["messages"])
    assert result["condition"] == native.CONDITION and result["fixture_only"] is True


def test_initial_sdk_capture_has_no_model_tools_export_or_scoring(tmp_path):
    backend, owner = FixtureBackend(), ProgrammedOwner()
    captures = []
    result = sdk_collect(
        tmp_path, owner, backend, initial_capture=lambda request, record: captures.append(record))
    assert result["status"] == "initial_request_captured"
    assert owner.generated == backend.exports == 0 and backend.commands == []
    assert len(captures) == 1 and result["capture_counters"]["native_SDK_LLM_entries"] == 1
