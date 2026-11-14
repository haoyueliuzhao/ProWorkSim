"""New host episode: admit the frozen 24 CPU lanes, never the old 176 CPU floor.

The original actor/controller/runtime bundle and all historical host sources
remain immutable. The replacement is compiled into the actual new _run AST,
including the zero-model diagnostic path, before Docker is opened.
"""
from __future__ import annotations

import ast
import os
from types import FunctionType

from . import software_benchmark_episode_context_v203_2_3_r3 as previous
from .software_benchmark_candidates_v054 import reference

VERSION = "v203.2.3-recovery-frozen-cpu-lanes-owned-episode-r3"


def _cpus(value):
    if not isinstance(value, str) or not value:
        raise ValueError("A frozen CPU lane must be a nonempty comma-separated set")
    parts = value.split(",")
    if any(not item.isdigit() or str(int(item)) != item for item in parts):
        raise ValueError("CPU lane encoding is not canonical")
    cpus = [int(item) for item in parts]
    if len(cpus) != len(set(cpus)):
        raise ValueError("A CPU lane repeats a CPU")
    return cpus


def validate_cpu_lanes(scope, policy):
    """Bind concrete policy lanes to this scope's captured pool and limits.

    32 is an aggregate upper bound, not a required host-pool size. Only the
    simultaneous coordinator, two actor/controller pairs and grader are counted.
    Public fixture qualifications are a separate, already-closed phase.
    """
    frozen = scope.load(reference(scope.CPU_POOL_FILE))
    pool = frozen.get("cpu_ids")
    constraints = scope.CONSTRAINTS
    if (frozen.get("uid") != os.getuid() or frozen.get("captured_before_run") is not True
            or not isinstance(pool, list) or not pool
            or any(type(cpu) is not int or cpu < 0 for cpu in pool)
            or len(pool) != len(set(pool))
            or policy.host_cpu_pool() != pool or scope.host_cpu_pool() != pool):
        raise ValueError("Actual policy CPU pool differs from the frozen ordinary-user inventory")
    if policy.CONSTRAINTS != constraints:
        raise ValueError("Actual policy limits differ from the frozen scope")
    if (scope.MAX_GENERATIONS != 2 or scope.MAX_GRADERS != 1 or scope.MANAGER_CPUS != 8
            or constraints.get("active_actor_limit") != 2
            or constraints.get("active_controller_limit") != 2
            or constraints.get("active_grader_limit") != 1
            or constraints.get("actor_cpu") != 4 or constraints.get("controller_cpu") != 2
            or constraints.get("grader_cpu") != 4
            or constraints.get("coordinator_cpu_quota_percent") != 800
            or constraints.get("required_lane_cpu_count") != 24
            or constraints.get("maximum_combined_reserved_cpu") != 32
            or len(pool) > constraints["maximum_combined_reserved_cpu"]):
        raise ValueError("The frozen 24-lane layout or 32-CPU upper bound changed")
    specs = [("coordinator", 0, 8)]
    specs += [(role, index, width) for index in range(2) for role, width in (("actor", 4), ("controller", 2))]
    specs += [("grader", 0, 4)]
    lanes, seen = {}, set()
    for role, index, width in specs:
        actual = _cpus(policy.cpu_set(role, index))
        expected = _cpus(scope.cpu_set(role, index))
        if actual != expected or len(actual) != width:
            raise ValueError("Actual CPU lane differs from its frozen width/assignment: " + role)
        if not set(actual) <= set(pool):
            raise ValueError("A CPU lane escapes the frozen pool: " + role)
        if seen.intersection(actual):
            raise ValueError("Simultaneous runtime CPU lanes overlap: " + role)
        seen.update(actual)
        lanes[f"{role}-{index}"] = actual
    if len(seen) != constraints["required_lane_cpu_count"]:
        raise ValueError("The captured pool cannot supply all 24 declared CPU lanes")
    return {"version": VERSION, "frozen_cpu_inventory": reference(scope.CPU_POOL_FILE),
        "captured_pool": pool, "actual_lanes": lanes, "simultaneous_assigned_cpus": sorted(seen),
        "required_lane_cpu_count": 24, "aggregate_cpu_upper_bound": 32,
        "unused_captured_cpus": sorted(set(pool) - seen), "lanes_pairwise_disjoint": True,
        "all_lanes_within_frozen_pool": True, "host_cpu_pool_expanded": False}


