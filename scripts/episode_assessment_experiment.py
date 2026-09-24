"""R4: responsibility-separated assessments of actual modular staff episodes."""

import argparse
import copy
import hashlib
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from proworksim.audit import code_identity
from proworksim.domains import research_review
from proworksim.evaluation import assess_episode
from proworksim.scenarios import build_scenario, bind_runtime, load_scenario, run_scenario
from proworksim.staff_runtime import StaffRuntime
from proworksim.workers.team_policies import ReconciliationPolicy, ReviewerPolicy

CASES = (
    "upstream_wrong_downstream_faithful",
    "metadata_right_body_wrong",
    "reasonable_unknown",
    "evaluator_fault",
)
COMMON = (
    "declared_scenario_constructed",
    "actual_modular_runtime_reached_boundary",
    "independent_capture_equals_experience",
    "assessment_execution_complete",
    "repeated_assessment_equal",
    "all_world_facts_preserved",
    "all_immutable_bytes_preserved",
    "unrelated_project_preserved",
    "no_undeclared_goal_pass",
    "no_undeclared_process_pass",
    "successful_forbidden_action_is_process_violation",
    "fixed_source_preservation_assessed",
    "controller_and_environment_separate",
)
SPECIFIC = {
    CASES[0]: (
        "wrong_upstream_institutionally_accepted",
        "upstream_content_fails",
        "downstream_faithful_content_passes",
        "downstream_literal_business_target_fails",
        "one_injected_upstream_defect",
    ),
    CASES[1]: (
        "pending_delivery_retained",
        "metadata_correct_body_wrong_detected",
        "metadata_literal_target_passes_without_erasing_body_failure",
        "no_review_or_automatic_repair",
    ),
    CASES[2]: (
        "known_null_source_is_legitimate",
        "content_contract_passes",
        "unobserved_goal_stays_unassessed",
        "explicit_null_target_is_known_and_passes",
    ),
    CASES[3]: (
        "evaluation_fault_separate_from_worker_content",
        "fault_has_actual_read_evidence",
        "independent_target_still_assessable",
        "business_acceptance_survives_evaluation_fault",
    ),
}
CHECKS = {name: COMMON + SPECIFIC[name] for name in CASES}
PROTOCOL = {
    "suite": "episode-assessment-R4-v0.10",
    "cases": CASES,
    "checks": CHECKS,
    "planned_checks": sum(map(len, CHECKS.values())),
    "scope": "Four independent synthetic modular episodes; one explicit policy fault and one evaluator fault are separate controls, not model runs. No evaluator output feeds policies or scenario control.",
    "literal_truth": "Initial finite ledger has one cost conflict (80 versus90). Report source revenue120 with baseline100; incomplete cost is actual null. Finite report metadata and full body are assessed independently.",
    "process_scope": "Only explicit retained-episode forbidden-action and exact-byte preservation declarations; no open professional compliance inference.",
}


class WrongSummaryPolicy(ReconciliationPolicy):
    """Declared experimental fault in the policy's real write decision."""

    def __init__(self):
        super().__init__()
        self.config["experiment_fault"] = "summary_conflict_2_instead_of_1"

    def decide(self, context):
        result = super().decide(context)
        if result.get("action") in {"write_object", "create_object"}:
            data = result["arguments"].get("data", {})
            if "reconciliation" in data:
                data["reconciliation"]["summary"]["conflict"] = 2
        return result


