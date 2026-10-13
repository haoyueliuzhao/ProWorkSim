"""v050 S*4/4 original-input bridge with fixed 24 x 2 base measure.

All actor/critic loss, optimizer, row ordering and probability code remains the
original H=1 code object. Only strict source identities/readers and optional
actor composition are privately bound; old sources and module globals stay put.
"""
from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

from . import online_training
from . import software_learning_v049 as original
from . import software_learning_v049r1 as repaired
from .software_member_views_v050 import adaptation_spec as reader_spec
from .software_member_views_v050 import bind_private_function, member_view, prepare_window
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "software-learning-bridge-v0.50"
COMPOSITION_VERSION = "software-composition-weights-v0.50"
MEMBERS = original.MEMBERS
CRITIC_MEMBERS = original.CRITIC_MEMBERS
COORDINATE_BINDING = original.COORDINATE_BINDING
NUMERICAL_STATE_FIELDS = original.NUMERICAL_STATE_FIELDS
SLOT_IDS = tuple(f"org50-train-{root}-r{repeat:02d}" for root in ("LA", "LB") for repeat in range(1, 13))
TRAINING_WINDOW_ID = "v050-o1-learning-window-01"
software_feature_function = original.software_feature_function
validate_selected_trace = original.validate_selected_trace


def _declared_slots(entries, declaration):
    slots = original._declared_slots(entries, declaration)
    if ([row["slot_id"] for row in slots] != list(SLOT_IDS)
            or declaration["window_id"] != TRAINING_WINDOW_ID
            or declaration["min_class_count"] != 2):
        raise ValueError("v050 requires the exact new 24-slot inventory, M12 and unchanged support threshold")
    for group in (slots[:12], slots[12:]):
        if len({row["xi_id"] for row in group}) != 1:
            raise ValueError("All twelve repeats must share their exact root situation")
    if slots[0]["xi_id"] == slots[12]["xi_id"]:
        raise ValueError("LA and LB remain distinct support roots")
    return slots


def bind_s_star_checkpoint(owner, directory):
    """Reference the existing complete B4/4 without writing another checkpoint."""
    if (owner.phase != "idle" or owner.busy or owner.sampling_only
            or tuple(owner.recipe["members"]) != CRITIC_MEMBERS
            or (owner.actor_steps, owner.critic_steps) != (4, 4)):
        raise ValueError("S* is the idle complete existing B4/4 with stable O1 coordinates")
    path = Path(directory).resolve() / "checkpoint.json"
    checkpoint = read_json(path)
    state = owner._state_bundle()
    observed = online_training.tensor_tree_digest(state, owner.torch)
    if (observed != checkpoint.get("state_tensor_digest")
            or checkpoint.get("actor_identity") != owner.freeze_identity()):
        raise ValueError("Loaded complete S* differs from the existing frozen B checkpoint")
    return {"checkpoint_ref": online_training.reference(path),
        "state_tensor_digest": observed,
        "learning_protected_digest": online_training.tensor_tree_digest(
            {key: state[key] for key in NUMERICAL_STATE_FIELDS}, owner.torch),
        "actor_identity": owner.freeze_identity(), "recipe_sha256": digest(json_bytes(owner.recipe)),
        "member_coordinate_mapping": copy.deepcopy(COORDINATE_BINDING),
        "actor_steps": 4, "critic_steps": 4,
        "checkpoint_written": False, "new_parameter_updates": 0}


def prepare_training_admission(entries, declaration, recipe):
    """CPU metadata admission before any expensive B training or gradient call."""
    from .software_training_v050 import bind_rollout

    _declared_slots(entries, declaration)
    if tuple(recipe["members"]) != CRITIC_MEMBERS:
        raise ValueError("Keep the same stable critic coordinate order")
    gamma = declaration["gamma_identity"]
    if (gamma.get("learning_bridge_version") != VERSION
            or gamma.get("source_usage") != "policy_training"
            or gamma.get("optimizer_update_allowed") is not True
            or gamma.get("s_star", {}).get("actor_identity") != declaration["actor_identity"]
            or gamma["s_star"].get("recipe_sha256") != digest(json_bytes(recipe))
            or (gamma["s_star"].get("actor_steps"), gamma["s_star"].get("critic_steps")) != (4, 4)):
        raise ValueError("CPU admission requires the exact S*4/4 training declaration and recipe")
    for entry in entries:
        if entry.get("rollout") is not None:
            bind_rollout(declaration, entry["slot_id"], entry["rollout"], mapping=entry.get("mapping"))
    result = prepare_window(entries, declaration["actor_identity"], declaration["window_id"],
                            recipe, software_feature_function)
    if result["slot_count"] != 24:
        raise ValueError("Missing original slots cannot shrink the global base measure")
    result["v050_measure"] = {"joint_slots": 24, "members_per_slot": 2,
        "global_member_denominator_factor": 48, "repeats_per_root": 12,
        "own_actor_mask_changed": False, "residual_reweighted": False,
        "GPU_or_optimizer_calls": 0, "behavior_probability_recomputation_executed": False}
    return result


