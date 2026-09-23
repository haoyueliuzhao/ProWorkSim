"""X1/X2 finite reconciliation in real worlds through public project ports.

Expected business conclusions are literal manual truth. Controllers install
synthetic packages, inject explicitly labeled wrong products, and recover a real
provider. The worker receives only tools/observe/call, never hidden state.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec
from proworksim.storage import digest
from proworksim.templates.reconciliation import literal_truth, package
from proworksim.workers.reconciliation import ReconciliationWorker
from proworksim.world_core import WorldCore

CASES = (
    "combined",
    "renamed_reordered_split",
    "routed_material",
    "unavailable_then_recovered",
    "negative_controls",
    "review_repair",
)
COMMON_CHECKS = (
    "public_strategy_delivers",
    "actual_immutable_delivery_passes_domain",
    "business_truth_is_independently_correct",
    "unresolved_is_valid_explicit_exit",
    "source_bytes_not_rewritten",
    "worker_trace_matches_independent_port_capture",
)
END_CHECKS = ("all_sources_preserved_at_end",)
CHECKS = {
    "combined": COMMON_CHECKS + END_CHECKS,
    "renamed_reordered_split": COMMON_CHECKS + END_CHECKS,
    "routed_material": COMMON_CHECKS + END_CHECKS,
    "unavailable_then_recovered": (
        "unavailable_table_is_world_blocking_not_zero",
        "blocked_exit_has_no_fabricated_delivery",
    )
    + COMMON_CHECKS
    + END_CHECKS,
    "negative_controls": COMMON_CHECKS
    + (
        "reject_actual_omitted_group",
        "reject_actual_duplicate_group",
        "reject_actual_incomparable_difference",
        "reject_actual_unknown_as_zero",
        "reject_actual_correct_metadata_wrong_table",
        "recover_under_same_requirement",
        "no_requirement_replacement_for_content_errors",
    )
    + END_CHECKS,
    "review_repair": COMMON_CHECKS
    + (
        "actual_omission_fails_content",
        "review_finding_derived_from_actual_read_set",
        "public_worker_repaired_same_work",
        "repair_content_correct",
        "reviewer_reads_real_restored_conflict",
        "repair_preserves_unchanged_requirement_and_old_bytes",
        "unrelated_rows_preserved_after_targeted_repair",
    )
    + END_CHECKS,
}
COMPARISONS = ("two_organizations_match_each_other_and_literal_truth",)
MEASUREMENT_VERSION = "reconciliation-measurement-v0.9.1"

PROTOCOL = {
    "suite": "finite-reconciliation-X1-X2-v0.9",
    "cases": CASES,
    "checks": CHECKS,
    "planned_checks": sum(len(names) for names in CHECKS.values()),
    "comparisons": COMPARISONS,
    "measurement_version": MEASUREMENT_VERSION,
    "measurement_history": "Development dev1-dev4 recorded executed checks only. This version freezes the 58 planned check names and pads not-executed checks; no prior report is relabeled or backfilled.",
    "truth": "Nine manually enumerated groups, 18 source records; exact unit conversion and no fuzzy matching or currency conversion",
    "variation": "Combined versus split whole-field JSON, row order, project aliases, actor names/display names, filenames and source locations",
    "not_executed": "Construction failures preserve traceback and all declared check names; missing executions are failed checks with not_executed=true. Executed and planned denominators are separate; layout comparison is additional.",
    "scope": "Synthetic finite reconciliation, public program strategy, actual immutable files/submissions; no model or training benefit claim",
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def public_port(session, records):
    class Port:
        __slots__ = ()

        def tools(self):
            value = session.tools()
            records.append({"kind": "tools", "value": copy.deepcopy(value)})
            return value

        def observe(self):
            value = session.observe()
            records.append({"kind": "observation", "value": copy.deepcopy(value)})
            return value

        def call(self, action, **arguments):
            value = session.call(action, **arguments)
            records.append(
                {
                    "kind": "call",
                    "action": action,
                    "arguments": copy.deepcopy(arguments),
                    "response": copy.deepcopy(value),
                }
            )
            return value

    return Port()


class Evidence:
    def __init__(self, name, output):
        self.name, self.output = name, Path(output)
        self.calls, self.capture, self.workers, self.checks, self.evaluations = [], [], [], [], []
        self.world = None
        self.owner = "fin_operator" if name == "renamed_reordered_split" else "analyst"
        self.reviewer = "quality_reader" if name == "renamed_reordered_split" else "reviewer"

    def call(self, actor, action, **arguments):
        result = self.world.session(actor, None if action == "install_project" else "A").call(
            action, **arguments
        )
        self.calls.append(
            {
                "actor": actor,
                "action": action,
                "arguments": copy.deepcopy(arguments),
                "response": copy.deepcopy(result),
            }
        )
        if not result.get("ok"):
            raise AssertionError(result)
        return result["result"]

    def check(self, name, actual, expected=True):
        if name not in CHECKS[self.name] or any(check["name"] == name for check in self.checks):
            raise AssertionError("Undeclared or repeated reconciliation check: " + name)
        self.checks.append(
            {
                "name": name,
                "actual": copy.deepcopy(actual),
                "expected": copy.deepcopy(expected),
                "passed": actual == expected,
                "not_executed": False,
            }
        )

    def evaluate(self, submission):
        value = self.world.evaluate_submission("A", "A::reconcile", submission["submission_id"])
        self.evaluations.append(copy.deepcopy(value))
        return value

    def worker(self):
        worker = ReconciliationWorker(
            public_port(self.world.session(self.owner, "A"), self.capture),
            split=self.name == "renamed_reordered_split",
        )
        value = worker.run("A::reconcile")
        self.workers.append({"outcome": copy.deepcopy(value), "transcript": worker.transcript})
        return value

    def setup(self):
        self.world = WorldCore.create(
            self.output / "world",
            WorldSpec(
                world_id="reconciliation-" + self.name,
                actors={
                    self.owner: {
                        "display_name": "资料核对员"
                        if self.name == "renamed_reordered_split"
                        else "Analyst"
                    },
                    self.reviewer: {"display_name": "Review desk"},
                },
                bootstrap_grants=[
                    {"actor_id": self.reviewer, "scope": "world", "power": "install_project"}
                ],
            ),
        )
        config = package(
            owner=self.owner,
            reviewer=self.reviewer,
            variant=self.name == "renamed_reordered_split",
            hidden_right=self.name in {"routed_material", "unavailable_then_recovered"},
            unavailable=self.name == "unavailable_then_recovered",
            review=self.name in {"negative_controls", "review_repair"},
        )
        self.call(self.reviewer, "install_project", package=config)
        self.initial = copy.deepcopy(self.world.store.load())
        self.source_hashes = {
            oid: digest(self.world.store.version_path(obj, "v1").read_bytes())
            for oid, obj in self.initial["artifacts"].items()
        }

    def immutable_sources(self):
        state = self.world.store.load()
        return all(
            digest(self.world.store.version_path(state["artifacts"][oid], "v1").read_bytes())
            == value
            for oid, value in self.source_hashes.items()
        )


def business_truth(data):
    return {
        r["key"][1]: {k: r[k] for k in ("status", "left_value", "right_value", "delta")}
        for r in data["reconciliation"]["rows"]
    }


def replace_delivery(ev, previous, data):
    ev.call(
        ev.owner,
        "withdraw",
        work_id="A::reconcile",
        submission_id=previous["submission_id"],
        reason="Explicit controlled erroneous delivery or same-requirement repair",
    )
    ev.call(
        ev.owner,
        "write_object",
        alias="comparison",
        work_id="A::reconcile",
        data=data,
        dependencies=list(data["sources"].values()),
    )
    return ev.call(ev.owner, "submit", work_id="A::reconcile", artifacts=["comparison"])


def negative_controls(ev, good):
    latest = good["submission"]
    for defect in (
        "omitted_group",
        "duplicate_group",
        "incomparable_difference",
        "unknown_as_zero",
        "correct_metadata_wrong_table",
    ):
        bad = copy.deepcopy(good["data"])
        rows = bad["reconciliation"]["rows"]
        by_metric = {r["key"][1]: r for r in rows}
        if defect == "omitted_group":
            bad["reconciliation"]["rows"] = [r for r in rows if r["key"][1] != "cost"]
        elif defect == "duplicate_group":
            rows.append(copy.deepcopy(rows[0]))
        elif defect == "incomparable_difference":
            by_metric["fx"].update(status="matched", left_value=6, right_value=6, delta=0)
        elif defect == "unknown_as_zero":
            by_metric["unknown"].update(status="conflict", left_value=0, right_value=8, delta=-8)
        else:
            by_metric["cost"]["right_value"] = 80
        latest = replace_delivery(ev, latest, bad)
        result = ev.evaluate(latest)
        ev.check("reject_actual_" + defect, result["passed"], False)
    repaired = replace_delivery(ev, latest, good["data"])
    ev.check("recover_under_same_requirement", ev.evaluate(repaired)["passed"])
    state = ev.world.store.load()
    ev.check(
        "no_requirement_replacement_for_content_errors",
        [list(state["work_items"]), state["work_items"]["A::reconcile"]["requirement_version"]],
        [["A::reconcile"], 1],
    )


def review_repair(ev, good):
    bad = copy.deepcopy(good["data"])
    bad["reconciliation"]["rows"] = [
        row for row in bad["reconciliation"]["rows"] if row["key"][1] != "cost"
    ]
    wrong = replace_delivery(ev, good["submission"], bad)
    ev.check("actual_omission_fails_content", ev.evaluate(wrong)["passed"], False)
    inspected = ev.call(
        ev.reviewer,
        "inspect_submission",
        work_id="A::reconcile",
        submission_id=wrong["submission_id"],
    )
    # The reviewer reads actual returned fixed versions and real source material.
    versions = wrong["artifact_versions"]
    oid, vid = next(iter(versions.items()))
    actual = ev.call(
        ev.reviewer, "read_object", object_id=oid, version_id=vid, work_id="A::reconcile"
    )
    source = ev.call(
        ev.reviewer, "read_object", alias="ledger", version_id="v1", work_id="A::reconcile"
    )
    missing = {r["metric"] for r in source["data"]["records"]} - {
        r["key"][1] for r in actual["data"]["reconciliation"]["rows"]
    }
    ev.check("review_finding_derived_from_actual_read_set", sorted(missing), ["cost"])
    source_ref = {
        "object_id": source["reference"]["artifact_id"],
        "version_id": "v1",
        "locator": ["records", 2],
    }
    issue = ev.call(
        ev.reviewer,
        "raise_issue",
        work_id="A::reconcile",
        submission_id=wrong["submission_id"],
        issue_key="missing-cost",
        object_id=oid,
        version_id=vid,
        locator=["reconciliation", "rows"],
        description="The cost key present in the ledger is absent from the delivered comparison",
        evidence=[source_ref],
        blocking=True,
    )
    old_version_bytes = ev.world.store.version_path(
        ev.world.store.load()["artifacts"][oid], vid
    ).read_bytes()
    repaired = ev.worker()
    ev.check(
        "public_worker_repaired_same_work",
        [repaired["status"], repaired.get("work_id")],
        ["submitted", "A::reconcile"],
    )
    repaired_sub = repaired["submission"]
    ev.check("repair_content_correct", ev.evaluate(repaired_sub)["passed"])
    new_vid = repaired_sub["artifact_versions"][oid]
    ev.call(ev.owner, "read_object", object_id=oid, version_id=new_vid, work_id="A::reconcile")
    response = ev.call(
        ev.owner,
        "respond_issue",
        issue_id=issue["issue_id"],
        response_key="restored-cost",
        submission_id=repaired_sub["submission_id"],
        body="Restored the omitted cost comparison and retained its real conflict; other rows unchanged",
        evidence=[
            {"object_id": oid, "version_id": new_vid, "locator": ["reconciliation", "rows", 2]}
        ],
    )
    new_vid = repaired_sub["artifact_versions"][oid]
    new_read = ev.call(
        ev.reviewer, "read_object", object_id=oid, version_id=new_vid, work_id="A::reconcile"
    )
    restored = next(r for r in new_read["data"]["reconciliation"]["rows"] if r["key"][1] == "cost")
    ev.check(
        "reviewer_reads_real_restored_conflict",
        [restored["status"], restored["delta"]],
        ["conflict", -10],
    )
    decision = ev.call(
        ev.reviewer,
        "decide_issue",
        issue_id=issue["issue_id"],
        response_id=response["response_id"],
        decision_key="cost-confirmed",
        decision="accept_fix",
        reason="Read new exact delivery: the omitted cost group is present with both source values",
    )
    ev.call(
        ev.reviewer, "approve", work_id="A::reconcile", submission_id=repaired_sub["submission_id"]
    )
    state = ev.world.store.load()
    ev.check(
        "repair_preserves_unchanged_requirement_and_old_bytes",
        state["work_items"]["A::reconcile"]["requirement_version"] == 1
        and len(state["work_items"]) == 1
        and ev.world.store.version_path(state["artifacts"][oid], vid).read_bytes()
        == old_version_bytes,
    )
    ev.check(
        "unrelated_rows_preserved_after_targeted_repair",
        [r for r in repaired["data"]["reconciliation"]["rows"] if r["key"][1] != "cost"],
        bad["reconciliation"]["rows"],
    )
    return {"inspection": inspected, "issue": issue, "response": response, "decision": decision}


def execute(ev):
    ev.setup()
    first = ev.worker()
    if ev.name == "unavailable_then_recovered":
        ev.check("unavailable_table_is_world_blocking_not_zero", first["status"], "world_blocked")
        state = ev.world.store.load()
        ev.check(
            "blocked_exit_has_no_fabricated_delivery",
            state["work_items"]["A::reconcile"]["submissions"],
            [],
        )
        ev.call(
            ev.reviewer,
            "set_information_availability",
            route_id="right-material",
            available=True,
            reason="The previously unavailable actual statement is now releasable",
        )
        first = ev.worker()
    ev.check("public_strategy_delivers", first["status"], "submitted")
    if first["status"] != "submitted":
        raise AssertionError(first)
    result = ev.evaluate(first["submission"])
    ev.check("actual_immutable_delivery_passes_domain", result["passed"])
    ev.check(
        "business_truth_is_independently_correct", business_truth(first["data"]), literal_truth()
    )
    ev.check(
        "unresolved_is_valid_explicit_exit",
        first["data"]["reconciliation"]["summary"],
        {
            "matched": 1,
            "converted": 1,
            "conflict": 1,
            "incomparable": 3,
            "missing": 2,
            "ambiguous": 1,
        },
    )
    ev.check("source_bytes_not_rewritten", ev.immutable_sources())
    ev.check(
        "worker_trace_matches_independent_port_capture",
        [entry for w in ev.workers for entry in w["transcript"]],
        ev.capture,
    )
    details = None
    if ev.name == "negative_controls":
        negative_controls(ev, first)
    elif ev.name == "review_repair":
        details = review_repair(ev, first)
    ev.check("all_sources_preserved_at_end", ev.immutable_sources())
    return {
        "business": business_truth(first["data"]),
        "details": details,
        "status": first["status"],
    }


def run_case(name, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    ev = Evidence(name, output)
    outcome, error = None, None
    try:
        outcome = execute(ev)
    except Exception:
        error = traceback.format_exc()
    for check_name in CHECKS[name]:
        if not any(check["name"] == check_name for check in ev.checks):
            ev.checks.append({"name": check_name, "passed": False, "not_executed": True})
    result = {
        "case": name,
        "measurement_version": MEASUREMENT_VERSION,
        "total_checks": len(CHECKS[name]),
        "executed_checks": sum(not check["not_executed"] for check in ev.checks),
        "not_executed": sum(check["not_executed"] for check in ev.checks),
        "passed": error is None and all(c["passed"] for c in ev.checks),
        "construction_error": error,
        "checks": ev.checks,
        "calls": ev.calls,
        "public_capture": ev.capture,
        "workers": ev.workers,
        "evaluations": ev.evaluations,
        "outcome": outcome,
    }
    if ev.world:
        write_json(output / "final-state.json", ev.world.store.load())
    write_json(output / "report.json", result)
    return result


def run(output, workers=4, cases=CASES):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    selected_protocol = {
        **PROTOCOL,
        "selected_cases": cases,
        "selected_planned_checks": sum(len(CHECKS[name]) for name in cases),
    }
    write_json(output / "protocol.json", selected_protocol)
    started = datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda name: run_case(name, output / name), cases))
    by_name = {r["case"]: r for r in results}
    comparisons = []
    if all(name in by_name for name in ("combined", "renamed_reordered_split")):
        a, b = [by_name[name] for name in ("combined", "renamed_reordered_split")]
        comparisons.append(
            {
                "name": COMPARISONS[0],
                "not_executed": not bool(a["outcome"] and b["outcome"]),
                "passed": bool(
                    a["outcome"]
                    and b["outcome"]
                    and a["outcome"]["business"] == b["outcome"]["business"] == literal_truth()
                ),
            }
        )
    result = {
        "source_before": before,
        "source_after": code_identity(),
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "protocol": selected_protocol,
        "measurement_version": MEASUREMENT_VERSION,
        "cases": results,
        "comparisons": comparisons,
        "planned_cases": len(cases),
        "completed_cases": sum(r["construction_error"] is None for r in results),
        "total_checks": sum(len(CHECKS[name]) for name in cases),
        "executed_checks": sum(not c["not_executed"] for r in results for c in r["checks"]),
        "not_executed": sum(c["not_executed"] for r in results for c in r["checks"]),
        "total_comparisons": len(comparisons),
        "not_executed_comparisons": sum(c["not_executed"] for c in comparisons),
        "passed_checks": sum(c["passed"] for r in results for c in r["checks"]),
        "passed": all(r["passed"] for r in results) and all(c["passed"] for c in comparisons),
    }
    write_json(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--cases", nargs="*", choices=CASES)
    args = parser.parse_args()
    result = run(args.output, args.workers, args.cases or CASES)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "passed",
                    "planned_cases",
                    "completed_cases",
                    "total_checks",
                    "executed_checks",
                    "not_executed",
                    "passed_checks",
                )
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)
