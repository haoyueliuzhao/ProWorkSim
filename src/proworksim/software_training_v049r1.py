"""Isolated v049r1 consumers and read-only reexports of original closed slots.

Only MemberView consumers change. No source event, actual request, token trace,
reward, invoice, immutable world version or original export is overwritten.
"""
from __future__ import annotations

import copy
from pathlib import Path
from types import FunctionType, SimpleNamespace

from . import software_training_v049 as original
from . import team_validity as original_validity
from .software_member_views_v049r1 import member_view, member_view_from_episode
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = original.VERSION
REVISION = "software-training-record-binding-v0.49r1"
MAPPER = original.MAPPER
VALIDITY = original.VALIDITY
RUNTIME_VERSION = original.RUNTIME_VERSION
SDK_CONTEXT_SELECTION = original.SDK_CONTEXT_SELECTION
PAGING_VERSION = original.PAGING_VERSION
SCHEDULER = original.SCHEDULER
validate_case = original.validate_case
source_training_admission = original.source_training_admission
software_work_evidence = original.software_work_evidence
reward_record = original.reward_record
situation_id = original.situation_id
situation_fingerprint = original.situation_fingerprint
policy_spec = original.policy_spec
export_team_rollout = original.export_team_rollout
work_validity = original.work_validity


def _bound(function, namespace):
    bound = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = copy.deepcopy(function.__kwdefaults__)
    return bound


_support_globals = dict(original._support_globals)
_support_globals["member_view"] = member_view
for _name in ("declare_window", "_declaration", "expected_window", "bind_rollout"):
    _support_globals[_name] = _bound(original._support_globals[_name], _support_globals)
declare_window = _support_globals["declare_window"]
expected_window = _support_globals["expected_window"]
bind_rollout = _support_globals["bind_rollout"]
unavailable_slot_entry = _bound(original.unavailable_slot_entry, {**original.unavailable_slot_entry.__globals__, "expected_window": expected_window})


def assess_record_permission(episode, **kwargs):
    """Bind the source episode only in a private semantic-validator invocation."""
    root = Path(episode).resolve()
    if root.name == "manifest.json":
        root = root.parent
    namespace = dict(vars(original_validity))
    namespace["member_view"] = lambda rollout, member: member_view_from_episode(root, rollout, member)
    namespace["_record_permission_checks"] = _bound(original_validity._record_permission_checks, namespace)
    checker = _bound(original_validity.assess_record_permission, namespace)
    return checker(root, **kwargs)


def export_software_episode(prepared, episode, assessment, *, declaration, slot_id, captured, runtime_row):
    from .software_mapper_v049r1 import map_software_method

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


def _file_reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def _closed_slot_source(folder, declaration):
    """Accept only a declared, closed original v049 slot and its sealed files."""
    folder = Path(folder).resolve()
    row = read_json(folder / "slot-result.json")
    manifest = read_json(folder / "episode/manifest.json")
    variation = manifest.get("scenario", {}).get("variation", {})
    runtime = variation.get("organization_runtime", {})
    case = validate_case(variation.get("software_case"))
    if (manifest.get("status") != "closed" or runtime.get("version") != RUNTIME_VERSION
            or row.get("version") != RUNTIME_VERSION or runtime.get("case") != case
            or row.get("slot_id") != runtime.get("slot_id")
            or case.get("purpose") != "policy_training"
            or case.get("training_window_id") != declaration.get("window_id")
            or runtime.get("online_window_id") != declaration.get("window_id")
            or row.get("online_window_id") != declaration.get("window_id")
            or runtime.get("actor_identity") != declaration.get("actor_identity")
            or Path(row.get("episode_manifest", "")).resolve() != folder / "episode/manifest.json"):
        raise ValueError("r1 reexport requires the exact declared closed v049 training source")
    expected_window(declaration, row["slot_id"])
    required = ("slot-result.json", "assessment.json", "public-capture.json", "team-budget.json",
        "organization-evidence.json", "episode/manifest.json", "episode/experience.json",
        "episode/start/control/state.json", "episode/end/control/state.json")
    references = {name: _file_reference(folder / name) for name in required}
    for name in ("training-entry.json", "training-export.json"):
        if (folder / name).is_file():
            references[name] = _file_reference(folder / name)
    return folder, row, manifest, case, references


def _reward_spec(case):
    """Exact original metadata, never a world build or an acceptance execution."""
    return {"version": "software-organization-v0.49", "training_supported": case["training_eligible"],
        "purpose": case["purpose"], "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
        "independent_assessment": "assess_software_collaboration", "runtime_process_contract": case["process_contract"]}


