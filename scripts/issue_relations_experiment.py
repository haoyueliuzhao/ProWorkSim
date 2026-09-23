"""X4: two templates share located issue treatment; one real commit recovery cut.

Fixtures introduce two explicit writer mistakes in real JSON contents. Reviewer
and author actions use opaque public sessions. Backend inspection is restricted
to measurement and byte-for-byte checkpoint comparison, never a worker answer.
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.issues import derive_issue_view
from proworksim.core.journal import validate_committed_prefix
from proworksim.core.world import WorldSpec
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.templates.reconciliation import package as finance_package
from proworksim.templates.research_review import package as report_package
from proworksim.workers.reconciliation import ReconciliationWorker
from proworksim.workers.research_review import PublicReportWorker
from proworksim.world_core import WorldCore

GROUPS = ("finance", "report")
CHECKS = (
    "two_actual_content_defects", "located_issues_bind_exact_bad_submission",
    "duplicate_issue_has_no_new_relation", "partial_repair_preserves_unrelated_content",
    "resubmission_keeps_requirement_edition", "editing_does_not_close_issues",
    "one_decision_closes_only_one_issue", "remaining_issue_blocks_approval",
    "late_old_submission_issue_is_historical", "wrong_response_cannot_close_other_issue",
    "duplicate_decision_has_no_new_relation", "final_content_passes_domain_contract",
    "old_submission_and_version_bytes_preserved", "all_required_issues_resolved_then_approval",
)
RECOVERY_CHECKS = (
    "identical_checkpoint_copies", "real_commit_exit73", "committed_revision_delta1",
    "valid_committed_prefix", "full_state_equals_control", "file_bytes_equal_control",
    "public_result_equals_control", "actual_observations_equal_control",
    "exactly_one_decision_and_other_issue_open", "retry_has_no_formal_effect",
)
PROTOCOL = {
    "suite": "shared-issue-relations-X4-v0.9", "groups": GROUPS, "checks": CHECKS,
    "recovery": {"template": "report", "action": "decide_issue", "phase": "after_command_commit",
                 "checks": RECOVERY_CHECKS, "exit_code": 73},
    "scope": "Two real domain packages, each with two located defects, partial repair, evidence response and scoped review decision. Domain content evaluation is measured separately from institutional approval.",
    "worker_boundary": "Strategies and all repair/review actions receive only tools/observe/call ports. Harness deliberately injects two declared mistakes in public prepared content; it does not fabricate submissions, issues, approvals, or events in stored state.",
    "recovery_comparison": "One genuine checkpoint copied byte-for-byte. Full state normalized only for wall_seconds/state_digests; exact fixed bytes, original pre-cut observations, post-cut observations and public retry result compared.",
    "limitations": ["Finite synthetic cases, not general professional review quality", "Review decisions express institutional treatment, never create domain truth", "One process-exit cut, not concurrent writers or power-loss guarantees"],
}


def write(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def normalized(value):
    if isinstance(value, dict):
        return {key: normalized(child) for key, child in value.items()
                if key not in {"wall_seconds", "state_digests"}}
    if isinstance(value, list):
        return [normalized(child) for child in value]
    return value


def opaque(session, trace):
    class Port:
        __slots__ = ()

        def tools(self):
            value = session.tools()
            trace.append({"kind": "tools", "actor": session.actor_id, "value": copy.deepcopy(value)})
            return value

        def observe(self):
            value = session.observe()
            trace.append({"kind": "observation", "actor": session.actor_id, "value": copy.deepcopy(value)})
            return value

        def call(self, action, **arguments):
            value = session.call(action, **arguments)
            trace.append({"kind": "call", "actor": session.actor_id, "action": action,
                          "arguments": copy.deepcopy(arguments), "response": copy.deepcopy(value)})
            return value

    return Port()


def must(port, action, **arguments):
    response = port.call(action, **arguments)
    if not response.get("ok"):
        raise AssertionError({"action": action, "arguments": arguments, "response": response})
    return response["result"]


def fixed_bytes(world):
    state = world.store.load()
    return {aid + "/" + vid: digest(world.store.version_path(obj, vid).read_bytes())
            for aid, obj in state["artifacts"].items() for vid in obj["versions"]}


def tree(root):
    return {str(p.relative_to(root)): digest(p.read_bytes()) for p in sorted(root.rglob("*"))
            if p.is_file() and p.name != "world.lock"}


def _replace(document, path, value):
    target = document
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = copy.deepcopy(value)


def _value(document, path):
    for part in path:
        document = document[part]
    return document


class Fixture:
    def __init__(self, root, kind):
        self.kind, self.trace = kind, []
        self.pid = "FINANCE" if kind == "finance" else "REPORT"
        self.owner = "analyst" if kind == "finance" else "author"
        self.work = self.pid + ("::reconcile" if kind == "finance" else "::research")
        self.alias = "comparison" if kind == "finance" else "report"
        self.world = WorldCore.create(root / "world", WorldSpec(
            "shared-issues-" + kind, {self.owner: {}, "reviewer": {}, "manager": {}},
            bootstrap_grants=[{"actor_id": "manager", "scope": "world", "power": "install_project"}],
        ))
        pkg = (finance_package(self.pid, owner=self.owner, review=True) if kind == "finance"
               else report_package(self.pid, author=self.owner))
        must(opaque(self.world.session("manager"), self.trace), "install_project", package=pkg)
        self.author = opaque(self.world.session(self.owner, self.pid), self.trace)
        self.reviewer = opaque(self.world.session("reviewer", self.pid), self.trace)
        if kind == "finance":
            initial = ReconciliationWorker(self.author).run(self.work)
            if initial["status"] != "submitted":
                raise AssertionError(initial)
            self.good, self.deps = initial["data"], list(initial["data"]["sources"].values())
            must(self.author, "withdraw", work_id=self.work,
                 submission_id=initial["submission"]["submission_id"], reason="Explicit two-error fixture")
            self.locations = [["reconciliation", "rows", 1, "left_value"],
                              ["reconciliation", "rows", 2, "right_value"]]
            self.bad = copy.deepcopy(self.good)
            for location in self.locations:
                _replace(self.bad, location, 999)
        else:
            observation = self.author.observe()
            must(self.author, "adopt", alias="dataset",
                 object_id=observation["workspaces"][self.pid]["dataset"], version_id="v1",
                 policy="fixed", work_ids=[self.work])
            strategy = PublicReportWorker(self.author)
            self.good, self.deps = strategy.prepare(self.work)
            self.bad, _ = strategy.prepare(self.work, defects={"revenue": "body_number", "cost": "body_number"})
            self.locations = [["report", "sections", 1, "body"], ["report", "sections", 2, "body"]]
        self.bad_sub = self.deliver(self.bad)
        self.bad_ref = self.read_submission(self.bad_sub)[0]
        self.issue_args, self.issues = [], []
        for index, location in enumerate(self.locations):
            arguments = {"work_id": self.work, "submission_id": self.bad_sub["submission_id"],
                         "issue_key": "actual-defect-" + str(index), **self.bad_ref,
                         "locator": location, "description": "The located reader-facing value disagrees with its exact evidence",
                         "evidence": self.deps, "blocking": True}
            self.issue_args.append(arguments)
            self.issues.append(must(self.reviewer, "raise_issue", **arguments))

    def deliver(self, data):
        must(self.author, "write_object", alias=self.alias, data=data,
             dependencies=self.deps, work_id=self.work)
        return must(self.author, "submit", work_id=self.work, artifacts=[self.alias])

    def read_submission(self, submission):
        pinned = must(self.reviewer, "inspect_submission", work_id=self.work,
                      submission_id=submission["submission_id"])
        references = []
        for oid, vid in pinned["artifact_versions"].items():
            ref = {"object_id": oid, "version_id": vid}
            must(self.reviewer, "read_object", **ref, work_id=self.work)
            references.append(ref)
        for ref in self.deps:
            must(self.reviewer, "read_object", **ref, work_id=self.work)
        return references

    def partial(self):
        must(self.author, "withdraw", work_id=self.work, submission_id=self.bad_sub["submission_id"],
             reason="Repair only the first located defect under the same requirement")
        partial = copy.deepcopy(self.bad)
        _replace(partial, self.locations[0], _value(self.good, self.locations[0]))
        self.partial_sub = self.deliver(partial)
        response = must(self.author, "respond_issue", issue_id=self.issues[0]["issue_id"],
                        response_key="first-fix", submission_id=self.partial_sub["submission_id"],
                        body="The first located assertion now follows the exact evidence; the second is unchanged", evidence=self.deps)
        self.read_submission(self.partial_sub)
        self.decision_args = {"issue_id": self.issues[0]["issue_id"], "response_id": response["response_id"],
                              "decision_key": "first-fix-accepted", "decision": "accept_fix",
                              "reason": "Read the fixed submitted bytes and source evidence; only the first issue is treated"}
        return partial, response


def run_case(root, kind):
    root.mkdir(parents=True)
    checks, error, ev = [], None, {}

    def check(name, value, observed=None):
        checks.append({"name": name, "passed": bool(value), "observed": observed, "not_executed": False})

    try:
        fixture = Fixture(root, kind)
        world = fixture.world
        bad_evaluation = world.evaluate_submission(fixture.pid, fixture.work, fixture.bad_sub["submission_id"])
        check("two_actual_content_defects", all(_value(fixture.bad, path) != _value(fixture.good, path)
                                                for path in fixture.locations) and not bad_evaluation["passed"])
        check("located_issues_bind_exact_bad_submission", len(fixture.issues) == 2 and all(
            issue["submission_id"] == fixture.bad_sub["submission_id"] and issue["target"] == fixture.bad_ref
            and issue["active_at_creation"] for issue in fixture.issues))
        duplicate = must(fixture.reviewer, "raise_issue", **fixture.issue_args[0])
        check("duplicate_issue_has_no_new_relation", duplicate["issue_id"] == fixture.issues[0]["issue_id"]
              and len(world.store.load()["issues"]) == 2)
        partial, response = fixture.partial()
        expect_partial = copy.deepcopy(fixture.bad)
        _replace(expect_partial, fixture.locations[0], _value(fixture.good, fixture.locations[0]))
        read_partial = must(fixture.author, "read_object", alias=fixture.alias, work_id=fixture.work)["data"]
        check("partial_repair_preserves_unrelated_content", read_partial == expect_partial == partial
              and _value(partial, fixture.locations[1]) == _value(fixture.bad, fixture.locations[1]))
        state = world.store.load()
        check("resubmission_keeps_requirement_edition", fixture.partial_sub["requirement_version"]
              == fixture.bad_sub["requirement_version"] == state["work_items"][fixture.work]["requirement_version"] == 1
              and not state["work_replacements"])
        check("editing_does_not_close_issues", all(view["blocks_approval"]
              for view in derive_issue_view(state).values()))
        fixed_prior = fixed_bytes(world)
        old_submissions = copy.deepcopy(state["work_items"][fixture.work]["submissions"][:-1])
        first_decision = must(fixture.reviewer, "decide_issue", **fixture.decision_args)
        views = derive_issue_view(world.store.load())
        check("one_decision_closes_only_one_issue", views[fixture.issues[0]["issue_id"]]["status"] == "resolved"
              and views[fixture.issues[1]["issue_id"]]["blocks_approval"])
        denied = fixture.reviewer.call("approve", work_id=fixture.work,
                                       submission_id=fixture.partial_sub["submission_id"])
        check("remaining_issue_blocks_approval", denied.get("ok") is False)
        late = must(fixture.reviewer, "raise_issue", **{**fixture.issue_args[0], "issue_key": "late-old-version"})
        late_view = derive_issue_view(world.store.load())[late["issue_id"]]
        check("late_old_submission_issue_is_historical", not late["active_at_creation"]
              and late_view["applicability"] == "historical" and not late_view["blocks_approval"])
        wrong = fixture.reviewer.call("decide_issue", **{**fixture.decision_args,
            "issue_id": fixture.issues[1]["issue_id"], "decision_key": "wrong-response"})
        check("wrong_response_cannot_close_other_issue", wrong.get("ok") is False
              and derive_issue_view(world.store.load())[fixture.issues[1]["issue_id"]]["blocks_approval"])
        duplicate = must(fixture.reviewer, "decide_issue", **fixture.decision_args)
        check("duplicate_decision_has_no_new_relation", duplicate["decision_id"] == first_decision["decision_id"]
              and len(world.store.load()["issue_decisions"]) == 1)
        must(fixture.author, "withdraw", work_id=fixture.work,
             submission_id=fixture.partial_sub["submission_id"], reason="Repair the remaining second defect")
        final = fixture.deliver(fixture.good)
        second_response = must(fixture.author, "respond_issue", issue_id=fixture.issues[1]["issue_id"],
            response_key="second-fix", submission_id=final["submission_id"], body="Only the remaining located defect was corrected", evidence=fixture.deps)
        fixture.read_submission(final)
        must(fixture.reviewer, "decide_issue", issue_id=fixture.issues[1]["issue_id"],
             response_id=second_response["response_id"], decision_key="second-fix-accepted",
             decision="accept_fix", reason="Read exact final version and source evidence")
        final_evaluation = world.evaluate_submission(fixture.pid, fixture.work, final["submission_id"])
        check("final_content_passes_domain_contract", final_evaluation["passed"])
        state = world.store.load()
        check("old_submission_and_version_bytes_preserved", all(fixed_bytes(world)[key] == value
              for key, value in fixed_prior.items()) and state["work_items"][fixture.work]["submissions"][:len(old_submissions)] == old_submissions)
        approved = must(fixture.reviewer, "approve", work_id=fixture.work, submission_id=final["submission_id"])
        check("all_required_issues_resolved_then_approval", approved["review"]["decision"] == "accepted"
              and all(derive_issue_view(world.store.load())[issue["issue_id"]]["status"] == "resolved"
                      for issue in fixture.issues))
        ev = {"bad_evaluation": bad_evaluation, "final_evaluation": final_evaluation,
              "partial_data": partial, "old_submission_ids": [sub["submission_id"] for sub in old_submissions]}
        write(root / "public-transcript.json", fixture.trace)
    except Exception:
        error = traceback.format_exc()
        if "fixture" in locals():
            write(root / "public-transcript.json", fixture.trace)
    completed = {entry["name"] for entry in checks}
    checks.extend({"name": name, "passed": False, "not_executed": True}
                  for name in CHECKS if name not in completed)
    result = {"kind": kind, "checks": checks, "error": error, "evidence": ev,
              "passed": error is None and all(entry["passed"] for entry in checks)}
    write(root / "result.json", result)
    return result


def execute_decision(world, arguments):
    result = world.session("reviewer", "REPORT").call(
        "decide_issue", request_key="v09-issue-commit-cut", **arguments)
    if not result.get("ok") or result.get("pending_event_errors") or result.get("event_delivery_errors"):
        raise AssertionError(result)
    return result


def child(root, args_path, reached):
    world = WorldCore(root)

    def cut(phase, details):
        if phase == "after_command_commit":
            write(reached, {"phase": phase, "details": details, "pid": os.getpid()})
            os._exit(73)

    world.fault_hook = cut
    execute_decision(world, json.loads(args_path.read_text()))
    raise AssertionError("Expected commit hook did not execute")


def observations(world):
    return {actor: world.session(actor, "REPORT").observe() for actor in ("author", "reviewer")}


def run_recovery(root):
    root.mkdir(parents=True)
    checks, error, ev = [], None, {}

    def check(name, value, observed=None):
        checks.append({"name": name, "passed": bool(value), "observed": observed, "not_executed": False})

    try:
        fixture = Fixture(root / "checkpoint", "report")
        fixture.partial()
        prior = fixture.world.store.load()
        prior_observations = observations(fixture.world)
        args_path = root / "decision-arguments.json"
        write(args_path, fixture.decision_args)
        prior_path = Path("control/actual-prior-observations.json")
        write(fixture.world.store.root / prior_path, prior_observations)
        write(root / "setup-public-transcript.json", fixture.trace)
        control_path, fault_path = root / "control-world", root / "fault-world"
        for destination in (control_path, fault_path):
            shutil.copytree(fixture.world.store.root, destination, ignore=shutil.ignore_patterns("world.lock"))
        check("identical_checkpoint_copies", tree(control_path) == tree(fault_path) == tree(fixture.world.store.root))
        control = WorldCore(control_path)
        expected = execute_decision(control, fixture.decision_args)
        expected_observations = observations(control)
        reached = root / "fault-reached.json"
        process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", str(fault_path),
            "--arguments", str(args_path), "--reached", str(reached)], capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
        ev["process"] = {"returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr}
        check("real_commit_exit73", process.returncode == 73 and reached.exists(), ev["process"])
        crashed = json.loads((fault_path / "control/state.json").read_text())
        check("committed_revision_delta1", crashed["state_revision"] == prior["state_revision"] + 1)
        recovered = WorldCore(fault_path)
        actual = execute_decision(recovered, fixture.decision_args)
        actual_observations = observations(recovered)
        state = recovered.store.load()
        validate_committed_prefix(state)
        check("valid_committed_prefix", True)
        check("full_state_equals_control", normalized(state) == normalized(control.store.load()))
        check("file_bytes_equal_control", fixed_bytes(recovered) == fixed_bytes(control)
              and (fault_path / prior_path).read_bytes() == (control_path / prior_path).read_bytes()
              == (fixture.world.store.root / prior_path).read_bytes())
        check("public_result_equals_control", normalized(actual) == normalized(expected))
        check("actual_observations_equal_control", actual_observations == expected_observations
              and bool(prior_observations["reviewer"]["work_items"]))
        views = derive_issue_view(state)
        check("exactly_one_decision_and_other_issue_open", len(state["issue_decisions"]) == 1
              and views[fixture.issues[0]["issue_id"]]["status"] == "resolved"
              and views[fixture.issues[1]["issue_id"]]["blocks_approval"]
              and state["work_items"] == prior["work_items"])
        retried = execute_decision(recovered, fixture.decision_args)
        check("retry_has_no_formal_effect", retried == actual and recovered.store.load() == state)
        ev.update(control=write(root / "control.json", {"state": control.store.load(), "result": expected,
                  "observations": expected_observations}), recovered=write(root / "recovered.json", {
                  "state": state, "result": actual, "observations": actual_observations}),
                  prior_observations=prior_observations)
    except Exception:
        error = traceback.format_exc()
    completed = {entry["name"] for entry in checks}
    checks.extend({"name": name, "passed": False, "not_executed": True}
                  for name in RECOVERY_CHECKS if name not in completed)
    result = {"kind": "decision_commit_recovery", "checks": checks, "error": error,
              "evidence": ev, "passed": error is None and all(entry["passed"] for entry in checks)}
    write(root / "result.json", result)
    return result


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    write(output / "protocol.json", PROTOCOL)
    cases = [run_case(output / kind, kind) for kind in GROUPS]
    cases.append(run_recovery(output / "decision_commit_recovery"))
    result = {"protocol": PROTOCOL, "source_before": before, "source_after": code_identity(),
              "script_sha256": digest(Path(__file__).read_bytes()), "cases": cases,
              "cases_passed": sum(case["passed"] for case in cases), "case_count": len(cases),
              "checks_passed": sum(entry["passed"] for case in cases for entry in case["checks"]),
              "check_count": sum(len(case["checks"]) for case in cases),
              "not_executed": sum(entry["not_executed"] for case in cases for entry in case["checks"])}
    write(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", type=Path)
    parser.add_argument("--arguments", type=Path)
    parser.add_argument("--reached", type=Path)
    arguments = parser.parse_args()
    if arguments.child:
        child(arguments.child, arguments.arguments, arguments.reached)
    else:
        result = run(arguments.output)
        print(json.dumps({key: result[key] for key in ("cases_passed", "case_count", "checks_passed", "check_count", "not_executed")}))
        raise SystemExit(0 if result["cases_passed"] == result["case_count"] else 1)
