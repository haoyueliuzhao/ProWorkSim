"""Finite original-inventory continuation controls; no tensors, model or GPU."""
import copy
from types import SimpleNamespace
from pathlib import Path

import pytest

from proworksim.storage import digest
from scripts import software_learning_resume_v049r1 as resume
from scripts import software_learning_resume_supervisor_v049r1 as supervisor
from scripts.run_ne_v021 import reference, write


def units():
    return [{"slot_id": f"org49-train-{root}-r{repeat}", "root": root,
        "sampling_seed": 202610120490 + index, "first_member": "member_001" if root == "LA" else "member_002",
        "members": ["member_001", "member_002"], "purpose": "policy_training", "generation_token_cap": 500000}
        for index, (root, repeat) in enumerate(((root, repeat) for root in ("LA", "LB") for repeat in range(1, 5)), 1)]


def case(unit):
    return {"case_id": unit["root"], "condition": "O1", "purpose": "policy_training"}


def save_slot(root, unit, source, *, R=1, cost=100):
    folder = resume._unit_folder(root, unit)
    row = {"slot_id": unit["slot_id"], "sampling_seed": unit["sampling_seed"], "first_member": unit["first_member"],
        "status": "closed", "R": R, "purpose": "policy_training", "training_eligible": True,
        "condition": "O1", "actor_identity": {"fake": "no-tensors"},
        "episode_manifest": str((folder / "episode/manifest.json").resolve()),
        "actor_updates": 0, "critic_updates": 0, "new_backward_calls": 0,
        "usage": {"decisions": 1, "attempts": 1, "prompt_tokens": cost - 1, "completion_tokens": 1,
                  "total_tokens": cost, "uncertain_usage_attempts": 0}, "team_budget": {"tests": {"used": 1}}}
    scope = {"slot_id": unit["slot_id"], "case": case(unit), "online_window_id": "v049-o1-learning-window-01",
             "actor_identity": row["actor_identity"]}
    write(folder / "slot-result.json", row)
    write(folder / "episode/manifest.json", {"status": "closed", "source_start": source,
          "scenario": {"variation": {"organization_runtime": scope}}})
    write(folder / "mechanical-measurement.json", {"decision": "continue", "fixture_only": True})
    for filename in ("assessment.json", "public-capture.json", "evaluation-guard.json"):
        write(folder / filename, {"fixture_only": True})
    return folder


def parent(tmp_path, monkeypatch):
    root = tmp_path / "original"
    source = {"code_commit": "original-e222-fixture", "code_dirty": False}
    plan = {"version": resume.ORIGINAL_VERSION, "source": source, "source_files": {},
            "workers": list(resume.WORKERS), "inventory": {"training_slots": units()}}
    write(root / "plan.json", resume._seal(plan, "plan_sha256"))
    statefile = root / "s0/actual/checkpoint/shared-state.pt"
    statefile.parent.mkdir(parents=True)
    statefile.write_bytes(b"EXPLICIT CPU FIXTURE, NOT A TORCH STATE")
    checkpoint = {"state": reference(statefile), "state_tensor_digest": "a" * 64,
                  "actor_steps": 3, "critic_steps": 3}
    write(statefile.parent / "checkpoint.json", checkpoint)
    s0 = {"checkpoint_ref": reference(statefile.parent / "checkpoint.json"),
          "state_tensor_digest": checkpoint["state_tensor_digest"], "actor_identity": {"fake": "no-tensors"}}
    write(root / "s0.json", s0)
    write(root / "declaration.json", {"window_id": "v049-o1-learning-window-01", "gamma_identity": {"s0": s0}, "actor_identity": s0["actor_identity"],
        "slots": [{"slot_id": u["slot_id"]} for u in units()]})
    states = {name: {"status": "stopped", "attempted": False, "elapsed_gpu_seconds": 0} for name in resume.WORKERS}
    for name in ("s0", "collect-LA", "collect-LB"):
        states[name].update(status="complete" if name == "s0" else "stopped", attempted=True,
                            ended_at=100, exit_code=0, elapsed_gpu_seconds=10)
        write(root / name / "actual/report.json", {"status": "complete" if name == "s0" else "paused_before_next_slot",
            "source_before": source, "source_after": source, "new_actor_steps": 0, "new_critic_steps": 0})
    write(root / "supervisor.json", {"status": "closed_with_unknowns", "source": source, "ended_at": 100, "states": states})
    monkeypatch.setattr(resume.original, "_case", case)
    for index in (0, 1, 2, 4, 5):
        save_slot(root, units()[index], source, R=index % 2)
    return root