class ApprovalDespiteFindingPolicy(ReviewerPolicy):
    """Read actual submitted/source bytes, then deliberately approve a known issue."""

    def __init__(self):
        super().__init__()
        self.config["experiment_fault"] = "approve_despite_actual_public_finding"

    def decide(self, context):
        result = super().decide(context)
        if result.get("action") == "raise_issue":
            arguments = result["arguments"]
            result["action"] = "approve"
            result["arguments"] = {key: arguments[key] for key in ("work_id", "submission_id")}
        return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def scenario(name):
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "scenarios-v10"
        / ("chain-accepted.json" if name == CASES[0] else "report-direct.json")
    )
    spec = load_scenario(path)
    spec["scenario_id"] = "R4-" + name
    spec["events"] = []
    spec["projects"].append({"recipe": "reconciliation", "parameters": {"project_id": "UNRELATED"}})
    if name == CASES[0]:
        spec["boundary"]["complete_when"] = {
            "all": [
                {"work": {"project": pid, "node": node, "phase": "accepted"}}
                for pid, node in (("FINANCE", "reconcile"), ("REPORT", "research"))
            ]
        }
    else:
        spec["boundary"]["complete_when"] = {
            "work": {
                "project": "REPORT",
                "node": "research",
                "phase": "pending" if name == CASES[1] else "accepted",
            }
        }
    if name == CASES[1]:
        spec["roles"] = [role for role in spec["roles"] if role["policy"] == "report_author"]
        spec["roles"][0]["config"] = {"initial_defects": {"revenue": "body_number"}}
    elif name == CASES[2]:
        spec["projects"][0]["parameters"]["incomplete"] = True
    return spec


def _bytes(world, state):
    return {
        aid + "@" + vid: hashlib.sha256(world.store.version_path(obj, vid).read_bytes()).hexdigest()
        for aid, obj in state["artifacts"].items()
        for vid in obj["versions"]
    }


