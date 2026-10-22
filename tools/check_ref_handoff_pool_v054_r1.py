"""Necessary CPU-only closure/chain/transition controls; no real service calls."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import Mock, patch
from proworksim import software_benchmark_ref_handoff_pool_v054_r1 as handoff
from proworksim import software_benchmark_resident_session_v054 as session
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def fixture(root):
    slots = {"slots": [{"slot_id": f"s-{i}", "slot_index": i + 1,
        "arm": ["REF", "MATCH", "PROJECT"][i % 3], "seed": i} for i in range(1500)]}
    state = {"rows": [{"slot": row, "generation": {"status": "closed" if i else "technical_unknown"},
                      "scores": {"code": {"status": "pending"}}, "delivery": {"status": "not_applicable"}}
                     for i, row in enumerate(slots["slots"])]}
    slots_ref = write_new(root / "slots.json", slots)
    snapshot = write_new(root / "state.json", state)
    policy_ref = write_new(root / "policy.json", {"fixture": True})
    overlay_ref = write_new(root / "overlay.json", {"fixture": True})
    overlay = {"target_pool_policy": policy_ref, "slots": slots_ref, "queue_state_path": snapshot["path"]}
    policy = {"pool_root": str(root), "maximum_residents": 8, "queue_state_path": snapshot["path"], "slots": slots_ref}
    directory = root / "events"
    directory.mkdir()
    event = {"event": "register", "version": handoff.pool.EVENT_VERSION, "sequence": 1,
        "previous_event": None, "pool_policy": policy_ref, "resident_id": "ref", "mode": "REF",
        "gpu_index": 7, "gpu_uuid": "GPU-fixture", "declaration": {"fixture": True}}
    registration = write_new(directory / "00000001.json", event)
    evidence = handoff.boundary.ref_generation_evidence(state, slots)
    proof = {"version": handoff.boundary.VERSION, "generation_evidence": evidence, "slots": slots_ref,
        "source": reference(handoff.boundary.__file__), "registration": registration,
        "all_ref_generation_quiescent": True, "resident_session_idle": True, "resident_inflight": 0,
        "all_ref_generation_workers_quiet": True, "all_ref_registered_scopes_quiet": True,
        "all_ref_scores_claimed_complete": False}
    proof_ref = write_new(root / "proof.json", proof)
    intent = write_new(root / "intent.json", {"registration": registration, "overlay": overlay_ref,
        "queue_snapshot": snapshot, "runtime_boundary": proof_ref})
    closure = {"version": handoff.CLOSURE_VERSION, "overlay": overlay_ref, "registration": registration,
        "intent": intent, "queue_snapshot": snapshot, "runtime_boundary": proof_ref,
        "resource_retirement_only": True, "score_completion_required": False,
        "historical_results_and_unknown_costs_preserved": True, "formal_episodes_replayed": 0,
        "different_user_processes_stopped": 0, "stop_returncode": 0,
        "resident_session_idle": True, "old_unit_stopped": True,
        "old_cgroup_empty": True, "old_launcher_gone": True,
        "post_stop_unit": {"MainPID": "0", "ActiveState": "inactive"}}
    closure_ref = write_new(root / "closure.json", closure)
    return locals()


def rejected(call):
    try:
        call()
    except ValueError:
        return True
    raise AssertionError("Unsafe control was accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = []
    with tempfile.TemporaryDirectory(prefix="pws-ref-handoff-cpu-") as temporary:
        root = Path(temporary)
        value = fixture(root)
        overlay_ref, overlay, policy = value["overlay_ref"], value["overlay"], value["policy"]
        policy_ref, registration = value["policy_ref"], value["registration"]
        with patch.object(handoff, "validate_overlay", return_value=overlay), \
                patch.object(handoff.pool, "validate_pool_policy", return_value=policy), \
                patch.object(handoff.pool, "_static_registration"):
            retired = handoff.append_retirement(overlay_ref, {"resident_id": "ref",
                "registration": registration, "closure": value["closure_ref"]})
            assert handoff._read_target_pool(policy_ref, overlay_ref, overlay)["active"] == {}
            assert "all_500_ref_scored" not in handoff.pool.read_ref(value["closure_ref"])
            checks.append("terminal_499_closed_1_unknown_with_pending_scores_retires_truthfully")
            rejected(lambda: handoff.append_retirement(overlay_ref, {"resident_id": "ref",
                "registration": registration, "closure": value["closure_ref"]}))
            checks.append("duplicate_retirement_rejected")
            bad = {**value["closure"], "all_500_ref_scored": True}
            bad_ref = write_new(root / "bad-scored.json", bad)
            event = handoff.pool.read_ref(retired)
            old = {**value["event"], "event_reference": registration}
            rejected(lambda: handoff._validate_new_closure({**event, "closure": bad_ref}, old, overlay_ref, overlay))
            checks.append("invented_all_scored_evidence_rejected")
            bad_proof = write_new(root / "bad-proof.json", {**value["proof"], "resident_inflight": 1})
            bad_ref = write_new(root / "bad-inflight.json", {**value["closure"], "runtime_boundary": bad_proof})
            rejected(lambda: handoff._validate_new_closure({**event, "closure": bad_ref}, old, overlay_ref, overlay))
            checks.append("nonquiescent_proof_rejected")
            event_path = Path(retired["path"])
            event_path.write_text(json.dumps({**event, "previous_event": None}))
            rejected(lambda: handoff._read_target_pool(policy_ref, overlay_ref, overlay))
            checks.append("event_chain_tamper_rejected")
        with patch.object(handoff, "_OVERLAY_REF", overlay_ref), \
                patch.object(handoff, "validate_overlay", return_value=overlay), \
                patch.object(handoff, "_ORIGINAL_READ_POOL", return_value={"fixture_other_pool": True}) as original_read:
            assert handoff.read_pool({"other": True}) == {"fixture_other_pool": True}
            original_read.assert_called_once_with({"other": True})
            checks.append("other_pool_reader_unchanged")
        # All process/device effects below are mocks. The exact saved queue
        # bytes and previous failed device record must remain unchanged.
        before = Path(value["snapshot"]["path"]).read_bytes()
        provisioner = object.__new__(handoff.HandoffProvisioner)
        provisioner.overlay_ref, provisioner.overlay = overlay_ref, overlay
        provisioner.policy_ref, provisioner.policy, provisioner.root = policy_ref, policy, root
        provisioner.state = {"conversion": None, "devices": {"old": {"status": "failed_manual_action_required"}}}
        provisioner.save = Mock()
        process = {"pid": 99999999, "start_ticks": 1}
        observed = {"registration": registration, "status": {"active_claim": None, "inflight": 0, "poisoned": False},
            "declaration": {"unit": "proworksim-v054-resident-ref-fixture.service"},
            "ready": {"host_process": process, "invocation_id": "fixture", "cgroup": "/pws-no-such-fixture"},
            "ready_reference": {"fixture_ready": True}, "unit_state": {"fixture_unit": True}}
        current = {"active": {"ref": {**value["event"], "event_reference": registration}}}
        with patch.object(handoff, "validate_overlay", return_value=overlay), \
                patch.object(session, "admitted_resident", return_value=observed), \
                patch.object(handoff.boundary, "collect_runtime_boundary", return_value=value["proof"]), \
                patch.object(handoff.original, "unit_state", side_effect=[
                    {"InvocationID": "fixture", "MainPID": str(process["pid"])},
                    {"MainPID": "0", "ActiveState": "inactive"}]), \
                patch.object(handoff, "process_identity", side_effect=[process, FileNotFoundError()]), \
                patch.object(handoff.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as stop, \
                patch.object(handoff, "append_retirement", return_value={"fixture_retirement": True}):
            provisioner.convert_ref(current)
            assert stop.call_count == 1
            assert stop.call_args.args[0] == ["systemctl", "--user", "stop", observed["declaration"]["unit"]]
            assert provisioner.state["conversion"]["status"] == "ref_retired_waiting_for_mp_capacity"
            assert provisioner.state["devices"]["old"]["status"] == "failed_manual_action_required"
            assert Path(value["snapshot"]["path"]).read_bytes() == before
            stop.reset_mock()
            provisioner.convert_ref(current)
            stop.assert_not_called()
            checks.append("mocked_exact_stop_once_preserves_queue_failed_devices_and_no_replay")
        # Pending inventory must not even probe resident or create an intent.
        pending = copy.deepcopy(value["state"])
        pending["rows"][0]["generation"]["status"] = "pending"
        Path(value["snapshot"]["path"]).write_text(json.dumps(pending))
        provisioner.state["conversion"] = None
        with patch.object(handoff, "validate_overlay", return_value=overlay), \
                patch.object(session, "admitted_resident") as resident:
            provisioner.convert_ref(current)
            resident.assert_not_called()
            assert provisioner.state["conversion"] is None
            checks.append("pending_REF_does_not_probe_stop_or_create_intent")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    ref = write_new(args.output, {"version": "v054-ref-handoff-pool-cpu-control-r1", "status": "passed",
        "checks": checks, "checks_passed": len(checks), "actual_model_calls": 0,
        "actual_process_signals": 0, "actual_service_changes": 0,
        "formal_queue_writes": 0, "formal_claims": 0,
        "source": reference(handoff.__file__), "control": reference(__file__)})
    print(json.dumps(ref))


if __name__ == "__main__":
    main()