def test_retains_all_five_regardless_R_and_derives_only_original_three(tmp_path, monkeypatch):
    root = parent(tmp_path, monkeypatch)
    value = resume.derive_inventory(root, check_source=False)
    assert [u["slot_id"] for u in value["remaining_training_units"]] == ["org49-train-LA-r4", "org49-train-LB-r3", "org49-train-LB-r4"]
    assert [u["original_formal_R"] for u in value["retained_slots"]] == [0, 1, 0, 0, 1]
    assert value["replayed_slots"] == value["new_seeds"] == []
    assert value["retained_actual_cost"]["attempts"] == 5 and value["retained_actual_cost"]["total_tokens"] == 500
    assert [u["sampling_seed"] for u in value["remaining_training_units"]] == [202610120494, 202610120497, 202610120498]


@pytest.mark.parametrize("fault", ["in_flight", "prepared_not_closed", "old_update_attempted", "extra_episode"])
def test_no_replay_or_resume_from_ambiguous_original_boundary(tmp_path, monkeypatch, fault):
    root = parent(tmp_path, monkeypatch)
    value = resume.read_json(root / "supervisor.json")
    if fault == "in_flight":
        value["status"] = "running"
        write(root / "supervisor.json", value)
    elif fault == "prepared_not_closed":
        resume._unit_folder(root, units()[3]).mkdir(parents=True)
    elif fault == "old_update_attempted":
        value["states"]["update-B"]["attempted"] = True
        write(root / "supervisor.json", value)
    else:
        (root / "collect-LA/actual/episodes/extra-original-id").mkdir(parents=True)
    with pytest.raises(ValueError):
        resume.derive_inventory(root, check_source=False)


def test_exact_real_cost_caps_do_not_reuse_unspent_old_tokens():
    value = {"remaining_training_units": [1, 2, 3], "retained_actual_cost": {
        "total_tokens": 1617987, "decisions": 122, "attempts": 119, "member_tests": 14},
        "old_unspent_token_budget_not_transferred": 882013}
    caps = resume.budget_caps(value)
    assert caps["new_generation_slots_max"] == 15 and caps["new_actual_generation_tokens_max"] == 7500000
    assert caps["including_retained_actual_tokens_upper"] == 9117987
    assert caps["including_retained_actual_decisions_upper"] == 2042
    assert caps["including_retained_actual_attempts_upper"] == 2039
    assert caps["including_retained_actual_tests_upper"] == 494
    assert caps["old_unspent_tokens_not_transferred"] == 882013
    assert caps["new_S0_qualification_workers"] == 0


def test_model_visible_and_all_original_source_bytes_must_match(tmp_path):
    path = tmp_path / "src/original.py"
    path.parent.mkdir()
    path.write_text("original_model_visible_contract = True\n")
    original = {"source": {"commit": "fixture"}, "source_files": {"src/original.py": digest(path.read_bytes())}}
    assert resume.original_source_agreement(original, tmp_path)["passed"] is True
    path.write_text("original_model_visible_contract = False\n")
    with pytest.raises(ValueError, match="original frozen dependency changed"):
        resume.original_source_agreement(original, tmp_path)


def test_supervisor_reuses_S0_and_releases_only_two_original_remaining_groups(tmp_path, monkeypatch):
    old = parent(tmp_path, monkeypatch)
    inventory = resume.derive_inventory(old, check_source=False)
    state = supervisor.initial_states({"resume_inventory": inventory})
    assert state["s0"]["status"] == "complete" and state["s0"]["attempted"] is False
    assert state["s0"]["elapsed_gpu_seconds"] == 0
    assert supervisor.eligible_workers(state) == ["collect-LA", "collect-LB"]
    assert state["collect-LA"]["remaining_original_slot_ids"] == ["org49-train-LA-r4"]
    assert state["collect-LB"]["remaining_original_slot_ids"] == ["org49-train-LB-r3", "org49-train-LB-r4"]
    state["collect-LA"].update(status="complete", attempted=True)
    state["collect-LB"].update(status="complete", attempted=True)
    assert supervisor.eligible_workers(state) == ["update-B"]


