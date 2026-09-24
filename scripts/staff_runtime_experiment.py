"""R1/R2: independent public role policies through one finite runtime.

Controller installs declared fixtures and measures only. It never passes findings,
prepared bodies, evaluator returns, or hidden truth to policy contexts. The v0.9
controlled baseline remains a separate world whose results are compared semantically.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.issues import derive_issue_view
from proworksim.core.world import WorldSpec
from proworksim.storage import digest
from proworksim.templates.reconciliation import literal_truth, package as finance_package
from proworksim.templates.research_review import package as report_package
from proworksim.workers.reconciliation import ReconciliationWorker
from proworksim.workers.team_policies import (
    ReconciliationPolicy,
    ReportAuthorPolicy,
    ReviewerPolicy,
)
from proworksim.world_core import WorldCore

CASES = (
    "correct",
    "two_partial",
    "rebuttal",
    "reconciliation",
    "unavailable_parallel",
    "illegal_action",
    "private_visibility",
)
GROUPS = {"R1": list(CASES[:4]), "R2": list(CASES)}
COMMON = [
    "all_expected_work_accepted",
    "independent_literal_truth",
    "immutable_old_bytes_retained",
    "actual_sources_read",
    "public_capture_matches_runtime",
    "no_evaluation_answer_in_role_context",
    "literal_body_or_full_table",
]
EXTRA = {
    "correct": ["one_submission_no_forced_repair", "controlled_semantics_equal"],
    "two_partial": [
        "two_separate_local_repairs",
        "first_repair_leaves_second_issue_open",
        "unrelated_section_preserved",
        "explicit_two_treatments",
        "controlled_semantics_equal",
    ],
    "rebuttal": [
        "one_submission_no_rewrite",
        "evidence_rebuttal_explicit",
        "controlled_semantics_equal",
    ],
    "reconciliation": ["complete_nine_groups", "controlled_semantics_equal"],
    "unavailable_parallel": [
        "blocked_role_does_not_starve_other",
        "persistent_real_information_condition",
    ],
    "illegal_action": ["actual_rejection_retained", "runtime_does_not_replace_failed_action"],
    "private_visibility": ["unauthorized_role_never_sees_secret", "private_object_remains_private"],
}
PROTOCOL = {
    "suite": "staff-runtime-R1-R2-v0.10",
    "groups": GROUPS,
    "checks": {name: COMMON + EXTRA[name] for name in CASES},
    "truth": {
        "report": {
            "revenue": {"value": 120, "period": "2026H1", "trend": "up"},
            "cost": {"value": 70, "period": "2026H1", "trend": "down"},
        },
        "reconciliation": literal_truth(),
    },
    "boundary": "Runtime only offers independently bound roles action opportunities. Each policy sees its own real public tools/observation and own JSON memory/previous actual result. Measurement never enters role input.",
    "faults": {
        "two_partial": "Author explicitly configured with revenue body_number and cost body_period defects on first submission",
        "rebuttal": "Reviewer explicitly configured to raise one false opinion against correct actual body",
        "illegal_action": "Author explicitly configured to attempt approval without authority once",
    },
    "baseline": "Fresh v0.9 controlled driver using the same declared template and independent truths; compare semantic outcomes, source references, issue treatment, immutable history; action counts and log layout need not match.",
    "limits": [
        "Finite program strategies and synthetic existing templates",
        "No model/API/GPU/training",
        "Checkpoint guarantee only complete action-return boundaries",
        "Rules may remain unsupported; runtime never inserts repair content",
    ],
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


class Port:
    __slots__ = ("_session", "_capture", "_label")

    def __init__(self, session, capture, label):
        self._session, self._capture, self._label = session, capture, label

    def tools(self):
        value = self._session.tools()
        self._capture.append(
            {"kind": "tools", "worker_id": self._label, "result": copy.deepcopy(value)}
        )
        return value

    def observe(self):
        value = self._session.observe()
        self._capture.append(
            {"kind": "observation", "worker_id": self._label, "result": copy.deepcopy(value)}
        )
        return value

    def call(self, action, **arguments):
        value = self._session.call(action, **arguments)
        self._capture.append(
            {
                "kind": "call",
                "worker_id": self._label,
                "action": action,
                "arguments": copy.deepcopy(arguments),
                "result": copy.deepcopy(value),
            }
        )
        return value


def hashes(world):
    return {
        oid + "/" + vid: digest(world.store.version_path(obj, vid).read_bytes())
        for oid, obj in world.store.load()["artifacts"].items()
        for vid in obj["versions"]
    }


def merged(world, sub):
    state = world.store.load()
    result = {}
    for oid, vid in sub["artifact_versions"].items():
        result.update(
            json.loads(world.store.version_path(state["artifacts"][oid], vid).read_text())
        )
    return result


def semantic(world, wid):
    state = world.store.load()
    work = state["work_items"][wid]
    sub = work["submissions"][-1]
    data = merged(world, sub)
    if "report" in data:
        facts = {
            s["section_id"]: {k: s["claims"][0][k] for k in ("value", "period", "trend")}
            for s in data["report"]["sections"]
            if s.get("claims")
        }
    else:
        facts = {
            r["key"][1]: {k: r[k] for k in ("status", "left_value", "right_value", "delta")}
            for r in data["reconciliation"]["rows"]
        }
    issues = [i for i in state.get("issues", {}).values() if i["work_id"] == wid]
    return {
        "facts": facts,
        "source_refs": data["sources"],
        "accepted": sub["review"]["decision"] == "accepted",
        "document": data,
        "requirement_version": work["requirement_version"],
        "submission_count": len(work["submissions"]),
        "issue_count": len(issues),
        "response_count": sum(
            r["work_id"] == wid for r in state.get("issue_responses", {}).values()
        ),
        "decisions": sorted(
            r["decision"] for r in state.get("issue_decisions", {}).values() if r["work_id"] == wid
        ),
        "issue_statuses": sorted(derive_issue_view(state)[i["issue_id"]]["status"] for i in issues),
    }


def controlled(name, output):
    if name != "reconciliation":
        try:
            from scripts.research_review_experiment import run_case
        except ModuleNotFoundError:
            from research_review_experiment import run_case

        baseline_name = {
            "correct": "correct_prose",
            "two_partial": "two_defects",
            "rebuttal": "wrong_opinion",
        }[name]
        result = run_case(baseline_name, output)
        if not result["passed"]:
            raise AssertionError(
                "Controlled baseline failed: " + str(result.get("construction_error"))
            )
        return WorldCore(output / "world"), "REPORT::research"
    world = make_world(output / "world")
    installed = world.session("installer").call(
        "install_project", package=finance_package(review=True)
    )
    if not installed["ok"]:
        raise AssertionError(installed)
    worker = ReconciliationWorker(Port(world.session("analyst", "A"), [], "analyst"))
    delivered = worker.run()
    approved = world.session("reviewer", "A").call(
        "approve", work_id="A::reconcile", submission_id=delivered["submission"]["submission_id"]
    )
    if not approved["ok"]:
        raise AssertionError(approved)
    return world, "A::reconcile"


def make_world(path):
    return WorldCore.create(
        path,
        WorldSpec(
            world_id="unified-role-fixture",
            actors={
                a: {} for a in ("installer", "author", "reviewer", "analyst", "finance_reviewer")
            },
            bootstrap_grants=[
                {"actor_id": "installer", "scope": "world", "power": "install_project"}
            ],
        ),
    )


def run_case(name, output):
    from proworksim.staff_runtime import StaffRuntime

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    world, error, checks, captures, transitions = make_world(output / "world"), None, [], [], []
    runtime, baseline, outcome, old = None, None, None, None

    def check(label, observed, expected=True):
        checks.append(
            {
                "name": label,
                "observed": copy.deepcopy(observed),
                "expected": copy.deepcopy(expected),
                "passed": observed == expected,
                "not_executed": False,
            }
        )

    try:
        config = (
            {"initial_defects": {"revenue": "body_number", "cost": "body_period"}}
            if name == "two_partial"
            else {}
        )
        if name == "illegal_action":
            config["illegal_action_once"] = {
                "action": "approve",
                "arguments": {"work_id": "REPORT::research", "submission_id": "does-not-exist"},
            }
        package = finance_package(review=True) if name == "reconciliation" else report_package()
        if name == "private_visibility":
            package["objects"].append(
                {
                    "alias": "private-review-notes",
                    "kind": "json",
                    "filename": "private.json",
                    "owner": "reviewer",
                    "readers": ["reviewer"],
                    "data": {"private_marker": "PRIVATE-NOT-A-POLICY-ANSWER-432"},
                }
            )
        installed = world.session("installer").call("install_project", package=package)
        assert installed["ok"], installed
        if name == "reconciliation":
            bindings = {
                "analyst": ("analyst", "A", ReconciliationPolicy()),
                "reviewer": ("reviewer", "A", ReviewerPolicy()),
            }
            wid = "A::reconcile"
        else:
            bindings = {
                "author": ("author", "REPORT", ReportAuthorPolicy(**config)),
                "reviewer": (
                    "reviewer",
                    "REPORT",
                    ReviewerPolicy(wrong_opinion_once=name == "rebuttal"),
                ),
            }
            wid = "REPORT::research"
        if name == "unavailable_parallel":
            installed = world.session("installer").call(
                "install_project",
                package=finance_package(
                    reviewer="finance_reviewer", hidden_right=True, unavailable=True, review=True
                ),
            )
            assert installed["ok"], installed
            bindings = {"blocked_analyst": ("analyst", "A", ReconciliationPolicy()), **bindings}
        old = hashes(world)
        ports = {
            label: Port(world.session(actor, pid), captures, label)
            for label, (actor, pid, _) in bindings.items()
        }
        runtime = StaffRuntime(
            ports,
            {label: policy for label, (_, _, policy) in bindings.items()},
            run_id="R1R2-" + name,
        )
        idle = 0
        for _ in range(500):
            outcome = runtime.step()
            transitions.append({"step": copy.deepcopy(outcome), "state": world.store.load()})
            idle = 0 if outcome.get("action_performed") else idle + 1
            if idle >= len(bindings) * 3:
                break
        state = world.store.load()
        summary = semantic(world, wid)
        check("all_expected_work_accepted", summary["accepted"])
        expected = PROTOCOL["truth"]["reconciliation" if name == "reconciliation" else "report"]
        check("independent_literal_truth", summary["facts"], expected)
        if name == "reconciliation":
            table = summary["document"]["reconciliation"]
            check(
                "literal_body_or_full_table",
                table["summary"],
                {
                    "matched": 1,
                    "converted": 1,
                    "conflict": 1,
                    "incomparable": 3,
                    "missing": 2,
                    "ambiguous": 1,
                },
            )
        else:
            check(
                "literal_body_or_full_table",
                {s["section_id"]: s["body"] for s in summary["document"]["report"]["sections"]},
                {
                    "context": "Context retained verbatim: this synthetic report is limited to two stated metrics.",
                    "revenue": "Revenue in 2026H1: 120; trend up; source dataset:metrics.revenue.value.",
                    "cost": "Cost in 2026H1: 70; trend down; source dataset:metrics.cost.value.",
                },
            )
        check(
            "immutable_old_bytes_retained", all(hashes(world).get(k) == v for k, v in old.items())
        )
        calls = [c for c in captures if c["kind"] == "call"]
        check(
            "actual_sources_read",
            all(
                any(c["worker_id"] == label and c["action"] == "read_object" for c in calls)
                for label in bindings
                if label != "blocked_analyst"
            ),
        )
        # Runtime's actual schema is normalized below; values must exactly match every captured raw return.
        experience = runtime.snapshot().get("experience", [])
        check("public_capture_matches_runtime", captured_equal(captures, experience))
        check(
            "no_evaluation_answer_in_role_context",
            all(
                "evaluation" not in c["result"] and "hidden_truth" not in c["result"]
                for c in captures
                if c["kind"] == "observation"
            ),
        )
        subs = state["work_items"][wid]["submissions"]
        if name in {"correct", "two_partial", "rebuttal", "reconciliation"}:
            baseworld, basewid = controlled(name, output / "controlled")
            baseline = semantic(baseworld, basewid)
            # Aliases/IDs differ legally for fresh reconciliation output; input source refs stay exact.
            check("controlled_semantics_equal", summary, baseline)
        if name == "correct":
            check("one_submission_no_forced_repair", [len(subs), len(state["issues"])], [1, 0])
        elif name == "two_partial":
            check("two_separate_local_repairs", len(subs), 3)
            statuses_after_one = []
            for transition in transitions:
                decisions = transition["state"].get("issue_decisions", {})
                if len(decisions) == 1:
                    statuses_after_one = sorted(
                        v["status"] for v in derive_issue_view(transition["state"]).values()
                    )
                    break
            check("first_repair_leaves_second_issue_open", statuses_after_one, ["open", "resolved"])
            first, middle = merged(world, subs[0]), merged(world, subs[1])

            def untouched(data):
                return [s for s in data["report"]["sections"] if s["section_id"] != "revenue"]

            check("unrelated_section_preserved", untouched(first), untouched(middle))
            check("explicit_two_treatments", summary["decisions"], ["accept_fix", "accept_fix"])
        elif name == "rebuttal":
            check(
                "one_submission_no_rewrite",
                [
                    len(subs),
                    sum(
                        c["action"] == "write_object" and c["worker_id"] == "author" for c in calls
                    ),
                ],
                [1, 1],
            )
            check("evidence_rebuttal_explicit", summary["decisions"], ["accept_rebuttal"])
        elif name == "reconciliation":
            check("complete_nine_groups", len(summary["facts"]), 9)
        elif name == "unavailable_parallel":
            check(
                "blocked_role_does_not_starve_other",
                [summary["accepted"], len(state["work_items"]["A::reconcile"]["submissions"])],
                [True, 0],
            )
            check(
                "persistent_real_information_condition",
                any(c["work_item_id"] == "A::reconcile" for c in state["condition_specs"].values()),
            )
        elif name == "illegal_action":
            first_call = calls[0]
            check(
                "actual_rejection_retained",
                first_call["action"] == "approve" and not first_call["result"]["ok"],
            )
            check(
                "runtime_does_not_replace_failed_action",
                transitions[0]["step"].get("response"),
                first_call["result"],
            )
        elif name == "private_visibility":
            author_obs = [
                c["result"]
                for c in captures
                if c["kind"] == "observation" and c["worker_id"] == "author"
            ]
            private_oid = state["workspaces"]["REPORT"]["private-review-notes"]
            check(
                "unauthorized_role_never_sees_secret",
                all(
                    private_oid not in o["objects"]
                    and "private-review-notes" not in o["workspaces"]["REPORT"]
                    for o in author_obs
                ),
            )
            check(
                "private_object_remains_private",
                state["artifacts"][private_oid]["readers"],
                ["reviewer"],
            )
    except Exception:
        error = traceback.format_exc()
        summary = None
    for label in COMMON + EXTRA[name]:
        if not any(c["name"] == label for c in checks):
            checks.append({"name": label, "passed": False, "not_executed": True})
    result = {
        "case": name,
        "error": error,
        "checks": checks,
        "passed": error is None and all(c["passed"] for c in checks),
        "port_capture": captures,
        "runtime": runtime.snapshot() if runtime else None,
        "steps": [s["step"] for s in transitions],
        "outcome": outcome,
        "semantic_result": summary,
        "controlled_semantic_result": baseline,
        "immutable_initial_sha256": old,
    }
    write_json(output / "report.json", result)
    write_json(output / "final-state.json", world.store.load())
    write_json(output / "transition-states.json", transitions)
    return result


def captured_equal(captures, experience):
    """Normalize naming only, not payloads, order, actions or arguments."""
    normalized = []
    for record in experience.get("events", []):
        kind = record.get("kind")
        if kind not in {"public_tools", "public_observation", "tool_call"}:
            continue
        payload = record["payload"]
        entry = {
            "kind": {
                "public_tools": "tools",
                "public_observation": "observation",
                "tool_call": "call",
            }[kind],
            "worker_id": record["worker_id"],
            "result": payload,
        }
        if kind == "tool_call":
            entry.update(
                action=payload["action"],
                arguments={**payload["arguments"], "request_key": payload["request_key"]},
                result=payload["response"],
            )
        normalized.append(entry)
    return normalized == captures


def run(output, workers=4, groups=("R1", "R2")):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    selected = list(dict.fromkeys(name for group in groups for name in GROUPS[group]))
    before, started = code_identity(), datetime.now(timezone.utc).isoformat()
    write_json(
        output / "protocol.json",
        {**PROTOCOL, "selected_groups": list(groups), "selected_cases": selected},
    )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        cases = list(pool.map(lambda name: run_case(name, output / name), selected))
    report = {
        "source_before": before,
        "source_after": code_identity(),
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "protocol": PROTOCOL,
        "selected_groups": list(groups),
        "cases": cases,
        "passed": all(c["passed"] for c in cases),
        "passed_cases": sum(c["passed"] for c in cases),
        "passed_checks": sum(check["passed"] for case in cases for check in case["checks"]),
        "total_checks": sum(len(c["checks"]) for c in cases),
        "not_executed": sum(check["not_executed"] for case in cases for check in case["checks"]),
    }
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=list(GROUPS))
    args = parser.parse_args()
    result = run(args.output, args.workers, args.groups)
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("passed", "passed_cases", "passed_checks", "total_checks", "not_executed")
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)
