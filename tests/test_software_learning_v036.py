"""Tiny CPU original-token consumption under v036 Gamma; one shared B update only."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from proworksim.experience_allocation_v035 import allocation_gate, bind_candidate, freeze_allocation_plan
from proworksim.online_support import declare_window
from proworksim.software_context_v034 import SoftwareContextTransport
from proworksim.software_collaboration_v036 import PUBLIC_FEEDBACK_VERSION, member_test_specification
from proworksim.software_mapper_v036 import CLASS_ORDER, MAPPER, mapping_spec
from proworksim.software_learning_v036 import (
    MEMBERS, migrate_software_owner, update_software_window, validate_training_entries,
)
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.team_rollout import work_validity
from test_software_learning_v029 import _owner


def tiny_window(owner, directory):
    identity = owner.begin_window("v036-tiny-real-current-window")
    policies = {member: {"implementation": "proworksim.model_policy.ModelPolicy", "config": {
        "weight_identity": identity, "model_revision": identity["policy_version"]}} for member in MEMBERS}
    declaration = declare_window(owner.window_id, actor_identity=identity,
        gamma_identity={"explicit_tiny_CPU_control": True, "source_usage": "policy_training",
            "collection_mode": "current_policy_collection", "optimizer_update_allowed": True,
            "presentation_version": "software-context-v0.34",
            "gamma_version": "software-information-v0.36",
            "public_test_feedback_version": PUBLIC_FEEDBACK_VERSION,
            "member_test_specification": member_test_specification(), "mapper_specification": mapping_spec()}, min_class_count=2,
        slot_specs=[{"slot_id": str(i), "xi_id": "tiny-single-root::first=member_a",
                     "xi_fingerprint": digest(b"same CPU fixture state"), "active_members": list(MEMBERS),
                     "policies": policies, "mapping_spec_id": MAPPER} for i in range(16)])
    transport = SoftwareContextTransport(owner, directory / "contexts")
    payload = {"observation": {"contract": "A public contract", "root_goal": {"description": "A public contract"},
                               "current": "same actor-visible state"}}
    request = {"messages": [{"role": "user", "content": json.dumps(payload)},
                             {"role": "user", "content": json.dumps(payload)}],
               "model": "tiny", "temperature": 0.7, "max_tokens": 2}
    entries, records = [], []
    for i, slot in enumerate(declaration["slots"]):
        events = []
        def event(member, kind, value):
            events.append({"sequence": len(events), "worker_id": member, "kind": kind, "payload": value})
        for member in MEMBERS:
            call = slot["slot_id"] + "-" + member
            response = transport.complete(request, timeout_seconds=5)
            assert response["http_status"] == 200
            event(member, "public_observation", {})
            event(member, "model_call", {"stage": "started", "call_id": call,
                "request_sha256": digest(json_bytes(request))})
            event(member, "model_attempt", {"stage": "finished", "status": "success", "call_id": call,
                "request": copy.deepcopy(request), "response": response})
            event(member, "model_response", {"call_id": call, "response": response["body"]})
        failed = i == 14
        reward = {"eligible": True, "reward": 0.0 if failed else 1.0,
                  "episode_id": "tiny-episode-" + str(i), "manifest_sha256": "tiny-manifest-" + str(i)}
        rollout = {"rollout_id": reward["episode_id"], "manifest_sha256": reward["manifest_sha256"],
            "window": slot["window"], "members": {member: {"origin": "target_model"} for member in MEMBERS},
            "manifest": {"policies": policies}, "events": events, "reward_eligibility": reward,
            "online_scope": {"purpose": "policy_training", "source_training_admission": True,
                             "optimizer_update_allowed": True, "composition_reconfiguration_eligible": True,
                             "method_mapper_spec_sha256": digest(json_bytes(mapping_spec()))},
            "work_validity": work_validity([{"dimension": dimension,
                "value": not failed or dimension == "record", "evidence": {"explicit_cpu_fixture": True}}
                for dimension in ("record", "permission", "basis", "delivery")], spec_id="tiny-cpu")}
        category = CLASS_ORDER[0] if i < 7 else CLASS_ORDER[1] if i < 14 else None
        mapping = {"rollout_id": rollout["rollout_id"], "spec_id": slot["mapping_spec_id"],
                   "status": "mapped" if category else "unmapped", "class_id": category}
        entries.append({"slot_id": str(i), "active_members": list(MEMBERS), "rollout": rollout,
                        "reward": reward, "mapping": mapping, "training_eligible": True})
        records.append({"slot_id": str(i), "status": "closed", "rollout": rollout, "mapping": mapping})
    return entries, declaration, records


def test_tiny_cpu_original_tokens_fixed_denominator_and_v036_update(tmp_path):
    try:
        import torch
    except ModuleNotFoundError:
        project = Path(__file__).resolve().parents[1]
        interpreter = project / ".train-venv/bin/python"
        code = ("import sys; sys.path.extend(" + repr([p for p in sys.path if "site-packages" in p])
                + "); import pytest; raise SystemExit(pytest.main(" + repr([
                    str(Path(__file__).resolve()) + "::test_tiny_cpu_original_tokens_fixed_denominator_and_v036_update",
                    "-q", "--basetemp=" + str(tmp_path / "torch-control")]) + "))")
        result = subprocess.run([str(interpreter), "-c", code], cwd=project,
                                text=True, capture_output=True, timeout=120,
                                env={**os.environ, "CUDA_VISIBLE_DEVICES": ""})
        assert result.returncode == 0, result.stdout + result.stderr
        return
    assert not torch.cuda.is_initialized()
    tmp_path = Path(os.environ.get("PROWORKSIM_V036_INTEGRATION_RUN", str(tmp_path))) / "tiny-learning"
    tmp_path.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(36)
    owner = _owner(tmp_path, torch)
    assert owner.device == "cpu"
    owner.recipe["max_length"] = 512
    migrate_software_owner(owner, expected_steps=(0, 0))
    entries, declaration, records = tiny_window(owner, tmp_path)
    proof = validate_training_entries(owner, entries, declaration, request_evidence_root=tmp_path / "contexts")
    assert proof["original_slot_count"] == 16 and proof["admitted_decisions"] == 32
    assert proof["admitted_own_output_tokens"] == 64
    assert {row["actor_denominator"] for row in proof["rows"]} == {64}
    assert {row["critic_denominator"] for row in proof["rows"]} == {32}
    assert all(row["duplicate_values_removed"] == 3 for row in proof["rows"])
    folder = tmp_path / "contexts/request-00001"
    original = read_json(folder / "original-request.json")
    selected = read_json(folder / "selected-request.json")
    assert any(message not in original["messages"] for message in selected["messages"])
    assert any(row["slot_id"] == "14" for row in proof["rows"])  # The trusted R=0 target remains.
    assert any(row["slot_id"] == "15" for row in proof["rows"])  # Unmapped remains baseline.
    tampered = copy.deepcopy(entries)
    tampered[0]["rollout"]["online_scope"]["optimizer_update_allowed"] = False
    with pytest.raises(ValueError, match="purpose-isolated"):
        validate_training_entries(owner, tampered, declaration, request_evidence_root=tmp_path / "contexts")
    changed_mapper = copy.deepcopy(entries)
    changed_mapper[0]["rollout"]["online_scope"]["method_mapper_spec_sha256"] = digest(b"old-shadow-spec")
    with pytest.raises(ValueError, match="purpose-isolated"):
        validate_training_entries(owner, changed_mapper, declaration, request_evidence_root=tmp_path / "contexts")
    changed = copy.deepcopy(declaration)
    changed["gamma_identity"]["gamma_version"] = "software-information-v0.35"
    with pytest.raises(ValueError, match="purpose-isolated"):
        validate_training_entries(owner, entries, changed, request_evidence_root=tmp_path / "contexts")
    gate = allocation_gate(entries, declaration, records)
    development = {"purpose": "contribution_development", "split_manifest_sha256": digest(b"fresh split"),
        "initial_state_sha256": digest(b"common"), "training_rng_sha256": digest(b"rng"),
        "units": [{"unit_id": f"dev-{seed}-{root}", "root_id": "dev-" + str(root), "seed": seed, "weight": 1.0}
                  for seed in range(202610070201, 202610070205) for root in range(4)],
        "independent_units": [{"unit_id": f"test-{seed}-{root}", "root_id": "test-" + str(root), "seed": seed, "weight": 1.0}
                              for seed in range(202610070301, 202610070305) for root in range(4)],
        "provenance": "synthetic_cpu_control"}
    allocation = freeze_allocation_plan(gate["supports_by_xi"], eligible_blocks=gate["eligible_blocks"],
        development=development, budget={"max_unique_trial_updates": 33, "max_development_episodes": 528,
            "formal_updates_per_method": 1, "independent_episodes_per_method": 16})
    composition = bind_candidate(entries, declaration, records, allocation, "B")
    report = update_software_window(owner, entries, tmp_path / "shared-B", declaration=declaration,
        request_evidence_root=tmp_path / "contexts", composition=composition)
    assert report["status"] == "updated" and report["behavior_probability_passed"] is True
    assert report["backward_decisions_completed"] == 32
    assert report["actor_optimizer_steps"] == report["critic_optimizer_steps"] == 1
    consumption = read_json(tmp_path / "shared-B/composition-admission.json")
    assert consumption["version"] == "experience-allocation-v0.35-log-n-bound"
    assert consumption["Q_equals_B"] is True
    assert len(consumption["rows"]) == 32
    assert all(row["weight"] == 1 and row["actor_denominator"] == 64 for row in consumption["rows"])
    losses = read_json(tmp_path / "shared-B/losses.json")
    assert {row["slot_id"] for row in losses} == {str(i) for i in range(16)}
    assert read_json(tmp_path / "shared-B/software-consumption.json")["actual_material"]["admitted_own_output_tokens"] == 64

    assert not torch.cuda.is_initialized()
    atomic_write(tmp_path / "proof.json", json_bytes({"passed": True, "target_model_calls": 0,
        "synthetic_tiny_cpu_model_calls": 32, "execution_device": "cpu", "gpu_model_execution": False,
        "cuda_initialized_before": False, "cuda_initialized_after": False, "gpu_resource_telemetry_measured": False,
        "original_slots": 16, "admitted_decisions": 32, "own_output_tokens": 64,
        "actor_denominator": 64, "critic_denominator": 32, "R0_slot_retained": True,
        "unmapped_slot_retained": True, "old_Gamma_rejected": True, "changed_mapper_scope_seal_rejected": True,
        "development_units_frozen": 16, "independent_units_frozen": 16,
        "behavior_probability_recomputation_passed": True, "backward_decisions_completed": 32,
        "actor_updates": 1, "critic_updates": 1, "composition": "B", "all_original_slot_losses_retained": True,
        "scope": "One tiny synthetic CPU actor/critic update on all original own-token material under new Gamma and inherited allocation routing. No 9B qualification, real source solution, contribution feedback, independent model result or allocation benefit is claimed."}))
