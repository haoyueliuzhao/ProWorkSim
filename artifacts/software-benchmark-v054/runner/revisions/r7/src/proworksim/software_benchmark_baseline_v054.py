"""Admission of unchanged official trees with only their legitimate Git ancestry."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FORMAT_POLICY = ROOT / "config/v054-historical-git-format-exceptions-r31.json"
FORMAT_POLICY_SHA256 = "43f5dd872f7b6b3eb6ebb48441758daef2c590e40e62f971a5983ad05e9c992c"


def format_policy():
    raw = FORMAT_POLICY.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FORMAT_POLICY_SHA256:
        raise ValueError("Historical Git format policy changed")
    value = json.loads(raw)
    for repo in value["repos"].values():
        audit = repo["official_source_audit"]
        data = (ROOT / audit["path"]).read_bytes()
        if len(data) != audit["bytes"] or hashlib.sha256(data).hexdigest() != audit["sha256"]:
            raise ValueError("Official source audit changed after historical Git policy freezing")
    return value


def _fsck(value, *, schema, repo, official_image_id):
    if schema == "proworksim.v054.actor-admission-r3":
        if value.get("fsck_returncode") != 0 or value.get("historical_format_exceptions"):
            raise ValueError("Unqualified Git format diagnostic in the original r3 mapping")
        return
    policy = format_policy()
    if (value.get("historical_format_exception_policy_sha256") != FORMAT_POLICY_SHA256
            or value.get("fsck_structural_validation_passed") is not True
            or value.get("fsck_connectivity_returncode") != 0):
        raise ValueError("Git format exception lacks its exact structural/source policy")
    approved = {item["object_id"]: item for item in policy["repos"].get(repo, {}).get("objects", [])}
    exceptions = value.get("historical_format_exceptions")
    if not isinstance(exceptions, list):
        raise ValueError("Exact historical Git diagnostic evidence is required")
    lines = []
    for item in exceptions:
        known = approved.get(item.get("object_id"))
        if (known is None or any(item.get(key) != known[key] for key in (
                "object_id", "object_type", "diagnostic_code", "diagnostic_line", "raw_sha256"))
                or item.get("source_official_image_id") != official_image_id
                or item.get("source_same_diagnostic") is not True
                or item.get("source_in_allowed_closure") is not True
                or item.get("target_object_hash_verified") is not True
                or ("raw_bytes" in item and item["raw_bytes"] != known["raw_bytes"])):
            raise ValueError("Historical Git exception differs from the exact approved object/source")
        lines.append(item["diagnostic_line"])
    actual = value.get("fsck_diagnostic_lines")
    if (not isinstance(actual, list) or sorted(actual) != sorted(lines)
            or len(set(lines)) != len(lines)):
        raise ValueError("Git diagnostics contain an unapproved, missing or duplicate line")
    expected = (policy["expected_format_only_exit_codes"]["badTimezone_object_error_only"]
                if any(item["diagnostic_code"] == "badTimezone" for item in exceptions)
                else policy["expected_format_only_exit_codes"]["warnings_only"])
    if type(value.get("fsck_returncode")) is not int or value["fsck_returncode"] != expected:
        raise ValueError("Git fsck status contains more than the admitted historical format diagnostic")


def _closure(value, head, tree, base, *, schema, repo, official_image_id):
    if (value.get("allowed_head") != head or value.get("tree") != tree
            or value.get("dataset_base") != base
            or type(value.get("commit_count")) is not int or value["commit_count"] < 1
            or value.get("allowed_ancestry_only") is not True
            or value.get("all_refs_within_allowed_ancestry") is not True
            or value.get("no_unreachable_objects") is not True):
        raise ValueError("Legitimate Git ancestry closure is not admitted")
    _fsck(value, schema=schema, repo=repo, official_image_id=official_image_id)


def validate_mapping(mapping, *, instance, image):
    if (mapping.get("schema") not in {"proworksim.v054.actor-admission-r3", "proworksim.v054.actor-admission-r3.1"}
            or mapping.get("status") != "actor_baseline_admitted"
            or mapping["instance_id"] != instance["instance_id"]
            or mapping["dataset_base"] != instance["base_commit"]
            or mapping["official_image_id"] != image["image_id"]
            or mapping["official_manifest_digest"] != image["manifest_digest"]
            or mapping.get("official_grading_image_modified") is not False):
        raise ValueError("Final r3 mapping differs from the admitted original task/image")
    for key in ("dataset_base", "base_tree", "official_head", "official_tree", "actor_head", "actor_tree"):
        if not re.fullmatch(r"[0-9a-f]{40}", mapping[key]):
            raise ValueError("Full Git identity required in baseline mapping")
    if (mapping["actor_head"] != mapping["official_head"]
            or mapping["actor_tree"] != mapping["official_tree"]
            or mapping.get("working_tree_clean") is not True
            or mapping.get("target_package_copy_paths") != []):
        raise ValueError("Actor must preserve the official setup HEAD/tree and public isolation")
    _closure(mapping["git_ancestry"], mapping["official_head"], mapping["official_tree"],
             mapping["dataset_base"], schema=mapping["schema"], repo=mapping["repo"],
             official_image_id=mapping["official_image_id"])
    closures = {item["path"]: item for item in mapping.get("submodule_ancestry", [])}
    if len(closures) != len(mapping.get("submodules", [])):
        raise ValueError("Submodule ancestry inventory differs")
    for module in mapping.get("submodules", []):
        _closure(closures[module["path"]], module["official_commit"], module["official_tree"],
                 module["official_commit"], schema=mapping["schema"], repo=mapping["repo"],
                 official_image_id=mapping["official_image_id"])
    version = mapping["runtime_version"]
    if (version.get("equal") is not True or version["official"].get("returncode") != 0
            or version["actor"].get("returncode") != 0
            or version["official"].get("version") != version["actor"].get("version")
            or not isinstance(version["actor"].get("version"), str)):
        raise ValueError("Actor runtime package version differs from the official image")
    return mapping
