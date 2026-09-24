"""Read-only evaluation boundaries, separate from worker and world authority.

A failed assessment is not necessarily a failed worker. ``status`` identifies
what was observed; ``passed`` is retained solely as a finite-contract predicate.
No assessment result grants a permission or changes an institutional decision.
"""

import copy

STATUSES = (
    "pass",
    "content_failure",
    "structure_failure",
    "source_unavailable",
    "unassessed",
    "evaluator_error",
)
# This precedence summarizes simultaneous findings, never erases component results.
PRECEDENCE = (
    "evaluator_error",
    "structure_failure",
    "content_failure",
    "source_unavailable",
    "unassessed",
    "pass",
)


class EvaluationInputError(ValueError):
    """A recognized input condition, classified where its origin is known."""

    def __init__(self, status, reason):
        if status not in STATUSES or status in {"pass", "evaluator_error"}:
            raise ValueError("Invalid evaluation input status")
        self.status = status
        super().__init__(reason)


def combined_status(statuses):
    values = set(statuses)
    return next((status for status in PRECEDENCE if status in values), "unassessed")


def evaluator_fault(exc, *, boundary):
    return {
        "status": "evaluator_error",
        "passed": False,
        "reason": str(exc),
        "exception_type": type(exc).__name__,
        "boundary": boundary,
        "attribution": "evaluation_implementation_or_unclassified_internal_failure",
    }


def evaluate_submission(store, state, item, submission):
    """Contain unforeseen implementation failures without blaming the worker.

    Recognized malformed deliveries and unavailable sources are returned by the
    input boundaries in the domain evaluator. Only this explicit outer boundary
    catches arbitrary Exception; process cancellation and system exits propagate.
    """
    from .domains import work_product

    context = {}
    try:
        return work_product.evaluate_submission(store, state, item, submission, _context=context)
    except Exception as exc:
        return {
            "submission_id": submission.get("submission_id"),
            "evaluator_version": work_product.EVALUATOR_VERSION,
            **evaluator_fault(exc, boundary="submission_evaluator"),
            "checks": copy.deepcopy(context.get("checks", [])),
            "errors": copy.deepcopy(context.get("errors", [])),
            "read_set": copy.deepcopy(context.get("read_set", [])),
            "interrupted_check": copy.deepcopy(context.get("active_check")),
            "scope": "finite_json_xlsx_content_contract",
            "institutional_review": copy.deepcopy(submission.get("review")),
        }


EPISODE_ASSESSMENT_VERSION = "episode-assessment-v0.10"


def _fixed_submission(state, work_id, submission_id=None):
    item = state["work_items"].get(work_id)
    if item is None:
        raise ValueError("Unknown assessment work: " + str(work_id))
    submissions = item.get("submissions", [])
    if submission_id is None:
        return item, submissions[-1] if submissions else None
    selected = next((sub for sub in submissions if sub["submission_id"] == submission_id), None)
    if selected is None:
        raise ValueError("Submission does not belong to the declared assessment work")
    return item, selected


