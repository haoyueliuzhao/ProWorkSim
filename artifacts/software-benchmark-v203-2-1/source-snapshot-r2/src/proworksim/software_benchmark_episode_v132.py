"""Future host-only repair of the exact final v131 episode AST.

No old module globals, running owner, actor, model configuration or bundle are
modified. The final builder compile hook sees all earlier v131 insertions;
inspect.getsource on the generated function is deliberately not used.
"""
from __future__ import annotations

import ast
import builtins
import copy
from types import FunctionType

from . import software_benchmark_episode_v131 as previous
from . import software_benchmark_sdk_bundle_v132 as memory_bundle
from .software_benchmark_host_memory_v132 import HostMemoryGate


VERSION = "v132-bounded-host-episode-and-closure-r1"


def normalize_project_closure(value):
    """Map the real controller field explicitly; never choose between locks."""
    if not isinstance(value, dict):
        raise ValueError("A complete original controller closure is required")
    closure = dict(value)
    reference = closure.get("controller_candidate_lock")
    if (not isinstance(reference, dict) or set(reference) != {"path", "sha256", "bytes"}
            or not isinstance(reference["path"], str)
            or not isinstance(reference["sha256"], str) or len(reference["sha256"]) != 64
            or type(reference["bytes"]) is not int or reference["bytes"] < 0):
        raise ValueError("The original controller candidate lock is missing or invalid")
    if "project_candidate_lock" in closure and closure["project_candidate_lock"] != reference:
        raise ValueError("Two distinct controller candidate locks cannot be reconciled")
    closure["project_candidate_lock"] = dict(reference)
    return closure


def _assigned(node, name):
    return (isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))


def _callback(name, body, *, nonlocal_names=()):
    declarations = [ast.Nonlocal(names=list(nonlocal_names))] if nonlocal_names else []
    return ast.FunctionDef(name=name, args=ast.arguments(posonlyargs=[], args=[],
        kwonlyargs=[], kw_defaults=[], defaults=[]), body=declarations + body,
        decorator_list=[])


