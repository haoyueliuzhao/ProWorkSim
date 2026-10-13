"""Isolated v050 export consumer and read-only closed-source rematerialization.

No model call, tokenizer call, world action or new acceptance is involved. The
original v050 case, declaration, reward, input/output and support rules remain.
"""
from __future__ import annotations

import ast
import copy
import inspect

from . import software_training_v049r1 as reexport_source
from . import software_training_v050 as previous
from .software_member_views_v050 import bind_private_function
from .storage import digest

VERSION = previous.VERSION
REVISION = "software-training-export-binding-v0.50r1"
MAPPER = previous.MAPPER
VALIDITY = previous.VALIDITY
RUNTIME_VERSION = previous.RUNTIME_VERSION
SDK_CONTEXT_SELECTION = previous.SDK_CONTEXT_SELECTION
PAGING_VERSION = previous.PAGING_VERSION
SCHEDULER = previous.SCHEDULER
declare_window = previous.declare_window
expected_window = previous.expected_window
bind_rollout = previous.bind_rollout
unavailable_slot_entry = previous.unavailable_slot_entry


def _export_adapter():
    source = inspect.getsource(reexport_source.export_software_episode)
    tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        and node.module == "software_mapper_v049r1" and node.level == 1]
    if len(imports) != 1:
        raise ValueError("Bind exactly the unchanged export's strict Mapper consumer import")
    imports[0].module = "software_mapper_v050r1"
    namespace = dict(previous.export_software_episode.__globals__)
    exec(compile(tree, "<v050r1-original-export-new-strict-mapper-consumer>", "exec"), namespace)
    return namespace["export_software_episode"], {
        "version": REVISION,
        "source_function_sha256": digest(source.encode()),
        "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "previous_v050_adaptation": previous.adaptation_spec(),
        "only_v050_consumer_import_changed": True,
        "old_module_globals_modified": False,
        "original_source_reward_and_target_rules_changed": False,
    }


export_software_episode, _adaptation = _export_adapter()
_closed_slot_source = bind_private_function(reexport_source._closed_slot_source, {
    "validate_case": previous.validate_case, "RUNTIME_VERSION": RUNTIME_VERSION,
    "expected_window": expected_window})


def _reward_spec(case):
    """Exact v050 metadata; no world preparation or independent acceptance."""
    return {"version": "software-organization-v0.50", "training_supported": case["training_eligible"],
        "purpose": case["purpose"], "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
        "independent_assessment": "assess_software_collaboration", "runtime_process_contract": case["process_contract"]}


reexport_closed_slot = bind_private_function(reexport_source.reexport_closed_slot, {
    "_closed_slot_source": _closed_slot_source, "_reward_spec": _reward_spec,
    "export_software_episode": export_software_episode, "REVISION": REVISION})


def adaptation_spec():
    from .software_mapper_v050r1 import adaptation_spec as mapper_spec

    return {**copy.deepcopy(_adaptation), "mapper_consumer": mapper_spec(),
        "reexport_original_code_object_identical":
            reexport_closed_slot.__code__ is reexport_source.reexport_closed_slot.__code__,
        "new_runtime_identity": RUNTIME_VERSION,
        "new_model_or_tokenizer_or_world_calls": 0}
