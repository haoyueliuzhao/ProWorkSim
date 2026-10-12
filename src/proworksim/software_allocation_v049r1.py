"""Original v049 support/direction algorithm with the repaired reader binding.

One relative import changes: closed-rollout member views come from the isolated
v049r1 exporter. Support arithmetic, selection, feasible bounds and weights stay
original, and no old module global or declaration is modified.
"""
from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

from . import software_allocation_v049 as original
from .storage import digest, json_bytes

VERSION = original.VERSION
REVISION = "software-allocation-record-binding-v0.49r1"
feasible_radius = original.feasible_radius
select_direction = original.select_direction


def _adapt():
    source = inspect.getsource(original.build_support_report)
    tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
               and node.module == "software_training_v049" and node.level == 1]
    if (len(imports) != 1 or [(name.name, name.asname) for name in imports[0].names]
            != [("bind_rollout", None), ("expected_window", None)]):
        raise ValueError("Bind exactly the original v049 support reader import")
    imports[0].module = "software_training_v049r1"
    ast.fix_missing_locations(tree)
    namespace = dict(vars(original))
    exec(compile(tree, "<v049r1-original-support-single-reader-import>", "exec"), namespace)
    proof = {"version": REVISION, "original_function_source_sha256": digest(source.encode()),
        "original_module_sha256": digest(Path(original.__file__).read_bytes()),
        "changed_relative_imports": 1, "old_import": "software_training_v049",
        "new_import": "software_training_v049r1",
        "all_other_original_AST_nodes_retained": True,
        "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "mapping_specification_changed": False, "support_kernel_changed": False,
        "bounds": {"lower": original.LOWER, "upper": original.UPPER, "TV_limit": original.TV_LIMIT},
        "original_module_globals_modified": False}
    proof["sha256"] = digest(json_bytes(proof))
    return namespace["build_support_report"], proof


build_support_report, _adaptation = _adapt()


def adaptation_spec():
    return copy.deepcopy(_adaptation)
