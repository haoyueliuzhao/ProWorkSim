"""Frozen v105 task identities with unchanged managed closure evidence semantics.

This repair does not turn an old failed controller or a missing actor sync into
a successful execution. Host transfer, closure, and quiescence checks still apply.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .repository_sources_v054 import tree_manifest, validate_tree, is_readonly
from .software_benchmark_candidates_v054 import (
    checked, reference, write_new, lock_episode_candidates, read_episode_candidates, changed_paths,
)
from .storage import digest, json_bytes

VERSION = "v106-v105-managed-dual-endpoint-closure-r1"
CONDITION = "DEEPSEEK_NT_PROJECT_B5000K"
SEED_BASE = 202611020105
# Public prespecified v105 task order; no scores or reference patches are bundled.
TASK_IDS = (
    'pylint-dev__pylint-4970',
    'sphinx-doc__sphinx-7889',
    'sympy__sympy-21930',
    'mwaskom__seaborn-3069',
    'pytest-dev__pytest-7571',
    'sympy__sympy-19954',
    'pytest-dev__pytest-7490',
    'pytest-dev__pytest-6197',
    'psf__requests-2931',
    'astropy__astropy-14995',
    'scikit-learn__scikit-learn-10908',
    'matplotlib__matplotlib-23476',
    'pallets__flask-5014',
    'astropy__astropy-7606',
    'matplotlib__matplotlib-20826',
    'pydata__xarray-3677',
    'sphinx-doc__sphinx-10614',
    'sympy__sympy-15017',
    'django__django-13807',
    'psf__requests-1921',
    'astropy__astropy-8872',
    'pytest-dev__pytest-10081',
    'matplotlib__matplotlib-22865',
    'django__django-15103',
    'sphinx-doc__sphinx-8265',
    'pydata__xarray-4687',
    'sympy__sympy-23824',
    'pydata__xarray-6461',
    'django__django-13158',
    'sympy__sympy-15345',
    'django__django-15957',
    'django__django-15278',
    'astropy__astropy-7671',
    'psf__requests-1766',
    'psf__requests-5414',
    'pytest-dev__pytest-7432',
    'sphinx-doc__sphinx-9698',
    'scikit-learn__scikit-learn-11310',
    'mwaskom__seaborn-3187',
    'pylint-dev__pylint-4604',
    'scikit-learn__scikit-learn-14894',
    'pylint-dev__pylint-6528',
    'pydata__xarray-4966',
    'scikit-learn__scikit-learn-12682',
    'astropy__astropy-13579',
    'scikit-learn__scikit-learn-25232',
    'pylint-dev__pylint-4551',
    'matplotlib__matplotlib-22719',
    'sphinx-doc__sphinx-8593',
    'matplotlib__matplotlib-26466',
)


def validate_slot_identity(slot_id, instance_id):
    """Accept only one of the fifty frozen PROJECT task/seed combinations."""
    if not isinstance(instance_id, str) or instance_id not in TASK_IDS:
        raise ValueError("Managed closure task is outside the frozen v105 panel")
    seed = SEED_BASE + TASK_IDS.index(instance_id)
    expected = f"v105:{instance_id}:{CONDITION}:{seed}"
    if not isinstance(slot_id, str) or slot_id != expected:
        raise ValueError("Managed closure requires the exact v105 PROJECT task and seed")
    return {"slot_id": expected, "instance_id": instance_id, "condition_id": CONDITION, "seed": seed}



def validate_delivery_evidence(evidence, snapshot, baseline_bundle):
    """Verify a frozen controller record; never run tools, tests or a grader.

    Callers must also bind these bytes to the original trusted controller output,
    its unique generation/slot and quiescence proof. Self-consistency alone is
    not an execution attestation from an arbitrary supplied JSON object.
    """
    validate_slot_identity(evidence.get("slot_id"), evidence.get("instance_id"))
    if (evidence.get("version") != VERSION or snapshot.get("version") != VERSION
            or evidence.get("slot_id") != snapshot.get("slot_id")
            or evidence.get("instance_id") != snapshot.get("instance_id")
            or evidence.get("locked_before_grading") is not True
            or evidence.get("model_calls_after_lock") != 0
            or type(evidence.get("submitted")) is not bool
            or snapshot.get("submitted") is not evidence["submitted"]):
        raise ValueError("Managed closure identity or lock-before-score boundary differs")
    inventory = evidence.get("delivery_inventory")
    if not isinstance(inventory, list):
        raise ValueError("Complete legal-delivery inventory is required")
    if tree_manifest(baseline_bundle["files"], baseline_bundle["entry_metadata"])["tree_sha256"] != evidence.get("baseline_tree_sha256"):
        raise ValueError("Managed delivery evidence belongs to another baseline")
    if not evidence["submitted"]:
        if (inventory or any(snapshot.get(key) is not None for key in ("candidate", "source_reference", "tree_sha256"))
                or evidence.get("binding") is not None or evidence.get("same_tree") is not None):
            raise ValueError("No legal delivery cannot acquire a substituted working tree")
        return {"submitted": False, "same_tree": None, "legal_delivery_evidence": False}
    binding, candidate = evidence["binding"], snapshot["candidate"]
    delivery, patch, test = (binding[name] for name in ("delivery", "fixed_patch", "public_test_event"))
    source = snapshot["source_reference"]
    if (not inventory or inventory[-1] != delivery or delivery.get("actor_id") != "member_001"
            or patch.get("author") != "member_001" or test.get("actor_id") != "member_001"
            or test.get("kind") != "test" or test.get("executed") is not True
            or test.get("sequence") != delivery.get("test_sequence")
            or not isinstance(source, dict) or set(source) != {"object_id", "version_id"}
            or any(not isinstance(value, str) or not value for value in source.values())):
        raise ValueError("The last legal delivery lacks its actual member/version/test chain")
    expected = {"source_reference": source, "source_sha256": digest(json_bytes(candidate)),
                "files_sha256": digest(json_bytes(candidate["files"]))}
    metadata_sha = digest(json_bytes(candidate["entry_metadata"]))
    if any(any(row.get(key) != value for key, value in expected.items()) for row in (delivery, patch, test)):
        raise ValueError("Delivery, fixed patch and test must bind the same complete source version")
    if any(row.get("entry_metadata_sha256") != metadata_sha for row in (delivery, patch, test)):
        raise ValueError("Delivery source entry metadata differs")
    policy = evidence["file_policy"]
    validate_tree(candidate["files"], candidate["entry_metadata"], policy)
    validate_tree(baseline_bundle["files"], baseline_bundle["entry_metadata"], policy)
    for path in set(candidate["files"]) | set(baseline_bundle["files"]):
        if is_readonly(path, policy) and (
                candidate["files"].get(path) != baseline_bundle["files"].get(path)
                or candidate["entry_metadata"].get(path) != baseline_bundle["entry_metadata"].get(path)):
            raise ValueError("Legal delivery changed a read-only baseline entry")
    changes = changed_paths(baseline_bundle, candidate)
    if (any(patch.get(key) != value for key, value in changes.items())
            or patch.get("changed_paths") != sorted(set().union(*changes.values()))
            or patch.get("base_reference") != evidence["baseline_reference"]):
        raise ValueError("Fixed patch does not cover the complete baseline-to-delivery change")
    tree = tree_manifest(candidate["files"], candidate["entry_metadata"])["tree_sha256"]
    if (tree != snapshot["tree_sha256"]
            or tree != test.get("public_execution", {}).get("execution", {}).get("input_tree_sha256")
            or test.get("public_execution", {}).get("execution", {}).get("executed") is not True
            or evidence.get("same_tree") is not (tree == evidence["terminal_tree_sha256"])):
        raise ValueError("Actual public execution or final-tree relationship changed")
    return {"submitted": True, "same_tree": evidence["same_tree"],
            "legal_delivery_evidence": True, "managed_tree_sha256": tree,
            "delivery_id": delivery["delivery_id"], "public_test_sequence": test["sequence"]}


def export_managed_closure(prepared, folder, *, slot_id, sdk_closed):
    if sdk_closed is not True:
        raise ValueError("Only the closed current SDK episode may lock final managed candidates")
    validate_slot_identity(slot_id, prepared.case["case_id"])
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lock_ref = lock_episode_candidates(prepared, run_root=folder / "project-candidates")
    pair = read_episode_candidates(lock_ref)
    terminal, delivery_bundle = pair["terminal_code"], pair["last_legal_delivery"]
    lock = pair["lock"]
    with prepared.world.store.lock():
        state = prepared.world.store.load()
        prepared.world.state = state
        delivery_inventory = copy.deepcopy(prepared.world._software()["deliveries"])
        _, _, baseline = prepared.world._bundle("member_001", baseline=True)
    terminal_lock = json.loads(checked(lock["terminal_code"]).read_bytes())
    terminal_binding = json.loads(checked(terminal_lock["binding"]).read_bytes())
    binding = None
    delivery_reference = None
    delivery_tree = None
    if delivery_bundle is not None:
        delivery_lock = json.loads(checked(lock["last_legal_delivery"]).read_bytes())
        binding = json.loads(checked(delivery_lock["binding"]).read_bytes())
        tests = [event for event in state["software_events"]
                 if event.get("kind") == "test" and event.get("sequence") == binding["public_test_sequence"]]
        if len(tests) != 1:
            raise ValueError("The selected delivery lost its actual same-version public-test event")
        binding["public_test_event"] = copy.deepcopy(tests[0])
        delivery_reference, delivery_tree = delivery_lock["source_reference"], delivery_lock["tree_sha256"]
    snapshot = {"version": VERSION, "slot_id": slot_id, "instance_id": prepared.case["case_id"],
                "submitted": delivery_bundle is not None, "candidate": delivery_bundle,
                "source_reference": delivery_reference, "tree_sha256": delivery_tree}
    evidence = {"version": VERSION, "slot_id": slot_id, "instance_id": prepared.case["case_id"],
                "submitted": delivery_bundle is not None, "binding": binding,
                "delivery_inventory": delivery_inventory,
                "file_policy": copy.deepcopy(prepared.case["file_policy"]),
                "baseline_reference": terminal_binding["baseline_reference"],
                "baseline_tree_sha256": tree_manifest(baseline["files"], baseline["entry_metadata"])["tree_sha256"],
                "terminal_source_reference": terminal_lock["source_reference"],
                "terminal_tree_sha256": terminal_lock["tree_sha256"],
                "same_tree": lock["same_tree"], "locked_before_grading": True,
                "model_calls_after_lock": 0, "controller_candidate_lock": lock_ref}
    validate_delivery_evidence(evidence, snapshot, baseline)
    return {"terminal_bundle": terminal,
            "terminal_snapshot": write_new(folder / "project-terminal-snapshot.json", terminal),
            "baseline_snapshot": write_new(folder / "project-baseline-snapshot.json", baseline),
            "delivery_snapshot": write_new(folder / "project-delivery-snapshot.json", snapshot),
            "delivery_evidence": write_new(folder / "delivery-evidence.json", evidence),
            "terminal_tree_sha256": terminal_lock["tree_sha256"],
            "terminal_source_reference": terminal_lock["source_reference"],
            "project_candidate_lock": reference(folder / "project-candidates/lock.json")}
