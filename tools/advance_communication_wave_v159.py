"""Automatic score-blind engineering gate after all first-wave work drains."""
from __future__ import annotations

from functools import lru_cache
import importlib.util
import json
import sqlite3

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
from proworksim.software_communication_admission_v157 import assess_measurement


def build_gate(coordinator):
    from proworksim import software_benchmark_scope_v159 as scope
    target = coordinator.output/"wave1-engineering-gate.json"
    if target.is_file():
        return reference(target)
    folder = coordinator.output/"wave1-measurement-audit"
    if (folder/"attempt.json").exists():
        return None  # A failed audit is reviewed, never repeatedly hidden/replaced.
    planned = [r for r in coordinator.plan["rows"] if r["wave"] == 1]
    slots = {r["slot_id"] for r in planned}
    terminal = slots & (set(coordinator.finished) | set(coordinator.exceptions) | set(coordinator.deferred))
    if len(terminal) != len(planned) or not planned:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    write_new(folder/"attempt.json", {"planned_episodes": len(planned), "terminal_episodes": len(terminal),
                                     "scores_consulted": False, "model_calls": 0})
    errors, observers, unresolved = [], [], []
    try:
        authorization = scope.require_allowed("v157.run")
        for ref in scope.load(authorization["source_index"])["files"]:
            checked(ref)
        with sqlite3.connect(scope.LEDGER_FILE.resolve().as_uri()+"?mode=ro", uri=True) as db:
            entered_slots = {r[0] for r in db.execute("SELECT DISTINCT slot_id FROM requests")}
        for row in planned:
            episode = scope.BATCH_ROOT/"episodes"/str(row["slot_index"])
            paths = list(episode.glob("controller-output*/model-ledger/collaboration-observation/summary.json"))
            if not paths:
                unresolved.append({"slot_id": row["slot_id"], "reason": "no_observer_closure"})
                if row["slot_id"] in entered_slots:
                    errors.append({"slot_id": row["slot_id"],
                                   "reason": "entered_model_without_observer_closure"})
                continue
            if len(paths) != 1:
                errors.append({"slot_id": row["slot_id"], "reason": "ambiguous_observer_closure"})
                continue
            value = json.loads(paths[0].read_bytes())
            observers.append({"slot_id": row["slot_id"], "summary": reference(paths[0]),
                              "completion_status": value.get("completion_status"),
                              "presentations_complete": value.get("coverage", {}).get("presentations"),
                              "runtime_measurement_errors": value.get("runtime_measurement_errors")})
            if value.get("runtime_measurement_errors"):
                errors.append({"slot_id": row["slot_id"], "reason": "observer_measurement_error"})
            # Source attribution has an explicitly approved estimated 98% gate.
            # A nonzero unknown byte count is recorded, not a replacement 100%
            # source gate. The physical audit independently verifies every raw
            # request/response and its actual usage, including unknown spans.
            if value.get("completion_status") != "normal":
                unresolved.append({"slot_id": row["slot_id"], "reason": "partial_observer_closure"})
        manifest = scope.ROOT/"runs/software-benchmark-v055/tokenizer-r1/manifest.json"
        counter, metadata = load_official_content_counter(manifest, manifest_sha256=reference(manifest)["sha256"])
        spec = importlib.util.spec_from_file_location(
            "communication_physical_audit_v157", scope.ROOT/"tools/audit_communication_measurement_v157.py")
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        measurement = audit.audit(scope.LEDGER_FILE, [scope.BATCH_ROOT/"episodes"],
            lru_cache(maxsize=16384)(counter), metadata["tokenizer_id"], slots=slots,
            mechanism_gates={"G0-4": not errors, "G0-5": not errors, "G0-6": not errors})
        evidence = write_new(folder/"physical-measurement.json", measurement)
        observation = write_new(folder/"observer-integrity.json", {
            "observers": observers, "errors": errors, "unresolved": unresolved,
            "unreported_channels_not_assumed_complete": True, "scores_consulted": False})
        grant = scope.load(reference(scope.original_scope.ARTIFACT_ROOT/"user-amendment-r1/authorization.json"))
        measured = assess_measurement(measurement, grant)
        gate = {**measured, "wave": 1, "planned_episodes": len(planned),
            "terminal_episodes": len(terminal), "advance_to_wave_2": measured["passed"] and not errors,
            "exceptions_deferred": unresolved, "scores_consulted": False,
            "original_wave1_planned_episodes": 36,
            "predecessor_called_slots_excluded_not_claimed_passed": coordinator.plan['used_original_slots'],
            "original_full72_denominator_retained": True,
            "source_precision_gate": "local_token_estimate_not_UTF8_byte_fraction"}
        gate.update(physical_evidence=evidence, observer_evidence=observation,
                    source_index=authorization["source_index"], score_based_changes=False)
        return write_new(target, gate)
    except Exception as error:
        write_new(folder/"failure.json", {"status": "engineering_gate_needs_repair",
            "type": type(error).__name__, "reason": str(error), "scores_consulted": False,
            "automatic_model_replay": False, "previous_tasks_unchanged": True})
        return None
