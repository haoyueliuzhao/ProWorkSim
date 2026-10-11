"""Release only v045's original fourteen unopened slots from saved host evidence.

No historical model, tokenizer, business test or acceptance is executed. The
original two phases and all their source bytes remain immutable.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts.run_ne_v021 import write
from scripts.software_organization_admission_v044 import EvidenceReader, reference
from scripts.software_organization_admission_v045 import source_files
from scripts.software_organization_resume_admission_v045 import bind_refs, read_path

VERSION = "software-organization-complete-admission-v0.45"
SOURCE = Path(__file__).resolve().parents[1]
ORIGINAL_PLAN = "d1db9ae8b6487792bd0e021751d0153ecdc5f1bf73800b5fc5b33e8c64f1f82b"
PRIOR_PLAN = "0dae4e08692a14f161016707c0c885f4a7b060c89dfb3d8ab6d69b8435244e8e"
ORIGINAL_TREE = "944e4ae925423b62af54db5c5bd1bef8c5c7f7684ed23a89a533ae4c73035163"
COST_SHA = "c7e4cb944115d8a63f6a324bbd2edac75f52f3f3079e7b2abf912697626e4ef5"
FIRST_SLOT = "org45-r0-s0-S1"
FIXED_SLOT = "org45-r1-s1-S1"
RETAINED_IDS = (
    FIRST_SLOT,
    "org45-r0-s0-F2",
    "org45-r0-s0-O3",
    "org45-r0-s1-F2",
    "org45-r0-s1-O3",
    "org45-r0-s1-S1",
    "org45-r1-s0-O3",
    "org45-r1-s0-S1",
    "org45-r1-s0-F2",
    FIXED_SLOT,
)
TEAM_LIMITS = {
    "max_decisions": 128,
    "max_attempts": 128,
    "max_total_tokens": 500000,
    "max_test_runs": 32,
}
OLD_ACTUAL = {"decisions": 198, "attempts": 191, "total_tokens": 2563352, "run_tests": 19}
NEW_CAPS = {"decisions": 1792, "attempts": 1792, "total_tokens": 7000000, "run_tests": 448}
ALLOWED_NEW_CODE = frozenset(
    {
        "scripts/measure_organization_budget_v045.py",
        "scripts/measure_organization_feedback_v045r2.py",
        "scripts/measure_organization_work_v045r2.py",
        "tests/test_measure_organization_budget_v045.py",
        "tests/test_measure_organization_work_v045r2.py",
        "scripts/software_organization_complete_admission_v045.py",
        "scripts/software_organization_complete_v045.py",
        "tests/test_software_organization_complete_admission_v045.py",
        "tests/test_software_organization_complete_v045.py",
    }
)
DEPENDENCIES = (
    "common",
    "model_references",
    "expected_actor_identity",
    "expected_state_sha256",
    "runtime_dependency_path",
    "source_partition",
    "business_bindings",
    "feedback_protocol",
    "batch_stop_policy",
)


def require(value, reason):
    if not value:
        raise ValueError("v045 original14 admission rejected: " + reason)


def budget_caps():
    return {
        "old_actual": dict(OLD_ACTUAL),
        "new": dict(NEW_CAPS),
        "combined": {key: OLD_ACTUAL[key] + NEW_CAPS[key] for key in OLD_ACTUAL},
        "old_unused_tokens": 2436648,
        "transfer_old_unused": False,
        "optional_probe_budget_authorized": False,
    }


def remaining_inventory(plan, retained_ids=RETAINED_IDS):
    """Filter the original plan; never invent a replacement order or seed."""
    units = plan.get("assignments", {})
    require(
        tuple(units) == tuple(f"block-r{r}-s{s}" for r in range(4) for s in range(2)),
        "original eight block order changed",
    )
    flat = [u for rows in units.values() for u in rows]
    ids = [u.get("slot_id") for u in flat]
    require(
        len(ids) == len(set(ids)) == 24 and tuple(retained_ids) == RETAINED_IDS,
        "original or retained identity inventory changed",
    )
    require(
        [u["slot_id"] for u in flat if u["slot_id"] in retained_ids] == list(RETAINED_IDS),
        "retained original prefix changed",
    )
    require(set(plan.get("cases", {})) == set(units), "case inventory incomplete")
    for worker, rows in units.items():
        cases = plan["cases"][worker]
        require(len(cases) == len(rows) == 3, "original cases incomplete")
        r, s = int(worker[7]), int(worker[10])
        for unit, case in zip(rows, cases, strict=True):
            require(
                unit["slot_id"] == f"org45-r{r}-s{s}-{unit['condition']}"
                and unit["sampling_seed"] == (202610100451, 202610100452)[s]
                and unit["first_member"]
                == ("member_001" if unit["condition"] == "S1" else f"member_{1 + (r + s) % 2:03d}")
                and all(case.get(k) == unit[k] for k in ("case_id", "condition", "first_member"))
                and case.get("team_limits") == TEAM_LIMITS,
                "case identity or shared budget changed",
            )
    remaining = {
        w: copy.deepcopy([u for u in rows if u["slot_id"] not in retained_ids])
        for w, rows in units.items()
    }
    remaining = {w: rows for w, rows in remaining.items() if rows}
    require(
        list(remaining)
        == ["block-r1-s1", "block-r2-s0", "block-r2-s1", "block-r3-s0", "block-r3-s1"]
        and [[u["condition"] for u in rows] for rows in remaining.values()]
        == [
            ["O3", "F2"],
            ["O3", "F2", "S1"],
            ["F2", "S1", "O3"],
            ["S1", "F2", "O3"],
            ["F2", "O3", "S1"],
        ],
        "original fourteen-slot order changed",
    )
    return remaining


def remaining_cases(plan, inventory):
    return {
        w: [
            copy.deepcopy(case)
            for case, unit in zip(plan["cases"][w], plan["assignments"][w], strict=True)
            if unit["slot_id"] in {u["slot_id"] for u in rows}
        ]
        for w, rows in inventory.items()
    }


def source_audit(plan, source_root=SOURCE):
    root = Path(source_root).resolve()
    old, current = plan["source_files"], source_files(root)
    require(
        bool(old) and all(current.get(name) == sha for name, sha in old.items()),
        "prior plan source bytes changed or disappeared",
    )
    added = set(current) - set(old)
    require(
        added == ALLOWED_NEW_CODE,
        "only the nine declared host measurement/driver/test additions are allowed",
    )
    hasher = hashlib.sha256()
    for name in sorted(n for n in current if n.startswith("src/") and n.endswith(".py")):
        hasher.update(name.encode())
        hasher.update((root / name).read_bytes())
    require(
        hasher.hexdigest() == ORIGINAL_TREE == plan["source"]["source_tree_sha256"],
        "model-visible source tree changed",
    )
    return {
        "all_prior_bytes_unchanged": True,
        "prior_file_count": len(old),
        "prior_files": dict(old),
        "new_files": {n: current[n] for n in sorted(added)},
        "source_files": current,
        "source_tree_sha256": hasher.hexdigest(),
    }


def validate_never_started(roots, inventory):
    checks = []
    for worker, units in inventory.items():
        for unit in units:
            paths = [Path(root) / worker / "actual/episodes" / unit["slot_id"] for root in roots]
            require(
                all(not p.exists() and not p.is_symlink() for p in paths),
                "remaining slot has an earlier partial launch",
            )
            checks.append(
                {
                    "slot_id": unit["slot_id"],
                    "worker": worker,
                    "checked_absent_paths": [str(p) for p in paths],
                    "never_started_in_either_run": True,
                    "replay_permitted": False,
                }
            )
    return checks


def validate_work_revision(old, new, rejected_call_id):
    """Allow only the recovered non-generated opportunity in old resource views."""
    for key in (
        "current_program_work",
        "pending_program_relations",
        "pending_semantic_relations",
        "cross_member_applicability",
        "recorded_R",
        "recorded_submitted",
    ):
        require(
            old.get(key) == new.get(key), "structural unknowns or work conclusions changed: " + key
        )
    require(
        old.get("cross_member_applicability") == "not_applicable_no_partner",
        "fixed historical S1 work cannot gain a partner",
    )
    for key in (
        "has_evidenced_cross_member_chain",
        "has_evidenced_cross_member_use",
        "has_use_linked_to_final_fixed_delivery",
    ):
        before, after = old.get(key), new.get(key)
        require(
            before == after or before is None and after is False,
            "fixed S1 aggregation changed beyond resolved no-partner applicability",
        )
    left, right = (
        old.get("current_information_work"),
        copy.deepcopy(new.get("current_information_work")),
    )

    def normalize(before, after):
        if isinstance(before, dict) and isinstance(after, dict):
            if "later_member_opportunities" in before and before != after:
                require(
                    before.get("status") == after.get("status") == "recorded"
                    and isinstance(rejected_call_id, str)
                    and bool(rejected_call_id)
                    and after.get("later_member_opportunities")
                    == before["later_member_opportunities"] + 1
                    and rejected_call_id not in before.get("later_member_call_ids", [])
                    and after.get("later_member_call_ids")
                    == before.get("later_member_call_ids", []) + [rejected_call_id],
                    "recovered opportunity count or identity does not match fixed refusal",
                )
                after["later_member_opportunities"] = before["later_member_opportunities"]
                after["later_member_call_ids"] = copy.deepcopy(before["later_member_call_ids"])
            for key in before.keys() & after.keys():
                normalize(before[key], after[key])
        elif isinstance(before, list) and isinstance(after, list):
            for a, b in zip(before, after):
                normalize(a, b)

    normalize(left, right)
    require(left == right, "information content, actual input or generation count changed")


def validate_review_slot(slot, result, old_feedback, old_stop, feedback, stop, old_work, work):
    identity = slot["slot_id"]
    require(
        identity == result.get("slot_id") == feedback.get("slot_id") == stop.get("slot_id"),
        "review slot/result identity mismatch",
    )
    formal = {k: result[k] for k in ("status", "R", "submitted", "complete_delivery")}
    require(
        formal["status"] == "closed"
        and formal["R"] in (0, 1)
        and old_stop.get("formal_result") == stop.get("formal_result") == formal,
        "review changed a formal result",
    )
    require(
        stop.get("version") == old_stop.get("version") == "v045-batch-stop-scope-v044r2"
        and stop.get("decision") == "continue"
        and stop.get("global_violations") == []
        and stop.get("unresolved") == [],
        "retained slot is not cleared under original stop policy",
    )
    require(
        all(
            stop.get(k) is False
            for k in (
                "R_used_for_scope",
                "restart_current_member",
                "feedback_visibility_changed",
                "model_visible_Gamma_changed",
            )
        ),
        "review changed episode treatment",
    )
    require(
        all(
            stop.get(k) == 0
            for k in (
                "new_model_calls",
                "new_tokenizer_calls",
                "new_test_or_acceptance_executions",
                "new_world_actions",
            )
        ),
        "review executed work",
    )
    old_records, records = old_feedback["feedback_records"], feedback["feedback_records"]
    require(
        len(old_records) == len(records) == result["usage"]["attempts"],
        "feedback record count changed",
    )
    differences = []
    for before, after in zip(old_records, records, strict=True):
        if before != after:
            differences.append(before.get("feedback_id"))
            require(
                identity == FIXED_SLOT
                and before.get("feedback_id") == "feedback-698"
                and before["no_actual_followup"]["reason"] == "unknown_no_actual_followup"
                and after["no_actual_followup"]["reason"] == "member_fixed_budget"
                and {
                    k: v
                    for k, v in before.items()
                    if k not in {"no_actual_followup", "member_fixed_budget_attribution"}
                }
                == {
                    k: v
                    for k, v in after.items()
                    if k not in {"no_actual_followup", "member_fixed_budget_attribution"}
                },
                "feedback payload, actual presentation or another attribution changed",
            )
            require(
                after["no_actual_followup"]
                == {**before["no_actual_followup"], "reason": "member_fixed_budget"},
                "original no-followup evidence changed beyond the derived reason",
            )
            proof = after.get("member_fixed_budget_attribution", {})
            require(
                proof.get("status") == "bound_original_member_fixed_budget"
                and proof.get("slot_id") == identity
                and proof.get("feedback_id") == "feedback-698"
                and proof.get("member_fixed_token_cap") == 500000
                and proof.get("member_accounted_tokens") == 498562
                and proof.get("member_available_tokens") == 1438
                and proof.get("hard_context_headroom_tokens") == 1058
                and all(
                    proof.get(k) is False
                    for k in (
                        "attempt_started",
                        "actual_output",
                        "world_side_effect",
                        "later_member_generation",
                        "actual_feedback_presentation_added",
                        "R_used_for_classification",
                    )
                )
                and proof.get("charged_tokens") == 0
                and proof.get("member_remains_stopped") is True,
                "saved fixed-member refusal proof is incomplete or changed",
            )
    require(
        differences == (["feedback-698"] if identity == FIXED_SLOT else []),
        "fixed-budget correction missing or excessive",
    )
    for key in (
        "all_saved_feedback_units",
        "protocol_feedback_saved_exactly",
        "with_later_actual_generation",
        "presented_in_later_actual_generation",
        "presented_in_first_actual_followup",
        "without_later_actual_generation",
    ):
        require(
            old_feedback["denominators"][key] == feedback["denominators"][key],
            "feedback denominator changed",
        )
    require(
        feedback.get("measurement_gaps") == []
        and feedback["mechanism_gate_inputs"].get("resolved") is True,
        "new feedback evidence remains unresolved",
    )
    if identity != FIRST_SLOT:
        require(
            feedback["projection_audit"] == old_feedback["projection_audit"],
            "existing actual-input projection changed",
        )
    if identity != FIXED_SLOT:
        require(work == old_work, "unaffected work measurement changed")
    else:
        require(
            old_stop.get("decision") == "measurement_pending",
            "old fixed-budget pending receipt changed",
        )
        affected = next(r for r in records if r["feedback_id"] == "feedback-698")
        validate_work_revision(
            old_work, work, affected["member_fixed_budget_attribution"].get("call_id")
        )
    return feedback["denominators"]


def build_admission(original_run, prior_run, review_path, *, source_root=SOURCE):
    roots = (Path(original_run).resolve(), Path(prior_run).resolve())
    reader, refs = EvidenceReader(), {}

    def load(label, path):
        value, refs[label] = read_path(reader, path)
        return value

    plans = [load(f"phase{i}_plan", root / "plan.json") for i, root in enumerate(roots)]
    for plan, expected in zip(plans, (ORIGINAL_PLAN, PRIOR_PLAN), strict=True):
        require(
            plan.get("plan_sha256")
            == expected
            == digest(json_bytes({k: v for k, v in plan.items() if k != "plan_sha256"})),
            "wrong or edited historical plan",
        )
    original, prior = plans
    require(
        all(original[k] == prior[k] for k in DEPENDENCIES),
        "historical model-visible dependencies differ",
    )
    source = source_audit(prior, source_root)
    inventory = remaining_inventory(original)
    never = validate_never_started(roots, inventory)
    expected = (set(RETAINED_IDS[:1]), set(RETAINED_IDS[1:]))
    retained = {}
    for phase, root in enumerate(roots):
        supervisor = load(f"phase{phase}_supervisor", root / "supervisor.json")
        finish = load(f"phase{phase}_finish", root / "finish.json")
        require(
            supervisor.get("status") == finish.get("status") == "closed_with_unknowns"
            and "ended_at" in supervisor
            and "ended_at" in finish
            and finish.get("publication", {}).get("status") == "pushed",
            "historical phase not terminal and published",
        )
        require(
            all(
                s.get("status") in {"complete", "stopped"}
                for s in supervisor.get("states", {}).values()
            ),
            "historical worker still active",
        )
        actual = {p.name: p for p in root.glob("block-*/actual/episodes/*")}
        require(set(actual) == expected[phase], "historical executed or partial inventory changed")
        for identity, folder in actual.items():
            result = load(identity + "/result", folder / "slot-result.json")
            budget = load(identity + "/budget", folder / "team-budget.json")
            require(
                result.get("slot_id") == identity
                and result.get("status") == "closed"
                and type(result.get("R")) is int
                and result["R"] in (0, 1),
                "retained result no longer closed",
            )
            retained[identity] = {
                "slot_id": identity,
                "execution_phase": phase,
                "episode": str(folder),
                "result": refs[identity + "/result"],
                "budget": refs[identity + "/budget"],
                "usage": result["usage"],
                "run_tests": budget["tests"]["used"],
                "R": result["R"],
                "submitted": result["submitted"],
                "recollection_permitted": False,
            }
        for path in sorted((root / "mechanism-stops").glob("*.json")):
            load(f"phase{phase}_stop/{path.name}", path)
    totals = {
        key: sum(v["usage"][key] for v in retained.values())
        for key in ("decisions", "attempts", "total_tokens")
    }
    totals["run_tests"] = sum(v["run_tests"] for v in retained.values())
    require(
        totals == OLD_ACTUAL and sum(v["R"] for v in retained.values()) == 6,
        "retained result/cost arithmetic changed",
    )
    cost_ref = {
        "path": str(roots[1].parent / "v045-resume-final-analysis/cost-review.json"),
        "sha256": COST_SHA,
    }
    cost = reader.read(cost_ref)
    require(
        cost.get("final") is True
        and cost.get("issues") == []
        and cost["inventory"]["closed"] == 10
        and cost["inventory"]["not_started"] == 14
        and cost["totals"]["actual_model_calls"] == 191,
        "sealed original ten-slot cost evidence changed",
    )
    require(
        all(
            cost["guard_summary"].get(k) is True
            for k in (
                "all_actual_workers_source_unchanged",
                "all_actual_workers_common_3_3_exact",
                "all_actual_workers_profile_identity_exact",
                "all_actual_slot_rng_restored_exactly",
                "all_actual_slot_guard_checks_pass",
                "all_actual_slot_usage_reconciliations_pass",
            )
        )
        and cost["resource_guard_summary"].get("all_observed_resource_checks_pass") is True,
        "historical guard evidence failed",
    )
    require(
        [row["slot_id"] for row in cost["slots"]] == list(RETAINED_IDS),
        "sealed cost review retained slot order changed",
    )
    for row in cost["slots"]:
        identity = row["slot_id"]
        require(
            row["usage"] == retained[identity]["usage"]
            and row["R"] == retained[identity]["R"]
            and row["submitted"] == retained[identity]["submitted"],
            "saved result no longer matches its sealed cost audit",
        )
        for key, label in (("slot-result.json", "result"), ("team-budget.json", "budget")):
            ref = row["sources"][key]
            require(
                ref["sha256"] == retained[identity][label]["sha256"]
                and Path(ref["path"]).resolve() == Path(retained[identity][label]["path"]),
                "retained original artifact hash changed after audit",
            )
            reader.path(ref)
        reader.path(row["sources"]["evaluation-guard.json"])
    for plan in plans:
        bind_refs([plan["qualification"], plan["common"], plan["model_references"]], reader)
        require(
            reader.read(plan["qualification"]).get("passed") is True,
            "historical CPU qualification was not passed",
        )
    bind_refs(prior["resume_admission"], reader)
    first_review = reader.read(prior["first_slot_review"])
    require(first_review.get("passed") is True, "original interface correction receipt failed")
    summary, summary_ref = read_path(reader, review_path)
    require(
        summary.get("version") == "v045-original10-fixed-budget-remeasurement-r2"
        and summary.get("passed") is True,
        "new retained review did not pass",
    )
    require(
        summary.get("unchanged_results_fees_inputs_outputs") is True
        and summary.get("structural_unknowns_retained") == 3,
        "original work and execution invariants missing",
    )
    require(
        all(
            summary.get(k) == 0
            for k in (
                "new_model_calls",
                "new_tokenizer_calls",
                "new_test_or_acceptance_executions",
                "new_world_actions",
            )
        ),
        "review executed work",
    )
    controls = reader.read(summary["measurement_controls"])
    require(
        controls.get("passed") is True
        and controls.get("tests_passed") == 27
        and any(
            c.get("exit_code") == 0 and c.get("tests_passed") == 27
            for c in controls.get("commands", [])
        ),
        "finite measurement controls failed",
    )
    expected_sources = {name for name in ALLOWED_NEW_CODE if "measure_organization" in name}
    require(
        set(controls.get("sources", {})) == expected_sources
        and all(
            source["source_files"].get(name) == ref["sha256"]
            for name, ref in controls["sources"].items()
        ),
        "measurement controls source binding changed",
    )
    bind_refs([controls["sources"], controls["commands"]], reader)
    slots = summary.get("slots", [])
    require(
        [s.get("slot_id") for s in slots] == list(RETAINED_IDS),
        "new review must cover exactly retained ten in original order",
    )
    counts, reasons = Counter(), Counter()
    for slot in slots:
        identity = slot["slot_id"]
        folder = Path(retained[identity]["episode"])
        for key, name in (
            ("result", "slot-result.json"),
            ("budget", "team-budget.json"),
            ("old_feedback", "feedback-loop.json"),
            ("old_stop", "batch-stop-assessment.json"),
        ):
            require(
                slot[key] == reference(folder / name),
                "review artifact is not the original saved " + key,
            )
        values = {
            key: reader.read(slot[key])
            for key in (
                "result",
                "old_feedback",
                "old_stop",
                "revised_feedback",
                "revised_work",
                "revised_batch_stop",
            )
        }
        old_work = load(identity + "/old_work", folder / "work-use.json")
        if identity == FIRST_SLOT:
            require(
                slot["revised_feedback"] == first_review["revised_feedback"]
                and slot["revised_batch_stop"] == first_review["revised_batch_stop"],
                "first-slot existing correction changed",
            )
        denom = validate_review_slot(
            slot,
            values["result"],
            values["old_feedback"],
            values["old_stop"],
            values["revised_feedback"],
            values["revised_batch_stop"],
            old_work,
            values["revised_work"],
        )
        counts.update(
            {
                "feedback_saved": denom["all_saved_feedback_units"],
                "presented": denom["presented_in_first_actual_followup"],
                "no_followup": denom["without_later_actual_generation"],
            }
        )
        reasons.update(denom["no_followup_reasons"])
    require(
        dict(counts) == {"feedback_saved": 191, "presented": 175, "no_followup": 16}
        and all(summary["totals"].get(k) == v for k, v in counts.items())
        and reasons.get("member_fixed_budget") == 1
        and not reasons.get("unknown_no_actual_followup"),
        "corrected 191 = 175 + 16 attribution does not close",
    )
    output = {
        "version": VERSION,
        "passed": True,
        "original_run_root": str(roots[0]),
        "prior_run_root": str(roots[1]),
        "original_plan": refs["phase0_plan"],
        "prior_plan": refs["phase1_plan"],
        "historical_refs": refs,
        "source_audit": source,
        "source_files": source["source_files"],
        "retained_slots": [retained[i] for i in RETAINED_IDS],
        "retained_review": summary_ref,
        "original_cost_review": cost_ref,
        "remaining_assignments": inventory,
        "remaining_cases": remaining_cases(original, inventory),
        "never_started_evidence": never,
        "budget_caps": budget_caps(),
        "feedback_totals": dict(counts),
        "no_followup_reasons": dict(reasons),
        "qualification_reuse": [p["qualification"] for p in plans],
        "first_slot_review": prior["first_slot_review"],
        "model_identity": {k: original[k] for k in DEPENDENCIES},
        "bound_evidence": list(reader.checked.values()),
        "new_model_calls": 0,
        "new_tokenizer_calls": 0,
        "new_test_or_acceptance_executions": 0,
        "new_world_actions": 0,
        "new_backward_calls": 0,
        "scope": "Original fourteen unopened slots only; retain all ten results and both old pauses. Host fixed-member-budget attribution only, no model-visible or batch-stop scope change.",
    }
    output["admission_sha256"] = digest(json_bytes(output))
    return output


def create_admission(original_run, prior_run, review_path, output, *, source_root=SOURCE):
    output = Path(output)
    require(not output.exists(), "admission output already exists; preserve prior receipt")
    value = build_admission(original_run, prior_run, review_path, source_root=source_root)
    write(output, value)
    return value


def validate_admission(path, *, source_root=SOURCE):
    reader = EvidenceReader()
    value, _ = read_path(reader, path)
    require(
        value.get("version") == VERSION
        and value.get("passed") is True
        and value.get("admission_sha256")
        == digest(json_bytes({k: v for k, v in value.items() if k != "admission_sha256"})),
        "saved admission digest or status changed",
    )
    rebuilt = build_admission(
        value["original_run_root"],
        value["prior_run_root"],
        value["retained_review"]["path"],
        source_root=source_root,
    )
    require(
        rebuilt == value,
        "saved admission no longer binds original evidence and remaining inventory",
    )
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("create", "validate"))
    parser.add_argument("--original-run", type=Path)
    parser.add_argument("--prior-run", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = (
        create_admission(args.original_run, args.prior_run, args.review, args.output)
        if args.mode == "create"
        else validate_admission(args.output)
    )
    print(
        {"passed": value["passed"], "remaining": 14, "admission_sha256": value["admission_sha256"]}
    )


if __name__ == "__main__":
    main()
