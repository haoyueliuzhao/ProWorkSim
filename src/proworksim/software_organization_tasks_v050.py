"""Six predeclared v050 roots; immutable business sources, new window metadata.

LA/LB retain v045 source bytes and DA/DB retain v049 source bytes. Only DC/DD
are new authored development sources. No old episode becomes current material.
"""
from __future__ import annotations

import copy
import json

from . import software_learning_sources_v050 as fresh
from . import software_organization_tasks_v045 as training_source
from . import software_organization_tasks_v049 as retained
from .storage import digest, json_bytes

VERSION = "software-organization-tasks-v0.50"
PARTITION_VERSION = "software-organization-source-partition-v0.50"
TRAINING_WINDOW_ID = "v050-o1-learning-window-01"
ASSETS = fresh.ASSETS
TRAINING_CASE_IDS = retained.TRAINING_CASE_IDS
DEVELOPMENT_CASE_IDS = (*retained.DEVELOPMENT_CASE_IDS, *fresh.DEVELOPMENT_CASE_IDS)
TASK_IDS = CASE_IDS = (*TRAINING_CASE_IDS, *DEVELOPMENT_CASE_IDS)
TASK_LABELS = {**retained.TASK_LABELS, **fresh.TASK_LABELS}
FAMILIES = NAMES = {**retained.FAMILIES, **fresh.FAMILIES}
LOADS = {**retained.LOADS, **fresh.LOADS}
CASE_PURPOSES = {
    **dict.fromkeys(TRAINING_CASE_IDS, "policy_training"),
    **dict.fromkeys(DEVELOPMENT_CASE_IDS, "policy_development"),
}
DIAGNOSTIC_IDS = retained.DIAGNOSTIC_IDS
MEMBER_STARTER = retained.MEMBER_STARTER


def canonical_case_id(case_id):
    if case_id not in TASK_IDS:
        raise ValueError("Only the six predeclared v050 business roots are admitted")
    return case_id


def _checked_manifest(name, version):
    path = ASSETS / name
    value = json.loads(path.read_text())
    if value.get("version") != version or value.get("sha256") != digest(
        json_bytes({key: item for key, item in value.items() if key != "sha256"})
    ):
        raise ValueError("Frozen v050 window source registration changed: " + name)
    return value


def source_partition():
    value = _checked_manifest("window-source-partition.json", PARTITION_VERSION)
    if (
        value.get("assignments") != CASE_PURPOSES
        or value.get("families") != FAMILIES
        or value.get("training_window_id") != TRAINING_WINDOW_ID
        or value.get("new_development_family_count") != 2
        or value.get("reused_development_family_count") != 2
        or value.get("old_episode_material_admitted") is not False
        or value.get("old_results_reclassified") is not False
        or value.get("independent_confirmation_eligible") is not False
    ):
        raise ValueError("The new v050 window and business source partition changed")
    return value


def source_manifest():
    value = _checked_manifest("window-source-manifest.json", VERSION)
    expected_sources = {
        "retained_training_v045": training_source.source_manifest()["sha256"],
        "retained_development_v049": retained.source_manifest()["sha256"],
        "new_development_v050": fresh.source_manifest()["sha256"],
    }
    if (
        value.get("source_partition_sha256") != source_partition()["sha256"]
        or value.get("business_source_manifests") != expected_sources
        or [row["task_id"] for row in value.get("cases", [])] != list(TASK_IDS)
    ):
        raise ValueError("Frozen v050 source inventory or original asset identity changed")
    for row in value["cases"]:
        key = row["task_id"]
        if (
            row.get("purpose") != CASE_PURPOSES[key]
            or row.get("family") != FAMILIES[key]
            or row.get("new_business_root") is not (key in fresh.CASE_IDS)
            or row.get("training_eligible") is not (key in TRAINING_CASE_IDS)
            or row.get("independent_confirmation_eligible") is not False
        ):
            raise ValueError("Frozen v050 source scope changed")
    return value


def _provider(case_id):
    canonical_case_id(case_id)
    if case_id in TRAINING_CASE_IDS:
        return training_source
    return fresh if case_id in fresh.CASE_IDS else retained


def build_case(case_id):
    provider = _provider(case_id)
    value = copy.deepcopy(provider.build_case(case_id))
    manifest, partition = source_manifest(), source_partition()
    training = case_id in TRAINING_CASE_IDS
    purpose = CASE_PURPOSES[case_id]
    value.update(
        retained_source_version=value["version"],
        retained_source_purpose=value["purpose"],
        version=VERSION,
        purpose=purpose,
        usage=purpose,
        training_eligible=training,
        contribution_eligible=training,
        development_eligible=not training,
        training_window_id=TRAINING_WINDOW_ID if training else None,
        category="v050_window_training_root" if training else "authored_policy_development_root",
        v050_source_partition_sha256=partition["sha256"],
        v050_source_manifest_sha256=manifest["sha256"],
    )
    if training:
        value["new_root"] = False
    source = value["source_contract"]
    source.update(
        retained_source_purpose=source["purpose"],
        purpose=purpose,
        usage=purpose,
        training_eligible=training,
        contribution_eligible=training,
        development_eligible=not training,
        training_window_id=TRAINING_WINDOW_ID if training else None,
        eligibility_scope="new_v050_window_records_only" if training else "frozen_v050_development_panel_only",
        old_episode_material_admitted=False,
        v050_source_partition_sha256=partition["sha256"],
        v050_source_manifest_sha256=manifest["sha256"],
    )
    # Source manifest/partition, requirements, files and initial_binding remain the
    # original business-source values; the new registry has explicit new keys.
    return value


def _validate_files(case_id, files):
    return _provider(case_id)._validate_files(case_id, files)


def reference_solution(case_id):
    return _provider(case_id).reference_solution(case_id)


def provenance_controls(case_id):
    return _provider(case_id).provenance_controls(case_id)


def run_public_tests(case_id, files, *, run_root):
    return _provider(case_id).run_public_tests(case_id, files, run_root=run_root)


def prepare_initial_diagnostics(case_id, run_root):
    return _provider(case_id).prepare_initial_diagnostics(case_id, run_root)


def assess_files(case_id, files, *, run_root):
    result = _provider(case_id).assess_files(case_id, files, run_root=run_root)
    training = case_id in TRAINING_CASE_IDS
    return {
        **result,
        "retained_source_version": result["version"],
        "retained_source_purpose": result["purpose"],
        "version": VERSION,
        "purpose": CASE_PURPOSES[case_id],
        "usage": CASE_PURPOSES[case_id],
        "training_eligible": training,
        "contribution_eligible": training,
        "development_eligible": not training,
        "training_window_id": TRAINING_WINDOW_ID if training else None,
        "eligibility_scope": "new_v050_window_records_only" if training else "frozen_v050_development_panel_only",
        "independent_confirmation_eligible": False,
    }
