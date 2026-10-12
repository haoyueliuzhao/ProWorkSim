"""Read-only v049r1 attribution of already-bound pre-generation refusals.

The old shared-admission validator is retained except for one identity predicate:
when the organization budget wrapper omits world_instance_id, the same identity
must be proved from the original closed episode and its archived WorldCore states.
No manifest, event, refusal, native input, mask or historical result is rewritten.
"""
from __future__ import annotations

import ast
import copy
import inspect
import marshal
from pathlib import Path
from types import FunctionType

from . import member_views as original
from . import online_training
from .storage import digest, json_bytes, read_json

VERSION = "v049r1-original-episode-world-identity-binding"
ORIGINAL_MEMBER_VIEWS_SHA256 = "ef2d7b375abfc09ad61649c5f445cd526f4959c0d91a75626656930739aab640"
MEMBERS = ["member_001", "member_002"]
IDENTITY_FIELDS = ("world_id", "instance_id", "branch_id")
PREDICATE = 'final_wrapper.get("world_instance_id") != rollout["manifest"].get("identity", {}).get("instance_id")'


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def _reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": digest(raw), "bytes": len(raw)}


def _one(values, reason):
    _require(len(values) == 1, reason)
    return values[0]


def shared_admission_identity_proof(rollout, start, member_id):
    """Prove missing wrapper identity from immutable same-episode original files.

    This is the world/slot/source proof only. The original shared-admission
    validator must still prove every no-generation and budget condition.
    """
    episode_path = rollout.get("episode_path")
    _require(isinstance(episode_path, str) and episode_path, "missing_original_episode_path")
    episode = Path(episode_path).resolve()
    _require(episode.name == "episode", "original_episode_directory_required")
    folder = episode.parent
    manifest_path = episode / "manifest.json"
    manifest = read_json(manifest_path)
    manifest_ref = _reference(manifest_path)
    _require(manifest == rollout.get("manifest") and manifest_ref["sha256"] == rollout.get("manifest_sha256")
        and manifest.get("status") == "closed" and manifest.get("episode_id") == rollout.get("rollout_id"),
        "actual_closed_manifest_or_rollout_binding_differs")
    identity = manifest.get("identity", {})
    _require(set(identity) == set(IDENTITY_FIELDS)
        and all(isinstance(identity[key], str) and identity[key] for key in IDENTITY_FIELDS), "missing_original_world_identity")
    references = {"manifest": manifest_ref}
    states = {}
    for name in ("start", "end"):
        boundary = manifest.get(name, {})
        _require(boundary.get("path") == name and boundary.get("state", {}).get("path") == "control/state.json",
                 "unexpected_original_state_path")
        path = episode / name / "control/state.json"
        ref = _reference(path)
        state = read_json(path)
        _require(ref["sha256"] == boundary["state"].get("sha256")
            and boundary.get("identity") == identity
            and {key: state.get(key) for key in IDENTITY_FIELDS} == identity,
            "original_start_end_state_digest_or_world_identity_differs")
        references[name + "_state"] = ref
        states[name] = state
    experience = manifest.get("experience", {})
    _require(experience.get("path") == "experience.json", "unexpected_original_experience_path")
    experience_path = episode / "experience.json"
    ref = _reference(experience_path)
    history = read_json(experience_path)
    left, right = experience.get("start"), experience.get("end")
    _require(ref["sha256"] == experience.get("sha256") and isinstance(history.get("events"), list)
        and type(left) is int and type(right) is int and 0 <= left <= right <= len(history["events"])
        and history["events"][left:right] == rollout.get("events"), "original_episode_event_interval_differs")
    references["experience"] = ref
    scope = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
    case = scope.get("case", {})
    slot_id = scope.get("slot_id")
    _require(scope.get("version") == "software-organization-runtime-v0.49"
        and isinstance(slot_id, str) and slot_id == folder.name
        and scope.get("purpose") == case.get("purpose") == "policy_training"
        and scope.get("training_eligible") is True and case.get("training_eligible") is True
        and case.get("condition") == "O1" and case.get("active_roles") == MEMBERS
        and scope.get("online_window_id") == rollout["window"].get("window_id") == case.get("training_window_id")
        and manifest["scenario"]["variation"].get("software_case") == case,
        "original_v049_O1_slot_source_or_logical_window_differs")
    for state in states.values():
        software = [project["software"] for project in state.get("projects", {}).values() if "software" in project]
        _require(len(software) == 1 and software[0].get("case") == case, "archived_WorldCore_source_case_differs")
    result_path, budget_path = folder / "slot-result.json", folder / "team-budget.json"
    evidence_path = folder / "organization-evidence.json"
    result, budget, evidence = (read_json(path) for path in (result_path, budget_path, evidence_path))
    references.update(slot_result=_reference(result_path), final_budget=_reference(budget_path),
                      organization_evidence=_reference(evidence_path))
    final_wrapper = manifest.get("termination", {}).get("team_budget", {})
    _require("world_instance_id" not in final_wrapper, "fallback_only_for_absent_world_instance_field")
    _require(budget == final_wrapper == result.get("team_budget") == evidence.get("team_budget")
        and final_wrapper.get("slot_id") == slot_id,
        "same_slot_original_final_budget_copies_differ")
    _require(result.get("version") == scope["version"] and result.get("status") == "closed"
        and result.get("slot_id") == slot_id and result.get("case_id") == case.get("case_id")
        and result.get("condition") == "O1" and result.get("purpose") == "policy_training"
        and result.get("training_eligible") is True
        and result.get("online_window_id") == scope["online_window_id"]
        and result.get("actor_identity") == scope.get("actor_identity")
        and result.get("learning_binding") == scope.get("learning_binding")
        and result.get("episode_start_steps") == scope.get("episode_start_steps")
        and Path(result.get("episode_manifest", "")).resolve() == manifest_path
        and Path(result.get("raw_transport_path", "")).resolve() == folder / "raw-transport",
        "original_slot_result_or_loaded_state_binding_differs")
    result_boundary, original_boundary = result.get("boundary", {}), manifest["termination"]
    _require({key: value for key, value in result_boundary.items() if key != "deadline_receipt"}
        == {key: value for key, value in original_boundary.items() if key != "deadline_receipt"},
        "actual_result_and_episode_termination_differ")
    # v049 appends the final administrative-close receipt after finish_episode;
    # that later annotation never replaces the archived run_boundary below.
    if result_boundary.get("deadline_receipt") != original_boundary.get("deadline_receipt"):
        deadline_path = folder / "deadline-receipt.json"
        _require(result_boundary.get("deadline_receipt") == result.get("deadline_receipt") == read_json(deadline_path),
                 "later_deadline_annotation_lacks_original_close_receipt")
        references["later_deadline_receipt"] = _reference(deadline_path)
    events = rollout["events"]
    call_id = start.get("payload", {}).get("call_id")
    _require(member_id in MEMBERS and member_id in rollout.get("members", {})
        and start in events and start.get("worker_id") == member_id
        and manifest.get("policies", {}).get(member_id, {}).get("config", {}).get("weight_identity") == scope["actor_identity"],
        "member_start_or_original_shared_actor_differs")
    boundary = _one([event for event in events if event.get("kind") == "model_boundary_error"
        and event.get("worker_id") == member_id
        and event["payload"].get("opportunity_id") == start["payload"].get("opportunity_id")],
        "no_unique_original_member_boundary")
    final_event = _one([event for event in events if event.get("kind") == "run_boundary"], "no_unique_original_final_boundary")
    _require(final_event["payload"] == manifest["termination"]
        and start["sequence"] < boundary["sequence"] < final_event["sequence"], "original_boundary_order_or_termination_differs")
    ledger = boundary["payload"].get("team_budget")
    final = final_wrapper.get("model")
    actor = scope["actor_identity"]
    _require(original._sealed_team_ledger(ledger, rollout, actor) and original._sealed_team_ledger(final, rollout, actor)
        and ledger["limits"] == final["limits"]
        and all(final["records"].get(key) == value for key, value in ledger["records"].items()),
        "original_boundary_and_final_ledgers_not_sealed_or_monotone")
    proof = {"version": VERSION, "slot_id": slot_id, "member_id": member_id, "call_id": call_id,
        "episode_id": manifest["episode_id"], "archived_world_identity": copy.deepcopy(identity),
        "original_wrapper_field_absent": True, "original_records_modified": False,
        "original_manifest_sha256": manifest_ref["sha256"], "source_files": references,
        "boundary_event_sequence": boundary["sequence"], "final_event_sequence": final_event["sequence"],
        "boundary_ledger_sha256": ledger["state_sha256"], "final_ledger_sha256": final["state_sha256"],
        "scope": "Original same-episode WorldCore/manifest/slot identity proof only; all original no-generation, reservation, side-effect and budget predicates must additionally pass."}
    proof["proof_sha256"] = digest(json_bytes(proof))
    return proof


