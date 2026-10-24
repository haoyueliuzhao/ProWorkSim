"""Admit scoring only after all four requests gold/empty environment controls."""
from __future__ import annotations

import json

from . import software_benchmark_grading_environment_v057 as environment
from .software_benchmark_candidates_v054 import checked

VERSION = "v057-requests-grading-qualification-r1"
TASKS = set(environment.PROFILES)


def load(reference):
    return json.loads(checked(reference).read_bytes())


def validate_qualification(reference, original_request):
    """Validate actual control reports, never just a claimed passed flag."""
    value = load(reference)
    if (value.get("version") != VERSION or value.get("passed") is not True
            or set(value.get("tasks", [])) != TASKS or len(value.get("controls", [])) != 8
            or value.get("model_calls") != 0 or value.get("official_scores_changed") is not False):
        raise ValueError("All four gold and four empty grading controls must qualify")
    environment.validate_environment(value["environment_revision"])
    plan = load(value["plan"])
    if (plan.get("environment_revision") != value["environment_revision"]
            or plan.get("nat_registry") != value["nat_registry"]
            or set(plan.get("tasks", [])) != TASKS or plan.get("preparation_only") is not True):
        raise ValueError("Qualification does not bind its complete environment control plan")
    seen, requests = set(), {}
    for item in value["controls"]:
        task, kind = item["instance_id"], item["patch_kind"]
        if task not in TASKS or kind not in {"gold", "empty"} or (task, kind) in seen:
            raise ValueError("Duplicated or unplanned qualification control")
        seen.add((task, kind))
        receipt, identity = load(item["receipt"]), load(item["identity"])
        quiet, completion = load(item["quiescence"]), load(item["completion"])
        observed = load(item["initial_container"])
        original = load(item["original_request"])
        requests[task] = original
        if (receipt.get("instance_id") != task or receipt.get("patch_kind") != kind
                or receipt.get("status") != "official_report" or receipt.get("model_calls") != 0
                or receipt.get("preparation_only") is not True or receipt.get("actor_feedback") is not False
                or receipt.get("identity") != item["identity"]
                or identity.get("candidate_kind") != kind or identity.get("instance_id") != task
                or identity.get("plan") != value["plan"]
                or identity.get("environment_revision") != value["environment_revision"]
                or identity.get("original_request") != item["original_request"]
                or identity.get("nat_lane", {}).get("registry") != value["nat_registry"]
                or observed.get("nat_lane") != identity.get("nat_lane")
                or observed.get("host_network_namespace_shared") is not False
                or observed.get("timeout_route", {}).get("real_connect_timeout") is not True
                or quiet.get("quiescent") is not True or quiet.get("cleanup_errors")
                or quiet.get("owned_container_ids") != [observed.get("container_id")]
                or quiet.get("create_result_unknown") is not False
                or completion.get("returncode") != 0):
            raise ValueError("Control identity, completion, report or container quiescence is invalid")
        result = receipt.get("official_result")
        report = result[1].get(task, {}) if isinstance(result, list) and len(result) == 2 else {}
        if report.get("patch_successfully_applied") is not True or report.get("infra_failure"):
            raise ValueError("Control did not reach trustworthy official evaluation")
        if kind == "gold":
            if receipt.get("resolved") is not True or report.get("resolved") is not True:
                raise ValueError("Official reference repair did not pass this environment")
        elif (receipt.get("resolved") is not False or report.get("resolved") is not False
                or not report.get("tests_status", {}).get("FAIL_TO_PASS", {}).get("failure")):
            raise ValueError("Unchanged baseline did not fail its required target test")
        for key in ("image", "dataset", "baseline_mapping", "scorer_manifest"):
            if identity.get(key) != original[key]:
                raise ValueError("Control image, dataset, baseline or original harness changed")
    if seen != {(task, kind) for task in TASKS for kind in ("gold", "empty")}:
        raise ValueError("Qualification is missing a task or control endpoint")
    task = original_request["instance_id"]
    if task not in requests:
        raise ValueError("Candidate is outside the four admitted requests tasks")
    for key in ("image", "dataset", "baseline_mapping", "scorer_manifest"):
        if original_request[key] != requests[task][key]:
            raise ValueError("Candidate does not use the qualified task environment")
    return value