def _independent_target(store, state, target):
    import hashlib
    import json
    import math
    from .domains.work_product import _equal, _merge_json

    allowed = {
        "target_id",
        "work_id",
        "submission_id",
        "path",
        "expected",
        "availability",
        "role",
        "basis",
    }
    if (
        not isinstance(target, dict)
        or set(target) - allowed
        or not isinstance(target.get("target_id"), str)
        or not target["target_id"]
    ):
        raise ValueError("Independent target requires an identity and supported finite fields")
    result = {
        "target_id": target["target_id"],
        "scope": "independent_declared_goal",
        "declaration": copy.deepcopy(target),
        "read_set": [],
        "status": "unassessed",
        "passed": False,
    }
    if "expected" not in target or target.get("availability") == "unknown":
        return {**result, "reason": "No observed independent expected value was declared"}
    if target.get("availability", "known") not in {"known", "unknown"}:
        raise ValueError("Independent target availability must be known or unknown")
    expected, path = target["expected"], target.get("path")
    if type(expected) not in (str, int, float, bool, type(None)) or (
        type(expected) is float and not math.isfinite(expected)
    ):
        raise ValueError("Independent expected target must be a finite JSON scalar")
    if (
        not isinstance(path, list)
        or not path
        or any(
            not (isinstance(part, str) and part) and not (type(part) is int and part >= 0)
            for part in path
        )
    ):
        raise ValueError("Independent target path requires keys or nonnegative array indexes")
    _, submission = _fixed_submission(state, target.get("work_id"), target.get("submission_id"))
    if submission is None:
        return {**result, "reason": "No fixed submission exists"}
    result["submission_id"] = submission["submission_id"]
    documents = []
    try:
        for aid, vid in submission["artifact_versions"].items():
            artifact = state["artifacts"].get(aid)
            if artifact is None or vid not in artifact["versions"]:
                raise EvaluationInputError(
                    "source_unavailable", "Fixed submitted version is unavailable"
                )
            if artifact["kind"] != "json" or (
                "role" in target and artifact.get("deliverable_role") != target["role"]
            ):
                continue
            try:
                content = store.version_path(artifact, vid).read_bytes()
            except OSError as exc:
                raise EvaluationInputError("source_unavailable", str(exc)) from exc
            sha = hashlib.sha256(content).hexdigest()
            if sha != artifact["versions"][vid]["sha256"]:
                raise EvaluationInputError(
                    "source_unavailable", "Fixed submission digest differs from its committed bytes"
                )
            result["read_set"].append({"object_id": aid, "version_id": vid, "sha256": sha})
            try:
                document = json.loads(content)
            except ValueError as exc:
                raise EvaluationInputError("structure_failure", str(exc)) from exc
            if not isinstance(document, dict):
                raise EvaluationInputError(
                    "structure_failure", "Independent JSON target requires submitted objects"
                )
            documents.append(document)
        value, conflicts = _merge_json(documents)
        if path[0] in conflicts:
            raise EvaluationInputError(
                "structure_failure", "Ambiguous target across submitted files"
            )
        for part in path:
            if isinstance(value, dict) and isinstance(part, str) and part in value:
                value = value[part]
            elif isinstance(value, list) and type(part) is int and part < len(value):
                value = value[part]
            else:
                raise EvaluationInputError(
                    "structure_failure",
                    "Independent target path is absent from the fixed submission",
                )
        passed = _equal(value, expected)
        result.update(
            status="pass" if passed else "content_failure",
            passed=passed,
            actual=copy.deepcopy(value),
            expected=copy.deepcopy(expected),
        )
    except EvaluationInputError as exc:
        result.update(status=exc.status, reason=str(exc))
    return result


def _process_requirement(store, state, events, requirement):
    import hashlib

    rule = copy.deepcopy(requirement)
    if not isinstance(rule, dict) or not isinstance(rule.get("requirement_id"), str):
        raise ValueError("Process rule requires requirement_id")
    result = {
        "requirement_id": rule["requirement_id"],
        "declaration": rule,
        "status": "unassessed",
        "scope": "retained_episode_evidence_only",
    }
    if rule.get("kind") == "forbid_successful_tool":
        if set(rule) - {"requirement_id", "kind", "actions", "worker_ids"}:
            raise ValueError("Unsupported forbidden-tool rule fields")
        actions = rule.get("actions")
        workers = rule.get("worker_ids")
        if (
            not isinstance(actions, list)
            or not actions
            or any(not isinstance(action, str) for action in actions)
        ):
            raise ValueError("Forbidden-tool rule requires explicit tool names")
        if workers is not None and (
            not isinstance(workers, list) or any(not isinstance(worker, str) for worker in workers)
        ):
            raise ValueError("Process worker_ids must be declared labels")
        attempts = [
            event
            for event in events
            if event["kind"] == "tool_call"
            and event["payload"].get("action") in actions
            and (workers is None or event.get("worker_id") in workers)
        ]
        violations = [
            event["sequence"]
            for event in attempts
            if event["payload"].get("response", {}).get("ok") is True
        ]
        rejected = [
            event["sequence"]
            for event in attempts
            if event["payload"].get("response", {}).get("ok") is False
        ]
        result.update(
            status="violation" if violations else "pass",
            violation_sequences=violations,
            rejected_attempt_sequences=rejected,
        )
    elif rule.get("kind") == "preserve_version":
        if set(rule) != {"requirement_id", "kind", "object_id", "version_id", "sha256"}:
            raise ValueError("Preservation requires an exact version and initial byte digest")
        artifact = state["artifacts"].get(rule["object_id"])
        if artifact is None or rule["version_id"] not in artifact["versions"]:
            return {
                **result,
                "status": "source_unavailable",
                "reason": "Declared exact version unavailable",
            }
        try:
            actual = hashlib.sha256(
                store.version_path(artifact, rule["version_id"]).read_bytes()
            ).hexdigest()
        except OSError as exc:
            return {**result, "status": "source_unavailable", "reason": str(exc)}
        committed = artifact["versions"][rule["version_id"]]["sha256"]
        result.update(
            status="pass" if actual == committed == rule["sha256"] else "violation",
            actual_sha256=actual,
            committed_sha256=committed,
        )
    else:
        raise ValueError("Unsupported process requirement kind")
    return result