def _world_identity_mismatch(rollout, final_wrapper, start, member_id):
    if "world_instance_id" in final_wrapper:
        return final_wrapper.get("world_instance_id") != rollout["manifest"].get("identity", {}).get("instance_id")
    try:
        shared_admission_identity_proof(rollout, start, member_id)
        return False
    except (OSError, KeyError, TypeError, ValueError, AttributeError):
        return True


def _adapt_shared_validator():
    source_file = Path(original.__file__).resolve()
    _require(digest(source_file.read_bytes()) == ORIGINAL_MEMBER_VIEWS_SHA256, "original_member_view_source_changed")
    source = inspect.getsource(original._known_shared_admission_stop)
    tree = ast.parse(source)
    needle = ast.dump(ast.parse(PREDICATE, mode="eval").body, include_attributes=False)
    count = 0
    class IdentityPredicate(ast.NodeTransformer):
        def visit_Compare(self, node):
            nonlocal count
            if ast.dump(node, include_attributes=False) == needle:
                count += 1
                return ast.copy_location(ast.Call(func=ast.Name(id="_world_identity_mismatch", ctx=ast.Load()),
                    args=[ast.Name(id=name, ctx=ast.Load()) for name in ("rollout", "final_wrapper", "start", "member_id")], keywords=[]), node)
            return self.generic_visit(node)
    transformed = IdentityPredicate().visit(tree)
    _require(count == 1, "replace_exactly_one_original_world_identity_predicate")
    ast.fix_missing_locations(transformed)
    namespace = {**vars(original), "_world_identity_mismatch": _world_identity_mismatch}
    exec(compile(transformed, "<v049r1-original-shared-admission-one-identity-predicate>", "exec"), namespace)
    return namespace["_known_shared_admission_stop"], {
        "original_function_source_sha256": digest(source.encode()), "original_module": _reference(source_file),
        "original_predicate": PREDICATE, "replacement": "_world_identity_mismatch(rollout, final_wrapper, start, member_id)",
        "replaced_AST_predicates": count, "all_other_original_AST_nodes_retained": True,
        "adapted_AST_sha256": digest(ast.dump(transformed, include_attributes=False).encode())}


