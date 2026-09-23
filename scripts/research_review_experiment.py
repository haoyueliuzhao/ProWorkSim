"""X1/X2 report template through actual public tools, with literal external truths.

The finite author and reviewer receive opaque public ports. Only this measurement
harness sees state/files or calls content evaluation; its answers never feed back
into the strategies. Synthetic fault injection is declared before execution.
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
from proworksim.core.issues import derive_issue_view
from proworksim.storage import digest
from proworksim.templates.research_review import BACKGROUND, package
from proworksim.workers.research_review import PublicReportWorker
from proworksim.world_core import WorldCore

CASES = {
    "correct_prose": {},
    "compact_split": {"style": "compact", "split": True},
    "renamed": {
        "alias": "evidence",
        "author": "writer2",
        "reviewer": "editor2",
        "display_names": True,
    },
    "explicit_unknown": {"incomplete": True},
    "two_defects": {"defects": {"revenue": "body_number", "cost": "body_period"}},
    "period_and_source": {"defects": {"revenue": "body_period", "cost": "body_source"}},
    "late_duplicate": {"defects": {"revenue": "body_number"}},
    "wrong_opinion": {},
}
COMMON = [
    "literal_final_values_period_trend",
    "final_content_passes",
    "actual_public_strategy_transcripts",
    "source_and_old_bytes_unchanged",
    "same_work_and_requirement",
    "background_preserved",
]
EXTRA = {
    "correct_prose": ["correct_first_submission_directly_accepted"],
    "compact_split": [
        "correct_first_submission_directly_accepted",
        "two_legal_files_exact_dependencies",
    ],
    "renamed": ["correct_first_submission_directly_accepted"],
    "explicit_unknown": [
        "explicit_unknown_is_not_zero",
        "correct_first_submission_directly_accepted",
    ],
    "two_defects": [
        "independent_initial_body_defects",
        "two_issues_bound_to_actual_old_submission",
        "one_local_fix_leaves_other_defect",
        "only_fixed_issue_resolved",
        "remaining_issue_blocks_approval",
        "unrelated_section_preserved_after_local_fix",
        "both_issues_explicitly_resolved",
    ],
    "period_and_source": [
        "correct_numbers_cannot_hide_period_or_source_errors",
        "two_issues_resolved_after_actual_repair",
    ],
    "late_duplicate": [
        "old_comment_is_historical",
        "duplicate_comment_has_one_formal_effect",
        "late_comment_does_not_block_new_submission",
        "old_bad_content_remains_bad",
    ],
    "wrong_opinion": [
        "wrong_opinion_does_not_change_truth",
        "evidence_rebuttal_accepted_without_edit",
        "opinion_and_response_recorded",
    ],
}
PROTOCOL = {
    "suite": "research-review-X1-X2-v0.9",
    "cases": CASES,
    "checks": {name: COMMON + EXTRA[name] for name in CASES},
    "independent_truth": {
        "revenue": {"value": 120, "period": "2026H1", "trend": "up"},
        "cost": {"value": 70, "period": "2026H1", "trend": "down"},
        "unknown_cost": {"value": None, "trend": "unknown", "status": "unresolved"},
    },
    "body_contract": "Each contracted section has one complete reader-facing sentence in either public grammar; numbers/period/trend/citation and claim metadata are checked separately. Free prose outside these sections is unassessed.",
    "interface_boundary": "Authors/reviewers use only opaque tools/observe/call ports, read real immutable submission bytes and exact source versions, and import no evaluator. Measurement alone reads state and evaluates; no evaluation feedback enters the strategy.",
    "error_attribution": "Expected open-issue approval refusal is business_constraint. Deliberate bad body/opinion is injected strategy error. Unexpected exceptions or tool errors are construction failures retained verbatim, not automatically called environment faults.",
    "repair": "withdraw -> local file change -> submit SAME work and requirement, then separately respond and institutional decide. No automatic issue closure on edit or submission.",
    "limits": [
        "Synthetic finite metrics and controlled sentence grammar, not open-ended language quality",
        "Program strategies, no model/API/GPU/training",
        "No universal autonomous professional review claim",
        "Explicit unknown is a successful incomplete report result under this finite contract",
    ],
}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


class Port:
    __slots__ = ("_tools", "_observe", "_call")

    def __init__(self, tools, observe, call):
        self._tools, self._observe, self._call = tools, observe, call

    def tools(self):
        return self._tools()

    def observe(self):
        return self._observe()

    def call(self, action, **arguments):
        return self._call(action, **arguments)


class Evidence:
    def __init__(self, name, output):
        self.name, self.output, self.spec = name, output, CASES[name]
        self.checks, self.calls, self.observations, self.evaluations, self.tool_rejections = (
            [],
            [],
            [],
            [],
            [],
        )
        self.world = None
        self.author = self.reviewer = None

    def port(self, actor, pid):
        session = self.world.session(actor, pid)

        def call(action, **arguments):
            result = session.call(action, **arguments)
            self.calls.append(
                {
                    "actor": actor,
                    "project": pid,
                    "action": action,
                    "arguments": copy.deepcopy(arguments),
                    "result": copy.deepcopy(result),
                }
            )
            return result

        def observe():
            result = session.observe()
            self.observations.append({"actor": actor, "result": copy.deepcopy(result)})
            return result

        return Port(session.tools, observe, call)

    def check(self, name, observed, expected=True):
        if name not in COMMON + EXTRA[self.name] or any(c["name"] == name for c in self.checks):
            raise ValueError("Unknown/repeated check " + name)
        self.checks.append(
            {
                "name": name,
                "observed": copy.deepcopy(observed),
                "expected": copy.deepcopy(expected),
                "passed": observed == expected,
                "not_executed": False,
            }
        )

    def state(self):
        return self.world.store.load()

    def evaluate(self, sub):
        result = self.world.evaluate_submission("REPORT", "REPORT::research", sub["submission_id"])
        self.evaluations.append(copy.deepcopy(result))
        return result

    def hashes(self):
        return {
            oid + "/" + vid: digest(self.world.store.version_path(obj, vid).read_bytes())
            for oid, obj in self.state()["artifacts"].items()
            for vid in obj["versions"]
        }


def setup(ev):
    author, reviewer = ev.spec.get("author", "author"), ev.spec.get("reviewer", "reviewer")
    ev.world = WorldCore.create(
        ev.output / "world",
        WorldSpec(
            world_id="review-" + ev.name,
            actors={
                "installer": {},
                author: {
                    "display_name": "Researcher Renamed"
                    if ev.spec.get("display_names")
                    else "Author"
                },
                reviewer: {
                    "display_name": "Editor Renamed" if ev.spec.get("display_names") else "Reviewer"
                },
            },
            bootstrap_grants=[
                {"actor_id": "installer", "scope": "world", "power": "install_project"}
            ],
        ),
    )
    installed = ev.port("installer", None).call(
        "install_project",
        package=package(
            author=author,
            reviewer=reviewer,
            source_alias=ev.spec.get("alias", "dataset"),
            incomplete=ev.spec.get("incomplete", False),
        ),
    )
    if not installed["ok"]:
        raise AssertionError(installed)
    ev.author, ev.reviewer = (
        PublicReportWorker(ev.port(author, "REPORT")),
        PublicReportWorker(ev.port(reviewer, "REPORT")),
    )
    obs = ev.author.observe()
    alias = ev.spec.get("alias", "dataset")
    ev.author.call(
        "adopt",
        alias=alias,
        object_id=obs["workspaces"]["REPORT"][alias],
        version_id="v1",
        policy="fixed",
        work_ids=["REPORT::research"],
    )
    return alias


def submission_id(sub):
    return sub["submission_id"]


def issue_statuses(state):
    # Inspect the institutional record only for measurement, never strategy input.
    return {key: value["status"] for key, value in derive_issue_view(state).items()}


def respond_and_decide(ev, issue, sub, claim_id, *, decision="accept_fix"):
    wid = "REPORT::research"
    refs, _ = ev.author.source_data(wid, ev.author.spec(wid))
    response = ev.author.call(
        "respond_issue",
        issue_id=issue["issue_id"],
        response_key="response-" + submission_id(sub) + "-" + claim_id,
        submission_id=submission_id(sub),
        body="Evidence-backed correction of " + claim_id
        if decision == "accept_fix"
        else "The actual unchanged source supports the submitted value; the opinion is mistaken.",
        evidence=list(refs.values()),
    )
    # Reviewer independently re-reads the immutable new submission before decision.
    ev.reviewer.review(wid, submission_id(sub))
    return ev.reviewer.call(
        "decide_issue",
        issue_id=issue["issue_id"],
        response_id=response["response_id"],
        decision_key="decision-" + response["response_id"],
        decision=decision,
        reason="Read actual submitted body and source; finite assertion verified independently",
    )


def execute(ev):
    alias = setup(ev)
    wid = "REPORT::research"
    old_hashes = ev.hashes()
    initial_source = copy.deepcopy(
        ev.state()["artifacts"][ev.author.observe()["workspaces"]["REPORT"][alias]]
    )
    data, refs = ev.author.prepare(
        wid, style=ev.spec.get("style", "prose"), defects=ev.spec.get("defects")
    )
    first = ev.author.deliver(wid, data, refs, split=ev.spec.get("split", False))
    old_hashes.update(ev.hashes())  # Preserve actual first-submission bytes through repairs.
    first_eval = ev.evaluate(first)
    first_findings = ev.reviewer.review(wid, submission_id(first))
    final = first
    if ev.name in {"correct_prose", "compact_split", "renamed", "explicit_unknown"}:
        assert first_findings == []
        ev.reviewer.call("approve", work_id=wid, submission_id=submission_id(first))
        item = ev.state()["work_items"][wid]
        ev.check(
            "correct_first_submission_directly_accepted",
            len(item["submissions"]) == 1
            and item["submissions"][0]["review"]["decision"] == "accepted"
            and not ev.state().get("issues"),
        )
        if ev.name == "compact_split":
            ev.check(
                "two_legal_files_exact_dependencies",
                len(first["artifact_versions"]) == 2
                and all(
                    {
                        (ref.get("object_id", ref.get("artifact_id")), ref["version_id"])
                        for ref in ev.state()["artifacts"][oid]["versions"][vid]["derived_from"]
                    }
                    == {(ref["object_id"], ref["version_id"]) for ref in refs}
                    for oid, vid in first["artifact_versions"].items()
                ),
            )
        if ev.name == "explicit_unknown":
            cost = next(s for s in data["report"]["sections"] if s["section_id"] == "cost")[
                "claims"
            ][0]
            ev.check(
                "explicit_unknown_is_not_zero",
                [cost["value"], cost["trend"], cost["status"]],
                [None, "unknown", "unresolved"],
            )
    elif ev.name in {"two_defects", "period_and_source"}:
        issues = ev.reviewer.raise_findings(wid, submission_id(first), first_findings)
        assert len(issues) == 2
        if ev.name == "two_defects":
            ev.check(
                "independent_initial_body_defects",
                [f["claim_id"] for f in first_findings],
                ["revenue", "cost"],
            )
            ev.check(
                "two_issues_bound_to_actual_old_submission",
                len(set(i["issue_id"] for i in issues)) == 2 and not first_eval["passed"],
            )
        else:
            ev.check(
                "correct_numbers_cannot_hide_period_or_source_errors",
                not first_eval["passed"]
                and len(first_findings) == 2
                and [s["claims"][0]["value"] for s in data["report"]["sections"] if s.get("claims")]
                == [120, 70],
            )
        ev.author.call(
            "withdraw",
            work_id=wid,
            submission_id=submission_id(first),
            reason="Repair original requirements without revising them",
        )
        selected = {"revenue"} if ev.name == "two_defects" else {"revenue", "cost"}
        repaired, dependencies = ev.author.prepare(wid, fix_claims=selected)
        final = ev.author.deliver(wid, repaired, dependencies)
        remaining = ev.reviewer.review(wid, submission_id(final))
        respond_and_decide(ev, issues[0], final, "revenue")
        if ev.name == "two_defects":
            intermediate = ev.evaluate(final)
            ev.check(
                "one_local_fix_leaves_other_defect",
                [intermediate["passed"], [f["claim_id"] for f in remaining]],
                [False, ["cost"]],
            )
            statuses = issue_statuses(ev.state())
            ev.check(
                "only_fixed_issue_resolved",
                [statuses.get(issues[0]["issue_id"]), statuses.get(issues[1]["issue_id"])],
                ["resolved", "open"],
            )
            rejected = ev.reviewer._port.call(
                "approve", work_id=wid, submission_id=submission_id(final)
            )
            ev.tool_rejections.append(
                {
                    "expected_category": "business_constraint",
                    "action": "approve",
                    "reason": "One unresolved blocking issue remains",
                    "raw_return": rejected,
                }
            )
            ev.check("remaining_issue_blocks_approval", not rejected["ok"])

            def unchanged(document):
                return [s for s in document["report"]["sections"] if s["section_id"] != "revenue"]

            ev.check(
                "unrelated_section_preserved_after_local_fix", unchanged(repaired), unchanged(data)
            )
            ev.author.call(
                "withdraw",
                work_id=wid,
                submission_id=submission_id(final),
                reason="Repair remaining cost period only",
            )
            data, dependencies = ev.author.prepare(wid, fix_claims={"cost"})
            final = ev.author.deliver(wid, data, dependencies)
            assert ev.reviewer.review(wid, submission_id(final)) == []
        else:
            data = repaired
        respond_and_decide(ev, issues[1], final, "cost")
        statuses = issue_statuses(ev.state())
        ev.check(
            "both_issues_explicitly_resolved"
            if ev.name == "two_defects"
            else "two_issues_resolved_after_actual_repair",
            [statuses.get(i["issue_id"]) for i in issues],
            ["resolved", "resolved"],
        )
        ev.reviewer.call("approve", work_id=wid, submission_id=submission_id(final))
    elif ev.name == "late_duplicate":
        ev.author.call(
            "withdraw",
            work_id=wid,
            submission_id=submission_id(first),
            reason="Correct a visible body number",
        )
        data, refs = ev.author.prepare(wid, fix_claims={"revenue"})
        final = ev.author.deliver(wid, data, refs)
        assert ev.reviewer.review(wid, submission_id(final)) == []
        late_findings = ev.reviewer.review(wid, submission_id(first))
        late = ev.reviewer.raise_findings(wid, submission_id(first), late_findings)[0]
        before_repeat = copy.deepcopy(ev.state().get("issues"))
        repeated = ev.reviewer.raise_findings(wid, submission_id(first), late_findings)[0]
        ev.check(
            "duplicate_comment_has_one_formal_effect",
            late["issue_id"] == repeated["issue_id"] and ev.state().get("issues") == before_repeat,
        )
        ev.check(
            "old_comment_is_historical",
            derive_issue_view(ev.state())[late["issue_id"]]["applicability"],
            "historical",
        )
        ev.reviewer.call("approve", work_id=wid, submission_id=submission_id(final))
        ev.check(
            "late_comment_does_not_block_new_submission",
            ev.state()["work_items"][wid]["submissions"][-1]["review"]["decision"],
            "accepted",
        )
        ev.check("old_bad_content_remains_bad", not ev.evaluate(first)["passed"])
    elif ev.name == "wrong_opinion":
        assert first_findings == []
        _, _, locators = ev.reviewer.read_submission(wid, submission_id(first))
        evidence, _ = ev.reviewer.source_data(wid, ev.reviewer.spec(wid))
        wrong = ev.reviewer.call(
            "raise_issue",
            work_id=wid,
            submission_id=submission_id(first),
            issue_key="mistaken-opinion",
            **locators["report"],
            locator=["report", "sections", 1, "body"],
            description="Mistaken reviewer opinion: revenue should be 119",
            evidence=list(evidence.values()),
            blocking=True,
        )
        ev.check("wrong_opinion_does_not_change_truth", ev.evaluate(first)["passed"])
        hash_before_rebuttal = ev.hashes()
        respond_and_decide(ev, wrong, first, "revenue", decision="accept_rebuttal")
        ev.check(
            "evidence_rebuttal_accepted_without_edit",
            ev.hashes() == hash_before_rebuttal
            and issue_statuses(ev.state()).get(wrong["issue_id"]) == "resolved",
        )
        ev.check(
            "opinion_and_response_recorded",
            any(c["action"] == "raise_issue" for c in ev.calls)
            and any(c["action"] == "respond_issue" for c in ev.calls),
        )
        ev.reviewer.call("approve", work_id=wid, submission_id=submission_id(first))
    final_eval = ev.evaluate(final)
    _, actual, _ = ev.reviewer.read_submission(wid, submission_id(final))
    facts = {
        s["section_id"]: {k: s["claims"][0][k] for k in ("value", "period", "trend")}
        for s in actual["report"]["sections"]
        if s.get("claims")
    }
    expected = {
        "revenue": {"value": 120, "period": "2026H1", "trend": "up"},
        "cost": {
            "value": None if ev.spec.get("incomplete") else 70,
            "period": "2026H1",
            "trend": "unknown" if ev.spec.get("incomplete") else "down",
        },
    }
    ev.check("literal_final_values_period_trend", facts, expected)
    ev.check("final_content_passes", final_eval["passed"])
    ev.check(
        "actual_public_strategy_transcripts",
        all(
            any(x["kind"] == "observe" for x in worker.transcript)
            and any(x.get("action") == "read_object" for x in worker.transcript)
            for worker in (ev.author, ev.reviewer)
        ),
    )
    state = ev.state()
    ev.check(
        "source_and_old_bytes_unchanged",
        state["artifacts"][initial_source["artifact_id"]] == initial_source
        and all(ev.hashes()[k] == value for k, value in old_hashes.items()),
    )
    ev.check(
        "same_work_and_requirement",
        len(state["work_items"]) == 1
        and state["work_items"][wid]["requirement_version"] == 1
        and not state.get("work_replacements"),
    )
    ev.check(
        "background_preserved",
        next(s["body"] for s in actual["report"]["sections"] if s["section_id"] == "context"),
        BACKGROUND,
    )
    return {
        "facts": facts,
        "submission_id": submission_id(final),
        "content_passed": final_eval["passed"],
        "unassessed": "Open prose, style and professional sufficiency",
    }


def run_case(name, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    ev, error, outcome = Evidence(name, output), None, None
    try:
        outcome = execute(ev)
    except Exception:
        error = traceback.format_exc()
    for name_ in COMMON + EXTRA[name]:
        if not any(c["name"] == name_ for c in ev.checks):
            ev.checks.append({"name": name_, "passed": False, "not_executed": True})
    result = {
        "case": name,
        "construction_error": error,
        "checks": ev.checks,
        "passed": error is None and all(c["passed"] for c in ev.checks),
        "calls": ev.calls,
        "observations": ev.observations,
        "evaluations": ev.evaluations,
        "tool_rejections": ev.tool_rejections,
        "outcome": outcome,
        "worker_transcripts": {
            "author": ev.author.transcript if ev.author else [],
            "reviewer": ev.reviewer.transcript if ev.reviewer else [],
        },
    }
    if ev.world:
        write_json(output / "final-state.json", ev.state())
        result["immutable_file_sha256"] = ev.hashes()
    write_json(output / "report.json", result)
    return result


def run(output, workers=4):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before, started = code_identity(), datetime.now(timezone.utc).isoformat()
    write_json(output / "protocol.json", PROTOCOL)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda name: run_case(name, output / name), CASES))
    alternatives = [
        r for r in results if r["case"] in {"correct_prose", "compact_split", "renamed"}
    ]
    comparison = {
        "name": "legal_alternatives_match_literal_truth",
        "passed": all(r["passed"] for r in alternatives)
        and len(
            {
                json.dumps(r["outcome"]["facts"], sort_keys=True)
                for r in alternatives
                if r["outcome"]
            }
        )
        == 1,
    }
    report = {
        "source_before": before,
        "source_after": code_identity(),
        "protocol": PROTOCOL,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "cases": results,
        "comparisons": [comparison],
        "passed_cases": sum(r["passed"] for r in results),
        "passed_checks": sum(c["passed"] for r in results for c in r["checks"]),
        "total_checks": sum(len(COMMON) + len(EXTRA[name]) for name in CASES),
        "not_executed": sum(c["not_executed"] for r in results for c in r["checks"]),
        "passed": all(r["passed"] for r in results) and comparison["passed"],
    }
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    result = run(args.output, args.workers)
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("passed", "passed_cases", "passed_checks", "total_checks", "not_executed")
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)