def _source_folders(entries, declaration, source):
    _declared_slots(entries, declaration)
    if isinstance(source, (str, Path)) and Path(source).is_file():
        raise ValueError("v050 accepts only its explicit fresh collection roots, not an old mixed registry")
    folders, proof = repaired._source_folders(entries, declaration, source)
    for sid, folder in folders.items():
        manifest = read_json(folder / "episode/manifest.json")
        runtime = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
        if (runtime.get("version") != "software-organization-runtime-v0.50"
                or runtime.get("slot_id") != sid or runtime.get("purpose") != "policy_training"
                or runtime.get("online_window_id") != TRAINING_WINDOW_ID
                or runtime.get("actor_identity") != declaration["actor_identity"]):
            raise ValueError("Only new same-S* v050 episodes may supply actual native training targets")
    return folders, proof


def _native_admission_adapter():
    source = inspect.getsource(original.validate_training_entries)
    tree = ast.parse(source)
    targets = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and node.value == "s0"]
    if len(targets) != 1:
        raise ValueError("Bind exactly one old complete-start-state field")
    targets[0].value = "s_star"
    namespace = {**vars(original), **globals()}
    exec(compile(tree, "<v050-original-native-admission-new-S-star-field>", "exec"), namespace)
    return namespace["validate_training_entries"]


_native_admission = _native_admission_adapter()


def validate_training_entries(owner, entries, declaration, *, request_evidence_root, require_open_window=True):
    if (owner.actor_steps, owner.critic_steps) != (4, 4):
        raise ValueError("Every v050 branch must independently start from S*4/4")
    folders, sources = _source_folders(entries, declaration, request_evidence_root)
    validate = bind_private_function(_native_admission, {
        "_projection_index": lambda unused: repaired._source_index(folders)})
    proof = validate(owner, entries, declaration, request_evidence_root=request_evidence_root,
                     require_open_window=require_open_window)
    for row in proof["rows"]:
        allowed = folders[row["slot_id"]] / "raw-transport"
        if any(allowed not in Path(source["path"]).resolve().parents for source in row["source_files"]):
            raise ValueError("An original native target is bound to another declared slot")
    return {**proof, "record_reader_binding": reader_spec(), "actual_request_source_binding": sources,
        "global_member_denominator_factor": 48, "old_material_reused": False}


bind_composition = bind_private_function(original.bind_composition, {
    "COMPOSITION_VERSION": COMPOSITION_VERSION, "_declared_slots": _declared_slots})
validate_composition = bind_private_function(original.validate_composition, {
    "COMPOSITION_VERSION": COMPOSITION_VERSION, "bind_composition": bind_composition, "member_view": member_view})


class SupportGradientObserver(original.SupportGradientObserver):
    finish = bind_private_function(original.SupportGradientObserver.finish, {"VERSION": VERSION})


_numeric_update = bind_private_function(online_training.SharedActor.update_window, {"prepare_window": prepare_window})


class _NumericOwnerBinding:
    update_window = _numeric_update


_original_update_adapter = bind_private_function(original.update_window, {
    "VERSION": VERSION, "SharedActor": _NumericOwnerBinding,
    "validate_composition": validate_composition, "SupportGradientObserver": SupportGradientObserver})


def update_window(owner, entries, output, *, composition=None, observe_support_gradients=False):
    if (owner.actor_steps, owner.critic_steps) != (4, 4) or [row["slot_id"] for row in entries] != list(SLOT_IDS):
        raise ValueError("A v050 update independently starts at S*4/4 and retains all 24 slots")
    output = Path(output)
    receipt = {"version": VERSION, "reader": reader_spec(), "global_member_denominator_factor": 48,
        "original_H1_code_object_identical": _numeric_update.__code__ is online_training.SharedActor.update_window.__code__,
        "prepare_window_code_object_identical": prepare_window.__code__ is online_training.prepare_window.__code__,
        "original_module_globals_modified": False, "actor_composition_only": True,
        "critic_reweighted": False, "start_steps": [4, 4], "maximum_end_steps": [5, 5]}
    atomic_write(output.parent / (output.name + "-v050-learning-binding.json"), json_bytes(receipt))
    return _original_update_adapter(owner, entries, output, composition=composition,
                                    observe_support_gradients=observe_support_gradients)


update_software_window = bind_private_function(original.update_software_window, {
    "VERSION": VERSION, "validate_training_entries": validate_training_entries, "update_window": update_window})
