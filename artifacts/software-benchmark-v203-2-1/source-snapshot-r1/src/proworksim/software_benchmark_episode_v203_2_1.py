"""New role-pilot host binding, retaining bounded v132 export and lock fixes.

Construction still requires the caller's exact fresh authorization. The old
five-group bundle, parent slice, and source globals are never activated.
"""
from __future__ import annotations

import ast
import inspect
from types import FunctionType, SimpleNamespace

from . import software_benchmark_episode_v131 as strategy_base
from . import software_benchmark_episode_v132 as memory_base
from . import software_benchmark_alignment_contract_v203_2_1 as alignment
from .software_benchmark_runtime_inputs_v203_2_1 import validate_actor_selection
from .software_benchmark_candidates_v054 import reference

VERSION = "v203.2.1-passive-review2-bounded-host-episode-r1"


def _bound_function(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


def _strategy_builder(bundle):
    source = inspect.getsource(strategy_base.build_episode)
    edits = {
        "from . import software_benchmark_scope_v131 as scope":
            "from . import software_benchmark_scope_v203_2_1 as scope",
        "    from .software_benchmark_actor_parent_v131 import parent_bound_pair\n"
        "    namespace['OwnedActorPair'] = parent_bound_pair(value.OwnedActorPair)\n"
        "    value.OwnedActorPair = namespace['OwnedActorPair']\n":
            "    # No system parent: new scope bounds every owned object and aggregate admission.\n",
        "node.module = 'software_benchmark_project_closure_v131'":
            "node.module = 'software_benchmark_project_closure_v203_2_1'",
    }
    for old, new in edits.items():
        if source.count(old) != 1:
            raise ValueError("The exact strategy binding changed; review its migration")
        source = source.replace(old, new)
    namespace = {**strategy_base.build_episode.__globals__, "bundle": bundle,
        "CONTRACT_VERSION": alignment.VERSION, "VERSION": VERSION,
        "validate_condition": alignment.validate_condition,
        "validate_plan_identity": alignment.validate_plan_identity,
        "validate_actor_selection": validate_actor_selection, "__file__": __file__}
    namespace["validate_actor_ready"] = _bound_function(strategy_base.validate_actor_ready, namespace)
    # The old result checker contains a function-local old-contract import;
    # bind the actual executed import as well as its module-level namespace.
    result_source = inspect.getsource(strategy_base.validate_controller_result)
    old = "from .software_benchmark_alignment_contract_v131 import shared_strategy"
    if result_source.count(old) != 1:
        raise ValueError("The concrete controller result contract import changed")
    result_source = result_source.replace(old, "from .software_benchmark_alignment_contract_v203_2_1 import shared_strategy")
    exec(compile(result_source, __file__+":controller-result", "exec"), namespace)
    exec(compile(source, __file__+":strategy-builder", "exec"), namespace)
    return namespace["build_episode"]


def _memory_and_admission_ast(tree):
    revised, counts = memory_base.transform_episode_ast(tree)
    conditional = 0
    for parent in list(ast.walk(revised)):
        for _, block in ast.iter_fields(parent):
            if not isinstance(block, list):
                continue
            for index, node in enumerate(list(block)):
                if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name) and node.value.func.id == "admission_check"):
                    block[index] = ast.If(test=ast.UnaryOp(op=ast.Not(), operand=ast.Name(id="diagnostic", ctx=ast.Load())),
                                          body=[node], orelse=[])
                    conditional += 1
    if conditional != 1:
        raise ValueError("The exact formal startup admission point changed")
    function = revised.body[0]
    function.body.insert(1, ast.parse("if diagnostic:\n    validate_diagnostic_entry(row, diagnostic_index)\n").body[0])
    return ast.fix_missing_locations(revised), {**counts, "formal_start_admission": conditional,
                                                "exact_zero_model_diagnostic_guard": 1}


