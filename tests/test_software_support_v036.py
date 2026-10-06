"""New Gamma/purpose/export bindings only; no P3 execution or real-model work."""
import copy
import os
from pathlib import Path

import pytest

from proworksim.software_collaboration_v036 import (
    PUBLIC_FEEDBACK_VERSION, case_spec, member_test_specification,
)
from proworksim.software_mapper_v036 import mapping_spec
from proworksim.software_runtime_v036 import window_spec
from proworksim.software_training_v036 import source_training_admission
from proworksim.storage import atomic_write, digest, json_bytes, read_json
from scripts.software_support_v036 import (
    CONFIRMATION_SEEDS, DEVELOPMENT_SEEDS, inventories,
)


def gamma(usage, mode):
    return {"source_usage": usage, "collection_mode": mode,
        "optimizer_update_allowed": usage == "policy_training",
        "gamma_version": "software-information-v0.36",
        "public_test_feedback_version": PUBLIC_FEEDBACK_VERSION,
        "member_test_specification": member_test_specification(),
        "mapper_specification": mapping_spec()}


def test_fixed_sixteen_new_seeds_and_four_root_paired_panels():
    rows = inventories()
    assert {key: len(value) for key, value in rows.items()} == {
        "support": 16, "development": 16, "confirmation": 16}
    assert [r["sampling_seed"] for r in rows["support"]] == list(range(202610070101, 202610070117))
    assert {(r["case_id"], r["first_member"]) for r in rows["support"]} == {("sp-script-inventory-v035", "member_a")}
    for name, seeds in (("development", DEVELOPMENT_SEEDS), ("confirmation", CONFIRMATION_SEEDS)):
        assert len(seeds) == 4 and len({r["case_id"] for r in rows[name]}) == 4
        for seed in seeds:
            chosen = [r for r in rows[name] if r["sampling_seed"] == seed]
            assert len(chosen) == 4 and len({r["case_id"] for r in chosen}) == 4
        assert all(r["first_member"] == "member_a" for r in rows[name])
    for name, usage, mode in (("support", "policy_training", "current_policy_collection"),
        ("development", "contribution_development", "frozen_development"),
        ("confirmation", "independent_confirmation", "frozen_evaluation")):
        spec = window_spec("cpu-fixed-" + name, rows[name], usage)
        assert spec["mode"] == mode and spec["budget"]["max_slots"] == 16
        for row in rows[name][0:4]:
            case = case_spec(row["case_id"])
            scope = source_training_admission(case, gamma(usage, mode))
            assert scope["training_eligible"] is (name == "support")
            assert scope["method_mapper_spec_sha256"] == digest(json_bytes(mapping_spec()))
        case = case_spec(rows[name][0]["case_id"])
        for change in ({"gamma_version": "software-information-v0.35"},
                       {"member_test_specification": {"legacy": True}},
                       {"mapper_specification": {"legacy": True}}):
            with pytest.raises(ValueError, match="relabeled"):
                source_training_admission(case, {**gamma(usage, mode), **change})
        if name != "support":
            with pytest.raises(ValueError):
                window_spec("wrong-purpose", rows[name], "policy_training")
            with pytest.raises(ValueError, match="relabeled"):
                source_training_admission(case, {**gamma(usage, mode), "optimizer_update_allowed": True})
    mixed = copy.deepcopy(rows["support"])
    mixed[-1]["first_member"] = "member_b"
    with pytest.raises(ValueError, match="exact root"):
        window_spec("mixed", mixed, "policy_training")


def test_actual_collector_exports_new_gamma_and_purpose_without_update(tmp_path):
    pytest.importorskip("openhands.sdk")
    torch = pytest.importorskip("torch")
    from proworksim.software_context_v034 import SoftwareContextTransport
    from proworksim.software_runtime_v036 import collect_software_window
    from proworksim.team_rollout import optimizer_scope_allows_update
    from test_software_v033 import ScriptedCPUOwner

    assert not torch.cuda.is_initialized()
    root = Path(os.environ.get("PROWORKSIM_V036_INTEGRATION_RUN", str(tmp_path))) / "collector"
    rows, proofs = inventories(), []
    for name, usage in (("support", "policy_training"), ("development", "contribution_development"),
                        ("confirmation", "independent_confirmation")):
        folder = root / name
        owner = ScriptedCPUOwner(folder / "unused-old-context")
        owner.window_id = "explicit-v036-scripted-cpu-" + name
        owner.facade.transport = SoftwareContextTransport(owner, folder / "slot-0/raw-transport/context-projections")
        # One retained training root and one added root for each later source purpose.
        chosen = rows[name][:1] if name == "support" else rows[name][2:3]
        entries = collect_software_window(owner.facade, window_spec(owner.window_id, chosen, usage), folder)
        assert len(entries) == 1 and len(owner.requests) == 2 and owner.device == "cpu"
        entry = entries[0]
        assert entry["reward"]["eligible"] is True and entry["reward"]["reward"] == 0
        assert entry["training_eligible"] is (name == "support")
        assert optimizer_scope_allows_update(entry["rollout"]) is (name == "support")
        assert entry["rollout"]["online_scope"]["method_mapper_spec_sha256"] == digest(json_bytes(mapping_spec()))
        assert entry["mapping"]["status"] == "unmapped"
        assert entry["mapping"]["collection_mapper_binding_matches"] is True
        assert entry["mapping"]["composition_support_eligible"] is False
        assert entry["rollout"]["work_validity"]["components"]["record"]["value"] is True
        declaration = read_json(folder / "declaration.json")
        for key, value in gamma(usage, window_spec(owner.window_id, chosen, usage)["mode"]).items():
            assert declaration["gamma_identity"][key] == value
        evidence = read_json(folder / "slot-0/software-evidence.json")
        assert evidence["binding_matches_views"] is True
        assert all(view["own_action_tokens"] == 1 for view in evidence["member_views"].values())
        responses = [event["payload"]["response"] for event in entry["rollout"]["events"]
                     if event["kind"] == "model_response"]
        assert len(responses) == 2 and all(r["token_trace"]["output_ids"] == [7] for r in responses)
        assert read_json(folder / "summary.json")["optimizer_updates_executed_during_collection"] == 0
        guard = read_json(folder / "slot-0/evaluation-guard.json")
        assert guard["learning_unchanged"] is guard["rng_restored_exactly"] is True
        proofs.append({"source_purpose": usage, "case_id": chosen[0]["case_id"], "R": 0,
            "synthetic_responses": 2, "own_output_tokens": 2, "record_validity": True,
            "mapping_status": "unmapped", "collection_mapper_binding_matches": True,
            "composition_support_eligible": False, "optimizer_updates": 0})
    assert not torch.cuda.is_initialized()
    atomic_write(root / "proof.json", json_bytes({"passed": True, "target_model_calls": 0,
        "scripted_cpu_responses": 6, "execution_device": "cpu", "gpu_model_execution": False,
        "cuda_initialized_before": False, "cuda_initialized_after": False,
        "gpu_resource_telemetry_measured": False, "optimizer_updates": 0, "windows": proofs,
        "scope": "Actual SDK/archive/exporter/Mapper glue with explicit synthetic staff_done responses. No model is constructed or sampled; no source solution or support episode is supplied to a real policy."}))
