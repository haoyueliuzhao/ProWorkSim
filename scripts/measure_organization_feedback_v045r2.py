"""v045r1 feedback facts plus strict original member-fixed-budget attribution.

Only the derived reason changes. Projection, contents, actual presentations,
page accounting, retirement proof, formal outcome and historical receipts stay.
"""
from __future__ import annotations

from collections import Counter
import copy
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_budget_v045 as budget_proof
from scripts import measure_organization_feedback_v045r1 as previous

VERSION = "organization-feedback-opportunities-v0.45r2"


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
    result.update(version=VERSION, inherited_feedback_version=previous.VERSION,
        original_v045r1_remeasurement_sha256=digest(json_bytes(baseline)),
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


def measure_episode(episode_dir):
    folder = Path(episode_dir).resolve()
    baseline = previous.measure_episode(folder)
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
