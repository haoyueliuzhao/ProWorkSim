"""Original-token archival for frozen model/interface development screening.

The historical module naming is retained for collector API symmetry. This module
contains no optimizer or method classifier. Every exported rollout explicitly
forbids optimization and composition reconfiguration, even after full delivery.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .member_views import member_view
from .online_support import bind_rollout, expected_window
from .software_collaboration_v030 import PURPOSE, software_collaboration_facts, validate_case
from .software_runtime_v030 import DIAGNOSTICS, MODE, SDK_CONTEXT_SELECTION, VERSION as RUNTIME_VERSION, situation_id
from .software_tasks_v030 import _validate_files
from .storage import Store, digest, json_bytes, read_json
from .team_rollout import export_team_rollout, work_validity
from .team_validity import assess_record_permission

VERSION = "software-development-token-projection-v0.30"
VALIDITY = "software-development-complete-work-v0.30"
PROCESS_KINDS = ("task_created", "task_revised", "claim", "delegate", "task_returned", "work_message",
                 "dependency_declared", "dependency_removed", "edit", "patch_fixed", "handoff", "integrate", "test", "submit")


def source_training_admission(case, gamma):
    """Both source purpose and collection mode are frozen; neither can be promoted."""
    validate_case(case)
    if gamma.get("source_usage") != PURPOSE or gamma.get("collection_mode") != MODE:
        raise ValueError("Development sources are admitted only for frozen_screening")
    if gamma.get("optimizer_update_allowed") is not False:
        raise ValueError("The frozen screening declaration must explicitly forbid optimizer updates")
    return {"version": VERSION, "purpose": PURPOSE, "collection_mode": MODE,
            "optimizer_update_allowed": False, "source_training_admission": False,
            "composition_reconfiguration_eligible": False, "training_eligible": False,
            "mapping_controls_token_ownership": False,
            "method_classification_performed": False, "support_computation_performed": False}


def _bundle(store, state, reference):
    artifact = state["artifacts"][reference["object_id"]]
    version = reference["version_id"]
    raw = store.version_path(artifact, version).read_bytes()
    if digest(raw) != artifact["versions"][version]["sha256"]:
        raise ValueError("Archived source bytes differ from their exact immutable version")
    return json.loads(raw)


def software_work_evidence(episode, assessment):
    """Bind actual events and the latest immutable delivery without AST categories."""
    root = Path(episode)
    manifest = read_json(root / "manifest.json")
    if manifest["status"] != "closed":
        raise ValueError("Development evidence requires the closed original episode")
    start = read_json(root / "start/control/state.json")
    state = read_json(root / "end/control/state.json")
    initial = software_collaboration_facts(start)
    facts = software_collaboration_facts(state)
    case = validate_case(facts["case"])
    if initial["case"] != case:
        raise ValueError("Root contract or source purpose changed during work")
    old = initial["events"]
    if facts["events"][:len(old)] != old:
        raise ValueError("Historical software events were rewritten")
    events = facts["events"][len(old):]
    for event in events:
        receipt = state["operation_commits"].get(event["operation_id"])
        if (receipt is None or receipt["bound_actor"] != event["actor_id"]
                or receipt["public_result"]["action_id"] != event["action_id"]
                or event["actor_id"] not in case["active_roles"]):
            raise ValueError("Software event lacks the original active member WorldCore receipt")
    if assessment.get("status") not in {"evaluable", "unknown"}:
        raise ValueError("Assessment must retain evaluable or unknown status")
    if assessment["status"] == "evaluable" and (type(assessment.get("R")) is not int or assessment["R"] not in (0, 1)):
        raise ValueError("An evaluable development result must be Boolean")
    if assessment["status"] == "unknown" and assessment.get("R") is not None:
        raise ValueError("Unknown evaluation cannot be filled with zero")
    if (assessment.get("source_contract") != case["source_contract"]
            or assessment.get("purpose") != PURPOSE or assessment.get("training_eligible") is not False):
        raise ValueError("Assessment belongs to another source contract or purpose")
    submitted = bool(facts["deliveries"])
    if assessment.get("submitted") is not submitted:
        raise ValueError("Assessment does not match archived fixed delivery availability")
    delivery = facts["deliveries"][-1] if submitted else None
    delivery_sequence = None
    if delivery is not None:
        if assessment.get("delivery") != delivery:
            raise ValueError("Assessment must bind the latest fixed delivery")
        bundle = _bundle(Store(root / "end"), state, delivery["source_reference"])
        _validate_files(case["case_id"], bundle["files"])
        if (digest(json_bytes(bundle)) != delivery["source_sha256"]
                or digest(json_bytes(bundle["files"])) != delivery["files_sha256"]
                or assessment.get("source_reference") != delivery["source_reference"]
                or assessment.get("files_sha256") != delivery["files_sha256"]):
            raise ValueError("Fixed delivery byte/version identities changed")
        endings = [event for event in events if event["kind"] == "submit"
                   and event.get("delivery_id") == delivery["delivery_id"]]
        if len(endings) != 1:
            raise ValueError("Fixed submission must originate in this original episode")
        delivery_sequence = endings[0]["sequence"]
        if assessment["status"] == "evaluable" and (
            assessment.get("executed") is not True or type(assessment.get("passed")) is not bool
            or assessment["R"] != int(assessment["passed"])
            or assessment["passed"] != all(assessment["components"].values())
        ):
            raise ValueError("Known delivery requires its full independently executed conjunction")
    elif assessment.get("R") == 1:
        raise ValueError("A missing fixed delivery cannot receive complete success")
    diagnostics = {
        "version": DIAGNOSTICS, "counts": {kind: sum(event["kind"] == kind for event in events) for kind in PROCESS_KINDS},
        "per_member_counts": {member: {kind: sum(event["kind"] == kind and event["actor_id"] == member for event in events)
                                        for kind in PROCESS_KINDS} for member in case["active_roles"]},
        "active_members": list(case["active_roles"]), "organization_level": case["organization_level"],
        "latest_fixed_delivery_sequence": delivery_sequence,
        "forced_initial_failure_feedback": case["forced_initial_failure_feedback"],
        "forced_initial_feedback_is_actor_discovery": False,
        "method_classification_performed": False, "support_computation_performed": False,
        "scope": "Original committed event counts across the whole episode; no method, code authorship, value or causal credit classification",
    }
    return {"version": VERSION, "manifest_sha256": digest((root / "manifest.json").read_bytes()),
            "case": copy.deepcopy(case), "delivery": copy.deepcopy(delivery),
            "assessment_sha256": digest(json_bytes(assessment)), "assessment_status": assessment["status"],
            "complete_delivery_passed": None if assessment["status"] == "unknown" else assessment["R"] == 1,
            "original_events": copy.deepcopy(events), "process_diagnostics": diagnostics,
            "scope": "Frozen root-contract and exact original delivery binding; no old net-AST or process Mapper is called"}


def export_software_episode(prepared, episode, assessment, *, declaration, slot_id, captured):
    root = Path(episode)
    manifest = read_json(root / "manifest.json")
    case = validate_case(prepared.case)
    variation = manifest["scenario"].get("variation", {})
    if variation.get("software_case") != case:
        raise ValueError("The exact development case must be frozen before the first opportunity")
    window = expected_window(declaration, slot_id)
    slot = next(row for row in declaration["slots"] if row["slot_id"] == slot_id)
    initial = {"case": case, "reward_spec": prepared.reward_spec,
               "initial_business_sha256": prepared.prefix["prepared_business_state_sha256"]}
    runtime = variation.get("software_runtime", {})
    if (runtime.get("version") != RUNTIME_VERSION or window["xi_id"] != situation_id(case)
            or runtime.get("sdk_context_selection") != SDK_CONTEXT_SELECTION
            or declaration["gamma_identity"].get("sdk_context_selection") != SDK_CONTEXT_SELECTION
            or window["xi_fingerprint"] != digest(json_bytes(initial))
            or slot["mapping_spec_id"] != DIAGNOSTICS
            or slot["active_members"] != list(prepared.active_roles)
            or list(prepared.active_roles) != case["active_roles"]
            or any(runtime.get(key) != case.get(key) for key in (
                "first_member", "active_roles", "role_decision_limits", "scheduling_protocol", "category"))):
        raise ValueError("Exact source case, active members, first opportunity or frozen scheduling differs")
    scope = source_training_admission(case, declaration["gamma_identity"])
    if runtime.get("source_usage") != PURPOSE or runtime.get("collection_mode") != MODE:
        raise ValueError("Archived runtime cannot relabel development purpose or collection mode")
    members = {role["role_id"]: {"actor_id": role["actor"], "origin": "target_model"}
               for role in prepared.scenario["roles"]}
    common = assess_record_permission(root, members=members, independent_capture=captured,
                                      spec_id=VALIDITY, window=window)
    evidence = software_work_evidence(root, assessment)
    if evidence["case"] != case:
        raise ValueError("Archived work uses another frozen root/source contract")
    checks = [check for component in common["components"].values() for check in component["checks"]]
    references = {"manifest_sha256": evidence["manifest_sha256"],
                  "independent_assessment_sha256": evidence["assessment_sha256"],
                  "source_contract": copy.deepcopy(case["source_contract"])}
    checks.extend([
        {"dimension": "basis", "value": True,
         "reason": "Frozen public root contract, source, active members and original receipts bind", "evidence": references},
        {"dimension": "delivery", "value": evidence["complete_delivery_passed"],
         "reason": "Latest exact fixed delivery independently meets the full development contract, or remains false/unknown",
         "evidence": references},
    ])
    validity = work_validity(checks, spec_id=VALIDITY)
    reward = {"version": VERSION, "episode_id": manifest["episode_id"],
              "manifest_sha256": evidence["manifest_sha256"], "eligible": assessment["status"] == "evaluable",
              "reward": assessment["R"], "completed": assessment["R"] == 1, "scope": case["task_type"],
              "source_assessment_sha256": evidence["assessment_sha256"], "spec": copy.deepcopy(prepared.reward_spec)}
    rollout = export_team_rollout(root, window=window, members=members, validity=validity, reward=reward)
    rollout["online_scope"] = scope
    # The generic binder's legacy mapper slot is only an identity placeholder;
    # its optional default unmapped record is neither exported nor interpreted.
    bound = bind_rollout(declaration, slot_id, rollout)
    views = {member: member_view(rollout, member) for member in members}
    return {"slot_id": slot_id, "rollout": rollout, "reward": reward,
            "active_members": list(prepared.active_roles), "training_eligible": False,
            "process_diagnostics": evidence["process_diagnostics"]}, {
        "version": VERSION, "original_work_evidence": evidence, "work_validity": validity,
        "member_views": views, "binding_matches_views": bound["member_views"] == views,
        "training_probability_qualified": False, "optimizer_update_allowed": False,
        "method_classification_performed": False, "support_computation_performed": False,
        "scope": "Actual original member tokens retained for audit; development samples can never enter an optimizer window",
    }
