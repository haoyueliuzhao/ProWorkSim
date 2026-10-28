"""Narrow, source-bound reuse of v064 gold/empty environment controls."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

from . import software_benchmark_dispatch_v066 as policy
from .software_benchmark_candidates_v054 import checked, reference

VERSION = "v066-reused-qualification-r1"
PROOF_VERSION = "v066-official-scoring-equivalence-r1"
COMPONENTS = ("scorer", "grading_environment", "requests_offline", "requests_tls", "tcp_transport")
SOURCE_MANIFEST_FIELDS = frozenset(("adapter", "guard", "environment_router",
    "offline_requests_adapter", "real_tls_requests_adapter"))


def load(ref):
    return json.loads(checked(ref).read_bytes())


def normalized_ast(source, *, scorer=False):
    """Allow only the declared batch namespace rename and reuse validator."""
    tree = ast.parse(source.replace("v066", "v064"))
    if scorer:
        tree.body = [node for node in tree.body if not (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "validate_qualification")]
    options = {"show_empty": True} if "show_empty" in inspect.signature(ast.dump).parameters else {}
    return ast.dump(tree, include_attributes=False, **options)


def compare_sources(old_source, new_source, *, scorer=False):
    old = normalized_ast(old_source, scorer=scorer)
    new = normalized_ast(new_source, scorer=scorer)
    if old != new:
        raise ValueError("Scoring/environment code differs beyond the scoped version rename")
    return hashlib.sha256(old.encode()).hexdigest()


def equivalent_manifest_fields(old, new):
    if set(old) != set(new):
        raise ValueError("The scoring manifest schema changed")
    allowed = SOURCE_MANIFEST_FIELDS | {"version"}
    changed = [key for key in old if key not in allowed and old[key] != new[key]]
    if changed:
        raise ValueError("Scoring rules, dependencies or limits changed: " + ",".join(sorted(changed)))
    if (old["version"] != "v064-offline-capability-official-scorer-r1"
            or new["version"] != "v066-offline-capability-official-scorer-r1"):
        raise ValueError("Unexpected scoring versions")
    for field in SOURCE_MANIFEST_FIELDS:
        old_path, new_path = checked(old[field]), checked(new[field])
        if str(new_path) != str(old_path).replace("v064.py", "v066.py"):
            raise ValueError("Unexpected source alias in a scoring manifest: " + field)
    return sorted(set(old) - allowed)


def equivalence_value(old_manifest_ref, new_manifest_ref, plan_ref, inventory_ref):
    inventory = load(inventory_ref)
    if (inventory_ref != reference(policy.RESUME_FILE) or plan_ref != reference(policy.PLAN_FILE)
            or inventory["original_plan"] != reference(policy.PREDECESSOR_ROOT / "plan.json")):
        raise ValueError("Qualification reuse belongs to another continuation or old plan")
    if (old_manifest_ref != reference(policy.PREDECESSOR_ROOT / "coordinator/scorer-manifest.json")
            or new_manifest_ref != reference(policy.COORDINATOR_RUN_ROOT / "scorer-manifest.json")):
        raise ValueError("Use only the exact original and continuation scorer manifests")
    fields = equivalent_manifest_fields(load(old_manifest_ref), load(new_manifest_ref))
    sources = []
    for name in COMPONENTS:
        base = policy.ROOT / "src/proworksim" / ("software_benchmark_" + name)
        old_ref, new_ref = reference(str(base) + "_v064.py"), reference(str(base) + "_v066.py")
        digest = compare_sources(checked(old_ref).read_text(), checked(new_ref).read_text(), scorer=name == "scorer")
        sources.append({"component": name, "old": old_ref, "new": new_ref,
                        "normalized_AST_sha256": digest})
    return {"version": PROOF_VERSION, "old_manifest": old_manifest_ref,
        "new_manifest": new_manifest_ref, "old_plan": inventory["original_plan"],
        "new_plan": plan_ref, "continuation_inventory": inventory_ref,
        "unchanged_manifest_fields": fields, "sources": sources,
        "normalization": "Only literal v066 to v064 namespace; scorer validate_qualification excluded and old validator called for reused proofs",
        "host_dispatch_guard_equivalence_claimed": False,
        "official_tests_scoring_baseline_limits_and_environment_unchanged": True,
        "new_model_or_container_calls": 0}


def validate_reused(ref, config, plan_ref):
    value = load(ref)
    inventory_ref = reference(policy.RESUME_FILE)
    inventory = load(inventory_ref)
    task = config["instance_id"]
    original_ref = inventory.get("old_qualified", {}).get(task)
    expected_path = policy.COORDINATOR_RUN_ROOT / "qualifications" / (task + ".json")
    if (value.get("version") != VERSION or value.get("instance_id") != task
            or value.get("passed") is not True or value.get("model_calls") != 0
            or value.get("plan") != plan_ref or plan_ref != reference(policy.PLAN_FILE)
            or Path(ref["path"]).resolve() != expected_path
            or value.get("original_qualification") != original_ref or original_ref is None
            or value.get("original_plan") != inventory["original_plan"]
            or value.get("continuation_inventory") != inventory_ref):
        raise ValueError("Reused qualification is not the exact admitted old task proof")
    proof = load(value["equivalence_proof"])
    expected = equivalence_value(proof["old_manifest"], proof["new_manifest"], plan_ref, inventory_ref)
    if proof != expected:
        raise ValueError("Frozen scoring equivalence proof changed")
    old_plan, new_plan = load(inventory["original_plan"]), load(plan_ref)
    old_config_ref = old_plan["environments"][task]["configuration"]
    if (new_plan["environments"][task]["configuration"] != old_config_ref
            or config["scorer_request_base"] != load(old_config_ref)["scorer_request_base"]):
        raise ValueError("Qualification baseline/dataset/image configuration changed")
    from . import software_benchmark_scorer_v064 as old_scorer
    old_scorer.validate_qualification(original_ref, config, inventory["original_plan"])
    return value
