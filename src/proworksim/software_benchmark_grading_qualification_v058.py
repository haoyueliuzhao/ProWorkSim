"""Read-only, per-instance admission for fresh v058 offline grading controls.

Every qualification covers exactly one gold/empty pair. The immutable control
plan still contains all four tasks; an unqualified sibling never becomes an
implicit failure or a reason to relabel a historical v057 control as v058.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from . import software_benchmark_grading_environment_v058 as environment
from .software_benchmark_candidates_v054 import checked
from .software_benchmark_scorer_v054 import canonical
from .storage import digest

VERSION = "v058-requests-task-qualification-r1"
ADMISSION_VERSION = "v058-offline-requests-fixture-admission-r1"
ROOT = Path(__file__).resolve().parents[2]
ADMISSION_SOURCE = ROOT / "tools/check_ref_grading_environment_v058.py"
TASKS = frozenset(environment.PROFILES)
BOUND_FIELDS = ("image", "dataset", "baseline_mapping", "scorer_manifest")
NAMESPACES = ("net", "mnt", "pid", "ipc")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
NAT_FIELDS = frozenset(("nat_registry", "nat_lane", "grading_nat_registry", "grading_network_lane"))


def load(reference):
    value = json.loads(checked(reference).read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Expected an immutable grading evidence object")
    return value


def _no_nat(value):
    if NAT_FIELDS.intersection(value):
        raise ValueError("v058 admission cannot reuse historical NAT evidence")


def _all_tasks(tasks):
    return isinstance(tasks, list) and len(tasks) == len(TASKS) and set(tasks) == TASKS


def _namespaces_are_private(evidence):
    if not isinstance(evidence, dict) or evidence.get("all_distinct") is not True:
        return False
    host, grader = evidence.get("host"), evidence.get("grader")
    if not isinstance(host, dict) or not isinstance(grader, dict):
        return False
    return all(type(host.get(name)) is int and type(grader.get(name)) is int
               and host[name] > 0 and grader[name] > 0 and host[name] != grader[name]
               for name in NAMESPACES)


def validate_qualification(reference, original_request):
    """Admit only the requested instance, without starting or inspecting resources."""
    value = load(reference)
    task = original_request.get("instance_id")
    controls = value.get("controls")
    if (task not in TASKS or value.get("instance_id") != task
            or value.get("version") != VERSION or value.get("passed") is not True
            or not _all_tasks(value.get("tasks"))
            or not isinstance(controls, list) or len(controls) != 2
            or type(value.get("model_calls")) is not int or value["model_calls"] != 0
            or value.get("official_scores_changed") is not False):
        raise ValueError("A fresh single-task gold/empty qualification is required")
    _no_nat(value)
    manifest = environment.validate_environment(value["environment_revision"])
    if manifest.get("version") != environment.VERSION or manifest.get("network_mode") != "none":
        raise ValueError("Only the v058 offline environment can qualify")
    _no_nat(manifest)
    profile = manifest["profiles"][task]
    if profile.get("admission_enabled") is not True or profile.get("blockers") != []:
        raise ValueError("This task environment remains disabled by an unresolved compatibility blocker")
    plan = load(value["plan"])
    _no_nat(plan)
    if (plan.get("version") != ADMISSION_VERSION
            or plan.get("environment_revision") != value["environment_revision"]
            or not _all_tasks(plan.get("tasks")) or plan.get("preparation_only") is not True
            or plan.get("actor_feedback") is not False or plan.get("model_calls") != 0
            or plan.get("official_candidate_scores_changed") is not False
            or checked(plan["source"]).resolve() != ADMISSION_SOURCE.resolve()):
        raise ValueError("Qualification must bind the complete fresh control plan and source")
    rows = plan.get("rows", [])
    if not isinstance(rows, list) or len(rows) != 2 * len(TASKS):
        raise ValueError("The full four-task control plan must remain present")
    keys = [(row.get("instance_id"), row.get("patch_kind")) for row in rows]
    if len(set(keys)) != len(keys) or set(keys) != {(t, k) for t in TASKS for k in ("gold", "empty")}:
        raise ValueError("Duplicated or missing tasks in the complete control plan")
    planned = {(row["instance_id"], row["patch_kind"]): row for row in rows}
    seen, original_refs, container_ids, run_ids = set(), [], set(), set()
    for item in controls:
        kind = item.get("patch_kind")
        if item.get("instance_id") != task or kind not in {"gold", "empty"} or kind in seen:
            raise ValueError("Qualification must contain its own unique gold and empty controls")
        seen.add(kind)
        row = planned[task, kind]
        if item.get("original_request") != row["original_request"]:
            raise ValueError("Control differs from its planned original task request")
        folder = Path(row["directory"])
        if not folder.is_absolute():
            raise ValueError("Control evidence directory must be absolute")
        for field, relative in (("receipt", "receipt.json"), ("quiescence", "quiescence.json"),
                                ("completion", "completion.json"),
                                ("initial_container", "official-output/initial-container.json"),
                                ("identity", "official-output/identity.json")):
            if Path(item[field]["path"]).resolve() != (folder / relative).resolve():
                raise ValueError("Control evidence path differs from its planned gold/empty endpoint")
        receipt, identity = load(item["receipt"]), load(item["identity"])
        quiet, completion = load(item["quiescence"]), load(item["completion"])
        observed, original = load(item["initial_container"]), load(item["original_request"])
        original_refs.append(item["original_request"])
        for record in (item, row, receipt, identity, observed):
            _no_nat(record)
        if (original.get("instance_id") != task
                or any(identity.get(key) != original.get(key)
                       or original_request.get(key) != original.get(key) for key in BOUND_FIELDS)):
            raise ValueError("Candidate or control differs from the qualified task environment")
        expected_run = "v058-env-admission-" + kind + "-" + digest(canonical(identity))[:40]
        if (receipt.get("version") != ADMISSION_VERSION or identity.get("version") != ADMISSION_VERSION
                or receipt.get("instance_id") != task or receipt.get("patch_kind") != kind
                or receipt.get("status") != "official_report" or receipt.get("model_calls") != 0
                or receipt.get("preparation_only") is not True or receipt.get("actor_feedback") is not False
                or receipt.get("official_candidate_scores_changed") is not False
                or receipt.get("identity") != item["identity"] or receipt.get("run_id") != expected_run
                or identity.get("candidate_kind") != kind or identity.get("instance_id") != task
                or identity.get("plan") != value["plan"] or identity.get("source") != plan["source"]
                or identity.get("environment_revision") != value["environment_revision"]
                or identity.get("original_request") != item["original_request"]
                or identity.get("limits") != original.get("limits")
                or identity.get("scoring_cpuset_cpus") != row["scoring_cpuset_cpus"]
                or identity.get("model_calls") != 0 or identity.get("preparation_only") is not True
                or identity.get("actor_feedback") is not False
                or identity.get("official_candidate_scores_changed") is not False
                or identity.get("candidate_tree_identity_claimed") is not False
                or completion.get("version") != ADMISSION_VERSION or completion.get("instance_id") != task
                or completion.get("returncode") != 0 or completion.get("status") != "process_exited"):
            raise ValueError("Fresh control identity, run ID or successful completion is invalid")
        patch_hash, patch_bytes = identity.get("gold_patch_sha256"), identity.get("gold_patch_bytes")
        if (not isinstance(patch_hash, str) or HEX64.fullmatch(patch_hash) is None
                or type(patch_bytes) is not int or patch_bytes < 0
                or (kind == "empty" and (patch_hash != digest(b"") or patch_bytes != 0))
                or (kind == "gold" and patch_bytes == 0)):
            raise ValueError("Reference and empty patch identities must be distinct and explicit")
        mapping = load(original["baseline_mapping"])
        cid = observed.get("container_id")
        if (not isinstance(cid, str) or HEX64.fullmatch(cid) is None
                or cid in container_ids or expected_run in run_ids
                or observed.get("environment_revision") != value["environment_revision"]
                or observed.get("image_id") != original["image"].get("image_id")
                or observed.get("head") != mapping.get("official_head")
                or observed.get("head_git_tree") != mapping.get("official_tree")
                or observed.get("working_tree_clean") is not True or observed.get("git_returncode") != 0
                or observed.get("effective_network_mode") != "none"
                or observed.get("host_config", {}).get("NetworkMode") != "none"
                or observed.get("host_network_namespace_shared") is not False
                or not _namespaces_are_private(observed.get("namespace_evidence"))
                or observed.get("httpbin_service_scope") != "container_loopback"
                or observed.get("local_httpbin") is not True
                or observed.get("standalone_httpbin") is not profile["standalone_httpbin"]
                or observed.get("task_files_changed") is not False
                or observed.get("timeout_route", {}).get("real_connect_timeout") is not True
                or quiet.get("quiescent") is not True or quiet.get("cleanup_errors") != []
                or quiet.get("owned_container_ids") != [cid]
                or quiet.get("create_result_unknown") is not False):
            raise ValueError("Offline container identity, namespace, baseline or quiescence is invalid")
        container_ids.add(cid)
        run_ids.add(expected_run)
        result = receipt.get("official_result")
        report = result[1].get(task, {}) if (isinstance(result, list) and len(result) == 2
                                           and isinstance(result[1], dict)) else {}
        if report.get("patch_successfully_applied") is not True or report.get("infra_failure"):
            raise ValueError("Control did not reach trustworthy official evaluation")
        if kind == "gold":
            if receipt.get("resolved") is not True or report.get("resolved") is not True:
                raise ValueError("Official reference repair did not pass this task environment")
        elif (receipt.get("resolved") is not False or report.get("resolved") is not False
                or not report.get("tests_status", {}).get("FAIL_TO_PASS", {}).get("failure")):
            raise ValueError("Unchanged baseline did not fail its required target test")
    if seen != {"gold", "empty"} or original_refs[0] != original_refs[1]:
        raise ValueError("Both controls must use the same fixed original task request")
    return value
