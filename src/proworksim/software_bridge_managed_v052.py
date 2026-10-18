"""Keep the v051 managed S1 execution; replace only post-work assessment hooks.

The original collector's model loop, prompt, tools, budgets and internal P/raw
identity are retained. Two function-local imports bind a pre-scoring terminal
lock and complete-identity assessment reuse for this new v052 inventory.
"""
from __future__ import annotations

import ast
import copy
from functools import cache
import inspect
from pathlib import Path

from . import software_calibration_collector_v051 as collector
from . import software_calibration_world_v051 as world_library
from .software_bridge_sources_v052 import checked, grade_locked_candidate, lock_final_candidate, write_new
from .storage import digest, json_bytes, read_json

VERSION = "software-bridge-managed-assessment-v0.52"
validate_case = world_library.validate_case


def current_tree(prepared):
    prepared.world.state = prepared.world.store.load()
    artifact, version, bundle = prepared.world._bundle("member_001")
    return copy.deepcopy(bundle), world_library.previous.previous.base._reference(artifact, version)


def assess_software_collaboration(prepared, *, run_root):
    """Freeze the terminal tree before inspecting either terminal or fixed score."""
    if hasattr(prepared, "_v052_terminal_lock"):
        raise ValueError("The terminal candidate can be locked only once")
    root = Path(run_root).resolve().parent / "terminal-code"
    bundle, source_reference = current_tree(prepared)
    lock_ref = lock_final_candidate(provider=prepared.source_provider,
        task_id=prepared.case["case_id"], candidate_files=bundle["files"], run_root=root / "prelocked-source")
    lock = {"member_id": "member_001", "source_reference": source_reference,
        "source_sha256": digest(json_bytes(bundle)), "files_sha256": digest(json_bytes(bundle["files"])),
        "bridge_candidate_lock": lock_ref}
    write_new(root / "terminal-candidate-lock.json", lock)
    prepared._v052_terminal_lock = {"root": str(root), "lock": lock}
    return world_library.assess_software_collaboration(prepared, run_root=run_root)


def assess_terminal_working_tree(prepared, *, run_root, fixed_assessment=None):
    bound = getattr(prepared, "_v052_terminal_lock", None)
    if bound is None or Path(run_root).resolve() != Path(bound["root"]):
        raise ValueError("Terminal scoring requires its earlier unique lock")
    root, lock = Path(bound["root"]), bound["lock"]
    if read_json(root / "terminal-candidate-lock.json") != lock:
        raise ValueError("Terminal lock changed after work ended")
    bundle, source_reference = current_tree(prepared)
    if (source_reference != lock["source_reference"]
            or digest(json_bytes(bundle)) != lock["source_sha256"]
            or digest(json_bytes(bundle["files"])) != lock["files_sha256"]):
        raise ValueError("The managed terminal tree changed after the pre-scoring lock")
    checked(lock["bridge_candidate_lock"])
    grade = grade_locked_candidate(provider=prepared.source_provider,
        lock_reference=lock["bridge_candidate_lock"], fixed_assessment=fixed_assessment)
    if grade["files_sha256"] != lock["files_sha256"]:
        raise ValueError("A managed legal source tree unexpectedly changed during canonical export")
    same_raw_tree = bool(fixed_assessment and fixed_assessment.get("submitted")
                        and fixed_assessment.get("files_sha256") == lock["files_sha256"])
    if grade["reused_same_fixed_tree_assessment"] is not same_raw_tree:
        raise ValueError("Same managed tree must also have the same complete evaluation identity")
    result = {**grade, **lock, "version": VERSION,
        "scope": "New v052 episode only; pre-scoring sole terminal tree and complete-identity reuse. "
                 "The inherited managed model loop and fixed-delivery outcome remain unchanged."}
    write_new(root / "terminal-code-assessment.json", result)
    return result


@cache
def collector_binding():
    source = inspect.getsource(collector.collect_episode)
    tree = ast.parse(source)
    changes = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "software_calibration_world_v051":
            node.module = "software_bridge_managed_v052"
            changes += 1
    if changes != 2:
        raise ValueError("The inherited collector's two assessment/validation import sites changed")
    ast.fix_missing_locations(tree)
    namespace = dict(collector.__dict__)
    exec(compile(tree, "<v052-only-prelocked-assessment-imports>", "exec"), namespace)
    return namespace["collect_episode"], {"version": VERSION,
        "original_collector_source_sha256": digest(source.encode()), "changed_import_sites": changes,
        "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "original_internal_runtime_version": collector.VERSION,
        "model_loop_prompt_tools_budget_or_history_changed": False,
        "old_module_globals_or_records_modified": False}


def collect_episode(owner, prepared, folder, *, sampling_seed, slot_id, **kwargs):
    if not slot_id.startswith("v052-") or owner.freeze_identity().get("checkpoint") is not None:
        raise ValueError("PS1 is a new v052 episode using the original release without an adapter")
    function, adaptation = collector_binding()
    write_new(Path(folder) / "v052-managed-binding.json", {"version": VERSION,
        "slot_id": slot_id, "bridge_condition": "PS1", "inherited_calibration_condition": "P",
        "adaptation": adaptation})
    return function(owner, prepared, folder, sampling_seed=sampling_seed, slot_id=slot_id,
                    calibration_condition="P", **kwargs)