def _bind_role_limits(value, scope):
    from . import software_benchmark_docker_actor_v066 as original
    provider = value.OwnedActorPair.create_container.__globals__
    if (provider is vars(original)
            or provider["container_options"].__globals__ is not provider
            or provider["validate_container"].__globals__ is not provider):
        raise ValueError("Actual creation and validation need one private provider namespace")
    declared = scope.CONSTRAINTS
    expected = {"actor": (declared["actor_cpu"], declared["actor_memory_bytes"], 512),
                "controller": (declared["controller_cpu"], declared["controller_memory_bytes"], 256)}
    if expected != {"actor": (4, 16*1024**3, 512), "controller": (2, 32*1024**3, 256)}:
        raise ValueError("The reviewed pilot actor/controller resource settings changed")
    provider["ROLES"] = expected
    value.actual_role_limits = {key: list(limits) for key, limits in expected.items()}


def _diagnostic_validator(scope, guard):
    def validate(row, index):
        if type(index) is not int or index != 1:
            raise PermissionError("Only a declared zero-model diagnostic index may enter")
        authority = guard("v066.run", slot_id=row["slot_id"], instance_id=row["instance_id"])
        plan_ref = reference(scope.PLAN_FILE)
        if authority.get("plan") != plan_ref:
            raise PermissionError("Diagnostic guard did not authorize this exact new plan")
        plan = scope.load(plan_ref)
        specs = [item for item in plan["diagnostics"] if item["index"] == index]
        if (len(specs) != 1 or specs[0].get("slot_id") != row["slot_id"]
                or specs[0].get("organization_id") != row["organization_id"] or specs[0].get("model_calls") != 0):
            raise PermissionError("Diagnostic row and fixed group differ from the exact zero-model plan")
        for role in ("actor", "controller", "volume"):
            item = plan["resources"].get(f"diagnostic-{index}-{role}", {})
            if (item.get("role") != role or item.get("diagnostic") is not True
                    or item.get("diagnostic_index") != index or item.get("slot_id") != row["slot_id"]
                    or item.get("instance_id") != row["instance_id"]):
                raise PermissionError("Diagnostic creation is outside its exact unused resource identity")
    return validate


def build_episode(*, scope, guard, host_memory=None, admission_check=lambda row: None):
    from . import software_benchmark_sdk_bundle_v203_2_1 as bundle
    strategy = SimpleNamespace(build_episode=_strategy_builder(bundle))
    namespace = {**memory_base.build_episode.__globals__, "previous": strategy,
                 "memory_bundle": bundle, "VERSION": VERSION, "__file__": __file__,
                 "transform_episode_ast": _memory_and_admission_ast}
    builder = _bound_function(memory_base.build_episode, namespace)
    value = builder(scope=scope, guard=guard, host_memory=host_memory, admission_check=admission_check)
    actual = value._run.__globals__
    actual["validate_diagnostic_entry"] = _diagnostic_validator(scope, guard)
    _bind_role_limits(value, scope)
    # This batch already declares a128GiB storage floor in its frozen plan.
    # Bind the actual preliminary wait to that declared floor, leaving the old
    # v066 implementation and its historical256GiB default unchanged.
    original_capacity = actual["capacity"]
    def capacity():
        measured = original_capacity()
        minimum = scope.CONSTRAINTS['disk_minimum_free_bytes']
        measured['admit'] = (measured['memory_available_bytes'] >= measured['memory_floor_with_two_pairs_and_two_graders']
            and measured['disk_free_bytes'] >= minimum and measured['load_1m'] < 140)
        measured['disk_floor_with_two_actor_reservations'] = minimum
        measured['disk_floor_source'] = 'current_frozen_scope_constraint'
        return measured
    actual['capacity'] = value.capacity = capacity
    actual['wait_capacity'] = value.wait_capacity = _bound_function(actual['wait_capacity'],
        {**actual['wait_capacity'].__globals__, 'capacity':capacity})
    if (actual["runtime"] is not bundle or actual["validate_condition"] is not alignment.validate_condition
            or value.run_episode.__globals__["_run"] is not value._run):
        raise ValueError("The actual pilot entry lost its new strategy or bounded final export")
    value.new_system_parent_slice = False
    value.allowed_organization_ids = alignment.GROUP_IDS
    return value
