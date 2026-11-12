"""Organization-development variants of four already-used schema roots.

Only organization wording and source identity change. The pinned public and
private quality drivers receive the same executable files as the parent roots;
old manifests, purposes and results remain untouched.
"""
from __future__ import annotations

import copy

from . import software_tasks_v036 as previous
from .storage import digest, json_bytes

VERSION = "software-organization-tasks-v0.38"
PURPOSE = "organization_development"
ORIGINAL_CASE_IDS = previous.CONTRIBUTION_CASE_IDS
TASK_IDS = CASE_IDS = tuple(name + "-orgdev-v038" for name in ORIGINAL_CASE_IDS)
ORIGINAL_IDS = dict(zip(TASK_IDS, ORIGINAL_CASE_IDS, strict=True))
NAMES = dict.fromkeys(TASK_IDS, "schema")
OLD_ORGANIZATION = (
    "This is one immutable root goal, not an execution task list. Two equal members\n"
    "start with private copies and no assigned tasks or owners. Create, revise, claim\n"
    "and coordinate your own work as useful. One member may complete everything;\n"
    "communication, two-person editing and a particular work order are not required.")
NEW_ORGANIZATION = (
    "This is one immutable root goal, not an execution task list. Equal members\n"
    "start with private copies and no assigned tasks or owners. Create, revise, claim\n"
    "and coordinate your own work as useful. One member may complete everything;\n"
    "communication, shared editing and a particular work order are not required.\n"
    "Your execution condition defines the initial members and birth limits.\n"
    "This run is organization development, not training or independent confirmation.")


def canonical_case_id(case_id):
    if case_id in ORIGINAL_CASE_IDS:
        return case_id + "-orgdev-v038"
    if case_id not in TASK_IDS:
        raise ValueError("Only four already-used schema organization-development roots are admitted")
    return case_id


def source_partition():
    payload = {"version": VERSION, "purpose": PURPOSE,
        "assignments": dict.fromkeys(TASK_IDS, PURPOSE), "original_ids": ORIGINAL_IDS,
        "parent_partition_sha256": previous.source_partition()["sha256"],
        "training_eligible": False, "independent_confirmation_eligible": False,
        "old_results_reclassified": False}
    return {**payload, "sha256": digest(json_bytes(payload))}


def source_manifest():
    rows = []
    for case_id, original_id in ORIGINAL_IDS.items():
        original = previous.build_case(original_id)
        contract = original["root_goal"]
        if contract.count(OLD_ORGANIZATION) != 1:
            raise ValueError("Parent organization paragraph changed")
        derived = contract.replace(OLD_ORGANIZATION, NEW_ORGANIZATION, 1)
        rows.append({"task_id": case_id, "original_case_id": original_id,
            "purpose": PURPOSE, "requirements_sha256": digest(derived.encode()),
            "parent_requirements_sha256": digest(contract.encode()),
            "parent_source_manifest_sha256": original["source_contract"]["source_manifest_sha256"],
            "public_checks_sha256": original["source_contract"]["public_checks_sha256"],
            "independent_verifier_sha256": original["source_contract"]["independent_verifier_sha256"],
            "training_eligible": False, "independent_confirmation_eligible": False})
    payload = {"version": VERSION, "cases": rows,
        "source_partition_sha256": source_partition()["sha256"],
        "scope": "Derived organization wording and purposes; unchanged pinned code and quality drivers"}
    return {**payload, "sha256": digest(json_bytes(payload))}


def build_case(case_id):
    case_id = canonical_case_id(case_id)
    original_id = ORIGINAL_IDS[case_id]
    value = copy.deepcopy(previous.build_case(original_id))
    before = value["root_goal"]
    if before.count(OLD_ORGANIZATION) != 1:
        raise ValueError("Parent organization-only paragraph differs from the frozen text")
    contract = before.replace(OLD_ORGANIZATION, NEW_ORGANIZATION, 1)
    parent_contract = copy.deepcopy(value["source_contract"])
    partition = source_partition()
    value.update(version=VERSION, task_id=case_id, original_case_id=original_id,
        purpose=PURPOSE, training_eligible=False, contribution_eligible=False,
        independent_confirmation_eligible=False, root_goal=contract,
        source_partition_sha256=partition["sha256"])
    value["files"]["contract.md"] = contract
    value["source_contract"].update(purpose=PURPOSE, organization_variant_id=case_id,
        original_case_id=original_id, original_purpose=parent_contract["purpose"],
        original_source_contract=parent_contract,
        source_asset_ids=[case_id], source_partition_sha256=partition["sha256"],
        source_manifest_sha256=source_manifest()["sha256"],
        parent_source_manifest_sha256=parent_contract["source_manifest_sha256"],
        requirements_sha256=digest(contract.encode()), public_requirements=contract,
        organization_text_revision={"before": OLD_ORGANIZATION, "after": NEW_ORGANIZATION,
            "scope": "Organization and purpose wording only; public/private quality drivers unchanged"},
        training_eligible=False, independent_confirmation_eligible=False)
    value["initial_binding"] = {
        "original_contract_sha256": digest(before.encode()),
        "organization_contract_sha256": digest(contract.encode()),
        "initial_files_sha256": digest(json_bytes(value["files"])),
        "public_driver_sha256": digest(value["files"]["test_visible.py"].encode()),
        "independent_verifier_sha256": parent_contract["independent_verifier_sha256"],
        "public_checks_sha256": parent_contract["public_checks_sha256"]}
    return value


def _validate_files(case_id, files):
    case = build_case(case_id)
    if set(files) != set(case["files"]) or any(files[name] != text
            for name, text in case["files"].items() if name not in case["editable_paths"]):
        raise ValueError("Only the unchanged declared editable application paths may change")


def _parent_files(case_id, files):
    _validate_files(case_id, files)
    original_id = ORIGINAL_IDS[canonical_case_id(case_id)]
    restored = dict(files)
    restored["contract.md"] = previous.build_case(original_id)["root_goal"]
    return original_id, restored


def run_public_tests(case_id, files, *, run_root):
    original_id, restored = _parent_files(case_id, files)
    return previous.run_public_tests(original_id, restored, run_root=run_root)


def assess_files(case_id, files, *, run_root):
    original_id, restored = _parent_files(case_id, files)
    result = previous.assess_files(original_id, restored, run_root=run_root)
    result.update(version=VERSION, task_id=canonical_case_id(case_id), purpose=PURPOSE,
        original_case_id=original_id, training_eligible=False,
        independent_confirmation_eligible=False)
    return result


def reference_solution(case_id):
    """CPU controls only; never used in initial material or actor observations."""
    original_id = ORIGINAL_IDS[canonical_case_id(case_id)]
    result = previous.reference_solution(original_id)
    result["contract.md"] = build_case(case_id)["root_goal"]
    return result