def _observed_rows(views):
    return {member: [copy.deepcopy(row) for row in view["decisions"] if row.get("actual_response") is not None]
            for member, view in views.items()}


def reexport_closed_slot(folder, declaration, destination):
    """Write only a fresh r1 destination; all model/world sources remain read-only."""
    folder, row, manifest, case, references = _closed_slot_source(folder, declaration)
    destination = Path(destination).resolve()
    if destination.exists() or destination == folder or folder in destination.parents:
        raise ValueError("r1 reexports require a fresh destination outside the original slot")
    original_entry = read_json(folder / "training-entry.json") if (folder / "training-entry.json").is_file() else None
    original_export = read_json(folder / "training-export.json") if (folder / "training-export.json").is_file() else None
    reward_spec = _reward_spec(case)
    if original_entry is not None and original_entry.get("reward", {}).get("spec") != reward_spec:
        raise ValueError("Original entry reward metadata differs from the archived frozen source case")
    prepared = SimpleNamespace(case=case, scenario=copy.deepcopy(manifest["scenario"]),
        active_roles=list(case["active_roles"]), reward_spec=reward_spec)
    assessment = read_json(folder / "assessment.json")
    entry, details = export_software_episode(prepared, folder / "episode", assessment,
        declaration=declaration, slot_id=row["slot_id"], captured=read_json(folder / "public-capture.json"), runtime_row=row)
    unchanged = {}
    if original_entry is not None:
        for name in ("slot_id", "reward", "active_members", "training_eligible", "process_diagnostics"):
            unchanged["entry:" + name] = entry.get(name) == original_entry.get(name)
        for name in ("window", "members", "manifest", "manifest_sha256", "episode_path", "events", "event_interval",
                     "reward_eligibility", "online_scope", "origin_note"):
            unchanged["rollout:" + name] = entry["rollout"].get(name) == original_entry["rollout"].get(name)
    if original_export is not None:
        unchanged["original_work_evidence"] = details["original_work_evidence"] == original_export["original_work_evidence"]
        unchanged["every_observed_completion_row"] = _observed_rows(details["member_views"]) == _observed_rows(original_export["member_views"])
    if not all(unchanged.values()):
        raise ValueError("Record-only r1 reexport changed original observations, native targets, rewards or source evidence")
    source_unchanged = {name: _file_reference(reference["path"]) == reference for name, reference in references.items()}
    if not all(source_unchanged.values()):
        raise ValueError("An original source file changed during the read-only reexport")
    before_views = original_export.get("member_views", {}) if original_export else {}
    report = {"version": REVISION, "slot_id": row["slot_id"], "source_folder": str(folder),
        "destination": str(destination), "declaration_sha256": digest(json_bytes(declaration)),
        "source_references": references, "source_files_unchanged": source_unchanged,
        "original_observation_target_reward_invariants": unchanged,
        "old_entry_json_effect_equal": entry == original_entry if original_entry is not None else None,
        "old_export_payload_equal": details == original_export if original_export is not None else None,
        "old_work_validity": original_entry["rollout"]["work_validity"] if original_entry else None,
        "new_work_validity": entry["rollout"]["work_validity"],
        "old_mapping": original_entry.get("mapping") if original_entry else None, "new_mapping": entry["mapping"],
        "member_views": {member: {
            "old_complete_actor_trajectory": before_views.get(member, {}).get("complete_actor_trajectory"),
            "new_complete_actor_trajectory": view["complete_actor_trajectory"],
            "old_complete_semantic_trajectory": before_views.get(member, {}).get("complete_semantic_trajectory"),
            "new_complete_semantic_trajectory": view["complete_semantic_trajectory"],
            "original_observed_completions": len(_observed_rows({member: view})[member]),
            "own_action_tokens": view["own_action_tokens"],
            "old_diagnostics": before_views.get(member, {}).get("diagnostics"),
            "new_diagnostics": view["diagnostics"],
        } for member, view in details["member_views"].items()},
        "formal_R": row["R"], "reported_original_usage": copy.deepcopy(row["usage"]),
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_gpu_calls": 0,
        "new_business_tests_or_acceptances": 0, "new_world_actions": 0,
        "scope": "New record interpretation only; original world/model events, native input/output/masks, formal reward, usage and unknown records remain at original paths."}
    destination.mkdir(parents=True, exist_ok=False)
    atomic_write(destination / "training-entry.json", json_bytes(entry))
    atomic_write(destination / "training-export.json", json_bytes(details))
    atomic_write(destination / "rematerialization-receipt.json", json_bytes(report))
    return entry, details


rematerialize_closed_episode = reexport_closed_slot
