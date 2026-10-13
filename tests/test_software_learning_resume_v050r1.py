"""Finite CPU controls for preserving the original v050 first slot and inventory."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import software_learning_resume_v050r1 as host
from scripts import software_learning_resume_supervisor_v050r1 as supervisor
from scripts import software_learning_resume_reporting_v050r1 as reporting
from scripts.run_ne_v021 import reference, write


def original_fixture(tmp_path):
    root = tmp_path / "original"
    design = json.loads(host.DESIGN.read_text())
    source, actor = {"code_commit": "old", "code_dirty": False}, {"policy": "same4"}
    checkpoint = {"actor_identity": actor, "actor_steps": 4, "critic_steps": 4, "state_tensor_digest": "same-state"}
    write(tmp_path / "checkpoint.json", checkpoint)
    checkpoint_ref = reference(tmp_path / "checkpoint.json")
    star = {**checkpoint, "checkpoint_ref": checkpoint_ref}
    declaration = {"actor_identity": actor, "window_id": "v050-o1-learning-window-01",
        "gamma_identity": {"s_star": star}, "slots": [{"slot_id": u["slot_id"]} for u in design["training_slots"]]}
    parent = host.seal({"version": host.original.VERSION, "source": source, "source_files": {},
        "workers": list(host.WORKERS), "limits": host.LIMITS, "gpu_preference": list(host.GPU_ORDER),
        "inventory": design, "s_star_checkpoint": checkpoint_ref, "prior_artifact_roots": []}, "plan_sha256")
    write(root / "plan.json", parent)
    write(root / "declaration.json", declaration)
    write(root / "s_star.json", star)
    write(root / "precollection-binding.json", host.seal({"declaration": reference(root / "declaration.json"),
        "s_star": reference(root / "s_star.json")}))
    states = {name: {"status": "stopped", "attempted": False, "elapsed_gpu_seconds": 0} for name in host.WORKERS}
    for name, seconds in (("s_star", 50), ("collect-0", 380)):
        states[name].update(status="complete" if name == "s_star" else "stopped", attempted=True,
            exit_code=0 if name == "s_star" else 1, ended_at=100, elapsed_gpu_seconds=seconds, pid=99999999)
        write(root / name / "actual/report.json", {"status": "complete" if name == "s_star" else "execution_error",
            "success_boundary": name == "s_star", "source_before": source, "source_after": source,
            "new_actor_steps": 0, "new_critic_steps": 0, "actor_steps": 4, "critic_steps": 4,
            "error": None if name == "s_star" else {"type": "ValueError", "message": "Original v049 export evidence seal differs"}})
    write(root / "collect-0/actual/loaded-state.json", {"branch": "S_star", "restored": checkpoint,
        "actor_identity": actor, "actor_steps": 4, "critic_steps": 4})
    write(root / "supervisor.json", {"status": "closed_with_unknowns", "ended_at": 100,
        "source": source, "states": states})
    unit = design["training_slots"][0]
    folder = root / "collect-0/actual/episodes" / host.FIRST_SLOT
    usage = {"decisions": 14, "attempts": 14, "prompt_tokens": 183551, "completion_tokens": 3944,
        "total_tokens": 187495, "budget_charged_tokens": 187495, "uncertain_usage_attempts": 0}
    row = {**unit, "version": "software-organization-runtime-v0.50", "status": "closed", "R": 0,
        "R_joint": 0, "Q_joint": 10 / 12, "condition": "O1", "training_eligible": True,
        "online_window_id": declaration["window_id"], "actor_identity": actor,
        "episode_manifest": str(folder / "episode/manifest.json"),
        "actor_updates": 0, "critic_updates": 0, "new_backward_calls": 0, "usage": usage,
        "team_budget": {"tests": {"used": 3}, "model": {"held_tokens": 0, "integrity_failure": None,
            "charged_tokens": 187495, "records": {str(i): {"status": "settled"} for i in range(14)}}},
        "deadline_receipt": {"dispatches": {str(i): {"status": "returned"} for i in range(14)},
            "all_dispatched_attempts_settled": True, "unique_final_acceptance": True,
            "closed_before_hard_deadline": True, "final_assessment_calls": 1}}
    write(folder / "slot-result.json", row)
    write(folder / "episode/manifest.json", {"status": "closed", "source_start": source, "source_end": source,
        "scenario": {"variation": {"organization_runtime": {"slot_id": host.FIRST_SLOT,
            "actor_identity": actor, "version": "software-organization-runtime-v0.50"}}}})
    write(folder / "mechanical-measurement.json", {"decision": "continue"})
    write(folder / "evaluation-guard.json", dict.fromkeys(("learning_unchanged", "rng_restored_exactly",
        "software_binding_unchanged", "actor_identity_unchanged"), True))
    return root


def derive(root):
    return host.derive_inventory(root, check_processes=False)


def test_closed_R0_retained_and_no_budget_transfer(tmp_path):
    old = original_fixture(tmp_path)
    result = derive(old)
    assert result["retained_slots"][0]["original_formal_R"] == 0
    assert len(result["remaining_training_units"]) == 23
    assert result["retained_actual_cost"]["worker_gpu_seconds_including_original_S_star"] == 430
    caps = host.budget_caps(result)
    assert caps["old_unspent_tokens_not_transferred"] == 312505
    assert caps["including_retained_actual_tokens_upper"] == 27687495
    assert caps["including_retained_actual_decisions_upper"] == caps["including_retained_actual_attempts_upper"] == 7054
    assert caps["including_retained_actual_tests_upper"] == 1763


@pytest.mark.parametrize("mutation", ["extra_worker", "prepared_slot", "different_fault", "changed_Sstar", "unsettled", "guard_failed"])
def test_unclosed_or_changed_original_material_rejects_resume(tmp_path, mutation):
    root = original_fixture(tmp_path)
    folder = root / "collect-0/actual/episodes" / host.FIRST_SLOT
    if mutation == "extra_worker":
        path = root / "supervisor.json"
        data = json.loads(path.read_text())
        data["states"]["collect-1"]["attempted"] = True
    elif mutation == "prepared_slot":
        (folder.parent / "org50-train-LA-r04").mkdir()
        path, data = None, None
    elif mutation == "different_fault":
        path = root / "collect-0/actual/report.json"
        data = json.loads(path.read_text())
        data["error"]["message"] = "signal 15"
    elif mutation == "changed_Sstar":
        path = root / "collect-0/actual/loaded-state.json"
        data = json.loads(path.read_text())
        data["actor_steps"] = 3
    elif mutation == "unsettled":
        path = folder / "slot-result.json"
        data = json.loads(path.read_text())
        data["team_budget"]["model"]["records"]["13"]["status"] = "reserved"
    else:
        path = folder / "evaluation-guard.json"
        data = json.loads(path.read_text())
        data["rng_restored_exactly"] = False
    if path is not None:
        write(path, data)
    with pytest.raises(ValueError):
        derive(root)


def test_original_shard_order_and_full_scientific_inventory_are_preserved(tmp_path):
    root = original_fixture(tmp_path)
    plan = json.loads((root / "plan.json").read_text())
    plan.update(original_root=str(root), resume_inventory=derive(root))
    observed = [host.worker_units(plan, name) for name in host.COLLECTION]
    assert list(map(len, observed)) == [7, 8, 8]
    assert {u["slot_id"] for group in observed for u in group} == {u["slot_id"] for u in plan["inventory"]["training_slots"][1:]}
    assert [u["slot_id"] for u in observed[0]] == plan["inventory"]["collection_shards"]["collect-0"][1:]
    assert len(reporting.inventory(plan)) == 56
    states = supervisor.initial_states(plan)
    assert states["s_star"]["attempted"] is False
    assert states["s_star"]["elapsed_gpu_seconds"] == 0
    assert supervisor.eligible_workers(states) == list(host.COLLECTION)
    for name in host.COLLECTION:
        states[name].update(status="complete", attempted=True)
    assert supervisor.eligible_workers(states) == []
    assert supervisor.eligible_workers(states, {"run_B50": True}) == ["update-B"]
    supervisor.apply_support_gate(states, {"run_B50": False})
    assert all(states[n]["status"] == "not_applicable" for n in (*host.UPDATES, *host.DEVELOPMENT))


def materialized_fixture(tmp_path):
    old = original_fixture(tmp_path)
    root = tmp_path / "resume"
    plan = json.loads((old / "plan.json").read_text())
    plan.update(original_root=str(old), resume_inventory=derive(old))
    path = root / "retained" / host.FIRST_SLOT / "training-entry.json"
    first_folder = Path(plan["resume_inventory"]["retained_slots"][0]["episode_folder"])
    write(path, {"slot_id": host.FIRST_SLOT, "rollout": {"episode_path": str(first_folder / "episode")}})
    plan["retained_export"] = {"training-entry.json": reference(path)}
    for worker in host.COLLECTION:
        entries = []
        for unit in host.worker_units(plan, worker):
            folder = root / worker / "actual/episodes" / unit["slot_id"]
            entry = {"slot_id": unit["slot_id"], "rollout": {"episode_path": str(folder / "episode")}}
            for name, value in (("training-entry.json", entry), ("slot-result.json", {"slot_id": unit["slot_id"]}),
                                ("episode/manifest.json", {"fixture": True})):
                write(folder / name, value)
            entries.append(entry)
        write(root / worker / "actual/entries.json", entries)
    return root, plan


def test_registry_materializes_exact_original_first_plus23_in_full_order(tmp_path):
    root, plan = materialized_fixture(tmp_path)
    entries, sources = host.materialize_entries(plan, root)
    assert len(entries) == len(sources) == 24
    assert [e["slot_id"] for e in entries] == [u["slot_id"] for u in plan["inventory"]["training_slots"]]
    assert sources[0]["source_result"]["path"].startswith(plan["original_root"])
    assert all(str(root) in s["source_result"]["path"] for s in sources[1:])


@pytest.mark.parametrize("mutation", ["replay_first", "missing", "same_episode", "modified_export"])
def test_duplicate_missing_or_substituted_material_cannot_enter_training(tmp_path, mutation):
    root, plan = materialized_fixture(tmp_path)
    shard = root / "collect-0/actual/entries.json"
    rows = json.loads(shard.read_text())
    if mutation == "replay_first":
        rows.insert(0, json.loads(Path(plan["retained_export"]["training-entry.json"]["path"]).read_text()))
    elif mutation == "missing":
        rows.pop()
    elif mutation == "same_episode":
        rows[0]["rollout"]["episode_path"] = rows[1]["rollout"]["episode_path"]
        write(root / "collect-0/actual/episodes" / rows[0]["slot_id"] / "training-entry.json", rows[0])
    else:
        rows[0]["extra"] = "mutation"
    write(shard, rows)
    with pytest.raises(ValueError):
        host.materialize_entries(plan, root)


def test_private_host_adapters_only_change_declared_imports_and_globals():
    collect = host.private_adapter(host.original._collect, import_modules={
        "proworksim.software_training_v050": "proworksim.software_training_v050r1"})
    update = host.private_adapter(host.original._update, import_modules={
        "proworksim.software_learning_v050": "proworksim.software_learning_v050r1"})
    worker = host.private_adapter(host.original.run_worker)
    assert "proworksim.software_training_v050r1" in collect.__code__.co_names
    assert "proworksim.software_learning_v050r1" in update.__code__.co_names
    assert worker.__code__ is host.original.run_worker.__code__
    assert worker.__globals__["original"] is host.original.original
    assert worker.__globals__["_collect"] is host._collect
    assert host.original.run_worker.__globals__["frozen"] is host.original.frozen
    with pytest.raises(ValueError):
        host.private_adapter(host.original._collect, import_modules={"not.a.dependency": "anything"})
    with pytest.raises(ValueError, match="never dispatched"):
        host.run_worker("unused", "s_star", "unused")


def test_real_launch_command_is_recorded_and_original_supervisor_unchanged(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(supervisor.previous.subprocess, "Popen", lambda argv, **kw: calls.append(copy.deepcopy(argv)))
    monkeypatch.setattr(supervisor, "code_identity", lambda: {"fixture": True})
    argv = ["python", "-m", "scripts.software_learning_v050", "worker", "--worker", "collect-0",
        "--output", str(tmp_path / "collect-0/actual")]
    supervisor.launch(argv, env={"CUDA_VISIBLE_DEVICES": "4"})
    receipt = json.loads((tmp_path / "collect-0/worker-launch.json").read_text())
    assert calls == [receipt["actual_command"]] == [argv]
    assert argv[2] == host.MODULE
    assert receipt["requested_command"][2] == "scripts.software_learning_v050"
    contract = supervisor.contract()
    assert contract["original_supervisor_code_object_identical"] is True
    assert contract["original_supervisor_globals_unchanged"] is True
    assert contract["gpu_preference"] == list(range(8))
    assert contract["limits"]["minimum_free_gpu_mib"] == 57344


def test_private_worker_reaches_new_collector_without_loading_GPU(tmp_path, monkeypatch):
    output = tmp_path / "collect-0/actual"
    source = {"fixture": True}
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    write(tmp_path / "supervisor.json", {"states": {"collect-0": {"status": "running", "attempted": True}}})
    owner = SimpleNamespace(actor_steps=4, critic_steps=4, _make_identity=lambda: {"actor": 4})
    inherited = SimpleNamespace(validate_worker_interpreter=lambda unused: None)
    adapter = host.private_adapter(host.original.run_worker, dependencies={
        "frozen": lambda unused: {}, "code_identity": lambda: source,
        "_load_owner": lambda *a: owner, "_collect": lambda *a: {"status": "complete", "rows": []}})
    # Keep the exact original.run_worker code while replacing the sole interpreter guard for this CPU fixture.
    adapter.__globals__["original"] = SimpleNamespace(inherited=inherited)
    result = adapter(tmp_path, "collect-0", output)
    assert result["status"] == "complete" and result["actor_steps"] == 4
    assert result["new_actor_steps"] == result["new_critic_steps"] == 0


def test_reporter_counts_original_worker_seconds_once(tmp_path):
    old = original_fixture(tmp_path)
    states = json.loads((old / "supervisor.json").read_text())["states"]
    new = {name: {"status": "not_applicable", "attempted": False, "elapsed_gpu_seconds": 0} for name in host.WORKERS}
    new["s_star"].update(status="complete", original_complete_state_reused=True)
    new["collect-0"].update(status="complete", attempted=True, elapsed_gpu_seconds=10)
    result = reporting.merged_costs(states, new)
    assert result["complete_worker_seconds"] == 440
    assert result["original_phase"]["complete_worker_seconds"] == 430
    assert result["original_S_star_and_collector_counted_once"] is True


def retained_export_fixture(root, derived):
    retained = derived["retained_slots"][0]
    folder = Path(retained["episode_folder"])
    exported = root.parent / "cpu-original-first"
    entry = {"slot_id": host.FIRST_SLOT, "rollout": {"episode_path": str(folder / "episode"),
        "manifest_sha256": retained["source_manifest"]["sha256"]}}
    receipt = {"slot_id": host.FIRST_SLOT, "source_folder": str(folder),
        "declaration_sha256": derived["original_declaration"]["sha256"],
        "formal_R": 0, "reported_original_usage": retained["actual_usage"],
        "source_files_unchanged": {"source": True}, "original_observation_target_reward_invariants": {},
        "old_entry_json_effect_equal": None,
        **dict.fromkeys(("new_model_calls", "new_tokenizer_calls", "new_gpu_calls",
            "new_business_tests_or_acceptances", "new_world_actions"), 0)}
    for name, value in (("training-entry.json", entry), ("training-export.json", {"fixture": True}),
                        ("rematerialization-receipt.json", receipt)):
        write(exported / name, value)
    return {name: reference(exported / name) for name in
        ("training-entry.json", "training-export.json", "rematerialization-receipt.json")}


def test_prepare_reuses_unique_CPU_export_and_original_declaration_bytes(tmp_path, monkeypatch):
    old = original_fixture(tmp_path)
    derived = derive(old)
    refs = retained_export_fixture(old, derived)
    controls = tmp_path / "controls.json"
    write(controls, host.seal({"passed": True, "new_model_calls": 0, "new_gpu_workers": 0,
        "new_backward_calls": 0, "original_first_rematerialized": refs}))
    protocol = tmp_path / "protocol.md"
    protocol.write_text("fixture frozen protocol")
    monkeypatch.setattr(host, "PROTOCOL", protocol)
    monkeypatch.setattr(host, "source_files", lambda: {})
    monkeypatch.setattr(host, "code_identity", lambda: {"code_commit": "new", "code_dirty": False})
    root = tmp_path / "resume"
    plan = host.prepare(root, original_root=old, controls=controls)
    assert host.frozen(root) == plan
    assert not (root / "s_star/actual").exists()
    assert (root / "declaration.json").read_bytes() == (old / "declaration.json").read_bytes()
    for name, ref in refs.items():
        assert Path(plan["retained_export"][name]["path"]).read_bytes() == Path(ref["path"]).read_bytes()
    with pytest.raises(FileExistsError):
        host.prepare(root, original_root=old, controls=controls)


def test_retained_export_receipt_cannot_change_original_cost_or_claim_replay(tmp_path):
    old = original_fixture(tmp_path)
    derived = derive(old)
    refs = retained_export_fixture(old, derived)
    declaration = json.loads((old / "declaration.json").read_text())
    assert host.validate_retained_export(refs, derived, declaration)["slot_id"] == host.FIRST_SLOT
    path = Path(refs["rematerialization-receipt.json"]["path"])
    value = json.loads(path.read_text())
    value["new_model_calls"] = 1
    write(path, value)
    refs["rematerialization-receipt.json"] = reference(path)
    with pytest.raises(ValueError):
        host.validate_retained_export(refs, derived, declaration)


def test_private_support_gate_keeps_original24_and48_measure(tmp_path, monkeypatch):
    from test_software_learning_v050 import fixture
    entries, declaration, recipe, design, admission, support = fixture(residual=True)
    monkeypatch.setattr(host, "frozen", lambda root: {"source": {}, "inventory": design, "s_star_recipe": recipe})
    monkeypatch.setattr(host, "materialize_entries", lambda *args: (entries, []))
    write(tmp_path / "declaration.json", declaration)
    gate = host.run_support_gate(tmp_path)
    assert gate["run_B50"] is True
    assert json.loads((tmp_path / "pretraining-admission.json").read_text()) == admission
    assert json.loads((tmp_path / "support-before-training.json").read_text()) == support
    assert support["global_member_denominator_factor"] == 48
    assert json.loads((tmp_path / "source-registry.json").read_text())["version"] == host.VERSION
