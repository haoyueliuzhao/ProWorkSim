"""Strict unique-source registry for the unchanged v050 learner.

One retained original v050 slot and the same remaining 23 slots keep the original
24-by-2 measure. All numerical learning, target validation and source predicates
are inherited unchanged; only the explicit source-root lookup gains a registry.
"""
from __future__ import annotations

from pathlib import Path

from . import software_learning_v049r1 as source_helpers
from . import software_learning_v050 as previous
from .software_member_views_v050 import bind_private_function
from .storage import digest, json_bytes, read_json

VERSION = previous.VERSION
REVISION = "software-learning-source-binding-v0.50r1"
REGISTRY_VERSION = "software-learning-original-inventory-resume-v0.50-r1"
MEMBERS, CRITIC_MEMBERS = previous.MEMBERS, previous.CRITIC_MEMBERS
SLOT_IDS, TRAINING_WINDOW_ID = previous.SLOT_IDS, previous.TRAINING_WINDOW_ID
prepare_training_admission = previous.prepare_training_admission
bind_s_star_checkpoint = previous.bind_s_star_checkpoint
bind_composition = previous.bind_composition
validate_composition = previous.validate_composition
update_window = previous.update_window
_checked_reference = source_helpers._checked_reference


def _source_folders(entries, declaration, source):
    previous._declared_slots(entries, declaration)
    root = Path(source).resolve()
    path = root / "source-registry.json" if root.is_dir() else root
    registry = read_json(path)
    sources = registry.get("sources", [])
    if (registry.get("version") != REGISTRY_VERSION
            or registry.get("sha256") != digest(json_bytes({k: v for k, v in registry.items() if k != "sha256"}))
            or registry.get("slot_count") != 24 or registry.get("old_material_included") is not False
            or [row.get("slot_id") for row in sources] != list(SLOT_IDS)
            or read_json(_checked_reference(registry.get("declaration"))) != declaration):
        raise ValueError("v050r1 requires the sealed original ordered 24-slot declaration/source registry")
    folders, source_folders, entry_paths = {}, [], []
    for index, (entry, source_row) in enumerate(zip(entries, sources, strict=True)):
        sid = entry["slot_id"]
        entry_path = _checked_reference(source_row.get("entry"))
        row_path = _checked_reference(source_row.get("source_result"))
        manifest_path = _checked_reference(source_row.get("source_manifest"))
        folder = row_path.parent
        rollout = entry.get("rollout")
        if (read_json(entry_path) != entry or row_path.name != "slot-result.json"
                or manifest_path != folder / "episode/manifest.json"
                or rollout is not None and (
                    Path(rollout.get("episode_path", "")).resolve() != folder / "episode"
                    or rollout.get("manifest_sha256") != digest(manifest_path.read_bytes()))):
            raise ValueError("Registry entry must bind its exact original episode/result/manifest")
        manifest, row = read_json(manifest_path), read_json(row_path)
        runtime = manifest.get("scenario", {}).get("variation", {}).get("organization_runtime", {})
        if (manifest.get("status") != "closed" or rollout is not None and rollout.get("manifest") != manifest
                or row.get("version") != "software-organization-runtime-v0.50"
                or runtime.get("version") != "software-organization-runtime-v0.50"
                or runtime.get("purpose") != "policy_training"
                or runtime.get("slot_id") != sid or row.get("slot_id") != sid
                or runtime.get("sampling_seed") != 202610130501 + index
                or row.get("sampling_seed") != runtime.get("sampling_seed")
                or row.get("online_window_id") != declaration["window_id"]
                or runtime.get("online_window_id") != declaration["window_id"]
                or row.get("actor_identity") != declaration["actor_identity"]
                or runtime.get("actor_identity") != declaration["actor_identity"]
                or Path(row.get("episode_manifest", "")).resolve() != manifest_path):
            raise ValueError("Only the original same-S*/window/seed closed v050 source may enter training")
        if rollout is not None:
            folders[sid] = folder
        source_folders.append(folder)
        entry_paths.append(entry_path)
    if len(set(source_folders)) != 24 or len(set(entry_paths)) != 24:
        raise ValueError("Each original slot needs its own unique episode and export entry")
    checked, original_proof = previous._source_folders(entries, declaration, source_folders)
    if checked != folders:
        raise ValueError("Original v050 source checks must agree with the exact registry")
    return folders, {"kind": "sealed_v050_unique_original_and_resume_registry",
        "reference": source_helpers._reference(path), "original_checks": original_proof,
        "registry_binding_revision": REVISION, "native_sources_copied": False,
        "original_declaration_changed": False, "original_slot_count": 24}


validate_training_entries = bind_private_function(previous.validate_training_entries, {
    "_source_folders": _source_folders})
update_software_window = bind_private_function(previous.update_software_window, {
    "validate_training_entries": validate_training_entries})
