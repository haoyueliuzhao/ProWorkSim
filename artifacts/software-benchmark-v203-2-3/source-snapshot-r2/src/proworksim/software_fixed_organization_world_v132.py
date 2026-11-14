"""Same v131 world, with only its two preparation audit hashes streamed."""
from __future__ import annotations

import ast
import inspect
import textwrap
from types import FunctionType

from . import software_fixed_organization_world_v131 as previous
from .software_benchmark_initial_state_hash_v132 import initial_business_state_digest


MEMORY_REVISION = "v132-preparation-audit-hash-streaming-r1"


def _streamed_preparation(function, **bindings):
    # Both are ordinary static source functions (v065 and v131), never the
    # dynamically generated episode function whose source lines are ambiguous.
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    count = 0
    class ReplaceDigest(ast.NodeTransformer):
        def visit_Call(self, node):
            nonlocal count
            if ast.unparse(node) == "digest(json_bytes(initial_business_state(world)))":
                count += 1
                return ast.copy_location(ast.Call(func=ast.Name(id="initial_business_state_digest",
                    ctx=ast.Load()), args=[ast.Name(id="world", ctx=ast.Load())], keywords=[]), node)
            return self.generic_visit(node)
    tree = ReplaceDigest().visit(tree)
    if count != 1 or len(tree.body) != 1:
        raise ValueError("The single original preparation hash expression changed")
    namespace = {**function.__globals__, **bindings,
                 "initial_business_state_digest": initial_business_state_digest}
    exec(compile(ast.fix_missing_locations(tree), __file__, "exec"), namespace)
    return namespace[function.__name__]


_raw_build = _streamed_preparation(previous._raw_build)
build_software_collaboration_case = _streamed_preparation(
    previous.build_software_collaboration_case, _raw_build=_raw_build)
prepare_case = FunctionType(previous.prepare_case.__code__,
    {**previous.prepare_case.__globals__, "build_software_collaboration_case": build_software_collaboration_case},
    previous.prepare_case.__name__, previous.prepare_case.__defaults__, previous.prepare_case.__closure__)
prepare_case.__kwdefaults__ = previous.prepare_case.__kwdefaults__


def __getattr__(name):
    return getattr(previous, name)
