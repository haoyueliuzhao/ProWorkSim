"""Strict v050 export-seal consumer over the unchanged delivery Mapper.

The original v050 consumer retained a v049-only export identity predicate. This
isolated binding changes that one identity and its error label, preserving every
seal, source, actual-input and delivery-route predicate and the frozen Mapper.
"""
from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

from . import software_mapper_v049 as original
from . import software_mapper_v050 as previous
from .software_member_views_v050 import bind_private_function
from .storage import digest

VERSION = "software-mapper-export-binding-v0.50r1"
MAPPER = previous.MAPPER
mapping_spec = previous.mapping_spec
Evidence = previous.Evidence


def _validator_adapter():
    source = inspect.getsource(original._validate_export_evidence)
    tree = ast.parse(source)
    replacements = {
        "software-training-export-v0.49": "software-training-export-v0.50",
        "Original v049 export evidence seal differs": "Original v050 export evidence seal differs",
    }
    changed = dict.fromkeys(replacements, 0)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in replacements:
            changed[node.value] += 1
            node.value = replacements[node.value]
    if changed != dict.fromkeys(replacements, 1):
        raise ValueError("Bind exactly the old export version predicate and its diagnostic label")
    namespace = dict(original._validate_export_evidence.__globals__)
    exec(compile(tree, "<v050r1-strict-original-export-seal-consumer>", "exec"), namespace)
    return namespace["_validate_export_evidence"], {
        "version": VERSION,
        "source_function_sha256": digest(source.encode()),
        "source_module_sha256": digest(Path(original.__file__).read_bytes()),
        "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "explicit_constant_replacements": replacements,
        "other_original_predicates_preserved": True,
        "mapper_specification_changed": False,
        "old_module_globals_modified": False,
    }


_validate_export_evidence, _adaptation = _validator_adapter()
map_software_method = bind_private_function(previous.map_software_method, {
    "_validate_export_evidence": _validate_export_evidence})


def adaptation_spec():
    return copy.deepcopy(_adaptation)