def replace_cpu_guard(tree):
    """Replace exactly the legacy formal/diagnostic guard, not a guessed number."""
    replacements = 0
    for parent in list(ast.walk(tree)):
        for _, block in ast.iter_fields(parent):
            if not isinstance(block, list):
                continue
            for index, node in enumerate(list(block)):
                if (isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "diagnostic"
                        and len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)
                        and ast.unparse(node.orelse[0].test) == "len(policy.host_cpu_pool()) < 176"):
                    if (len(node.body) != 1 or not isinstance(node.body[0], ast.If)
                            or ast.unparse(node.body[0].test) != "len(os.sched_getaffinity(0)) < 4"):
                        raise ValueError("Legacy diagnostic CPU guard shape changed")
                    block[index:index + 1] = ast.parse(
                        "result['cpu_lane_admission'] = validate_runtime_cpu_lanes(policy)\n").body
                    replacements += 1
    if replacements != 1:
        raise ValueError("Expected exactly one actual legacy CPU guard, found " + str(replacements))
    return ast.fix_missing_locations(tree)


def _transform(tree):
    updated, counts = previous._memory_and_admission_ast(tree)
    return replace_cpu_guard(updated), {**counts, "actual_frozen_cpu_lane_guard": 1}


def assert_actual_cpu_guard(value):
    tree = value.memory_transformed_ast
    checks = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "validate_runtime_cpu_lanes"]
    if (len(checks) != 1 or "validate_runtime_cpu_lanes" not in value._run.__code__.co_names
            or "len(policy.host_cpu_pool()) < 176" in ast.unparse(tree)
            or value.run_episode.__globals__["_run"] is not value._run):
        raise ValueError("The actual compiled episode lost its CPU lane admission")
    return {"actual_compiled_run_guard_calls": 1, "legacy_176_guard_absent": True,
            "formal_and_diagnostic_use_same_guard": True}


def build_episode(*, scope, guard, host_memory=None, admission_check=lambda row: None):
    namespace = {**vars(previous), "VERSION": VERSION, "__file__": __file__,
                 "_memory_and_admission_ast": _transform}
    namespace["_strategy_builder"] = previous._bound_function(previous._strategy_builder, namespace)
    builder = previous._bound_function(previous.build_episode, namespace)
    value = builder(scope=scope, guard=guard, host_memory=host_memory, admission_check=admission_check)
    actual = value._run.__globals__

    def validate(policy):
        return validate_cpu_lanes(scope, policy)

    actual["validate_runtime_cpu_lanes"] = validate
    value.validate_runtime_cpu_lanes = validate
    value.cpu_guard_binding = assert_actual_cpu_guard(value)

    def run_diagnostic(index=1, *, stop_event=None):
        authority = guard("v066.run")
        if authority.get("plan") != reference(scope.PLAN_FILE):
            raise PermissionError("Diagnostic requires this exact new execution plan")
        plan = scope.load(authority["plan"])
        bindings = [item for item in plan["diagnostics"] if item["index"] == index]
        if type(index) is not int or len(bindings) != 1 or bindings[0].get("model_calls") != 0:
            raise PermissionError("No exact zero-model diagnostic identity")
        rows = [row for row in plan["rows"] if row["slot_id"] == bindings[0]["slot_id"]]
        if len(rows) != 1:
            raise PermissionError("Diagnostic slot must identify one frozen row")
        # The actual _run validates all three diagnostic resource claims and
        # executes bundle extraction, actor/controller ready/RPC and retention.
        return value._run(rows[0], None, diagnostic=True, diagnostic_index=index, stop_event=stop_event)

    value.run_diagnostic = run_diagnostic
    value.deployment_revision = VERSION
    return value
