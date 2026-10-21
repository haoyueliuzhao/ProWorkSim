"""Evaluate only newly added AST guards; never import Torch, FLA or the model."""
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


def ref(path):
    data = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


root = Path(__file__).resolve().parent
old_path = root / "diagnostic-prior.py"
new_path = root / "diagnostic-with-bindings.py"
old, new = (ast.parse(p.read_text()) for p in (old_path, new_path))
prior = json.loads((root / "prior-six-controls.json").read_text())
assert prior["passed"] is True
assert prior["source"]["sha256"] == ref(old_path)["sha256"]
functions = [{x.name: x for x in tree.body if isinstance(x, ast.FunctionDef)}
             for tree in (old, new)]
unchanged = {}
for name in ("implementation", "fixed_prompt", "compare_logits"):
    unchanged[name] = ast.dump(functions[0][name]) == ast.dump(functions[1][name])
assert all(unchanged.values())
tails = [ast.Module(body=f["qualify_loaded_owner"].body[9:], type_ignores=[])
         for f in functions]
unchanged["model_execution_budget_and_closure_body"] = ast.dump(tails[0]) == ast.dump(tails[1])
assert unchanged["model_execution_budget_and_closure_body"]
constants = {x.targets[0].id: ast.literal_eval(x.value) for x in new.body
             if isinstance(x, ast.Assign) and isinstance(x.targets[0], ast.Name)
             and x.targets[0].id in {"VERSION", "REQUESTS", "GATES", "SYMBOLS", "REQUIRED_ENVIRONMENT"}}
for key in ("REQUESTS", "GATES", "SYMBOLS"):
    previous = next(x.value for x in old.body if isinstance(x, ast.Assign)
                    and isinstance(x.targets[0], ast.Name) and x.targets[0].id == key)
    unchanged[key] = ast.literal_eval(previous) == constants[key]
assert all(unchanged.values())
body = functions[1]["qualify_loaded_owner"].body
assert all(isinstance(body[i], ast.If) for i in (3, 5, 7))
guards = [compile(ast.Expression(body[i].test), "<exact-source-guard>", "eval")
          for i in (3, 5, 7)]
plan_path = root / "plan.json"
plan = json.loads(plan_path.read_text())
operator_path = Path(plan["operator_control"]["path"])
assert {k: ref(operator_path)[k] for k in ("sha256", "bytes")} == {
    k: plan["operator_control"][k] for k in ("sha256", "bytes")}
operator = json.loads(operator_path.read_text())
environment = constants["REQUIRED_ENVIRONMENT"]


def rejected(candidate_plan, candidate_operator, env):
    namespace = {**constants, "plan": candidate_plan, "operator": candidate_operator,
                 "enabled": candidate_plan.get("enabled_symbols"),
                 "os": SimpleNamespace(environ=env)}
    return any(eval(code, namespace) for code in guards)


checks = {"real_fixed_plan_and_environment_admitted": not rejected(plan, operator, environment)}
changed = copy.deepcopy(operator)
changed["qualified_symbols"] = [plan["enabled_symbols"][0]]
checks["operator_symbol_mismatch_rejected"] = rejected(plan, changed, environment)
changed = copy.deepcopy(operator)
changed["dependency_manifest"]["sha256"] = "0" * 64
checks["operator_dependency_digest_mismatch_rejected"] = rejected(plan, changed, environment)
changed = copy.deepcopy(operator)
changed["dependency_manifest"]["path"] += ".different"
checks["operator_dependency_path_mismatch_rejected"] = rejected(plan, changed, environment)
changed = dict(environment)
changed.pop("FLA_DISABLE_TENSOR_CACHE")
checks["missing_runtime_cache_disable_rejected"] = rejected(plan, operator, changed)
changed = dict(environment, FLA_DISABLE_TENSOR_CACHE="0")
checks["wrong_runtime_cache_disable_rejected"] = rejected(plan, operator, changed)
changed = copy.deepcopy(plan)
changed["required_environment"].pop("FLA_DISABLE_TENSOR_CACHE")
checks["missing_plan_cache_disable_rejected"] = rejected(changed, operator, environment)
assert all(checks.values())
receipt = {"version": "v054-kernel-model-new-binding-cpu-control-r1", "passed": True,
           "source": ref(new_path), "source_sha256": ref(new_path)["sha256"],
           "plan": ref(plan_path), "operator_admission": ref(operator_path),
           "prior_six_controls_reused_without_rerun": ref(root / "prior-six-controls.json"),
           "prior_functions_and_body_AST_equal": unchanged, "new_guard_controls": checks,
           "execution_method": "Only original guard AST expressions evaluated with fixed JSON and CPU dictionaries; no model module imported.",
           "torch_imports": 0, "CUDA_calls": 0, "model_calls": 0,
           "limitations": "Does not claim full function, model or deployment execution. Reuses prior unchanged mathematical, provenance and budget controls."}
(root / "new-binding-control.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
