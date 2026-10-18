"""Finite synthetic HOLD bindings only; no business material, SDK or model work."""
import copy

import pytest

from proworksim import software_holdout_measurement_v051 as measure
from proworksim.storage import json_bytes
from scripts import software_holdout_v051 as host


def states():
    return {name: {"checkpoint": {"path": "/CPU/" + name, "sha256": name, "bytes": 1},
        "actor_identity": {"adapter_sha256": "adapter-" + name, "policy_version": "CPU-" + name},
        "historical_steps": [4, 4] if name == "S_star" else [5, 5],
        "state_file_reference_from_original_metadata": {"path": "/CPU/" + name + ".pt", "sha256": name, "bytes": 1}}
        for name in measure.CONDITIONS}


def actor_row(name, registry):
    auth = registry[name]
    return {"heldout_condition": name, "checkpoint_authorization": auth,
        "episode_start_steps": {"actor_steps": auth["historical_steps"][0], "critic_steps": auth["historical_steps"][1]},
        "actor_identity": {"checkpoint": auth["checkpoint"], "source_actor_identity": auth["actor_identity"],
            "retained_state_authorization": auth, "adapter_sha256": auth["actor_identity"]["adapter_sha256"]}}


def metadata():
    rows = []
    names = list(host.CONDITIONS)
    for index, task in enumerate(host.HOLD_IDS):
        order = names[index % 4:] + names[:index % 4]
        for name in order:
            rows.append({"slot_id": f"v051-{task}-{name}", "task_id": task, "condition": name, "partition": "HOLD",
                "seed": 202610170561 + index, "first_member": "member_001" if index % 2 == 0 else "member_002",
                "condition_order_for_task": order, "generation_tokens": 500000, "decisions": 128,
                "attempts": 128, "project_public_tests": 32})
    return {"rows": rows, "states": states()}


def test_condition_to_exact_checkpoint_rejects_B_Q_swap_even_at_identical_five_steps():
    registry = states()
    for name in measure.CONDITIONS:
        assert measure.state_binding(actor_row(name, registry), registry)["heldout_condition"] == name
    wrong = actor_row("Q_plus", registry)
    wrong["heldout_condition"] = "B"
    with pytest.raises(ValueError, match="registry_or_steps"):
        measure.state_binding(wrong, registry)


def test_original_two_member_proof_code_is_unchanged_and_absence_removes_only_its_gap():
    before = measure.original.MEMBERS[:]
    values = measure.namespace(None, states())
    for name in ("assess_records", "lifecycle_history", "audit_projection", "bind_context", "bind_shared_budget", "bind_member_fixed_budget"):
        assert values[name].__code__ is getattr(measure.original, name).__code__
    assert values["MEMBERS"] == measure.original.MEMBERS == before == ["member_001", "member_002"]
    old = {"measurement_gaps": [{"reason": "missing_authorized_initial_diagnostic_contract"}, {"reason": "other_missing_source"}],
           "mechanism_gate_inputs": {"resolved": False}, "episode_closed": True}
    proof = {"initial_diagnostics": {}, "member_assignments": dict.fromkeys(before, [])}
    new = measure.adapt_initial_absence(old, proof)
    assert new["measurement_gaps"] == [{"reason": "other_missing_source"}]
    assert new["mechanism_gate_inputs"]["resolved"] is False
    assert len(old["measurement_gaps"]) == 2
    with pytest.raises(ValueError, match="uniquely_bound"):
        measure.adapt_initial_absence(old, {**proof, "member_assignments": {"member_001": []}})


