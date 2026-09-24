"""Versioned finite reward mapping over fixed episode diagnostics.

This module never approves work, edits assessment facts, or rewards numbers of
messages, institutional approvals, issue decisions, publications or submissions.
Unknown evidence and evaluator/service failures remain excluded with reward null.
"""

import copy
import math

REWARD_VERSION = "reward-spec-v0.11"


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_reward_spec(spec):
    if not isinstance(spec, dict) or set(spec) - {
        "version",
        "reward_id",
        "objectives",
        "process_requirements",
        "cost",
    }:
        raise ValueError("Unsupported reward specification")
    result = copy.deepcopy(spec)
    if (
        result.get("version") != REWARD_VERSION
        or not isinstance(result.get("reward_id"), str)
        or not result["reward_id"]
    ):
        raise ValueError("Reward requires its version and nonempty identity")
    objectives = result.get("objectives")
    if not isinstance(objectives, list) or not objectives:
        raise ValueError("Reward requires declared finite objectives")
    identities = set()
    for goal in objectives:
        if not isinstance(goal, dict) or goal.get("kind") not in {"content", "independent_target"}:
            raise ValueError("Unsupported reward objective kind")
        if goal["kind"] == "content" and ("work_id" in goal) == ("work_node" in goal):
            raise ValueError("Content reward requires exactly one work_id or work_node")
        field = (
            ("work_id" if "work_id" in goal else "work_node")
            if goal["kind"] == "content"
            else "target_id"
        )
        if (
            set(goal) - {"kind", field, "weight"}
            or not isinstance(goal.get(field), str)
            or not goal[field]
        ):
            raise ValueError("Reward objective requires its exact identity")
        identity = goal["kind"], goal[field]
        if identity in identities:
            raise ValueError("Reward cannot count the same objective twice")
        identities.add(identity)
        goal.setdefault("weight", 1)
        if not _finite(goal["weight"]) or goal["weight"] <= 0:
            raise ValueError("Reward weight must be positive and finite")
    requirements = result.setdefault("process_requirements", [])
    if (
        not isinstance(requirements, list)
        or any(not isinstance(item, str) for item in requirements)
        or len(requirements) != len(set(requirements))
    ):
        raise ValueError("Process constraints require distinct identities")
    if "cost" in result:
        cost = result["cost"]
        if (
            not isinstance(cost, dict)
            or set(cost) != {"per_tool_call", "max_penalty"}
            or any(not _finite(value) or value < 0 for value in cost.values())
        ):
            raise ValueError("Cost requires nonnegative finite per_tool_call and max_penalty")
    return result


def episode_reward(assessment, spec):
    """Map only a fixed historical episode, retaining all failure denominators."""
    spec = validate_reward_spec(spec)
    result = {
        "version": REWARD_VERSION,
        "reward_id": spec["reward_id"],
        "spec": spec,
        "eligible": False,
        "reward": None,
        "components": [],
        "exclusions": [],
        "process_violations": [],
    }
    if not isinstance(assessment, dict) or "historical_episode" not in assessment:
        result["exclusions"].append("Fixed historical episode identity is required")
        return result
    result["episode_id"] = assessment["historical_episode"]["episode_id"]
    result["manifest_sha256"] = assessment["historical_episode"]["manifest_sha256"]
    if assessment.get("assessment_execution", {}).get("status") != "complete":
        result["exclusions"].append("Assessment execution is unavailable or faulty")
        return result
    content = {
        row["work_id"]: row["evaluation"]
        for row in assessment.get("content_quality", {}).get("submissions", [])
    }
    goals = {
        row["target_id"]: row
        for row in assessment.get("independent_targets", {}).get("targets", [])
    }
    fixed = assessment["historical_episode"]["fixed_deliveries"]
    for goal in spec["objectives"]:
        key = goal.get("work_id", goal.get("target_id"))
        if "work_node" in goal:
            key = assessment["historical_episode"].get("node_bindings", {}).get(goal["work_node"])
        value = content.get(key) if goal["kind"] == "content" else goals.get(key)
        status = value.get("status") if value else None
        no_submission = (
            goal["kind"] == "content" and key in fixed and fixed[key]["submission_id"] is None
        )
        if no_submission:
            score, reason = 0, "Declared episode responsibility ended without a submission"
        elif status == "pass":
            prior = assessment["historical_episode"].get("start_fixed_deliveries", {}).get(key, {})
            if (
                goal["kind"] == "content"
                and prior.get("submission_id") is not None
                and (
                    prior["submission_id"] == fixed[key]["submission_id"]
                    or prior.get("artifact_versions") == fixed[key]["artifact_versions"]
                )
            ):
                score, reason = (
                    None,
                    "Passed fixed submission predates this episode; no new work credit",
                )
                result["exclusions"].append(
                    {"objective": key, "status": "inherited_submission", "reason": reason}
                )
            else:
                score, reason = 1, "Declared finite objective passed"
        elif status in {"content_failure", "structure_failure"}:
            score, reason = 0, "Real evaluable delivered failure retained"
        else:
            score, reason = None, "Objective is missing, unknown, unavailable or evaluator-faulty"
            result["exclusions"].append({"objective": key, "status": status, "reason": reason})
        result["components"].append(
            {
                "kind": goal["kind"],
                "identity": key,
                "weight": goal["weight"],
                "diagnostic_status": status,
                "score": score,
                "reason": reason,
            }
        )
    requirements = {
        row["requirement_id"]: row
        for row in assessment.get("process_constraints", {}).get("requirements", [])
    }
    for identity in spec["process_requirements"]:
        status = requirements.get(identity, {}).get("status")
        if status == "violation":
            result["process_violations"].append(identity)
        elif status != "pass":
            result["exclusions"].append({"process_requirement": identity, "status": status})
    problems = assessment.get("runtime_problems", {})
    for event in problems.get("events", []):
        if (
            event.get("kind") in {"interface_error", "interface_exception", "model_service_error"}
            or event.get("status") == "environment_error"
            or event.get("payload", {}).get("status") == "model_service_error"
        ):
            result["exclusions"].append(
                {
                    "runtime_sequence": event.get("sequence"),
                    "reason": "Observed infrastructure/service failure",
                }
            )
    result["cost_penalty"] = 0
    if "cost" in spec:
        counts = assessment.get("evidence_scope", {}).get("event_counts")
        calls = counts.get("tool_call", 0) if isinstance(counts, dict) else None
        if type(calls) is not int or calls < 0:
            result["exclusions"].append("Actual episode tool-call count is unavailable")
        else:
            result["cost_penalty"] = min(
                spec["cost"]["max_penalty"], calls * spec["cost"]["per_tool_call"]
            )
    # A proven violation of an explicitly required process gate is sufficient
    # for task non-completion even when the content itself remains unassessed.
    # Infrastructure faults/unavailable evidence keep their exclusion priority.
    if result["process_violations"] and result["exclusions"]:
        only_unassessed_components = all(
            isinstance(reason, dict)
            and "objective" in reason
            and reason.get("status") == "unassessed"
            for reason in result["exclusions"]
        )
        if only_unassessed_components:
            result["unassessed_components"] = result["exclusions"]
            result["exclusions"] = []
            result.update(
                eligible=True,
                reward=0.0,
                decisive_evidence="Explicit required process violation; unknown content component remains null",
            )
            return result
    if result["exclusions"]:
        return result
    score = sum(row["weight"] * row["score"] for row in result["components"]) / sum(
        row["weight"] for row in result["components"]
    )
    result.update(
        eligible=True,
        reward=0.0 if result["process_violations"] else max(0.0, score - result["cost_penalty"]),
    )
    return result
