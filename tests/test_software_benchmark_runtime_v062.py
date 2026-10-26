"""New BASE/FIX integration boundaries without Docker, model or service access."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_docker_actor_v062 as actor
from proworksim import software_benchmark_episode_v062 as episode
from proworksim import software_benchmark_sdk_bundle_v062 as bundle
from proworksim import software_benchmark_public_context_v062 as public
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v062_controller", ROOT / "tools/run_ref_controller_v062.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)
spec = importlib.util.spec_from_file_location("v062_worker", ROOT / "tools/run_native_worker_docker_v062.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
PYTHON = "/opt/miniconda3/envs/testbed/bin/python"
CANARY = "HIDDEN_KEY_GOLD_EVAL_MUST_STAY_ON_HOST"


def public_environment():
    return {"kind": "official_image", "image_id": "sha256:" + "a" * 64,
            "source_config_sha256": "a" * 64, "public_python": PYTHON,
            "environment": {"PATH": "/opt/miniconda3/envs/testbed/bin:/usr/bin:/bin",
                            "CONDA_PREFIX": "/opt/miniconda3/envs/testbed",
                            "CONDA_DEFAULT_ENV": "testbed", "HOST_SECRET": CANARY}}


def configuration(tmp_path, arm="BASE5M"):
    budget = 10_000_000 if arm == "FIX10M" else 5_000_000
    condition = {"version": "v056-ref-budget-condition-r1", "condition_id": "REF_B10000K" if arm == "FIX10M" else "REF_B5000K",
        "arm": "REF", "single_agent": True, "training": False,
        "episode_limits": {"input_plus_output_tokens": budget, "all_model_attempts": 512,
                           "agent_decisions": 512, "soft_seconds": 21600, "hard_seconds": 23400},
        "inference": {"total_context": 131072, "maximum_full_input": 98304, "output_limit": 32768,
                      "temperature": .6, "top_p": .95, "top_k": 20, "max_tokens": 32768,
                      "automatic_retries": 0, "chat_template_kwargs": {"enable_thinking": True}}}
    condition_ref = write_new(tmp_path / (arm + "-condition.json"), condition)
    row = {"slot_index": 0, "slot_id": "v062:synthetic:" + arm + ":7", "source_slot_id": "v056:synthetic",
           "instance_id": "synthetic", "repo": "synthetic/repo", "execution_arm": arm,
           "seed": 7, "replicate": 0, "condition_id": condition["condition_id"],
           "generation_token_upper_bound": budget, "measurement_kind": "capability_probe"}
    config = {**row, "configuration": condition_ref,
              "public_task": {"instance_id": "synthetic", "repo": "synthetic/repo",
                              "base_commit": "b" * 40, "problem_statement": "Original public issue",
                              "not_public": CANARY},
              "scorer_request_base": {"gold": CANARY, "eval_script": CANARY},
              "ref_api_key_file": CANARY, "source_configuration": CANARY}
    row["configuration"] = write_new(tmp_path / (arm + "-host.json"), config)
    return row, config


@pytest.mark.parametrize("arm", ["BASE5M", "FIX5M", "FIX10M"])
def test_controller_gets_only_one_public_task_and_arm_specific_public_facts(tmp_path, arm):
    row, config = configuration(tmp_path, arm)
    context = None if arm == "BASE5M" else {"version": public.VERSION, "instance_id": "synthetic",
        "visible_text": "Public facts", "visible_facts": {"python": PYTHON}, "sources": CANARY}
    files = bundle.controller_inputs(config, row, {"type": "ready"},
        {"port": 18171, "deployment_version": "v062-owned-user-ref-resident-r1", "api_key": CANARY},
        "http://127.0.0.1:18171", public_context=context, public_environment=public_environment())
    projected = json.loads(files["controller-config.json"])
    assert CANARY not in json.dumps(projected)
    assert projected["slot_id"] == row["slot_id"]
    assert projected["configuration"]["sha256"] == config["configuration"]["sha256"]
    assert projected["model_identity_value"]["deployment_version"] == "v062-owned-user-ref-resident-r1"
    assert controller.validate_config(projected) is projected
    if arm == "BASE5M":
        assert "public_context" not in projected and "public_environment" not in projected
    else:
        assert set(projected["public_context"]) == {"version", "visible_text", "visible_facts"}
        assert "HOST_SECRET" not in projected["public_environment"]["environment"]


def test_base_cannot_receive_fixed_guidance_or_hidden_controller_keys(tmp_path):
    row, config = configuration(tmp_path)
    with pytest.raises(ValueError, match="BASE"):
        bundle.controller_inputs(config, row, {}, {}, "http://127.0.0.1:18171", public_context={})
    files = bundle.controller_inputs(config, row, {}, {}, "http://127.0.0.1:18171")
    projected = json.loads(files["controller-config.json"])
    with pytest.raises(ValueError, match="fixed layout"):
        controller.validate_config(projected | {"gold_patch": CANARY})
    config["execution_arm"] = "FIX5M"
    with pytest.raises(ValueError, match="exact new"):
        bundle.controller_inputs(config, row, {}, {}, "http://127.0.0.1:18171")


def test_new_row_binding_rejects_swapped_seed_arm_and_old_slot(tmp_path, monkeypatch):
    row, config = configuration(tmp_path)
    other, _ = configuration(tmp_path, "FIX5M")
    other["slot_index"] = 1
    plan = write_new(tmp_path / "plan.json", {"rows": [row, other]})
    monkeypatch.setattr(episode.policy, "require_v062_allowed", lambda *a, **kw: {"plan": plan})
    actual, _, limits = episode._row_and_config(row, False)
    assert actual == config and limits["input_plus_output_tokens"] == 5_000_000
    for changed in ({"seed": 8}, {"execution_arm": "FIX5M"}, {"slot_id": "v056:synthetic"}):
        with pytest.raises(ValueError, match="exact new"):
            episode._row_and_config(row | changed, False)


def test_backup_diagnostic_arm_comes_from_exact_resource_not_index_parity(tmp_path, monkeypatch):
    row, _ = configuration(tmp_path, "BASE5M")
    plan = write_new(tmp_path / "plan.json", {"rows": [row], "resources": {
        "diagnostic-4-actor": {"slot_id": row["slot_id"], "diagnostic": True, "execution_arm": "BASE5M"}}})
    monkeypatch.setattr(episode.policy, "require_v062_allowed", lambda *a, **kw: {"plan": plan})
    called = []
    monkeypatch.setattr(episode, "_run", lambda row, resident, **kw: called.append((row, kw)))
    episode.run_diagnostic(4)
    assert called[0][0]["execution_arm"] == "BASE5M"
    assert called[0][1]["diagnostic_index"] == 4
    with pytest.raises(ValueError, match="grant"):
        episode.run_diagnostic(3)


def test_feedback_subclass_archives_original_before_returning_modified_copy():
    raw = {"type": "observation", "tool": "terminal", "id": 1,
           "observation": {"is_error": True, "exit_code": None,
                           "metadata": {"exit_code": -1, "pid": -1},
                           "content": [{"type": "text", "text": public.MULTI_COMMAND_PREFIX + "(1) pwd\n(2) pwd"}]},
           "llm_content": [{"type": "text", "text": "original"}]}
    class OriginalRPC:
        def __init__(self):
            self.transcript = []
        def request(self, tool, action, *, timeout_seconds=None):
            self.transcript.append({"request": action, "response": raw})
            return raw
    rpc = controller.feedback_rpc_class(OriginalRPC)()
    rpc.public_python, rpc.feedback_events = PYTHON, []
    result = rpc.request("terminal", {"command": "pwd\npwd"})
    assert rpc.transcript[0]["response"] == raw and len(raw["llm_content"]) == 1
    assert result["observation"] == raw["observation"] and len(result["llm_content"]) == 2
    assert rpc.feedback_events[0]["automatic_retry"] is False


def test_actor_keeps_networknone_capdrop_and_exact_new_named_volume():
    ref = {"sha256": "a" * 64}
    claim = {"key": "actor-0", "docker_name": "pws-v062-actor", "spec": {
        "role": "actor", "image_id": "sha256:" + "b" * 64}}
    options = actor.container_options("actor", ref, claim, "pws-v062-volume", [actor.RUNTIME + "/bin/python"])
    assert options["network_mode"] == "none" and options["cap_drop"] == ["ALL"]
    assert options["cap_add"] == [] and options["privileged"] is False
    assert options["mounts"][0]["Type"] == "volume" and "volumes" not in options
    with pytest.raises(ValueError, match="owned Docker"):
        actor.container_options("actor", ref, claim, "pws-v061-old", [actor.RUNTIME + "/bin/python"])


def test_actor_new_implementation_keeps_original_public_interpreter_binding():
    value = {"version": "v062-private-docker-native-worker-r1", "private_roots": list(map(str, worker.PRIVATE_ROOTS)),
             "stdlib": str(worker.STDLIB), "vision_enabled": False, "public_environment": public_environment(),
             "instance_id": "synthetic", "official_task_admitted": True,
             "actor_image_id": public_environment()["image_id"], "baseline_head": "b" * 40,
             "baseline_tree": "c" * 40}
    assert worker.validate_config(value)["public_python"] == PYTHON
    old = copy.deepcopy(value)
    old["version"] = "v061-private-docker-native-worker-r1"
    with pytest.raises(ValueError, match="frozen private"):
        worker.validate_config(old)


def test_preparation_failure_retains_new_identity_without_consuming_docker(tmp_path, monkeypatch):
    row, _ = configuration(tmp_path)
    monkeypatch.setattr(episode, "BATCH", tmp_path)
    monkeypatch.setattr(episode, "_row_and_config", lambda *a: ({}, {}, {}))
    monkeypatch.setattr(episode, "wait_capacity", lambda *a: {"admit": True})
    def fail():
        raise ValueError("runtime unavailable before Docker")
    monkeypatch.setattr(episode.runtime, "prepare_bundle", fail)
    result_ref = episode.run_episode(row, {})
    result = episode.load(result_ref)
    assert result["status"] == "technical_unknown" and result["candidate_lock"] is None
    assert result["slot_id"] == row["slot_id"] and result["measurement_kind"] == "capability_probe"
    assert episode.load(result["quiescence"])["all_owned_objects_removed"] is True
    assert result["failure_scope"] == "global" and result["batch_stop_required"] is True
    assert reference(tmp_path / "episodes/0/result.json") == result_ref


def test_sdk_package_has_explicit_native_allowlist_and_no_scoring_or_host_plan():
    assert set(bundle.CRITICAL_MODULES) <= set(bundle.PROJECT_MODULES)
    forbidden = ("scorer", "grading", "dispatch", "episode_v062", "evaluation", "training")
    assert all(not any(part in name for part in forbidden) for name in bundle.PROJECT_MODULES)
    assert "WorldSpec" not in bundle.PACKAGE_INITIALIZER and "from ." not in bundle.PACKAGE_INITIALIZER
    assert "run_ref_controller_v062.py" in bundle.TOOLS
    assert "run_native_worker_docker_v062.py" in bundle.TOOLS


def test_only_settled_candidate_content_failure_is_local_with_trusted_retained_tree():
    result = {"status": "technical_unknown", "failure_category": "task_candidate_export_rejected",
              "controller_status": "closed", "terminal_capture_after_trusted_closure": True,
              "unscored_terminal_snapshot": {"path": "retained", "sha256": "a" * 64},
              "ledger": {"known_actual_tokens": 123, "complete_actual_tokens": 123,
                         "inflight": None, "uncertain_reserved_tokens": 0}}
    cleanup = {"quiescent": True, "cleanup_errors": [], "create_result_unknown": False,
               "all_owned_objects_removed": True}
    assert episode.classify_failure_scope(result, cleanup) == "local"
    for change in ({"failure_category": "source_integrity"}, {"controller_status": "technical_unknown"},
                   {"unscored_terminal_snapshot": None},
                   {"ledger": result["ledger"] | {"inflight": {"request": 1}}},
                   {"ledger": result["ledger"] | {"complete_actual_tokens": None}}):
        assert episode.classify_failure_scope(result | change, cleanup) == "global"
    assert episode.classify_failure_scope(result, cleanup | {"create_result_unknown": True}) == "global"