def run_case(name, output):
    directory = Path(output) / name
    directory.mkdir(parents=True, exist_ok=False)
    checks = []
    report = {"case": name, "checks": checks, "construction_error": None}

    def check(key, value):
        if key not in CHECKS[name] or key in {row["name"] for row in checks}:
            raise AssertionError("Undeclared/repeated R4 check: " + key)
        checks.append(
            {
                "name": key,
                "passed": bool(value),
                "actual": bool(value),
                "expected": True,
                "not_executed": False,
            }
        )

    try:
        spec = scenario(name)
        write_json(directory / "scenario.json", spec)
        deployment = build_scenario(spec, directory / "world")
        check("declared_scenario_constructed", deployment.status == "ready")
        if deployment.status != "ready":
            raise AssertionError(deployment.diagnostics)
        world = deployment.world
        initial = copy.deepcopy(world.store.load())
        other = copy.deepcopy(initial["work_items"]["UNRELATED::reconcile"])
        capture = {}
        runtime = bind_runtime(deployment, captured=capture)
        if name == CASES[0]:
            policies = dict(runtime.policies)
            policies["analyst"] = WrongSummaryPolicy()
            policies["finance_reviewer"] = ApprovalDespiteFindingPolicy()
            runtime.recorder.record(
                "controller_action",
                {
                    "stage": "declared_policy_fault_binding",
                    "policies": {
                        label: copy.deepcopy(policy.config) for label, policy in policies.items()
                    },
                    "world_mutation": False,
                },
            )
            runtime = StaffRuntime(
                runtime.ports,
                policies,
                run_id="R4-upstream-policy-fault",
                recorder=runtime.recorder,
            )
        outcome = run_scenario(deployment, runtime=runtime)
        report["run"] = {
            k: copy.deepcopy(v)
            for k, v in outcome.items()
            if k not in {"worker_checkpoint", "experience", "outcomes"}
        }
        check(
            "actual_modular_runtime_reached_boundary",
            outcome["status"] in {"completed", "boundary_reached"},
        )
        if name == CASES[3]:
            runtime.recorder.record(
                "controller_action",
                {
                    "stage": "declared_evaluation_fault",
                    "boundary": "research_review.evaluate_check",
                    "exception_type": "RuntimeError",
                    "world_mutation": False,
                },
            )
        experience = runtime.recorder.snapshot()
        write_json(directory / "experience.json", experience)
        write_json(directory / "independent-capture.json", capture)
        check(
            "independent_capture_equals_experience",
            all(
                capture[label]
                == [
                    {"kind": event["kind"], "payload": event["payload"]}
                    for event in experience["events"]
                    if event.get("worker_id") == label
                    and event["kind"] in {"public_tools", "public_observation", "tool_call"}
                ]
                for label in capture
            ),
        )
        before = copy.deepcopy(world.store.load())
        files = _bytes(world, before)
        selected = (
            ["FINANCE::reconcile", "REPORT::research"] if name == CASES[0] else ["REPORT::research"]
        )
        sub = before["work_items"]["REPORT::research"]["submissions"][-1]
        docs = [
            json.loads(world.store.version_path(before["artifacts"][aid], vid).read_bytes())
            for aid, vid in sub["artifact_versions"].items()
        ]
        document = next(data for data in docs if "report" in data)
        section_id = "conflict" if name == CASES[0] else "cost" if name == CASES[2] else "revenue"
        section_index = next(
            i
            for i, row in enumerate(document["report"]["sections"])
            if row["section_id"] == section_id
        )
        targets = [
            {
                "target_id": "literal-business-target",
                "work_id": "REPORT::research",
                "path": ["report", "sections", section_index, "claims", 0, "value"],
                "expected": 1 if name == CASES[0] else None if name == CASES[2] else 120,
                "basis": "manual_fixture_literal",
            }
        ]
        if name == CASES[2]:
            targets.append(
                {
                    "target_id": "unobserved-external-cost",
                    "work_id": "REPORT::research",
                    "availability": "unknown",
                    "basis": "No external cost truth was observed",
                }
            )
        source_id = next(
            aid for aid, obj in initial["artifacts"].items() if obj["project_id"] == "UNRELATED"
        )
        preserved = {
            "requirement_id": "background-source-preservation",
            "kind": "preserve_version",
            "object_id": source_id,
            "version_id": "v1",
            "sha256": files[source_id + "@v1"],
        }
        if name == CASES[3]:

            def fail(*args, **kwargs):
                raise RuntimeError("Declared independent evaluator implementation fault")

            with patch.object(research_review, "evaluate_check", fail):
                assessments = [
                    assess_episode(
                        world.store,
                        before,
                        experience,
                        work_ids=selected,
                        independent_targets=targets,
                        process_requirements=[preserved],
                    )
                    for _ in range(2)
                ]
        else:
            assessments = [
                assess_episode(
                    world.store,
                    before,
                    experience,
                    work_ids=selected,
                    independent_targets=targets,
                    process_requirements=[preserved],
                )
                for _ in range(2)
            ]
        assessment = assessments[0]
        check(
            "assessment_execution_complete",
            assessment["assessment_execution"]["status"] == "complete",
        )
        check("repeated_assessment_equal", assessments[0] == assessments[1])
        no_declarations = assess_episode(world.store, before, experience, work_ids=selected)
        check(
            "no_undeclared_goal_pass",
            no_declarations["independent_targets"]["status"] == "unassessed",
        )
        check(
            "no_undeclared_process_pass",
            no_declarations["process_constraints"]["status"] == "unassessed",
        )
        forbidden = assess_episode(
            world.store,
            before,
            experience,
            work_ids=selected,
            process_requirements=[
                {
                    "requirement_id": "declared-forbidden-submit-control",
                    "kind": "forbid_successful_tool",
                    "actions": ["submit"],
                }
            ],
        )
        check(
            "successful_forbidden_action_is_process_violation",
            forbidden["process_constraints"]["status"] == "violation"
            and bool(forbidden["process_constraints"]["requirements"][0]["violation_sequences"]),
        )
        check(
            "fixed_source_preservation_assessed",
            assessment["process_constraints"]["status"] == "pass",
        )
        check(
            "controller_and_environment_separate",
            assessment["external_events"]["controller"]
            == [event for event in experience["events"] if event["kind"] == "controller_action"]
            and assessment["external_events"]["environment"]
            == [event for event in experience["events"] if event["kind"] == "environment_event"],
        )
        by_work = {
            row["work_id"]: row["evaluation"]
            for row in assessment["content_quality"]["submissions"]
        }
        b = by_work["REPORT::research"]
        goal = assessment["independent_targets"]["targets"][0]
        if name == CASES[0]:
            check(
                "wrong_upstream_institutionally_accepted",
                before["work_items"]["FINANCE::reconcile"]["status"] == "accepted",
            )
            check(
                "upstream_content_fails",
                by_work["FINANCE::reconcile"]["status"] == "content_failure",
            )
            check("downstream_faithful_content_passes", b["status"] == "pass")
            check(
                "downstream_literal_business_target_fails",
                goal["status"] == "content_failure"
                and goal["actual"] == 2
                and goal["expected"] == 1,
            )
            check(
                "one_injected_upstream_defect",
                len(by_work["FINANCE::reconcile"]["checks"][0]["diagnostics"]) == 1
                and by_work["FINANCE::reconcile"]["checks"][0]["diagnostics"][0]["issue"]
                == "summary",
            )
        elif name == CASES[1]:
            check(
                "pending_delivery_retained",
                before["work_items"]["REPORT::research"]["status"] == "in_review",
            )
            diagnostic = next(
                row for row in b["checks"][0]["diagnostics"] if row["claim_id"] == "revenue"
            )
            check(
                "metadata_correct_body_wrong_detected",
                b["status"] == "content_failure"
                and diagnostic["metadata_correct"]
                and not diagnostic["body_correct"],
            )
            check(
                "metadata_literal_target_passes_without_erasing_body_failure",
                goal["status"] == "pass" and b["status"] == "content_failure",
            )
            check(
                "no_review_or_automatic_repair",
                sub["review"] is None
                and len(before["work_items"]["REPORT::research"]["submissions"]) == 1
                and not before["issues"],
            )
        elif name == CASES[2]:
            unknowns = [
                row
                for row in assessment["incompleteness"]["items"]
                if row["kind"] == "explicit_unknown_report_claim"
            ]
            check(
                "known_null_source_is_legitimate",
                bool(unknowns)
                and all(row["validated"] and row["source_value"] is None for row in unknowns),
            )
            check("content_contract_passes", b["status"] == "pass")
            check(
                "unobserved_goal_stays_unassessed",
                assessment["independent_targets"]["targets"][1]["status"] == "unassessed",
            )
            check(
                "explicit_null_target_is_known_and_passes",
                goal["status"] == "pass" and goal["actual"] is None,
            )
        else:
            check(
                "evaluation_fault_separate_from_worker_content",
                b["status"] == "evaluator_error"
                and bool(assessment["runtime_problems"]["evaluator_faults"]),
            )
            check(
                "fault_has_actual_read_evidence",
                len(b["read_set"]) >= 2 and b["interrupted_check"]["kind"] == "research_report",
            )
            check("independent_target_still_assessable", goal["status"] == "pass")
            check(
                "business_acceptance_survives_evaluation_fault",
                before["work_items"]["REPORT::research"]["status"] == "accepted",
            )
        check("all_world_facts_preserved", before == world.store.load())
        check("all_immutable_bytes_preserved", files == _bytes(world, world.store.load()))
        check(
            "unrelated_project_preserved",
            other == world.store.load()["work_items"]["UNRELATED::reconcile"]
            and "UNRELATED" in world.store.load()["projects"],
        )
        report["assessment"] = assessment
        report["process_violation_control"] = forbidden["process_constraints"]
        write_json(directory / "experience.json", experience)
        write_json(directory / "independent-capture.json", capture)
        write_json(directory / "assessments.json", assessments)
        write_json(directory / "fixed-files.json", files)
    except Exception:
        report["construction_error"] = traceback.format_exc()
    for key in CHECKS[name]:
        if key not in {row["name"] for row in checks}:
            checks.append({"name": key, "passed": False, "not_executed": True})
    report.update(
        passed=all(row["passed"] for row in checks),
        passed_checks=sum(row["passed"] for row in checks),
        total_checks=len(CHECKS[name]),
        not_executed=sum(row["not_executed"] for row in checks),
    )
    write_json(directory / "report.json", report)
    return report


def run(output, workers=3):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        cases = list(executor.map(lambda name: run_case(name, output), CASES[:-1]))
    cases.append(run_case(CASES[-1], output))
    report = {
        "protocol": PROTOCOL,
        "source_before": before,
        "source_after": code_identity(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": cases,
        "passed": all(row["passed"] for row in cases),
        "passed_checks": sum(row["passed_checks"] for row in cases),
        "total_checks": sum(row["total_checks"] for row in cases),
        "not_executed": sum(row["not_executed"] for row in cases),
    }
    write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    result = run(args.output, args.workers)
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("passed", "passed_checks", "total_checks", "not_executed")
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)
