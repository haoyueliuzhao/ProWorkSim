"""Mechanical formal-path equivalence of the isolated v066 diagnostic package."""
import ast
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = (
    "run_native_worker_docker", "run_ref_controller", "run_project_controller",
    "run_managed_worker_docker",
)


def tree(path):
    return ast.parse(path.read_bytes(), filename=str(path))


def canonical(value):
    return ast.dump(value, annotate_fields=True, include_attributes=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_ref(path):
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def normalize_deadline(value, name):
    value = copy.deepcopy(value)
    replacements = []
    for node in ast.walk(value):
        if not isinstance(node, ast.FunctionDef) or node.name not in {"install_lifecycle_deadline", "install_deadline"}:
            continue
        for child in ast.walk(node):
            if (name == "run_native_worker_docker" and isinstance(child, ast.Tuple)
                    and [getattr(element, "value", None) for element in child.elts] == [600, 24000]):
                child.elts[0].value = 180
                replacements.append("install_lifecycle_deadline allowed diagnostic maximum 180→600; formal maximum remains24000")
            elif (name in {"run_ref_controller", "run_project_controller"} and isinstance(child, ast.IfExp)
                    and isinstance(child.body, ast.Constant) and child.body.value == 600
                    and isinstance(child.orelse, ast.Constant) and child.orelse.value == 24000
                    and canonical(child.test) == canonical(ast.parse('config["diagnostic"]', mode="eval").body)):
                child.body.value = 180
                replacements.append(node.name + " diagnostic-only branch 180→600; formal branch remains24000")
    expected = 0 if name == "run_managed_worker_docker" else 1
    assert len(replacements) == expected, (name, replacements)
    return value, replacements


class BuilderPaths(ast.NodeTransformer):
    """Only metadata and the four new copied tool module names may differ."""
    def visit_Constant(self, node):
        if not isinstance(node.value, str):
            return node
        value = node.value.replace(
            "Local-only SDK bundle for v066 with extended zero-model diagnostic lifetime.",
            "Local-only SDK and explicit managed-runtime bundle for the v064 Docker pair.")
        value = value.replace("runs/software-benchmark-v066/sdk-bundle-r1", "runs/software-benchmark-v064/sdk-bundle-r2")
        value = value.replace("v066-local-ref-project-sdk-container-bundle-r1", "v064-local-ref-project-sdk-container-bundle-r2")
        for name in ENTRYPOINTS:
            value = value.replace(name + "_v066", name + "_v064")
        node.value = value
        return node


def audit():
    rows = []
    for name in ENTRYPOINTS:
        old, new = (ROOT / "tools" / (name + suffix) for suffix in ("_v064.py", "_v066.py"))
        before, after = tree(old), tree(new)
        normalized, differences = normalize_deadline(after, name)
        assert canonical(before) == canonical(normalized), "Unreviewed formal source difference: " + name
        rows.append({"entrypoint": name, "original": file_ref(old), "new": file_ref(new),
            "allowed_changes": differences, "original_AST_sha256": fingerprint(before),
            "normalized_new_AST_sha256": fingerprint(normalized), "formal_algorithm_AST_equal": True})
    old = ROOT / "src/proworksim/software_benchmark_sdk_bundle_v064.py"
    new = old.with_name("software_benchmark_sdk_bundle_v066.py")
    before, after = tree(old), tree(new)
    normalized = BuilderPaths().visit(copy.deepcopy(after))
    assert canonical(before) == canonical(normalized), "Unexpected builder selection/probe/algorithm difference"
    return {"version": "v066-diagnostic-only-SDK-AST-equivalence-r1", "passed": True,
        "entries": rows, "builder": {"original": file_ref(old), "new": file_ref(new),
            "original_AST_sha256": fingerprint(before), "normalized_new_AST_sha256": fingerprint(normalized),
            "allowed_changes": ["new artifact root and version metadata", "four copied entrypoint module paths in tools/aliases/probe"]},
        "formal_lifecycle_seconds": 24000, "formal_soft_seconds": 21600, "formal_hard_seconds": 23400,
        "diagnostic_lifecycle_seconds_before": 180, "diagnostic_lifecycle_seconds_after": 600,
        "model_visible_tools_prompts_sampling_or_budget_changed": False,
        "actor_implementation_and_FIFO_wire_strings_changed": False,
        "core_model_managed_harness_sources": "unchanged v064 bytes copied by the new builder",
        "shared_server_or_runtime_operations": 0}


def test_ast_whitelist_covers_all_entrypoints_and_builder():
    assert audit()["passed"]


@pytest.mark.parametrize("name,function", [
    ("run_native_worker_docker", "install_lifecycle_deadline"),
    ("run_ref_controller", "install_lifecycle_deadline"),
    ("run_project_controller", "install_deadline"),
])
def test_deadline_guards_accept_only_new_diagnostic_and_original_formal_limits(name, function):
    node = next(row for row in tree(ROOT / "tools" / (name + "_v066.py")).body
                if isinstance(row, ast.FunctionDef) and row.name == function)
    observed = []
    scope = {"time": SimpleNamespace(monotonic=lambda: 100),
        "signal": SimpleNamespace(SIGALRM=14, ITIMER_REAL=0, signal=lambda *_: None,
                                  setitimer=lambda *args: observed.append(args)),
        "os": SimpleNamespace(_exit=lambda *_: (_ for _ in ()).throw(AssertionError("No exit in CPU fixture")))}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "deadline-CPU-fixture", "exec"), scope)
    run = scope[function]
    for diagnostic, maximum in ((True, 600), (False, 24000)):
        run({"diagnostic": diagnostic, "maximum_lifecycle_seconds": maximum,
             "lifecycle_deadline": 100 + maximum - 1})
        assert observed[-1] == (0, maximum - 1)
    with pytest.raises(ValueError):
        run({"diagnostic": True, "maximum_lifecycle_seconds": 180, "lifecycle_deadline": 200})
    if name != "run_native_worker_docker":
        with pytest.raises(ValueError):
            run({"diagnostic": False, "maximum_lifecycle_seconds": 600, "lifecycle_deadline": 200})
