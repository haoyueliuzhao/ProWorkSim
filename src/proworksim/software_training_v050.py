"""New v050 source declarations over unchanged O1 evidence and reward rules."""
from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

from . import software_training_v049 as original
from . import software_training_v049r1 as repaired
from . import team_validity
from .software_member_views_v050 import bind_private_function, member_view, member_view_from_episode
from .software_organization_tasks_v050 import TRAINING_WINDOW_ID, _validate_files
from .software_organization_v050 import PAGING_VERSION, PROJECT, SCHEDULER, member_instruction, validate_case
from .storage import digest

VERSION = "software-training-export-v0.50"
GAMMA_VERSION = "software-information-v0.50"
RUNTIME_VERSION = "software-organization-runtime-v0.50"
VALIDITY = original.VALIDITY
MAPPER = original.MAPPER
POLICY_IMPLEMENTATION = original.POLICY_IMPLEMENTATION
SDK_CONTEXT_SELECTION = original.SDK_CONTEXT_SELECTION
MODES = original.MODES

_support_globals = {**original._support_globals, "member_view": member_view}
for _name in ("declare_window", "_declaration", "expected_window", "bind_rollout"):
    _support_globals[_name] = bind_private_function(original._support_globals[_name], _support_globals)
# Each original function needs the same mutually rebound namespace.
for _name in ("declare_window", "_declaration", "expected_window", "bind_rollout"):
    _support_globals[_name].__globals__.update({
        key: _support_globals[key] for key in ("declare_window", "_declaration", "expected_window", "bind_rollout")})
declare_window = _support_globals["declare_window"]
expected_window = _support_globals["expected_window"]
bind_rollout = _support_globals["bind_rollout"]


def assess_record_permission(episode, **kwargs):
    root = Path(episode).resolve()
    if root.name == "manifest.json":
        root = root.parent
    checks = bind_private_function(team_validity._record_permission_checks, {
        "member_view": lambda rollout, member: member_view_from_episode(root, rollout, member)})
    assess = bind_private_function(team_validity.assess_record_permission, {"_record_permission_checks": checks})
    return assess(root, **kwargs)


_namespace = {**vars(original), **globals(), "_validate_files": _validate_files,
    "PAGING_VERSION": PAGING_VERSION, "PROJECT": PROJECT, "SCHEDULER": SCHEDULER,
    "member_instruction": member_instruction, "validate_case": validate_case}
for _name in ("policy_spec", "situation_id", "situation_fingerprint", "source_training_admission",
              "_runtime_binding", "software_work_evidence", "reward_record", "unavailable_slot_entry"):
    _namespace[_name] = bind_private_function(getattr(original, _name), _namespace)
for _name in ("policy_spec", "situation_id", "situation_fingerprint", "source_training_admission",
              "_runtime_binding", "software_work_evidence", "reward_record", "unavailable_slot_entry"):
    _namespace[_name].__globals__.update({key: value for key, value in _namespace.items()
        if key in ("policy_spec", "situation_id", "situation_fingerprint", "source_training_admission",
                   "_runtime_binding", "software_work_evidence", "reward_record", "unavailable_slot_entry")})
    globals()[_name] = _namespace[_name]


def _export_adapter():
    source = inspect.getsource(repaired.export_software_episode)
    tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        and node.module == "software_mapper_v049r1" and node.level == 1]
    if len(imports) != 1:
        raise ValueError("Bind exactly one unchanged Mapper consumer import")
    imports[0].module = "software_mapper_v050"
    namespace = {**_namespace, **globals()}
    exec(compile(tree, "<v050-original-export-strict-new-source-consumers>", "exec"), namespace)
    return namespace["export_software_episode"], {
        "source_function_sha256": digest(source.encode()),
        "single_mapper_import_changed": True,
        "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "new_training_window": TRAINING_WINDOW_ID,
        "old_module_globals_modified": False,
        "actual_policy_implementation": POLICY_IMPLEMENTATION,
        "new_runtime_identity": RUNTIME_VERSION,
        "mapper_spec_and_reward_algorithm_changed": False,
    }


export_software_episode, _adaptation = _export_adapter()


def adaptation_spec():
    return copy.deepcopy(_adaptation)
