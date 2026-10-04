"""Carry CPU admission over the isolated loading-evidence serialization repair."""

import argparse
import ast
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import checked, reference, write

SOURCE = Path(__file__).resolve().parents[1]
BACKEND = "src/proworksim/candidate_runtime_v030.py"


def numerical_backend_ast(path):
    """Remove only the newly tested evidence helper and its single JSON write."""
    tree = ast.parse(Path(path).read_text())
    tree.body = [node for node in tree.body
                 if not (isinstance(node, ast.FunctionDef) and node.name == "loading_info_record")]

    class EvidenceWriter(ast.NodeTransformer):
        count = 0

        def visit_Expr(self, node):
            call = node.value
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id == "atomic_write" and call.args
                    and any(isinstance(item, ast.Constant) and item.value == "dense-loading.json"
                            for item in ast.walk(call.args[0]))):
                self.count += 1
                return ast.Expr(value=ast.Constant(value="loading-evidence-json-write"))
            return self.generic_visit(node)

    transform = EvidenceWriter()
    tree = transform.visit(tree)
    if transform.count != 1:
        raise ValueError("Expected exactly one isolated loading evidence writer")
    return ast.dump(tree, include_attributes=False)


def qualify(prior_plan, checks_path, output):
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Recovery admission requires a clean execution checkout")
    prior = read_json(prior_plan)
    old_qualification = read_json(checked(prior["qualification"]))
    if (old_qualification.get("passed") is not True or old_qualification.get("model_calls") != 0
            or old_qualification["source"] != prior["source"]):
        raise ValueError("Original frozen CPU admission is not valid")
    old_root = Path(prior["source_root"])
    current_files = {str(path.relative_to(SOURCE)): path for path in (SOURCE / "src").rglob("*.py")}
    old_files = {str(path.relative_to(old_root)): path for path in (old_root / "src").rglob("*.py")}
    if set(current_files) != set(old_files):
        raise ValueError("Recovery must not add or remove source modules")
    changes = [name for name in current_files if current_files[name].read_bytes() != old_files[name].read_bytes()]
    if changes != [BACKEND]:
        raise ValueError("Only the loading-evidence backend repair is admitted")
    if numerical_backend_ast(SOURCE / BACKEND) != numerical_backend_ast(old_root / BACKEND):
        raise ValueError("Model numerical, native format or load-admission code changed")
    for name, expected in old_qualification["tested_files_sha256"].items():
        if name in {BACKEND, "tests/test_candidate_runtime_v030.py"}:
            continue
        if digest((SOURCE / name).read_bytes()) != expected:
            raise ValueError("Previously qualified implementation or test changed: " + name)
    checks = read_json(checks_path)
    if (checks["source_tree_sha256"] != source["source_tree_sha256"] or not checks["checks"]
            or any(row["returncode"] != 0 for row in checks["checks"])):
        raise ValueError("Targeted recovery checks failed or target another source")
    required = {BACKEND, "tests/test_candidate_runtime_v030.py",
                "scripts/recover_software_model_selection_v030.py", "tests/test_recover_software_model_selection_v030.py"}
    if not required <= checks["file_sha256"].keys():
        raise ValueError("Targeted evidence omits a changed recovery implementation")
    for name, expected in checks["file_sha256"].items():
        if digest((SOURCE / name).read_bytes()) != expected:
            raise ValueError("Targeted recovery file changed: " + name)
    value = {
        "version": "software-model-selection-recovery-cpu-v0.30", "source": source,
        "passed": True, "model_calls": 0, "gpu_used": False,
        "original_plan": reference(prior_plan), "original_qualification": prior["qualification"],
        "targeted_checks": reference(checks_path), "checks": checks["checks"],
        "allowed_source_delta": {"path": BACKEND, "old_sha256": digest((old_root / BACKEND).read_bytes()),
                                 "new_sha256": digest((SOURCE / BACKEND).read_bytes()),
                                 "numerical_backend_ast_equal_after_isolated_evidence_writer_removal": True},
        "tested_files_sha256": checks["file_sha256"],
        "scope": "Original CPU admission plus targeted repair checks. Every other source module and original protected script/test is byte-identical. Only loading diagnostic JSON representation changed; no repeated model sampling or claim that old tests were rerun on new source.",
    }
    write(output, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-plan", type=Path, required=True)
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(qualify(args.prior_plan.resolve(), args.checks.resolve(), args.output.resolve())["passed"])


if __name__ == "__main__":
    main()
