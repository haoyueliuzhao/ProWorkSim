"""Frozen v049 source/episode exports without changing native tokens or masks.

Trusted failures remain base-learning material. Full work validity and optional
route mapping are separate; unavailable original slots retain denominator mass.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

from .member_views import member_view
from . import online_support as original_support
from .model_policy import normalize_config
from .online_collection import _config
from .scenarios import initial_business_state
from .software_context_v048 import CANDIDATE_SHA256, VERSION as CONTEXT_VERSION
from .software_organization_runtime_v049 import VERSION as RUNTIME_VERSION, worker_type
from .software_organization_tasks_v049 import TRAINING_WINDOW_ID, _validate_files
from .software_organization_v049 import (
    PAGING_VERSION, PROJECT, SCHEDULER, member_instruction, validate_case,
)
from .software_runtime_v033 import SDK_CONTEXT_SELECTION
from .storage import Store, digest, json_bytes, read_json
from .team_rollout import export_team_rollout, work_validity
from .team_validity import assess_record_permission

VERSION = "software-training-export-v0.49"
VALIDITY = "software-complete-work-record-v0.49"
GAMMA_VERSION = "software-information-v0.49"
MAPPER = "software-work-delivery-mapper-v0.49"
POLICY_IMPLEMENTATION = "proworksim.software_organization_runtime_v049.worker_type.<locals>.StableO1Worker"
MODES = {"policy_training": "current_policy_collection", "policy_development": "frozen_policy_development"}
PROCESS_KINDS = ("task_created", "task_revised", "claim", "delegate", "task_returned", "work_message",
                 "dependency_declared", "dependency_removed", "edit", "patch_fixed", "handoff", "integrate", "test", "submit")


def policy_spec(owner, prepared):
    """Zero-sampling predeclaration of the actual strict-O1 SDK policy identities."""
    validate_case(prepared.case)
    kind = worker_type()
    implementation = kind.__module__ + "." + kind.__qualname__
    if implementation != POLICY_IMPLEMENTATION:
        raise ValueError("The frozen real O1 SDK worker implementation changed")
    policies = {}
    for member in prepared.case["active_roles"]:
        config = _config(owner, member, member_instruction(prepared.case),
                         {member: prepared.case["team_limits"]["max_decisions"]})
        config.update(context_policy="full_history", format_error_policy="format_feedback_budgeted_v033")
        policies[member] = {"implementation": implementation, "config": normalize_config(config)}
    return policies


def _v049_policies(policies, active, identity, *, harness=None):
    implementation = POLICY_IMPLEMENTATION
    if (harness != "openhands_v16" or active != ["member_001", "member_002"]
            or not isinstance(policies, dict) or set(policies) != set(active)):
        raise ValueError("v049 requires exactly its two real stable O1 SDK workers")
    for member in active:
        policy = policies[member]
        config = policy.get("config", {})
        if (policy.get("implementation") != implementation
                or config.get("weight_identity") != identity
                or config.get("model_revision") != identity["policy_version"]
                or config.get("context_policy") != "full_history"
                or config.get("format_error_policy") != "format_feedback_budgeted_v033"):
            raise ValueError("Actual stable-O1 worker or same-current-actor identity changed")
    return copy.deepcopy(policies)


# Execute the original declaration/binding implementations in private globals.
# Only the exact new real worker class gate differs; old support code/state stays
# untouched, and actual identities are never disguised as the old HarnessWorker.
_support_globals = dict(vars(original_support))
_support_globals["_policies"] = _v049_policies
for _name in ("declare_window", "_declaration", "expected_window", "bind_rollout"):
    _original = getattr(original_support, _name)
    _bound = FunctionType(_original.__code__, _support_globals, _name, _original.__defaults__, _original.__closure__)
    _bound.__kwdefaults__ = copy.deepcopy(_original.__kwdefaults__)
    _support_globals[_name] = _bound
    globals()[_name] = _bound

declare_window = _support_globals["declare_window"]
expected_window = _support_globals["expected_window"]
bind_rollout = _support_globals["bind_rollout"]


def situation_id(case):
    validate_case(case)
    return case["case_id"] + "::O1::active=" + ",".join(case["active_roles"]) + "::first=" + case["first_member"]


def _business_identity(world):
    value = initial_business_state(world)
    software = value["state"]["projects"][PROJECT]["software"]
    # These are controller-only preparation receipt paths/cache flags/timings;
    # actual public diagnostics, ordering, roles, permissions and bytes remain.
    for key in ("environment_preparation_provenance", "environment_preparation_cost"):
        software.pop(key, None)
    return value


def situation_fingerprint(prepared, *, episode=None):
    validate_case(prepared.case)
    if episode is None:
        world = SimpleNamespace(state=prepared.world.store.load(), store=prepared.world.store)
    else:
        root = Path(episode).resolve() / "start"
        world = SimpleNamespace(state=read_json(root / "control/state.json"), store=Store(root))
    return digest(json_bytes({"case": prepared.case, "reward_spec": prepared.reward_spec,
        "initial_business": _business_identity(world)}))


def source_training_admission(case, gamma):
    """New-window source permission cannot promote old or development records."""
    from .software_mapper_v049 import mapping_spec

    validate_case(case)
    usage, training = case["usage"], case["usage"] == "policy_training"
    spec = mapping_spec()
    if (case["purpose"] != usage or case["split"] != usage
            or case["training_eligible"] is not training
            or training and case["training_window_id"] != TRAINING_WINDOW_ID
            or gamma.get("source_usage") != usage or gamma.get("collection_mode") != MODES[usage]
            or gamma.get("optimizer_update_allowed") is not training
            or gamma.get("gamma_version") != GAMMA_VERSION
            or gamma.get("runtime_version") != RUNTIME_VERSION
            or gamma.get("presentation_version") != CONTEXT_VERSION
            or gamma.get("sdk_context_selection") != SDK_CONTEXT_SELECTION
            or gamma.get("mapper_specification") != spec
            or gamma.get("mapper_spec_sha256") != digest(json_bytes(spec))
            or gamma.get("presentation_identity", {}).get("candidate_sha256") != CANDIDATE_SHA256):
        raise ValueError("Frozen v049 source, window, runtime, Gamma1 or Mapper cannot be relabeled")
    return {"version": VERSION, "purpose": usage, "collection_mode": MODES[usage],
        "training_window_id": case["training_window_id"], "optimizer_update_allowed": training,
        "source_training_admission": training, "composition_reconfiguration_eligible": training,
        "training_eligible": training, "method_mapper_spec_sha256": digest(json_bytes(spec)),
        "mapping_controls_token_ownership": False, "method_classification_performed": True,
        "support_computation_performed": False,
        "scope": "Only newly bound original v049 records; reward-zero and unmapped records are not removed."}


def _reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def _bundle(store, state, reference):
    artifact = state["artifacts"][reference["object_id"]]
    version = reference["version_id"]
    raw = store.version_path(artifact, version).read_bytes()
    if digest(raw) != artifact["versions"][version]["sha256"]:
        raise ValueError("Archived business bytes differ from their immutable source version")
    return json.loads(raw)


def _facts(state):
    return {**copy.deepcopy(state["projects"][PROJECT]["software"]),
            "events": copy.deepcopy(state.get("software_events", []))}


def _runtime_binding(root, manifest, case, assessment, runtime_row):
    if not isinstance(runtime_row, dict):
        raise ValueError("A closed v049 export requires its actual runtime result")
    runtime = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
    result_path, assessment_path = root.parent / "slot-result.json", root.parent / "assessment.json"
    if (runtime.get("version") != RUNTIME_VERSION or runtime.get("case") != case
            or runtime.get("purpose") != case["purpose"]
            or runtime.get("context_protocol") != CONTEXT_VERSION
            or runtime.get("representation") != {"name": "Gamma1", "candidate_sha256": CANDIDATE_SHA256}
            or runtime_row.get("version") != RUNTIME_VERSION
            or runtime_row.get("purpose") != case["purpose"]
            or runtime_row.get("case_id") != case["case_id"]
            or runtime_row.get("slot_id") != runtime.get("slot_id")
            or runtime_row.get("sampling_seed") != runtime.get("sampling_seed")
            or runtime_row.get("first_member") != case["first_member"]
            or runtime_row.get("actor_identity") != runtime.get("actor_identity")
            or runtime_row.get("online_window_id") != runtime.get("online_window_id")
            or runtime_row.get("training_eligible") is not case["training_eligible"]
            or runtime_row.get("assessment") != assessment
            or runtime_row.get("representation") != "Gamma1"
            or runtime_row.get("representation_candidate_sha256") != CANDIDATE_SHA256
            or Path(runtime_row.get("episode_manifest", "")).resolve() != root / "manifest.json"
            or Path(runtime_row.get("assessment_path", "")).resolve() != assessment_path
            or not result_path.is_file() or read_json(result_path) != runtime_row
            or not assessment_path.is_file() or read_json(assessment_path) != assessment):
        raise ValueError("Actual closed runtime/source/assessment/Gamma1 binding differs")
    if (type(runtime_row.get("administrative_censoring")) is not bool
            or runtime_row.get("R") != assessment.get("R")
            or runtime_row.get("R_joint") != assessment.get("R")):
        raise ValueError("Runtime reward or administrative scope differs from the assessment")
    if case["training_eligible"] and runtime.get("online_window_id") != TRAINING_WINDOW_ID:
        raise ValueError("Old or independent episode window cannot enter the new training window")
    return runtime


def software_work_evidence(episode, assessment, *, runtime_row):
    """Return original committed work and sealed paths; no inferred authorship."""
    root = Path(episode).resolve()
    if root.name == "manifest.json":
        root = root.parent
    manifest = read_json(root / "manifest.json")
    if manifest["status"] != "closed":
        raise ValueError("Work evidence requires the closed original episode")
    start_path, end_path = root / "start/control/state.json", root / "end/control/state.json"
    start, state = read_json(start_path), read_json(end_path)
    initial, facts = _facts(start), _facts(state)
    case = validate_case(facts["case"])
    if initial["case"] != case or manifest["scenario"].get("variation", {}).get("software_case") != case:
        raise ValueError("Frozen source case differs across original episode boundaries")
    runtime = _runtime_binding(root, manifest, case, assessment, runtime_row)
    old = initial["events"]
    if facts["events"][:len(old)] != old:
        raise ValueError("Historical software events were rewritten")
    events = facts["events"][len(old):]
    for event in events:
        receipt = state["operation_commits"].get(event["operation_id"])
        if (receipt is None or receipt["bound_actor"] != event["actor_id"]
                or receipt["public_result"]["action_id"] != event["action_id"]
                or event["actor_id"] not in case["active_roles"]):
            raise ValueError("Software event lacks its original stable member WorldCore receipt")
    if assessment.get("status") not in {"evaluable", "unknown"}:
        raise ValueError("Retain evaluable or unknown source assessment status")
    if assessment["status"] == "evaluable" and (type(assessment.get("R")) is not int or assessment["R"] not in (0, 1)):
        raise ValueError("An evaluable formal reward must be Boolean")
    if assessment["status"] == "unknown" and assessment.get("R") is not None:
        raise ValueError("Unknown evaluation cannot be filled with zero")
    if (assessment.get("source_contract") != case["source_contract"]
            or assessment.get("purpose") != case["purpose"]
            or assessment.get("training_eligible") is not case["training_eligible"]):
        raise ValueError("Assessment belongs to another source or purpose")
    submitted = bool(facts["deliveries"])
    if assessment.get("submitted") is not submitted:
        raise ValueError("Assessment does not match archived fixed delivery availability")
    delivery = facts["deliveries"][-1] if submitted else None
    delivery_sequence = None
    if delivery is not None:
        if assessment.get("delivery") != delivery:
            raise ValueError("Assessment must bind the last original fixed delivery")
        bundle = _bundle(Store(root / "end"), state, delivery["source_reference"])
        _validate_files(case["case_id"], bundle["files"])
        if (digest(json_bytes(bundle)) != delivery["source_sha256"]
                or digest(json_bytes(bundle["files"])) != delivery["files_sha256"]
                or assessment.get("source_reference") != delivery["source_reference"]
                or assessment.get("files_sha256") != delivery["files_sha256"]):
            raise ValueError("Final fixed delivery byte/version identities changed")
        endings = [event for event in events if event["kind"] == "submit" and event.get("delivery_id") == delivery["delivery_id"]]
        if len(endings) != 1:
            raise ValueError("Fixed submission must originate in this original episode")
        delivery_sequence = endings[0]["sequence"]
        if assessment["status"] == "evaluable":
            raw_passed = assessment.get("raw_fixed_tree_passed", assessment.get("passed"))
            process_violation = assessment.get("process_violation", False)
            if (assessment.get("executed") is not True or type(raw_passed) is not bool
                    or raw_passed != all(assessment["components"].values())
                    or assessment["R"] != (0 if process_violation else int(raw_passed))):
                raise ValueError("Known delivery requires its raw fixed-tree and formal process conjunction")
    elif assessment.get("R") == 1:
        raise ValueError("A missing fixed delivery cannot receive complete success")
    diagnostics = {"version": VERSION,
        "counts": {kind: sum(event["kind"] == kind for event in events) for kind in PROCESS_KINDS},
        "per_member_counts": {member: {kind: sum(event["kind"] == kind and event["actor_id"] == member for event in events)
                                     for kind in PROCESS_KINDS} for member in case["active_roles"]},
        "active_members": list(case["active_roles"]), "organization_level": "O1",
        "latest_fixed_delivery_sequence": delivery_sequence,
        "scope": "Actual committed task, responsibility and product events only; no causal contribution or authorship inference."}
    result = {"version": VERSION, "manifest_sha256": digest((root / "manifest.json").read_bytes()),
        "episode_path": str(root), "slot_root": str(root.parent),
        "source_references": {"manifest": _reference(root / "manifest.json"), "start_state": _reference(start_path),
            "end_state": _reference(end_path), "assessment": _reference(root.parent / "assessment.json"),
            "runtime_result": _reference(root.parent / "slot-result.json")},
        "case": copy.deepcopy(case), "delivery": copy.deepcopy(delivery), "assessment": copy.deepcopy(assessment),
        "assessment_sha256": digest(json_bytes(assessment)), "assessment_status": assessment["status"],
        "complete_delivery_passed": None if assessment["status"] == "unknown" else assessment["R"] == 1,
        "original_events": copy.deepcopy(events), "initial_tasks": copy.deepcopy(initial["tasks"]),
        "final_tasks": copy.deepcopy(facts["tasks"]), "patches": copy.deepcopy(facts["patches"]),
        "process_diagnostics": diagnostics, "runtime_binding": copy.deepcopy(runtime),
        "administrative_censoring": runtime_row["administrative_censoring"],
        "scope": "Exact original committed responsibility/product facts and fixed-delivery provenance; no old symbol-tracker result is changed."}
    result["evidence_sha256"] = digest(json_bytes(result))
    return result


def unavailable_slot_entry(declaration, slot_id, reason):
    """Retain the planned slot and members without inventing reward or material."""
    window = expected_window(declaration, slot_id)
    slot = next(row for row in declaration["slots"] if row["slot_id"] == slot_id)
    if not isinstance(reason, str) or not reason:
        raise ValueError("Record the original missing/unknown-material reason")
    return {"slot_id": slot_id, "active_members": list(slot["active_members"]), "rollout": None,
        "reward": {"eligible": False, "reward": None}, "window": window,
        "status": "unavailable_original_slot", "reason": reason,
        "original_denominator_slot_retained": True}


def reward_record(manifest, manifest_sha256, assessment, runtime_row, *, case, reward_spec):
    """Original joint-policy terminal result; administrative token estimand stays separate."""
    known = assessment.get("status") == "evaluable"
    if (assessment.get("status") not in {"evaluable", "unknown"}
            or known and (type(assessment.get("R")) is not int or assessment["R"] not in (0, 1))
            or not known and assessment.get("R") is not None
            or runtime_row.get("R_joint") != assessment.get("R")
            or type(runtime_row.get("administrative_censoring")) is not bool
            or runtime_row.get("R_token") != (None if runtime_row["administrative_censoring"] else assessment["R"])):
        raise ValueError("Joint-policy reward and separate administrative token estimand differ")
    return {"version": VERSION, "episode_id": manifest["episode_id"],
        "manifest_sha256": manifest_sha256, "eligible": known, "reward": assessment["R"],
        "completed": known and assessment["R"] == 1, "scope": case["task_type"],
        "source_assessment_sha256": digest(json_bytes(assessment)), "spec": copy.deepcopy(reward_spec),
        "formal_R_joint": assessment["R"], "R_token": runtime_row["R_token"],
        "administrative_censoring": runtime_row["administrative_censoring"],
        "eligibility_scope": "Evaluable formal joint-policy results including R=0 and safe administrative closure; success, mapping and token-only censoring do not filter original base material."}


def export_software_episode(prepared, episode, assessment, *, declaration, slot_id, captured, runtime_row):
    from .software_mapper_v049 import map_software_method

    root = Path(episode).resolve()
    manifest = read_json(root / "manifest.json")
    case = validate_case(prepared.case)
    runtime = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
    window = expected_window(declaration, slot_id)
    slot = next(row for row in declaration["slots"] if row["slot_id"] == slot_id)
    if (manifest["scenario"].get("variation", {}).get("software_case") != case
            or runtime.get("case") != case or runtime.get("slot_id") != slot_id
            or runtime.get("online_window_id") != window["window_id"]
            or runtime.get("actor_identity") != declaration["actor_identity"]
            or window["xi_id"] != situation_id(case) or window["xi_fingerprint"] != situation_fingerprint(prepared, episode=root)
            or runtime.get("sdk_context_selection") != SDK_CONTEXT_SELECTION
            or runtime.get("test_feedback_protocol") != PAGING_VERSION
            or runtime.get("scheduling_protocol") != SCHEDULER
            or runtime.get("team_limits") != case["team_limits"]
            or slot["mapping_spec_id"] != MAPPER or slot["active_members"] != list(prepared.active_roles)
            or list(prepared.active_roles) != case["active_roles"]):
        raise ValueError("Exact v049 case, shared window, Gamma1 or stable member scheduling differs")
    scope = source_training_admission(case, declaration["gamma_identity"])
    members = {role["role_id"]: {"actor_id": role["actor"], "origin": "target_model"}
               for role in prepared.scenario["roles"]}
    capture_path = root.parent / "public-capture.json"
    if (Path(runtime_row.get("public_capture", "")).resolve() != capture_path
            or not capture_path.is_file() or read_json(capture_path) != captured):
        raise ValueError("Independent original public capture must retain its exact durable binding")
    evidence = software_work_evidence(root, assessment, runtime_row=runtime_row)
    if evidence["case"] != case:
        raise ValueError("Original work uses another frozen source contract")
    common = assess_record_permission(root, members=members, independent_capture=captured,
                                      spec_id=VALIDITY, window=window)
    checks = [check for component in common["components"].values() for check in component["checks"]]
    references = {"manifest_sha256": evidence["manifest_sha256"], "assessment_sha256": evidence["assessment_sha256"],
        "source_contract": copy.deepcopy(case["source_contract"]), "evidence_sha256": evidence["evidence_sha256"]}
    checks.extend([
        {"dimension": "basis", "value": True,
         "reason": "Frozen source/window/stable members and original committed work receipts bind", "evidence": references},
        {"dimension": "basis", "value": None if runtime_row["boundary"].get("execution_integrity_failure") else True,
         "reason": "An execution-integrity failure remains unknown, separately from a legal local resource ending", "evidence": references},
        {"dimension": "delivery", "value": evidence["complete_delivery_passed"],
         "reason": "Last exact fixed delivery meets the complete formal contract, or remains false/unknown", "evidence": references},
    ])
    validity = work_validity(checks, spec_id=VALIDITY)
    reward = reward_record(manifest, evidence["manifest_sha256"], assessment, runtime_row,
                           case=case, reward_spec=prepared.reward_spec)
    rollout = export_team_rollout(root, window=window, members=members, validity=validity, reward=reward)
    rollout["online_scope"] = scope
    mapping = map_software_method(rollout, evidence, spec=declaration["gamma_identity"]["mapper_specification"])
    bound = bind_rollout(declaration, slot_id, rollout, mapping=mapping)
    views = {member: member_view(rollout, member) for member in members}
    entry = {"slot_id": slot_id, "rollout": rollout, "reward": reward, "active_members": list(prepared.active_roles),
        "mapping": mapping, "training_eligible": scope["training_eligible"],
        "process_diagnostics": evidence["process_diagnostics"]}
    details = {"version": VERSION, "original_work_evidence": evidence, "work_validity": validity,
        "member_views": views, "binding_matches_views": bound["member_views"] == views,
        "training_probability_qualified": False, "optimizer_update_allowed": scope["optimizer_update_allowed"],
        "mapping": mapping, "method_classification_performed": True, "support_computation_performed": False,
        "scope": "Own original sampled output and archived native token IDs only. Upstream SDK request is provenance; the v049 learning bridge binds actual selected Gamma1 inputs before any optimizer use."}
    return entry, details