def test_eight_unique_original_sources_materialized_once_then_Q_reads_same_sha(tmp_path, monkeypatch):
    from proworksim import software_training_v049r1 as exporter
    old = parent(tmp_path, monkeypatch)
    derived = resume.derive_inventory(old, check_source=False)
    new = tmp_path / "resume"
    source = {"code_commit": "new-r1-fixture", "code_dirty": False}
    plan = {"source": source, "resume_inventory": derived, "inventory": {"training_slots": units()},
            "declaration": reference(old / "declaration.json"), "resume_of": reference(old / "plan.json")}
    write(new / "plan.json", plan)
    for unit in derived["remaining_training_units"]:
        save_slot(new, unit, source)
    calls = []
    def fake_export(folder, declaration, destination):
        sid = Path(folder).name
        calls.append(sid)
        destination.mkdir(parents=True)
        return {"slot_id": sid, "active_members": ["member_001", "member_002"], "fixture_only": True}, {"fixture_only": True}
    monkeypatch.setattr(exporter, "reexport_closed_slot", fake_export)
    entries = resume.materialize_entries(plan, new)
    assert calls == [u["slot_id"] for u in units()]
    assert resume.load_materialized_entries(plan, new) == entries
    assert len(calls) == 8
    registry = resume.read_json(new / "source-registry.json")
    assert [row["origin"] for row in registry["slots"]].count("original_v049") == 5
    assert [row["origin"] for row in registry["slots"]].count("resume_r1") == 3
    assert len({row["episode_folder"] for row in registry["slots"]}) == 8
    assert registry["development_sources_included"] is False and registry["original_files_copied"] is False
    with pytest.raises(FileExistsError):
        resume.materialize_entries(plan, new)
    changed = copy.deepcopy(entries)
    changed[0]["fixture_only"] = False
    write(new / "entries.json", changed)
    with pytest.raises(ValueError, match="Frozen evidence changed"):
        resume.load_materialized_entries(plan, new)


def test_collect_host_calls_only_remaining_slots_and_defers_training_export(tmp_path, monkeypatch):
    from proworksim import software_organization_runtime_v049 as runtime
    from proworksim import software_organization_measurement_v049 as measured
    from proworksim import software_training_v049r1 as exporter
    old = parent(tmp_path, monkeypatch)
    derived = resume.derive_inventory(old, check_source=False)
    new = tmp_path / "resume"
    plan = {"resume_inventory": derived, "declaration": reference(old / "declaration.json"),
            "design": {"sha256": "d" * 64}}
    called, closed, restored = [], [], []
    def restore(owner, root, branch, output):
        restored.append(branch)
        return {"state_tensor_digest": "s0-fixture"}
    monkeypatch.setattr(resume, "_restored_state", restore)
    monkeypatch.setattr(resume.original, "_new_prepared", lambda unit, path: SimpleNamespace(
        case={"active_roles": ["member_001", "member_002"]}))
    def collect(owner, prepared, folder, *, sampling_seed, slot_id, manage_owner_window, learning_binding):
        called.append((slot_id, sampling_seed, manage_owner_window, learning_binding["branch"]))
        folder.mkdir(parents=True)
        return {"slot_id": slot_id, "R": 0, "fixture_only": True}
    monkeypatch.setattr(runtime, "collect_episode", collect)
    def measure(row, destination):
        result = {"decision": "continue", "fixture_only": True}
        write(destination, result)
        return result
    monkeypatch.setattr(measured, "measure_slot", measure)
    def forbidden(*args, **kwargs):
        raise AssertionError("Training export must run once later, not in each collection")
    monkeypatch.setattr(exporter, "reexport_closed_slot", forbidden)
    owner = SimpleNamespace(capture_evaluation_state=lambda: {}, begin_window=lambda window: None,
        finish_evaluation=lambda entries, output: closed.extend(entries),
        finish_evaluation_guard=lambda guard: {"learning_unchanged": True, "rng_restored_exactly": True})
    for worker in ("collect-LA", "collect-LB"):
        report = resume._collect(owner, plan, new, worker, new / worker / "actual")
        assert report["status"] == "complete" and report["training_entries_materialization_deferred"] is True
    assert [row[0] for row in called] == [row["slot_id"] for row in derived["remaining_training_units"]]
    assert [row[1] for row in called] == [row["sampling_seed"] for row in derived["remaining_training_units"]]
    assert all(row[2:] == (False, "S0") for row in called)
    assert restored == ["S0", "S0"] and len(closed) == 3
    assert not list(new.rglob("training-entry.json")) and not list(new.rglob("entries.json"))
