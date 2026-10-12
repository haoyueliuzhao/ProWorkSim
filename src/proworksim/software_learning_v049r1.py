"""v049r1 original-material bridge over unchanged Gamma and numeric H=1 code.

Only record readers and an explicit unique source registry differ. The original
declaration, S0, native inputs, original own output mask criterion, denominator,
composition arithmetic and optimizer recipe remain in force.
"""
from __future__ import annotations

from pathlib import Path

from . import online_training
from . import software_learning_v049 as previous
from .software_learning_v029 import _projection_index as original_projection_index
from .software_member_views_v049r1 import (
    adaptation_spec, bind_private_function, member_view, prepare_window,
)
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "software-learning-record-reader-v0.49-r1"
REGISTRY_VERSION = "v049-unique-source-registry-r1"
software_feature_function = previous.software_feature_function
bind_composition = previous.bind_composition
validate_composition = bind_private_function(previous.validate_composition, {"member_view": member_view})


def _reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": digest(raw), "bytes": len(raw)}


def _checked_reference(reference):
    if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
        raise ValueError("Original source reference must include an explicit path and digest")
    path = Path(reference["path"]).resolve()
    if not path.is_file() or digest(path.read_bytes()) != reference.get("sha256"):
        raise ValueError("Original source reference is absent or changed")
    return path


def _source_folders(entries, declaration, source):
    expected = [slot["slot_id"] for slot in declaration["slots"]]
    if [entry["slot_id"] for entry in entries] != expected:
        raise ValueError("Only the original complete ordered slot inventory may bind source evidence")
    folders = {}
    for entry in entries:
        if entry.get("rollout") is not None:
            episode = Path(entry["rollout"]["episode_path"]).resolve()
            if episode.name != "episode":
                raise ValueError("Every original training source must be an archived episode")
            folders[entry["slot_id"]] = episode.parent
    if isinstance(source, (str, Path)) and Path(source).is_file():
        source = Path(source).resolve()
        registry = read_json(source)
        if (registry.get("version") != REGISTRY_VERSION
                or registry.get("sha256") != digest(json_bytes({key: value for key, value in registry.items() if key != "sha256"}))
                or [slot["slot_id"] for slot in registry.get("slots", [])] != expected):
            raise ValueError("Frozen original/new source registry seal or ordered inventory differs")
        registry_folders = []
        for row in registry["slots"]:
            folder = Path(row["episode_folder"]).resolve()
            registry_folders.append(folder)
            if row["slot_id"] in folders and folders[row["slot_id"]] != folder:
                raise ValueError("Rematerialized entry points outside its original unique registry slot")
            if row["origin"] not in {"original_v049", "resume_r1"}:
                raise ValueError("Source registry cannot add a third material origin")
            if (_checked_reference(row["source_result"]) != folder / "slot-result.json"
                    or _checked_reference(row["source_manifest"]) != folder / "episode/manifest.json"):
                raise ValueError("Registry source references must bind this exact original slot directory")
        if len(set(registry_folders)) != len(registry_folders):
            raise ValueError("An episode source directory cannot supply two original slots")
        proof = {"kind": "sealed_unique_source_registry", "reference": _reference(source)}
    else:
        roots = [Path(path).resolve() for path in source] if isinstance(source, (list, tuple)) else [Path(source).resolve()]
        if len(set(roots)) != len(roots) or not all(root.is_dir() for root in roots):
            raise ValueError("Explicit distinct existing original/resume source roots are required")
        if any(not any(folder == root or root in folder.parents for root in roots) for folder in folders.values()):
            raise ValueError("Original episode source lies outside the declared read-only source roots")
        proof = {"kind": "explicit_roots_exact_entry_slots_only", "roots": [str(root) for root in roots]}
    if len(set(folders.values())) != len(folders):
        raise ValueError("A source episode cannot be reused as a new raw slot")
    return folders, proof


def _source_index(folders):
    index = {}
    for folder in folders.values():
        observed = original_projection_index(folder / "raw-transport")
        if set(index) & set(observed):
            raise ValueError("Actual response IDs must remain globally unique across original and new slots")
        index.update(observed)
    return index


def validate_training_entries(owner, entries, declaration, *, request_evidence_root, require_open_window=True):
    folders, sources = _source_folders(entries, declaration, request_evidence_root)
    validate = bind_private_function(previous.validate_training_entries, {
        "member_view": member_view, "prepare_window": prepare_window,
        "_projection_index": lambda unused: _source_index(folders)})
    proof = validate(owner, entries, declaration, request_evidence_root=request_evidence_root,
                     require_open_window=require_open_window)
    for row in proof["rows"]:
        allowed = folders[row["slot_id"]] / "raw-transport"
        for source in row["source_files"]:
            path = Path(source["path"]).resolve()
            if allowed not in path.parents:
                raise ValueError("Original own native target is bound to a different slot's source")
    return {**proof, "record_reader_revision": VERSION, "record_reader_binding": adaptation_spec(),
        "actual_request_source_binding": sources, "original_declaration_changed": False,
        "source_files_copied_or_overwritten": False}


_numeric_update = bind_private_function(online_training.SharedActor.update_window, {"prepare_window": prepare_window})


class _NumericOwnerBinding:
    update_window = _numeric_update


_original_update_adapter = bind_private_function(previous.update_window, {
    "SharedActor": _NumericOwnerBinding, "validate_composition": validate_composition})


def update_window(owner, entries, output, *, composition=None, observe_support_gradients=False):
    output = Path(output)
    receipt = {"version": VERSION, "record_reader": adaptation_spec(),
        "original_H1_code_object_identical": _numeric_update.__code__ is online_training.SharedActor.update_window.__code__,
        "additional_effective_private_global_override": "prepare_window -> original code object with v049r1 member_view",
        "inherited_v049_overrides": ["validate_actor_composition"] + (["GroupGradientCapture"] if observe_support_gradients else []),
        "old_module_globals_changed": False, "original_declaration_Gamma_recipe_S0_changed": False,
        "scope": "Outer r1 reader provenance supplements the nested original v049 updater receipt; the numeric H1 function remains the original code object."}
    atomic_write(output.parent / (output.name + "-r1-reader-binding.json"), json_bytes(receipt))
    return _original_update_adapter(owner, entries, output, composition=composition,
                                    observe_support_gradients=observe_support_gradients)


update_software_window = bind_private_function(previous.update_software_window, {
    "validate_training_entries": validate_training_entries, "update_window": update_window})
