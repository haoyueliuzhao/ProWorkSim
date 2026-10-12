"""Finite CPU receipt/dispatch controls; no GPU, model, tokenizer or acceptance."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.storage import digest, json_bytes, read_json
from scripts import software_learning_development_resume_v049r2 as resume
from scripts import software_learning_development_resume_supervisor_v049r2 as supervisor
from scripts.run_ne_v021 import reference, write


def case(unit):
    return {"case_id": unit["root"], "purpose": "policy_development"}


def fixture_parent(tmp_path, monkeypatch):
    root, old = tmp_path / "r1", tmp_path / "original"
    source = {"code_commit": "CPU-FIXTURE-NO-MODELS", "code_dirty": False}
    design = read_json(resume.original.DESIGN)
    write(tmp_path / "design.json", design)
    write(old / "plan.json", resume._seal({"inventory": design}, "plan_sha256"))
    s0_checkpoint = {"actor_steps": 3, "critic_steps": 3, "state_tensor_digest": "s0",
        "actor_identity": {"fixture": "s0"}, "state": {"path": "unused-cpu-fixture-s0.pt", "sha256": "unused"}}
    write(old / "s0/actual/checkpoint/checkpoint.json", s0_checkpoint)
    s0 = {"checkpoint_ref": reference(old / "s0/actual/checkpoint/checkpoint.json"),
        "state_tensor_digest": "s0", "actor_identity": s0_checkpoint["actor_identity"]}
    write(old / "s0.json", s0)
    declaration = {"actor_identity": s0["actor_identity"], "gamma_identity": {"s0": s0}}
    write(old / "declaration.json", declaration)
    plan = {"version": resume.previous.VERSION, "workers": list(resume.previous.WORKERS),
        "source": source, "source_files": {}, "limits": resume.LIMITS, "inventory": design,
        "resume_of": reference(old / "plan.json"), "design": reference(tmp_path / "design.json"),
        "s0": reference(old / "s0.json"), "declaration": reference(old / "declaration.json")}
    write(root / "plan.json", resume._seal(plan, "plan_sha256"))
    states = {name: {"status": "not_applicable", "attempted": False} for name in resume.previous.WORKERS}
    states["s0"] = {"status": "complete", "attempted": False}
    for name in ("collect-LA", "collect-LB", "update-B"):
        states[name] = {"status": "complete", "attempted": True, "exit_code": 0, "ended_at": 100}
        write(root / name / "actual/report.json", {"status": "complete", "success_boundary": True,
            "source_before": source, "source_after": source})
    states["dev-B"] = {"status": "stopped", "attempted": True, "exit_code": -2, "ended_at": 200}
    write(root / "supervisor.json", {"status": "closed_with_unknowns", "source": source, "ended_at": 201, "states": states})
    slots = []
    for unit in design["training_slots"]:
        path = old / "fixture-training" / unit["slot_id"] / "slot-result.json"
        write(path, {"status": "closed", "R": 0})
        slots.append({"slot_id": unit["slot_id"], "source_result": reference(path)})
    write(root / "source-registry.json", resume._seal({"slots": slots, "declaration": plan["declaration"]}))
    write(root / "entries.json", {"explicit_CPU_fixture": True})
    write(root / "materialization.json", resume._seal({"passed": True, "original_slots_once_each": 8,
        "slots": slots, "source_registry": reference(root / "source-registry.json"), "entries": reference(root / "entries.json")}))
    state_path = root / "update-B/actual/checkpoint/shared-state.pt"
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(b"EXPLICIT CPU FIXTURE; NOT MODEL TENSORS")
    checkpoint = {"state": reference(state_path), "actor_identity": {"fixture": "B"}, "actor_steps": 4,
        "critic_steps": 4, "state_tensor_digest": "B", "serialized_reload_exact": True}
    write(state_path.parent / "checkpoint.json", checkpoint)
    update = {"status": "updated", "stage": "complete", "actor_optimizer_steps": 1, "critic_optimizer_steps": 1,
        "backward_decisions_completed": 206, "scheduled_slots": 8, "before_actor_identity": s0["actor_identity"]}
    write(root / "update-B/actual/update/report.json", update)
    b_report = read_json(root / "update-B/actual/report.json")
    b_report.update(checkpoint=checkpoint, final_actor_identity=checkpoint["actor_identity"],
        update_report=reference(root / "update-B/actual/update/report.json"))
    write(root / "update-B/actual/report.json", b_report)
    write(root / "support.json", {"fixture": True})
    direction = resume._seal({"selected": False, "reliable_base_material": True,
        "frozen_before_any_development": True, "B_update": b_report["update_report"],
        "support": reference(root / "support.json"), "direction": resume._seal({"selected": None,
            "design_sha256": plan["design"]["sha256"], "declaration_sha256": digest(json_bytes(declaration))}, "seal_sha256")}, "seal_sha256")
    write(root / "direction.json", direction)
    monkeypatch.setattr(resume.original, "_case", case)
    for index, unit in enumerate(design["development_units_shared_by_branches"][:2]):
        sid = unit["unit_id"] + "-B"
        folder = root / "dev-B/actual/episodes" / sid
        write(folder / "episode/manifest.json", {"source_start": source,
            "scenario": {"variation": {"organization_runtime": {"slot_id": sid, "case": case(unit)}}}})
        if index == 0:
            write(folder / "slot-result.json", {"status": "closed", "R": 1,
                "actor_identity": checkpoint["actor_identity"], "usage": {"total_tokens": 491926}})
        else:
            write(folder / "interruption.json", {"signal": 15, "sender": None})
    write(root / "mechanism-stops/dev-B.json", {"kind": "execution_fault", "original": True})
    def proof_checkpoint(cp, path):
        return {"checkpoint": str(path), "state": cp["state"], "state_tensor_digest": cp["state_tensor_digest"],
            "serialized_reload_exact": True, "loaded_map_location": "cpu"}
    proof = {"run_root": str(root), "direction": direction,
        "S0": proof_checkpoint(s0_checkpoint, old / "s0/actual/checkpoint/checkpoint.json"),
        "branches": {"Q_plus": {"status": "not_applicable"}, "Q_minus": {"status": "not_applicable"}, "B": {
            "status": "complete", "all_saved_state_top_level_fields_compared": True,
            "step_differences_match_native_report": True, "checkpoint": proof_checkpoint(checkpoint, state_path.parent / "checkpoint.json"),
            "completed_source_binding": {"frozen_source": source, "update_report": b_report["update_report"],
                "worker_checkpoint_equals_saved_checkpoint": True, "source_before_and_after_match_frozen_plan": True,
                "original_S0_restore_digest_matches": True}}},
        **dict.fromkeys(("actor_or_critic_models_loaded", "new_forward_calls", "new_backward_calls", "new_optimizer_steps", "GPU_API_calls"), 0)}
    proof_path = tmp_path / "independent-proof.json"
    write(proof_path, proof)
    return root, proof_path


def derive(root, proof):
    return resume.derive_inventory(root, state_proof=proof, check_source=False)


def test_source_inventory_retains_old_unknown_and_only_two_exact_DB_units(tmp_path, monkeypatch):
    root, proof = fixture_parent(tmp_path, monkeypatch)
    before = {str(p): digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
    inventory = derive(root, proof)
    assert [unit["unit_id"] for unit in inventory["remaining_development_units"]] == ["org49-dev-DB-s1", "org49-dev-DB-s2"]
    assert [unit["sampling_seed"] for unit in inventory["remaining_development_units"]] == [202610120593, 202610120594]
    assert all(unit["first_member"] == "member_002" for unit in inventory["remaining_development_units"])
    assert [row["R"] for row in inventory["retained_development"]] == [1, None]
    assert inventory["retained_development"][1]["complete_usage"] is None
    assert inventory["original_F_B"] is None and inventory["unknown_DA_s2_preserved"] is True
    assert inventory["new_seeds"] == inventory["replayed_slots"] == []
    assert before == {str(p): digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("fault", ["running_host", "living_worker", "B_unclean", "collection_unclean", "Q_attempted",
    "DB_prepared", "DA2_filled", "changed_B_bytes", "proof_S0", "proof_B", "proof_source", "training_unknown"])
def test_source_admission_rejects_ambiguous_or_changed_boundaries(tmp_path, monkeypatch, fault):
    root, proof = fixture_parent(tmp_path, monkeypatch)
    states = read_json(root / "supervisor.json")
    if fault == "running_host":
        states["status"] = "running"
    elif fault == "living_worker":
        states["states"]["dev-B"].update(pid=99, process_identity={"start_ticks": 123})
        monkeypatch.setattr(resume, "worker_identity", lambda pid: {"alive": True, "start_ticks": 123})
    elif fault in {"B_unclean", "collection_unclean"}:
        states["states"]["update-B" if fault == "B_unclean" else "collect-LB"]["exit_code"] = 1
    elif fault == "Q_attempted":
        states["states"]["update-Q_plus"]["attempted"] = True
    elif fault == "DB_prepared":
        (root / "dev-B/actual/episodes/org49-dev-DB-s1-B").mkdir()
    elif fault == "DA2_filled":
        write(root / "dev-B/actual/episodes/org49-dev-DA-s2-B/slot-result.json", {"status": "closed", "R": 0})
    elif fault == "changed_B_bytes":
        (root / "update-B/actual/checkpoint/shared-state.pt").write_bytes(b"WRONG STATE")
    elif fault.startswith("proof_"):
        value = read_json(proof)
        if fault == "proof_S0":
            value["S0"]["state_tensor_digest"] = "wrong"
        elif fault == "proof_B":
            value["branches"]["B"]["checkpoint"]["state_tensor_digest"] = "wrong"
        else:
            value["branches"]["B"]["completed_source_binding"]["frozen_source"] = {}
        write(proof, value)
    else:
        material = read_json(root / "materialization.json")
        registry = read_json(root / "source-registry.json")
        path = Path(registry["slots"][0]["source_result"]["path"])
        write(path, {"status": "closed", "R": None})
        registry["slots"][0]["source_result"] = reference(path)
        registry.pop("sha256")
        write(root / "source-registry.json", resume._seal(registry))
        material["source_registry"] = reference(root / "source-registry.json")
        material.pop("sha256")
        write(root / "materialization.json", resume._seal(material))
    write(root / "supervisor.json", states)
    with pytest.raises(ValueError):
        derive(root, proof)


def test_no_new_learning_or_old_budget_transfer_and_original_resource_limits():
    caps = resume.budget_caps()
    assert [caps[k] for k in ("new_generation_slots_max", "new_actual_generation_tokens_max", "new_decisions_max", "new_attempts_max", "new_member_tests_max")] == [2, 1000000, 256, 256, 64]
    assert all(caps[k] == 0 for k in ("old_unspent_budget_transferred", "new_actor_steps", "new_critic_steps", "new_backward_calls", "new_model_qualification_calls"))
    assert resume.LIMITS == resume.original.LIMITS == supervisor.LIMITS
    assert resume.GPU_ORDER == (3, 4, 5, 7)
    assert supervisor.LIMITS["gpu_capacity_stability_seconds"] == 60
    assert supervisor.LIMITS["minimum_free_gpu_mib"] == supervisor.LIMITS["own_gpu_memory_mib"] == 57344
    assert supervisor.LIMITS["minimum_live_free_gpu_mib"] == 6144
    assert supervisor.LIMITS["max_parallel_model_instances"] == 3


@pytest.mark.parametrize("wrong", ["digest", "identity", "step"])
def test_B_restore_mismatch_blocks_evaluation(tmp_path, wrong):
    path = tmp_path / "B/checkpoint.json"
    saved = {"state_tensor_digest": "B", "actor_identity": {"actor": "B"}}
    write(path, saved)
    restored, identity, steps = copy.deepcopy(saved), saved["actor_identity"], 4
    if wrong == "digest":
        restored["state_tensor_digest"] = "S0"
    elif wrong == "identity":
        identity = {"actor": "S0"}
    else:
        steps = 3
    owner = SimpleNamespace(restore_checkpoint=lambda path: restored, freeze_identity=lambda: identity,
        actor_steps=steps, critic_steps=4)
    with pytest.raises(ValueError, match="full B"):
        resume.restore_B(owner, {"resume_inventory": {"B_checkpoint": reference(path)}}, tmp_path / "out")
    assert not (tmp_path / "out/loaded-state.json").exists()


@pytest.mark.parametrize("decision", ["continue", "global_pause", "measurement_pending"])
def test_single_new_world_uses_restored_B_and_original_runtime_guards(tmp_path, monkeypatch, decision):
    from proworksim import software_organization_runtime_v049 as runtime
    from proworksim import software_organization_measurement_v049 as measurement
    root, proof = fixture_parent(tmp_path, monkeypatch)
    inventory = derive(root, proof)
    plan = {"resume_inventory": inventory, "declaration": inventory["declaration"], "design": {"sha256": "design"}}
    new = tmp_path / "r2"
    events = []
    cp = read_json(resume.checked(inventory["B_checkpoint"]))
    owner = SimpleNamespace(actor_steps=3, critic_steps=3)
    def restore(path):
        events.append(("restore", path))
        owner.actor_steps = owner.critic_steps = 4
        return cp
    owner.restore_checkpoint = restore
    owner.freeze_identity = lambda: cp["actor_identity"]
    owner.capture_evaluation_state = lambda: events.append(("guard_start",)) or {}
    owner.finish_evaluation_guard = lambda snapshot: events.append(("guard_finish",)) or {"learning_unchanged": True, "rng_restored_exactly": True}
    def prepared(unit, path):
        events.append(("new_world", unit["slot_id"], path))
        return SimpleNamespace(case={})
    monkeypatch.setattr(resume.original, "_new_prepared", prepared)
    def collect(owner, prepared, folder, **kwargs):
        assert owner.actor_steps == owner.critic_steps == 4
        events.append(("collect", kwargs))
        return {"slot_id": kwargs["slot_id"], "R": 0}
    monkeypatch.setattr(runtime, "collect_episode", collect)
    def measure(row, destination):
        write(destination, {"decision": decision})
        return {"decision": decision}
    monkeypatch.setattr(measurement, "measure_slot", measure)
    for worker in resume.WORKERS:
        report = resume.collect_development(owner, plan, new, worker, new / worker / "actual")
        assert report["status"] == ("complete" if decision == "continue" else decision if worker == resume.WORKERS[0] else "paused_before_next_slot")
    calls = [row[1] for row in events if row[0] == "collect"]
    assert len(calls) == (2 if decision == "continue" else 1)
    assert calls[0]["slot_id"] == "org49-dev-DB-s1-B" and calls[0]["sampling_seed"] == 202610120593
    assert calls[0]["manage_owner_window"] is True
    assert calls[0]["learning_binding"]["branch"] == "B" and calls[0]["learning_binding"]["loaded_checkpoint_state_digest"] == "B"
    assert [row[0] for row in events[:5]] == ["restore", "guard_start", "new_world", "collect", "guard_finish"]
    assert len([row for row in events if row[0] == "restore"]) == 2
    assert bool(list((new / "mechanism-stops").glob("*.json"))) is (decision != "continue")


def test_both_DB_workers_eligible_without_DA_success_selection():
    units = read_json(resume.original.DESIGN)["development_units_shared_by_branches"][2:]
    states = supervisor.initial_states({"resume_inventory": {"remaining_development_units": units}})
    assert supervisor.eligible_workers(states) == list(resume.WORKERS)
    states[resume.WORKERS[0]].update(status="complete", attempted=True, R=0)
    assert supervisor.eligible_workers(states) == [resume.WORKERS[1]]
    states[resume.WORKERS[1]]["attempted"] = True
    assert supervisor.eligible_workers(states) == []
    states["dev-DA"] = {"status": "not_started", "attempted": False}
    with pytest.raises(ValueError, match="two original DB"):
        supervisor.eligible_workers(states)


def test_signal_observation_does_not_invent_sender_and_host_stop_persists_first(tmp_path, monkeypatch):
    with pytest.raises(KeyboardInterrupt, match="signal 15"):
        resume.received_signal(15, None)
    process = SimpleNamespace(pid=123, poll=lambda: -15)
    state = {"process_identity": {"start_ticks": 1234}}
    seen = []
    def stop(process, state):
        receipt = read_json(tmp_path / "host-stop-actions/DB.json")
        assert receipt["reason"] == "resource_guard" and "stop_procedure_returned_at" not in receipt
        seen.append(receipt)
    monkeypatch.setattr(supervisor.support.continuation, "_stop_worker", stop)
    supervisor.request_stop(tmp_path, "DB", process, state, "resource_guard")
    assert len(seen) == 1 and state["host_stop_action"] == reference(tmp_path / "host-stop-actions/DB.json")


@pytest.mark.parametrize("fault", [None, "failed_controls", "unbound_controls", "changed_old_stop", "changed_frozen_budget"])
def test_prepare_and_frozen_require_bound_control_and_immutable_old_evidence(tmp_path, monkeypatch, fault):
    root, proof = fixture_parent(tmp_path, monkeypatch)
    parent = read_json(root / "plan.json")
    parent.update(prior_artifact_roots=[], gpu_preference=list(resume.GPU_ORDER),
        mapper_specification={}, source_partition={}, task_source_manifest={}, training_reward="unchanged",
        development_F="original-four-unknown-stays-null", common={}, model_references={})
    parent.pop("plan_sha256")
    write(root / "plan.json", resume._seal(parent, "plan_sha256"))
    control = {"passed": fault != "failed_controls", "new_model_calls": 0, "new_gpu_workers": 0,
        "original_plan": reference(root / "plan.json"), "state_proof": reference(proof)}
    if fault == "unbound_controls":
        control["original_plan"]["sha256"] = "wrong"
    control_path = tmp_path / "controls.json"
    write(control_path, resume._seal(control))
    monkeypatch.setattr(resume, "code_identity", lambda: {"code_commit": "new-fixture", "code_dirty": False})
    monkeypatch.setattr(resume, "source_files", lambda: {})
    new = tmp_path / "r2"
    if fault in {"failed_controls", "unbound_controls"}:
        with pytest.raises(ValueError, match="Finite CPU controls"):
            resume.prepare(new, original_root=root, controls=control_path, state_proof=proof)
        assert not new.exists()
        return
    plan = resume.prepare(new, original_root=root, controls=control_path, state_proof=proof)
    assert plan["workers"] == list(resume.WORKERS) and plan["inventory"] == parent["inventory"]
    assert plan["resume_cpu_controls"] == reference(control_path)
    assert resume.frozen(new) == plan
    with pytest.raises(FileExistsError):
        resume.prepare(new, original_root=root, controls=control_path, state_proof=proof)
    if fault == "changed_old_stop":
        write(root / "mechanism-stops/dev-B.json", {"kind": "invented-resolution"})
    elif fault == "changed_frozen_budget":
        plan["new_budget_caps"]["new_actual_generation_tokens_max"] = 1500000
        plan.pop("plan_sha256")
        write(new / "plan.json", resume._seal(plan, "plan_sha256"))
    else:
        return
    with pytest.raises(ValueError):
        resume.frozen(new)


@pytest.mark.parametrize("mode", ["parallel_complete", "measurement_pending", "external_exit", "host_resource_stop"])
def test_full_supervisor_CPU_simulation_parallel_and_pause_scope(tmp_path, monkeypatch, mode):
    root = tmp_path / "r2"
    root.mkdir()
    clock = SimpleNamespace(now=100.0)
    def sleep(seconds):
        clock.now += 60
        assert clock.now < 1000, "CPU host simulation must terminate"
    monkeypatch.setattr(supervisor, "time", SimpleNamespace(time=lambda: clock.now, sleep=sleep))
    units = read_json(resume.original.DESIGN)["development_units_shared_by_branches"][2:]
    source = {"fixture": "source"}
    plan = {"source": source, "resume_inventory": {"remaining_development_units": units,
        "original_supervisor": {"fixture": "retained-original-terminal"}}, "prior_artifact_roots": [],
        "limits": resume.LIMITS, "gpu_preference": list(resume.GPU_ORDER), "native_python": "FIXTURE-NO-PROCESS"}
    monkeypatch.setattr(resume, "frozen", lambda path: plan)
    device_rows = ["0, GPU-0, A100, 81920, 81920, 0", "3, GPU-3, A100, 81920, 81920, 0"]
    if mode == "parallel_complete":
        device_rows.append("4, GPU-4, A100, 81920, 81920, 0")
    sample = {"gpus": {"returncode": 0, "stdout": "\n".join(device_rows)}, "processes": {"returncode": 0, "stdout": ""}}
    monkeypatch.setattr(supervisor, "allowed_resources", lambda: sample)
    monkeypatch.setattr(supervisor, "target_resources", lambda *args, **kwargs: sample)
    monkeypatch.setattr(supervisor, "worker_env", lambda plan, gpu: {"CUDA_VISIBLE_DEVICES": str(gpu)})
    monkeypatch.setattr(supervisor, "worker_identity", lambda pid: {"start_ticks": pid, "alive": True})
    monkeypatch.setattr(supervisor, "rss", lambda pid: 0)
    monkeypatch.setattr(supervisor, "artifact_bytes", lambda path: 0)
    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda path: SimpleNamespace(free=1024**4))
    class Guard:
        def __init__(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            return {"stop_reason": "fixture_resource_stop" if mode == "host_resource_stop" else None}
    monkeypatch.setattr(supervisor, "TelemetryGuard", Guard)
    launched = []
    class FakeProcess:
        def __init__(self, argv, **kwargs):
            self.pid = 900 + len(launched)
            self.started = clock.now
            self.returncode = None
            self.name = argv[argv.index("--worker") + 1]
            self.gpu = int(kwargs["env"]["CUDA_VISIBLE_DEVICES"])
            assert argv[2] == "scripts.software_learning_development_resume_v049r2"
            assert self.gpu in (3, 4, 5, 7) and self.name in resume.WORKERS
            launched.append(self)
            status = "measurement_pending" if mode == "measurement_pending" else "complete"
            write(root / self.name / "actual/report.json", {"status": status, "source_before": source,
                "source_after": source, "success_boundary": status == "complete"})
        def poll(self):
            if self.returncode is None and clock.now > self.started and mode != "host_resource_stop":
                self.returncode = -2 if mode == "external_exit" else 0
            return self.returncode
        def wait(self, timeout):
            assert self.returncode is not None
            return self.returncode
    monkeypatch.setattr(supervisor.subprocess, "Popen", FakeProcess)
    def stop(process, state):
        assert (root / "host-stop-actions" / (process.name + ".json")).exists()
        process.returncode = -15
    monkeypatch.setattr(supervisor.support.continuation, "_stop_worker", stop)
    result = supervisor.supervise(root)
    assert result["original_unknown_DA_s2_preserved"] is True and result["original_F_B"] is None
    if mode == "parallel_complete":
        assert len(launched) == 2 and [process.gpu for process in launched] == [3, 4]
        assert launched[0].started == launched[1].started
        assert result["status"] == "complete" and not list((root / "mechanism-stops").glob("*.json"))
    else:
        assert len(launched) == 1 and result["status"] == "closed_with_unknowns"
        assert result["states"][resume.WORKERS[1]]["attempted"] is False
        pause = read_json(root / "mechanism-stops" / (resume.WORKERS[0] + "-supervisor.json"))
        assert pause["kind"] == ("measurement_pending" if mode == "measurement_pending" else "execution_fault")
    assert bool(list((root / "host-stop-actions").glob("*.json"))) is (mode == "host_resource_stop")
    with pytest.raises(FileExistsError):
        supervisor.supervise(root)


def test_host_stop_receipt_failure_still_stops_owned_child(tmp_path, monkeypatch):
    process = SimpleNamespace(pid=123, returncode=None)
    process.poll = lambda: process.returncode
    calls = []
    def failed_write(path, receipt):
        raise OSError("CPU-injected receipt write failure")
    def stop(child, state):
        calls.append(child.pid)
        child.returncode = -15
    monkeypatch.setattr(supervisor, "write", failed_write)
    monkeypatch.setattr(supervisor.support.continuation, "_stop_worker", stop)
    state = {"process_identity": {"start_ticks": 1234}}
    with pytest.raises(OSError, match="injected"):
        supervisor.request_stop(tmp_path, "DB", process, state, "resource_guard")
    assert calls == [123] and process.returncode == -15
    assert state["host_stop_receipt_error"]["type"] == "OSError"