_shared_validator, _adaptation = _adapt_shared_validator()


def known_shared_admission_stop(rollout, start, member_id):
    proof = _shared_validator(rollout, start, member_id)
    if proof is not None and "world_instance_id" not in rollout["manifest"]["termination"]["team_budget"]:
        try:
            identity = shared_admission_identity_proof(rollout, start, member_id)
        except (OSError, KeyError, TypeError, ValueError, AttributeError):
            return None
        return {**proof, "world_identity_attribution": identity, "attribution_revision": VERSION}
    return proof


def bind_private_function(function, overrides):
    """Reuse an original code object without mutating its module globals."""
    rebound = FunctionType(function.__code__, {**function.__globals__, **overrides}, function.__name__,
                           function.__defaults__, function.__closure__)
    rebound.__kwdefaults__ = function.__kwdefaults__
    return rebound


member_view = bind_private_function(original.member_view, {"_known_shared_admission_stop": known_shared_admission_stop})
prepare_window = bind_private_function(online_training.prepare_window, {"member_view": member_view})


def member_view_from_episode(episode, rollout, member_id):
    """Supply known archive location to old TeamValidity's internal view input.

    The original TeamValidity helper does not include provenance location in its
    ephemeral view dictionary. Only these two source-pointer fields are supplied;
    the original manifest, events, members and logical window are not changed.
    """
    path = Path(episode).resolve()
    if path.name == "manifest.json":
        path = path.parent
    if "episode_path" in rollout and Path(rollout["episode_path"]).resolve() != path:
        raise ValueError("Existing episode source pointer differs from the explicit source")
    sha = digest((path / "manifest.json").read_bytes())
    if "manifest_sha256" in rollout and rollout["manifest_sha256"] != sha:
        raise ValueError("Existing manifest source digest differs from the actual archive")
    return member_view({**rollout, "episode_path": str(path), "manifest_sha256": sha}, member_id)


def adaptation_spec():
    return {"version": VERSION, **copy.deepcopy(_adaptation),
        "reader_module": _reference(Path(__file__)),
        "original_member_view_code_sha256": digest(marshal.dumps(original.member_view.__code__)),
        "member_view_code_object_identical": member_view.__code__ is original.member_view.__code__,
        "prepare_window_code_object_identical": prepare_window.__code__ is online_training.prepare_window.__code__,
        "original_module_globals_modified": False, "original_episode_files_modified": False,
        "targets_reconstructed": False, "mask_criterion_changed": False,
        "scope": "Recognize fully source-bound zero-generation refusals; preserve all original target eligibility, numerical loss and denominator criteria."}
