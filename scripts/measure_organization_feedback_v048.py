"""v048 feedback attribution with an explicit frozen representation binding.

Retirement and fixed-budget proof logic is reused unchanged. Only the projection
reader and its explicit Gamma identity differ; old measurements stay untouched.
"""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_projection_v048 as previous
from scripts import measure_organization_budget_v047 as budget_proof
from scripts.measure_organization_feedback_v047 import bind_self_retirement
from scripts.measure_organization_feedback_v045r1 import (
    UnboundRetirement, apply_termination_revision, read, reference, require,
)

VERSION = "organization-feedback-opportunities-v0.48"


def measure_retirement(episode_dir, *, representation, candidate_sha256):
    folder = Path(episode_dir).resolve()
    baseline = previous.measure_episode(folder, representation=representation, candidate_sha256=candidate_sha256)
    bindings, failures = {}, []
    candidates = [row for row in baseline.get("feedback_records", []) if row.get("tool") == "retire_member"
                  and row.get("no_actual_followup") is not None]
    if candidates:
        try:
            result = read(folder / "slot-result.json")
            evidence = read(folder / "organization-evidence.json")
            budget = result.get("team_budget", evidence.get("team_budget", {})).get("model", {})
            state_path = folder / "prepared/world/control/state.json"
            if not state_path.is_file():
                state_path = folder / "episode/end/control/state.json"
            state = read(state_path)
            inputs = previous.base.Inputs(folder, evidence, budget)
            relevant = {"model_response", "model_call", "policy_decision", "tool_call", "model_action_link", "model_tool_result",
                        "model_boundary_error", "process_violation", "execution_integrity_error", "permission_violation"}
            experience = []
            with (folder / "experience.jsonl").open() as stream:
                for line in stream:
                    if any('"kind": "' + kind + '"' in line for kind in relevant):
                        item = json.loads(line)
                        if item.get("kind") in relevant:
                            experience.append(item)
            require(not inputs.issues, "independent_actual_input_binding_unresolved")
            for row in candidates:
                # A rejected retirement is ordinary business feedback, not a
                # successful termination claim. Preserve its existing budget/
                # wait/end explanation unless the recorded member was retired.
                if row.get("feedback_ok") is False and result.get("boundary", {}).get("role_stops", {}).get(row.get("member")) != "retired":
                    continue
                try:
                    proof = bind_self_retirement(row, state=state, result=result, evidence=evidence, budget=budget,
                        inputs=inputs, experience=experience, folder=folder)
                    proof["source_refs"] = {name: reference(path) for name, path in {
                        "result": folder / "slot-result.json", "evidence": folder / "organization-evidence.json",
                        "world_state": state_path, "experience": folder / "experience.jsonl"}.items()}
                    bindings[row["feedback_id"]] = proof
                except (UnboundRetirement, OSError, KeyError, IndexError, TypeError, ValueError) as error:
                    failures.append({"feedback_id": row["feedback_id"], "member": row.get("member"), "detail": str(error)})
        except (UnboundRetirement, OSError, KeyError, IndexError, TypeError, ValueError) as error:
            failures.extend({"feedback_id": row["feedback_id"], "member": row.get("member"), "detail": str(error)} for row in candidates)
    result = apply_termination_revision(baseline, bindings, failures)
    result["version"] = "organization-retirement-opportunities-v0.48"
    result["inherited_projection_version"] = previous.VERSION
    return result


def apply_budget_revision(baseline, bindings, failures):
    result = copy.deepcopy(baseline)
    changes = []
    for row in result.get("feedback_records", []):
        proof = bindings.get(row["feedback_id"])
        if proof is None:
            continue
        prior = row["no_actual_followup"]["reason"]
        row["no_actual_followup"]["reason"] = budget_proof.REASON
        row["member_fixed_budget_attribution"] = copy.deepcopy(proof)
        changes.append({"feedback_id": row["feedback_id"], "member": row["member"],
            "originating_call_id": row["originating_call_id"], "rejected_call_id": proof["call_id"],
            "previous_reason": prior, "revised_reason": budget_proof.REASON,
            "presentation_unchanged": True, "feedback_denominator_retained": True})
    result.update(version=VERSION, inherited_feedback_version="organization-retirement-opportunities-v0.48", capacity_projection_version=previous.VERSION,
        original_capacity_retirement_measurement_sha256=digest(json_bytes(baseline)),
        member_fixed_budget_revision={"version": budget_proof.VERSION, "bindings": list(bindings.values()),
            "unresolved": failures, "classification_changes": changes,
            "actual_model_visibility_unchanged": True, "original_R_unchanged": True})
    if baseline.get("status") != "measured":
        return result
    records = result["feedback_records"]
    result["denominators"]["no_followup_reasons"] = dict(Counter(
        r["no_actual_followup"]["reason"] for r in records if r.get("no_actual_followup")))
    for tool, counts in result["denominators"].get("by_tool", {}).items():
        counts["no_followup_reasons"] = dict(Counter(r["no_actual_followup"]["reason"] for r in records
            if (r.get("tool") or "unknown") == tool and r.get("no_actual_followup")))
    facts = result["mechanism_gate_inputs"]
    facts["unresolved_no_followup_ids"] = [r["feedback_id"] for r in records if r.get("no_actual_followup")
        and r["no_actual_followup"]["reason"] in {"unknown_no_actual_followup", "episode_unclosed_or_fault"}]
    result["measurement_gaps"].extend({"reason": "member_fixed_budget_attribution_unresolved", **item} for item in failures)
    facts["resolved"] = (not result["measurement_gaps"] and not facts["unresolved_no_followup_ids"]
        and not facts.get("page_protocol_unresolved") and result.get("episode_closed") is True)
    return result


def revise_records(baseline, **original):
    """Pure revision API used by finite counterexamples and the file reader."""
    bindings, failures = {}, []
    for row in baseline.get("feedback_records", []):
        followup = row.get("no_actual_followup") or {}
        terminal = followup.get("terminal_detail", {})
        if (followup.get("reason") != "unknown_no_actual_followup"
                or terminal.get("status") != "model_budget_exhausted"):
            continue
        try:
            bindings[row["feedback_id"]] = budget_proof.bind_feedback(row, **original)
        except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
            failures.append({"feedback_id": row["feedback_id"], "member": row.get("member"), "detail": str(error)})
    return apply_budget_revision(baseline, bindings, failures)


def measure_episode(episode_dir, *, representation, candidate_sha256):
    folder = Path(episode_dir).resolve()
    baseline = measure_retirement(folder, representation=representation, candidate_sha256=candidate_sha256)
    candidates = [r for r in baseline.get("feedback_records", [])
        if (r.get("no_actual_followup") or {}).get("reason") == "unknown_no_actual_followup"
        and (r["no_actual_followup"].get("terminal_detail") or {}).get("status") == "model_budget_exhausted"]
    if not candidates:
        return apply_budget_revision(baseline, {}, [])
    try:
        result = revise_records(baseline, **budget_proof.read_episode(folder))
        result["member_fixed_budget_revision"]["sources"] = {name: budget_proof.reference(folder / name) for name in
            ("slot-result.json", "organization-evidence.json", "team-budget.json", "experience.jsonl")}
        return result
    except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
        return apply_budget_revision(baseline, {}, [{"feedback_id": r["feedback_id"], "member": r.get("member"),
            "detail": str(error)} for r in candidates])
