"""Strict v050 record reader; retain the original source-bound refusal proof."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from . import member_views as original
from . import online_training
from . import software_member_views_v049r1 as previous
from .storage import digest

VERSION = "v050-original-episode-world-identity-binding"
bind_private_function = previous.bind_private_function


def _adapt_identity_proof():
    source = inspect.getsource(previous.shared_admission_identity_proof)
    tree = ast.parse(source)
    replacements = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "software-organization-runtime-v0.49":
            node.value = "software-organization-runtime-v0.50"
            replacements += 1
    if replacements != 1:
        raise ValueError("Bind exactly one original runtime identity predicate")
    namespace = {**previous.shared_admission_identity_proof.__globals__, "VERSION": VERSION}
    exec(compile(tree, "<v050-source-bound-refusal-new-runtime-identity>", "exec"), namespace)
    return namespace["shared_admission_identity_proof"], {
        "source_function_sha256": digest(source.encode()),
        "source_module_sha256": digest(Path(previous.__file__).read_bytes()),
        "replaced_runtime_identity_constants": replacements,
        "old_runtime": "software-organization-runtime-v0.49",
        "new_runtime": "software-organization-runtime-v0.50",
        "other_original_predicates_preserved": True,
        "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
    }


shared_admission_identity_proof, _proof = _adapt_identity_proof()
_world_identity_mismatch = bind_private_function(previous._world_identity_mismatch, {
    "shared_admission_identity_proof": shared_admission_identity_proof})
_shared_validator = bind_private_function(previous._shared_validator, {
    "_world_identity_mismatch": _world_identity_mismatch})
known_shared_admission_stop = bind_private_function(previous.known_shared_admission_stop, {
    "VERSION": VERSION, "_shared_validator": _shared_validator,
    "shared_admission_identity_proof": shared_admission_identity_proof})
member_view = bind_private_function(original.member_view, {
    "_known_shared_admission_stop": known_shared_admission_stop})
prepare_window = bind_private_function(online_training.prepare_window, {"member_view": member_view})
member_view_from_episode = bind_private_function(previous.member_view_from_episode, {"member_view": member_view})


def adaptation_spec():
    return {"version": VERSION, **_proof,
        "original_member_view_code_identical": member_view.__code__ is original.member_view.__code__,
        "original_prepare_window_code_identical": prepare_window.__code__ is online_training.prepare_window.__code__,
        "old_module_globals_modified": False, "old_sources_modified": False,
        "mask_criterion_changed": False, "targets_reconstructed": False}