def test_native_complete_receipts_match_sdk_multiset_and_exact_actual_cost(tmp_path, monkeypatch):
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json_bytes(value))
    folder, calls = tmp_path / "collection", tmp_path / "resident/calls"
    row = {"episode_manifest": str(folder / "episode/manifest.json"), "native_provider_calls_path": str(calls),
        "online_window_id": "holdout-v051:CPU-native-contract", "actor_identity": {"CPU_only": True},
        "usage": {"attempts": 1, "total_tokens": 5}}
    inputs, outputs = {"input_ids": [1, 2]}, [3, 4, 5]
    usage = {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    start = {"attempt_id": "a", "generation_started": True, "online_window_id": row["online_window_id"],
        "actor_identity": row["actor_identity"], "native_input": inputs, "reserved_maximum_tokens": 10}
    save(calls / "a-started.json", start)
    save(calls / "a-prepared.json", {**start, "generation_started": False})
    save(calls / "a-complete.json", {"attempt_id": "a", "actor_identity": row["actor_identity"],
        "input": inputs, "output_ids": outputs, "usage": usage, "path": "project"})
    response = {"body": {"prompt_projection": inputs, "token_trace": {"output_ids": outputs},
        "usage": usage, "actor_identity": row["actor_identity"]}}
    path = folder / "raw-transport/request-00001/response.json"
    save(path, response)
    monkeypatch.setattr(measure, "native_evidence_mode", lambda *a, **k: {
        "mode": "synthetic_contract_only", "formal_model_admission_eligible": False, "actual_model_generations": 0})
    value = measure.native_accounting_binding(row)
    assert value["known_actual_tokens"] == 5 and value["exact_response_multiset_bound"] is True
    assert value["formal_model_admission_eligible"] is False
    changed = copy.deepcopy(response)
    changed["body"]["token_trace"]["output_ids"] = [9]
    save(path, changed)
    with pytest.raises(ValueError, match="accounting_mismatch"):
        measure.native_accounting_binding(row)


def test_F_zero_is_known_only_when_mechanics_are_formal_and_terminal_tree_is_absent():
    row = {"condition": "B", "generation_tokens": 500000}
    result = {"F": 0, "R_joint": 0, "status": "closed", "heldout_condition": "B",
              "submitted": False, "mutable_terminal_working_tree_assessed": False}
    account = {"all_started_settled": True, "integrity_errors": [], "known_actual_tokens": 17}
    guard = {"passed": True}
    episode_guard = {"learning_unchanged": True, "rng_restored_exactly": True}
    mechanical = {"decision": "continue", "fixed_endpoint_binding": {"status": "verified"},
                  "native_accounting": {"formal_model_admission_eligible": True}}
    args = dict(result=result, accounting=account, guard=guard, episode_guard=episode_guard, measurement=mechanical)
    assert host.classify_closed(row, **args)["decision"] == "continue"
    assert host.classify_closed(row, **{**args, "measurement": {**mechanical, "decision": "measurement_pending"}})["decision"] == "global_pause"
    assert host.classify_closed(row, **{**args, "result": {**result, "R_code": 1}})["decision"] == "global_pause"
    registry = states()
    missing = {**actor_row("B", registry), "slot_id": "CPU-missing-original-evidence"}
    pending = measure.measure_slot(missing, provider=None, state_authorizations=registry)
    assert pending["decision"] == "measurement_pending"
    assert pending["stop_assessment"]["unresolved"] and not pending["stop_assessment"]["global_violations"]


def test_frozen_metadata_paths_keep_all32_with_partial_qualification_and_no_budget_transfer(tmp_path):
    root = tmp_path / "CPU-only-inventory"
    root.mkdir()
    def save(name, value):
        path = root / name
        host.write(path, value)
        return host.ref(path)
    fake = root / "source/fake.py"
    fake.parent.mkdir()
    fake.write_text("# synthetic metadata only\n")
    document = metadata()
    rows = host.inventory(document)
    common = {"version": "v051-holdout-common-implementation-freeze-v1", "frozen_before_business_material": True,
              "source_root": str(fake.parent), "source_files": {"fake.py": host.sha_file(fake)}}
    refs = {"inventory": save("inventory.json", document), "common_implementation_freeze": save("common.json", common),
            "source_access_release": save("source-access.json", {"CPU_fixture": True}),
            "resource_policy": save("resources.json", {"CPU_fixture": True})}
    source_ids, qualified = list(host.HOLD_IDS[:6]), list(host.HOLD_IDS[:5])
    source = {"fixture_only": False, "qualified_case_ids": source_ids,
              **{k: refs[k] for k in ("common_implementation_freeze", "source_access_release")}}
    refs["source_qualification"] = save("source.json", source)
    inputs = {"fixture_only": False, "qualified_case_ids": qualified,
              **{k: refs[k] for k in ("common_implementation_freeze", "source_qualification")}}
    refs["initial_inputs"] = save("inputs.json", inputs)
    statuses = [{"task_id": case, "source_status": "qualified" if case in source_ids else "source_blocked",
        "input_status": "qualified" if case in qualified else "input_blocked" if case in source_ids else "not_run_source_blocked",
        "dispatch_eligible": case in qualified, "reason": "synthetic fixture blocker" if case not in qualified else ""}
        for case in host.HOLD_IDS]
    admission = {"version": "v051-holdout-model-admission-v1", "released": True, "purpose": host.PURPOSE,
        "unresolved_blockers": [], "checks": dict.fromkeys(host.CHECKS, True), **refs,
        "resources": {"allowed_gpu_indices": list(range(8)), "max_residents": 4, "idle_only_admission": False},
        "qualified_case_ids": qualified, "task_qualification": statuses}
    _, blocked = host.gate_records(admission, source=source, inputs=inputs, common=common, references=refs)
    plan = host.sealed({"version": host.VERSION, "purpose": host.PURPOSE, "contract": host.CONTRACT,
        "limits": host.LIMITS, "gpu_preference": list(range(8)), "fresh_resident_per_slot": True,
        "worker_module": host.MODULE, "source_root": str(fake.parent), "source_files": common["source_files"],
        "rows": rows, "states": document["states"], "qualified_case_ids": qualified, "blocked_cases": blocked,
        "qualification_states": host.initial_states(rows, qualified), "admission_references": refs,
        "model_admission": save("admission.json", admission), "evidence": [],
        "adapter_manifest": save("adapter.json", {"CPU_fixture": True}),
        "model_manifest": save("model.json", {"CPU_fixture": True})})
    host.write(root / "plan.json", plan)
    loaded = host.frozen(root)
    assert len(loaded["rows"]) == 32 and sum(r["generation_tokens"] for r in loaded["rows"]) == 16000000
    statuses = loaded["qualification_states"].values()
    assert sum(s["status"] == "source_or_input_blocked" for s in statuses) == 12
    assert all(s["attempts"] == [] for s in statuses)
    assert all(host.inventory_state_closed(s) for s in host.initial_states(rows, []).values())
    bound, adaptation = host.supervisor_binding()
    assert adaptation["rebindings"] == {"worker_module": 1, "initial_states": 1, "inventory_terminal": 2}
    assert bound.__globals__["classify_closed"] is host.classify_closed
    assert host.base.classify_closed is not host.classify_closed