def transform_episode_ast(tree):
    tree = copy.deepcopy(tree)
    if (not isinstance(tree, ast.Module) or len(tree.body) != 1
            or not isinstance(tree.body[0], ast.FunctionDef) or tree.body[0].name != "_run"):
        raise ValueError("Only the final exact episode function may be adapted")
    function = tree.body[0]
    mains = [node for node in function.body if isinstance(node, ast.Try)
             and any(_assigned(item, "controller_exit") for item in node.body)]
    if len(mains) != 1:
        raise ValueError("The original controller lifecycle block changed")
    main = mains[0]
    counts = {"initial_snapshot": 0, "file_policy": 0, "closure_lock": 0,
              "final_phase": 0, "cleanup_phase": 0, "actual_start_check": 0}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Name) and call.func.id == "snapshot"
                    and any(k.arg == "name" and isinstance(k.value, ast.Constant)
                            and k.value.value == "baseline-snapshot" for k in call.keywords)):
                if ast.unparse(node.targets[0]) != "(baseline, baseline_ref)":
                    # ast.unparse uses unparenthesized tuples on some Python versions.
                    if ast.unparse(node.targets[0]) != "baseline, baseline_ref":
                        raise ValueError("The initial snapshot ownership changed")
                node.targets = [ast.Tuple(elts=[ast.Name(id="parked_baseline", ctx=ast.Store()),
                                               ast.Name(id="baseline_ref", ctx=ast.Store())], ctx=ast.Store())]
                node.value = ast.Call(func=ast.Attribute(value=ast.Name(id="host_memory", ctx=ast.Load()),
                    attr="capture_initial", ctx=ast.Load()), args=[ast.Subscript(
                        value=ast.Name(id="row", ctx=ast.Load()), slice=ast.Constant("slot_id"), ctx=ast.Load()),
                        ast.Name(id="snapshot", ctx=ast.Load()), *call.args], keywords=call.keywords)
                counts["initial_snapshot"] += 1
            if (_assigned(node, "closure") and isinstance(call.func, ast.Name) and call.func.id == "dict"
                    and len(call.args) == 1 and ast.unparse(call.args[0]) == "child['project_closure']"):
                call.func.id = "normalize_project_closure"
                counts["closure_lock"] += 1
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "file_policy" and ast.unparse(keyword.value) == "baseline['file_policy']":
                    keyword.value = ast.Attribute(value=ast.Name(id="parked_baseline", ctx=ast.Load()),
                                                  attr="file_policy", ctx=ast.Load())
                    counts["file_policy"] += 1
    # A drain that arrives after queue submission is still checked before the
    # first resource claim. No resume or cancellation of an entered model occurs.
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            for index, child in enumerate(node.body):
                if (isinstance(child, ast.Try) and child.body
                        and _assigned(child.body[0], "actor_reservation")):
                    child.body.insert(0, ast.parse("admission_check(row)\n").body[0])
                    counts["actual_start_check"] += 1
    starts = [i for i, node in enumerate(main.body) if _assigned(node, "transfer")
              and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)
              and node.value.func.attr == "download_compressed_archive"]
    if len(starts) != 1:
        raise ValueError("The original stopped-controller export boundary changed")
    start = starts[0]
    if not any(_assigned(node, "writer_proof") for node in main.body[:start]):
        raise ValueError("Writers must be stopped before waiting for host memory")
    heavy = ast.parse("baseline = host_memory.load(parked_baseline)\n").body + main.body[start:]
    callback = _callback("finish_original_episode", heavy, nonlocal_names=("terminal_ref", "writer_proof"))
    call = ast.parse("host_memory.run_heavy(row['slot_id'], 'closed_controller_export', finish_original_episode)\n").body
    main.body[start:] = [callback, *call]
    counts["final_phase"] = 1
    cleanup_starts = [i for i, node in enumerate(main.finalbody) if _assigned(node, "cleanup")]
    if len(cleanup_starts) != 1:
        raise ValueError("The original cleanup evidence boundary changed")
    start = cleanup_starts[0]
    pre_cleanup = ast.parse(
        "cleanup = None\n"
        "if pair is not None and writer_proof.get('all_quiet') is not True:\n"
        "    stopped_before_memory_wait = cleanup_step('writers_before_host_memory_wait', pair.stop_writers)\n"
        "    if stopped_before_memory_wait is not None:\n"
        "        writer_proof = stopped_before_memory_wait\n").body
    callback = _callback("retain_and_clean_original_episode", main.finalbody[start:],
                         nonlocal_names=("cleanup", "terminal_ref", "writer_proof"))
    call = ast.parse("host_memory.run_heavy(row['slot_id'], 'retention_and_owned_cleanup', retain_and_clean_original_episode)\n").body
    main.finalbody[start:] = [*pre_cleanup, callback, *call]
    counts["cleanup_phase"] = 1
    if any(value != 1 for value in counts.values()):
        raise ValueError("The exact future episode insertion points changed: " + str(counts))
    return ast.fix_missing_locations(tree), counts


def build_episode(*, scope, guard, host_memory=None, admission_check=lambda row: None):
    """Construct only; the supplied new scope must authorize actual execution.

    The coordinator shares one HostMemoryGate across every group and closes it
    only after all generation/scoring owners finish. No live v131 binding is
    changed. The new bundle changes only controller preparation audit hashing;
    actor code, tools and model-visible strategy remain v131.
    """
    memory = host_memory if host_memory is not None else HostMemoryGate()
    observed = []
    def compile_final(tree, filename, mode, *args, **kwargs):
        if observed or mode != "exec":
            raise ValueError("Expected exactly one final episode AST compilation")
        updated, counts = transform_episode_ast(tree)
        observed.append((updated, counts))
        return builtins.compile(updated, __file__, mode, *args, **kwargs)
    builder = FunctionType(previous.build_episode.__code__,
        {**previous.build_episode.__globals__, "compile": compile_final},
        previous.build_episode.__name__, previous.build_episode.__defaults__)
    builder.__kwdefaults__ = previous.build_episode.__kwdefaults__
    value = builder(scope=scope, guard=guard)
    if len(observed) != 1:
        raise ValueError("The new episode was not compiled through its declared binding")
    namespace = value._run.__globals__
    namespace.update(host_memory=memory, normalize_project_closure=normalize_project_closure,
                     admission_check=admission_check, runtime=memory_bundle)
    value.runtime = memory_bundle
    value.host_memory = memory
    value.deployment_revision = VERSION
    value.memory_integration_points = observed[0][1]
    value.memory_transformed_ast = observed[0][0]
    return value
