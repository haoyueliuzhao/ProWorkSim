"""CPU-only source partition and run-admission gates for software collaboration.

These gates validate provenance declarations, not repository behavior or model
performance. They never download tasks, launch a worker, or inherit old budgets.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

PURPOSES = (
    "interface_development", "policy_training", "contribution_development",
    "independent_confirmation",
)
TASK_FAMILIES = ("interface_producer_consumer", "cross_feature_integration")
MEMBER_CAPABILITIES = (
    "read", "edit", "test", "task_board", "exchange_patch", "integrate", "submit",
)
LEGACY_REPOSITORY = "github.com/marshmallow-code/marshmallow"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode()).hexdigest()


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def _sha(value, name, length=64):
    if not isinstance(value, str) or re.fullmatch(f"[0-9a-f]{{{length}}}", value) is None:
        raise ValueError(f"{name} requires a fixed {length}-digit lowercase hash")
    return value


def canonical_repository(value):
    """Canonicalize URL spelling; declared lineage must still identify forks."""
    _text(value, "repository")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1]
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("repository must be an HTTPS repository URL")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("repository credentials and alternate ports are not allowed")
    path = parsed.path.lower().rstrip("/").removesuffix(".git")
    if len(path.strip("/").split("/")) != 2:
        raise ValueError("repository must identify an owner/repository")
    return parsed.hostname.lower() + path


def _asset(raw):
    item = copy.deepcopy(dict(raw))
    for key in ("asset_id", "provider", "source_cluster"):
        _text(item.get(key), key)
    item["repository"] = canonical_repository(item.get("repository"))
    _sha(item.get("commit"), "commit", 40)
    _sha(item.get("target_patch_sha256"), "target_patch_sha256")
    _sha(item.get("environment_sha256"), "environment_sha256")
    # A generated candidate without an upstream issue uses a stable synthetic ID.
    _text(item.get("issue_id"), "issue_id")
    for field in ("test_sha256", "parent_asset_ids", "derivation_roots"):
        value = item.get(field)
        if not isinstance(value, list) or len(value) != len(set(value)):
            raise ValueError(f"{field} must be a list of unique identifiers")
        for element in value:
            _text(element, field)
        item[field] = sorted(value)
    if not item["test_sha256"] or not item["derivation_roots"]:
        raise ValueError("tests and derivation roots cannot be empty")
    for value in item["test_sha256"]:
        _sha(value, "test_sha256")
    if item.get("task_derivation_started") is not False:
        raise ValueError("assign source purposes before deriving collaboration tasks")
    if type(item.get("previously_used")) is not bool:
        raise ValueError("previously_used must be explicit")
    return item


def freeze_source_partition(assets: Sequence[Mapping], assignments: Mapping):
    """Freeze conservative whole-repository clusters before task derivation.

    Any shared repository, upstream cluster, commit, issue, target patch, test,
    derivation root, or parent edge joins a connected component. A component has
    one purpose; changing benchmark names does not separate its source lineage.
    """
    records = sorted((_asset(value) for value in assets), key=lambda item: item["asset_id"])
    ids = [item["asset_id"] for item in records]
    if not records or len(ids) != len(set(ids)):
        raise ValueError("nonempty inventory with unique asset IDs is required")
    if set(assignments) != set(ids) or any(p not in PURPOSES for p in assignments.values()):
        raise ValueError("assign every asset exactly one recognized purpose")
    parents = {key: key for key in ids}

    def root(key):
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    def join(a, b):
        left, right = sorted((root(a), root(b)))
        parents[right] = left

    seen = {}
    for item in records:
        key = item["asset_id"]
        for parent in item["parent_asset_ids"]:
            if parent not in parents:
                raise ValueError("all parent assets must be included in the inventory")
            join(key, parent)
        tags = [("repository", item["repository"]), ("cluster", item["source_cluster"]),
                ("commit", item["commit"]),
                ("issue", item["repository"] + "#" + item["issue_id"]),
                ("patch", item["target_patch_sha256"])]
        tags += [("test", value) for value in item["test_sha256"]]
        tags += [("derivation", value) for value in item["derivation_roots"]]
        for tag in tags:
            if tag in seen:
                join(key, seen[tag])
            else:
                seen[tag] = key
        purpose = assignments[key]
        if (item["previously_used"] or item["repository"] == LEGACY_REPOSITORY) and (
            purpose != "interface_development"
        ):
            raise ValueError("historical assets are restricted to interface development")
    groups = {}
    for key in ids:
        groups.setdefault(root(key), []).append(key)
    for group in groups.values():
        if len({assignments[key] for key in group}) != 1:
            raise ValueError(f"cross-purpose source leakage: {', '.join(group)}")
    payload = {"schema": "software-source-partition-v027", "assets": records,
               "assignments": dict(sorted(assignments.items())),
               "clusters": sorted(groups.values()),
               "policy": "whole_repository_and_lineage_disjoint",
               "frozen_before_task_derivation": True}
    return {**payload, "sha256": _digest(payload)}


def _verify_partition(partition):
    if not isinstance(partition, dict):
        raise ValueError("a frozen source partition is required")
    # Rebuild from original URLs because stored inventory uses canonical repo IDs.
    records = copy.deepcopy(partition.get("assets", []))
    for item in records:
        item["repository"] = "https://" + item["repository"]
    rebuilt = freeze_source_partition(records, partition.get("assignments", {}))
    if rebuilt != partition:
        raise ValueError("frozen source partition was changed or has an invalid digest")
    return {item["asset_id"]: item for item in partition["assets"]}


def validate_derived_tasks(partition, tasks, *, primary_training_source="swe_smith"):
    """Validate lineage and declared witnesses; no witness is executed here."""
    assets = _verify_partition(partition)
    if not tasks:
        raise ValueError("actual derived tasks are required for run admission")
    seen = set()
    for task in tasks:
        task_id = _text(task.get("task_id"), "task_id")
        if task_id in seen:
            raise ValueError("task IDs must be unique")
        seen.add(task_id)
        if task.get("partition_sha256") != partition["sha256"]:
            raise ValueError("task must reference its prior frozen source partition")
        if task.get("family") not in TASK_FAMILIES:
            raise ValueError("task must have a declared software collaboration family")
        source_ids = task.get("source_asset_ids")
        if not isinstance(source_ids, list) or not source_ids or len(set(source_ids)) != len(source_ids):
            raise ValueError("unique source_asset_ids are required")
        if any(key not in assets for key in source_ids):
            raise ValueError("task references an unpartitioned source")
        purpose = task.get("purpose")
        if purpose not in PURPOSES or any(
            partition["assignments"][key] != purpose for key in source_ids
        ):
            raise ValueError("derived task cannot change the source purpose")
        if purpose == "policy_training" and any(
            assets[key]["provider"] != primary_training_source for key in source_ids
        ):
            raise ValueError("training uses only the selected primary source")
        for field in ("requirements_sha256", "joint_solution_witness_sha256",
                      "dependency_witness_sha256", "independent_verifier_sha256"):
            _sha(task.get(field), field)
        members = task.get("members")
        if not isinstance(members, dict) or len(members) != 2:
            raise ValueError("two stable member identities are required")
        for member_id, capabilities in members.items():
            _text(member_id, "member_id")
            if not isinstance(capabilities, list) or set(capabilities) != set(MEMBER_CAPABILITIES):
                raise ValueError("both members must be able to code, test, organize and integrate")
    return {"tasks": len(tasks), "partition_sha256": partition["sha256"]}


def validate_on_policy_record(record, task, *, window_id, actor_sha256):
    """Reject teachers, old windows, and changed actor/member attribution."""
    if task.get("purpose") != "policy_training":
        raise ValueError("only policy_training tasks supply training experience")
    if record.get("origin") != "current_policy":
        raise ValueError("teacher and scripted trajectories are not current on-policy experience")
    if record.get("window_id") != window_id or record.get("actor_sha256") != actor_sha256:
        raise ValueError("experience must come from the declared current actor window")
    if record.get("task_id") != task.get("task_id") or record.get("member_id") not in task.get("members", {}):
        raise ValueError("experience must retain its original task and member identity")
    _sha(actor_sha256, "actor_sha256")
    _text(window_id, "window_id")
    _sha(record.get("raw_member_actions_sha256"), "raw_member_actions_sha256")
    return True


def require_run_admission(plan):
    """Fail closed on pending tasks, incomplete budget, or copied v0.26 limits."""
    if plan.get("schema") != "software-source-plan-v027":
        raise ValueError("a v027 source plan is required")
    if plan.get("primary_training_source") != "swe_smith":
        raise ValueError("SWE-smith is the selected primary; switching requires a new protocol")
    if plan.get("fallback_training_source") != "swe_gym":
        raise ValueError("SWE-Gym remains the declared inactive fallback")
    if plan.get("active_training_sources") != ["swe_smith"]:
        raise ValueError("do not build parallel training-source pipelines")
    if plan.get("teacher_trajectories_as_current_experience") is not False:
        raise ValueError("teacher trajectories cannot substitute for current policy experience")
    budget = plan.get("run_budget", {})
    if budget.get("protocol") != "software-collaboration-v027" or budget.get("inherited_from") is not None:
        raise ValueError("v027 must have its own budget, never an inherited v026 extension")
    if budget.get("frozen") is not True:
        raise ValueError("a separately frozen v027 run budget is required")
    for field in ("gpu_seconds", "wall_seconds", "episode_count", "max_decisions_per_member",
                  "context_tokens", "output_tokens"):
        value = budget.get(field)
        if type(value) is not int or not math.isfinite(value) or value <= 0:
            raise ValueError(f"a positive explicit {field} budget is required")
    if budget["output_tokens"] >= budget["context_tokens"]:
        raise ValueError("output reservation must leave space for the prompt")
    result = validate_derived_tasks(plan.get("partition"), plan.get("tasks"))
    if budget["episode_count"] < result["tasks"]:
        raise ValueError("episode budget does not cover the declared task inventory")
    return {**result, "source_admission": True, "execution_performed": False,
            "budget_sha256": _digest(budget), "semantic_witness_validation": "external_required"}
