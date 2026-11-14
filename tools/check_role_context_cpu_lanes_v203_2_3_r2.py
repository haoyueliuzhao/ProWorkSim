"""Necessary CPU guard controls; actual Docker diagnostic remains a separate gate."""
from __future__ import annotations

import argparse
import ast
import copy
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

from proworksim import software_benchmark_episode_v066 as original
from proworksim import software_benchmark_scope_v203_2_3_r2 as scope
from proworksim.software_benchmark_episode_v203_2_3_r2 import replace_cpu_guard, validate_cpu_lanes
from proworksim.software_benchmark_candidates_v054 import reference


def check(output):
    output.mkdir(parents=True, exist_ok=False)
    actual = validate_cpu_lanes(scope, scope.dispatch_view())
    roles = [("coordinator", 0), ("actor", 0), ("controller", 0), ("actor", 1), ("controller", 1), ("grader", 0)]
    baseline_lanes = {(role, index): scope.cpu_set(role, index) for role, index in roles}
    baseline_pool = actual["captured_pool"]
    results = []

    def fixture(name, *, pool=None, change=None, policy_change=None, policy_pool=None):
        pool = baseline_pool if pool is None else pool
        path = output / (name + "-pool.json")
        path.write_text(json.dumps({"uid": os.getuid(), "captured_before_run": True, "cpu_ids": pool}))
        lanes = {**baseline_lanes, **(change or {})}
        policy_lanes = {**lanes, **(policy_change or {})}
        given = SimpleNamespace(CPU_POOL_FILE=path, CONSTRAINTS=copy.deepcopy(scope.CONSTRAINTS),
            MAX_GENERATIONS=2, MAX_GRADERS=1, MANAGER_CPUS=8,
            load=lambda ref: json.loads(Path(ref["path"]).read_text()), host_cpu_pool=lambda: list(pool),
            cpu_set=lambda role, index=0: lanes[(role, index)])
        policy = SimpleNamespace(CONSTRAINTS=copy.deepcopy(scope.CONSTRAINTS),
            host_cpu_pool=lambda: list(pool if policy_pool is None else policy_pool),
            cpu_set=lambda role, index=0: policy_lanes[(role, index)])
        return given, policy

    def run_case(name, should_pass, **changes):
        given, policy = fixture(name, **changes)
        try:
            proof = validate_cpu_lanes(given, policy)
        except ValueError as error:
            if should_pass:
                raise
            results.append({"case": name, "passed": True, "rejected": True, "reason": str(error)})
        else:
            if not should_pass:
                raise AssertionError("Unsafe CPU lane fixture was admitted: " + name)
            results.append({"case": name, "passed": True, "rejected": False,
                "assigned_count": len(proof["simultaneous_assigned_cpus"]),
                "captured_count": len(proof["captured_pool"])})

    assigned = actual["simultaneous_assigned_cpus"]
    run_case("24_assigned_not_32_minimum", True, pool=assigned)
    run_case("32_captured_24_assigned", True)
    run_case("insufficient_pool", False, pool=assigned[:-1])
    run_case("out_of_pool_lane", False, change={("actor", 0): "1000,1001,1002,1003"})
    run_case("overlapping_roles", False, change={("controller", 0): baseline_lanes[("actor", 0)].rsplit(",", 2)[0]})
    run_case("wrong_lane_width", False, change={("actor", 0): baseline_lanes[("actor", 0)].rsplit(",", 1)[0]})
    run_case("policy_lane_differs", False, policy_change={("actor", 0): baseline_lanes[("grader", 0)]})
    run_case("expanded_policy_pool", False, policy_pool=list(range(240)))
    run_case("captured_pool_above_budget", False, pool=list(range(33)))

    original_source = inspect.getsource(original._run)
    tree = replace_cpu_guard(ast.parse(original_source))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "validate_runtime_cpu_lanes"]
    if len(calls) != 1 or "len(policy.host_cpu_pool()) < 176" in ast.unparse(tree):
        raise AssertionError("Actual inherited _run CPU guard was not replaced exactly")
    assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                      and isinstance(node.value, ast.Call) and node.value is calls[0])
    # Execute the exact replacement statement with both diagnostic flags. This
    # validates its unconditional placement, not the surrounding Docker lifecycle.
    probe = ast.parse("def probe(policy, diagnostic):\n    result = {}\n    return result\n")
    probe.body[0].body.insert(1, copy.deepcopy(assignment))
    invoked = []
    def validate(policy):
        invoked.append(True)
        return validate_cpu_lanes(scope, policy)
    namespace = {"validate_runtime_cpu_lanes": validate}
    exec(compile(ast.fix_missing_locations(probe), __file__ + ":actual-guard-statement", "exec"), namespace)
    for diagnostic in (False, True):
        namespace["probe"](scope.dispatch_view(), diagnostic)
    if len(invoked) != 2:
        raise AssertionError("Formal and diagnostic paths did not both execute the new guard")
    report = {"version": "v203.2.3-actual-cpu-lane-guard-controls-r2", "passed": True,
        "actual_frozen_scope": actual, "cases": results,
        "original_source": reference(Path(inspect.getfile(original))),
        "replacement_module": reference(Path(__file__).resolve().parents[1] / "src/proworksim/software_benchmark_episode_v203_2_3_r2.py"),
        "guard_in_actual_inherited_run_ast": True, "legacy_176_guard_removed": True,
        "formal_and_diagnostic_guard_statement_executed": True,
        "Docker_operations": 0, "model_calls": 0,
        "real_environment_qualification": False,
        "required_next_gate": "actual new actor/controller run_diagnostic through the compiled _run"}
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return {"passed": True, "cases": len(results), "summary": str(output / "summary.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.output.resolve()), ensure_ascii=False))
