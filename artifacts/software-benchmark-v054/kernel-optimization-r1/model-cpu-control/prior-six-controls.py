import functools
import importlib.util
import json
from pathlib import Path
import torch

root = Path(__file__).resolve().parent
source = root / "src/proworksim/software_benchmark_kernel_diagnostic_v054.py"
spec = importlib.util.spec_from_file_location("proworksim.software_benchmark_kernel_diagnostic_v054", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

reference = torch.tensor([0., 1., -1., 5., -5.])
assert module.compare_logits(torch, reference, reference.clone())["passed"]
assert not module.compare_logits(torch, reference, -reference)["passed"]
for broken in (torch.tensor([float("nan")]*5), torch.zeros(3)):
    try:
        module.compare_logits(torch, reference, broken)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid logit evidence was admitted")

def backend(x):
    return x

def decorate(original):
    implementation, is_new_implementation = backend, True
    @functools.wraps(original)
    def wrapped(*args):
        assert is_new_implementation
        return implementation(*args)
    return wrapped

wrapped = decorate(lambda value: value)
assert module.implementation(wrapped)["optimized"] is True
assert module.implementation(wrapped)["source"] == str(Path(__file__).resolve())
assert sum(row[2]+64 for row in module.REQUESTS) == module.GATES["maximum_total_tokens"]
assert [row[2] for row in module.REQUESTS] == [128,128,512,512,16384,16384]
from proworksim.software_benchmark_candidates_v054 import reference as file_ref
receipt = {"passed": True, "source": file_ref(source), "controls": [
    "identical_full_vocabulary_admitted", "large_logit_regression_rejected",
    "nonfinite_rejected", "shape_change_rejected", "actual_callable_provenance",
    "fixed_request_and_token_bound"], "CUDA_calls": 0, "model_calls": 0}
(root / "cpu-control.json").write_text(json.dumps(receipt, indent=2)+"\n")
print(json.dumps(receipt))
