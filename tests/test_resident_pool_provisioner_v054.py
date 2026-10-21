"""New deployment state controls only; no actual residents/models/benchmark data."""
import copy
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_resident_pool_v054 as pool
from proworksim import software_benchmark_resident_provisioner_v054 as provisioner
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def artifact(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_new(path, value)


def fixture_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(pool, "ROOT", tmp_path)
    monkeypatch.setattr(provisioner, "ROOT", tmp_path)
    root = tmp_path / "runs/software-benchmark-v054/control"
    root.mkdir(parents=True)
    spec = artifact(root, "spec.json", {"contract": {}, "capacity_receipt": {}, "model_manifest": {}})
    identity = artifact(root, "identity.json", {"fixture_only": True})
    ready = artifact(root, "ready.json", {"ready": True, "resident": True, "source_spec": spec,
        "gpu_index": 7, "gpu_uuid": "GPU-fixture7", "gpu_lease_held": True, "identity": identity})
    declaration = artifact(root, "declaration.json", {"mode": "REF", "gpu_index": 7,
        "gpu_uuid": "GPU-fixture7", "source_spec": spec, "ready_path": ready["path"]})
    control = artifact(root, "synthetic-check.json", {"fixture_only": True})
    registry = artifact(root, "registry.json", {"residents": {"REF": declaration}})
    inherited = artifact(root, "inherited.json", {"registry": registry, "admitted_modes": {"REF": {
        "passed": True, "resident_spec": spec, "check_receipt": control, "unsettled_tokens": 0}}})
    source = artifact(root, "source.json", {"files": []})
    slots = artifact(root, "slots.json", {"slots": []})
    policy = artifact(root, "policy.json", {"version": pool.POLICY_VERSION, "pool_root": str(root),
        "queue_state_path": str(root / "queue.json"), "physical_gpus": list(range(8)), "maximum_residents": 8,
        "minimum_free_mib": 46080, "minimum_total_mib": 81920,
        "allowed_gpu_names": ["NVIDIA A800-SXM4-80GB"], "allow_co_residency": True, "require_idle": False,
        "maximum_actual_load_attempts_per_gpu": 1, "maximum_preparation_calls_per_new_resident": 2,
        "automatic_retry_after_load_failure": False, "model_loading_authorized": True,
        "preparation_generation_authorized": True, "ref_to_mp_after_all_500_scored": True,
        "training_authorized": False, "source_manifest": source, "inherited_registry": registry,
        "inherited_admission": inherited, "match_template_declaration": declaration, "slots": slots})
    evidence = artifact(root, "admission.json", provisioner.admission(
        policy, declaration, control, "fixture-ref", inherited=True))
    fields = {"event": "register", "resident_id": "fixture-ref", "mode": "REF", "gpu_index": 7,
              "gpu_uuid": "GPU-fixture7", "source_spec": spec, "declaration": declaration, "admission": evidence}
    return root, policy, fields


def test_atomic_registration_retirement_and_full_ref_gate(tmp_path, monkeypatch):
    root, policy, fields = fixture_policy(tmp_path, monkeypatch)
    original = pool.append_event(policy, fields)
    active = pool.registrations(policy)[0]
    assert pool.validate_registration(active, policy)["event_reference"] == original
    with pytest.raises(ValueError, match="already registered"):
        pool.append_event(policy, fields)
    assert len(pool.read_pool(policy)["events"]) == 1
    invalid = artifact(root, "invalid-closure.json", {"registration": original, "old_cgroup_empty": False})
    with pytest.raises(ValueError, match="Retirement"):
        pool.append_event(policy, {"event": "retire", "resident_id": "fixture-ref",
                                  "registration": original, "closure": invalid})
    assert len(pool.read_pool(policy)["events"]) == 1
    closure = artifact(root, "closure.json", {"registration": original,
        **dict.fromkeys(("all_500_ref_scored", "resident_session_idle", "old_unit_stopped",
                        "old_cgroup_empty", "old_launcher_gone"), True)})
    pool.append_event(policy, {"event": "retire", "resident_id": "fixture-ref",
                              "registration": original, "closure": closure})
    assert pool.registrations(policy) == []
    assert reference(original["path"]) == original
    with pytest.raises(ValueError, match="current pool"):
        pool.validate_registration(active, policy)
    slots = {"slots": [{"slot_id": str(i), "arm": arm, "seed": i // 3}
                       for i, arm in enumerate(["REF", "MATCH", "PROJECT"] * 500)]}
    state = {"rows": [{"slot": slot, "generation": {"status": "closed"},
        "scores": {"code": {"status": "official_report", "resolved": False}},
        "delivery": {"status": "not_applicable"}} for slot in slots["slots"]]}
    assert pool.ref_completion_evidence(state, slots)["eligible"]
    state["rows"][0]["scores"]["code"]["status"] = "technical_unknown"
    assert not pool.ref_completion_evidence(state, slots)["eligible"]
    state["rows"][0]["scores"]["code"]["status"] = "official_report"
    state["rows"][3]["slot"] = copy.deepcopy(state["rows"][0]["slot"])
    with pytest.raises(ValueError, match="identity"):
        pool.ref_completion_evidence(state, slots)


def test_preload_resource_wait_and_failed_launch_are_not_replayed(tmp_path, monkeypatch):
    root, policy, fields = fixture_policy(tmp_path, monkeypatch)
    owner = root / "new-owner"
    owner.mkdir()
    spec = artifact(root, "new-spec.json", {"root": str(owner)})
    job = {"status": "startup_intent", "root": str(root), "declaration": fields["declaration"],
           "spec": spec, "unit": "fixture-only", "created_epoch": 0}
    monitor = provisioner.Provisioner(policy)
    monkeypatch.setattr(provisioner, "unit_state", lambda _: {"ActiveState": "failed", "MainPID": "0"})
    artifact(owner, "status.json", {"status": "resource_not_ready", "reason_code": "gpu_lease_busy",
                                    "model_load_started": False, "model_calls": 0})
    monitor.poll(job)
    assert job["status"] == "resource_wait" and not job["model_load_attempted"]
    Path(owner / "status.json").unlink()
    job["status"] = "startup_intent"
    artifact(owner, "launcher-started.json", {"fixture_only": True})
    monitor.poll(job)
    assert job["status"] == "failed_manual_action_required" and job["automatic_retry"] is False
    before = json.dumps(job, sort_keys=True)
    monkeypatch.setattr(provisioner, "unit_state", lambda _: pytest.fail("Failed device must never be retried"))
    monitor.poll(job)
    assert json.dumps(job, sort_keys=True) == before