def assess_episode(
    store, state, experience, *, work_ids=None, independent_targets=(), process_requirements=()
):
    """Assess retained fixed facts without writing the world or worker contexts.

    There is intentionally no overall success boolean: business approval,
    content validity, independent goals, process compliance and runtime health
    answer different questions. The caller is a trusted evaluator, not a worker.
    """
    from .core.projections import derive_current_work_view, derive_condition_view
    from .core.issues import derive_issue_view
    from .experience import ExperienceRecorder
    from .storage import digest, json_bytes
    from .tool_outcomes import classify_tool_result

    result = {"version": EPISODE_ASSESSMENT_VERSION, "assessment_execution": {"status": "complete"}}
    try:
        if not isinstance(experience, dict) or not isinstance(experience.get("events"), list):
            raise ValueError("Assessment requires a retained experience snapshot")
        events = ExperienceRecorder(experience["events"]).events
        views = derive_current_work_view(state)
        selected = sorted(
            work_ids
            if work_ids is not None
            else [wid for wid, view in views.items() if view["is_current"]]
        )
        if len(selected) != len(set(selected)):
            raise ValueError("Assessment work identities must be distinct")
        result["evidence_scope"] = {
            "world_id": state["world_id"],
            "work_ids": selected,
            "state_sha256": digest(json_bytes(state)),
            "experience_sha256": digest(json_bytes(experience)),
            "content_selection": "latest_fixed_submission_of_each_selected_work",
        }
        institutional, contents, incomplete, faults = [], [], [], []
        for wid in selected:
            item, submission = _fixed_submission(state, wid)
            view = views[wid]
            institutional.append(
                {
                    "work_id": wid,
                    "project_id": item["project_id"],
                    "requirement_version": item["requirement_version"],
                    "status": view["status"],
                    "is_current": view["is_current"],
                    "submission_id": submission["submission_id"] if submission else None,
                    "review": copy.deepcopy(submission.get("review")) if submission else None,
                    "submission_applicability": submission.get("current_applicability")
                    if submission
                    else None,
                }
            )
            evaluation = (
                evaluate_submission(store, state, item, submission)
                if submission
                else {
                    "status": "unassessed",
                    "passed": False,
                    "reason": "No fixed submission exists",
                    "checks": [],
                }
            )
            contents.append(
                {"work_id": wid, "project_id": item["project_id"], "evaluation": evaluation}
            )
            if evaluation["status"] in {"unassessed", "source_unavailable"}:
                incomplete.append(
                    {
                        "work_id": wid,
                        "kind": evaluation["status"],
                        "reason": evaluation.get("reason"),
                    }
                )
            if evaluation["status"] == "evaluator_error":
                faults.append(
                    {
                        "work_id": wid,
                        "kind": "evaluator_error",
                        "evaluation": copy.deepcopy(evaluation),
                    }
                )
            for check in evaluation.get("checks", []):
                for label in check.get("unassessed", []):
                    incomplete.append(
                        {"work_id": wid, "kind": "unassessed_contract_scope", "description": label}
                    )
                for row in check.get("declared_unresolved", []):
                    incomplete.append(
                        {
                            "work_id": wid,
                            "kind": "explicit_unresolved",
                            "validated": check["status"] == "pass",
                            "claim": copy.deepcopy(row),
                        }
                    )
                for diagnostic in check.get("diagnostics", []):
                    expected = diagnostic.get("expected")
                    if isinstance(expected, dict) and expected.get("status") == "unresolved":
                        incomplete.append(
                            {
                                "work_id": wid,
                                "kind": "explicit_unknown_report_claim",
                                "validated": diagnostic.get("passed", False),
                                "claim_id": diagnostic.get("claim_id"),
                                "source_value": expected.get("value"),
                            }
                        )
        result["institutional_progress"] = {
            "status": "observed",
            "works": institutional,
            "quality_claim": "none",
            "issues": {
                iid: view
                for iid, view in derive_issue_view(state).items()
                if view["work_id"] in selected
            },
            "conditions": {
                cid: view
                for cid, view in derive_condition_view(state).items()
                if state["condition_specs"][cid].get("work_id") in selected
            },
        }
        result["content_quality"] = {"submissions": contents}
        targets = [_independent_target(store, state, target) for target in independent_targets]
        result["independent_targets"] = {
            "status": combined_status(target["status"] for target in targets),
            "targets": targets,
            "reason": None if targets else "No independent goals declared",
        }
        for target in targets:
            if target["status"] in {"unassessed", "source_unavailable"}:
                incomplete.append(
                    {
                        "target_id": target["target_id"],
                        "kind": target["status"],
                        "reason": target.get("reason"),
                    }
                )
        process = [
            _process_requirement(store, state, events, requirement)
            for requirement in process_requirements
        ]
        process_status = (
            "violation"
            if any(row["status"] == "violation" for row in process)
            else "source_unavailable"
            if any(row["status"] == "source_unavailable" for row in process)
            else "pass"
            if process
            else "unassessed"
        )
        result["process_constraints"] = {
            "status": process_status,
            "requirements": process,
            "reason": None if process else "No process requirements declared",
        }
        runtime = []
        boundaries = []
        for event in events:
            kind, payload = event["kind"], event["payload"]
            if kind in {"interface_error", "policy_error", "binding_error"}:
                runtime.append(copy.deepcopy(event))
            elif kind == "tool_call":
                if "exception" in payload:
                    runtime.append(
                        {
                            "sequence": event["sequence"],
                            "worker_id": event.get("worker_id"),
                            "kind": "interface_exception",
                            "facts": copy.deepcopy(payload),
                        }
                    )
                elif payload.get("response", {}).get("ok") is False:
                    runtime.append(
                        {
                            "sequence": event["sequence"],
                            "worker_id": event.get("worker_id"),
                            "kind": "tool_rejection",
                            **classify_tool_result(payload["response"]),
                        }
                    )
            elif kind in {"run_boundary", "scenario_boundary"}:
                boundaries.append(copy.deepcopy(event))
                if payload.get("status") in {
                    "budget_exhausted",
                    "environment_error",
                    "policy_error",
                    "binding_mismatch",
                    "controller_rejected",
                    "unbuildable",
                    "capability_gap",
                }:
                    runtime.append(copy.deepcopy(event))
        result["incompleteness"] = {
            "items": incomplete,
            "interpretation": "Explicit contract-valid unknowns are not fabricated zeros or arithmetic failures",
        }
        result["runtime_problems"] = {
            "events": runtime,
            "evaluator_faults": faults,
            "run_boundaries": boundaries,
        }
        result["external_events"] = {
            "controller": [
                copy.deepcopy(event) for event in events if event["kind"] == "controller_action"
            ],
            "environment": [
                copy.deepcopy(event) for event in events if event["kind"] == "environment_event"
            ],
        }
    except Exception as exc:
        result["assessment_execution"] = evaluator_fault(exc, boundary="episode_assessment")
    return result
