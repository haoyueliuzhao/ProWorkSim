"""CPU-only math and persistence checks; no model, CUDA, or kernel execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import torch

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim/runs/software-benchmark-v054/kernel-optimization-r1/distribution-cpu-control-r2')
spec = importlib.util.spec_from_file_location('proworksim.software_benchmark_kernel_diagnostic_v054', ROOT / 'src/proworksim/software_benchmark_kernel_diagnostic_v054.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
torch.set_num_threads(1)
base = torch.tensor([-2., -1., 0., 1., 2.], device='cpu')
shift = m.compare_logits(torch, base, base + 10.)
assert shift['passed'] and not shift['original_gate_passed'] and shift['logit_nrmse'] > .03
assert shift['max_abs_probability_difference'] < 1e-6
perturbed = base + torch.tensor([0., .01, 0., -.01, .02])
observed = m.compare_logits(torch, base, perturbed)
a, b = (base / .7).log_softmax(-1), (perturbed / .7).log_softmax(-1)
expected = float((a.double().exp() * (a.double() - b.double())).sum())
assert observed['kl_reference_to_optimized'] == expected
assert observed['max_abs_probability_difference'] == float((a.exp() - b.exp()).abs().max())
a1, b1 = base.log_softmax(-1), perturbed.log_softmax(-1)
assert observed['max_abs_probability_difference'] != float((a1.exp() - b1.exp()).abs().max())
assert not observed['passed'] and observed['max_abs_probability_difference'] > 5e-4
large = m.compare_logits(torch, base, base + torch.tensor([0., 0., 0., 0., 1.]))
assert not large['passed'] and large['kl_reference_to_optimized'] > 1e-4
for bad in (float('nan'), float('inf'), float('-inf')):
    row = m.compare_logits(torch, base, torch.tensor([bad, -1., 0., 1., 2.]))
    assert not row['passed'] and not row['original_gate_passed'] and not row['finite']
assert not m.compare_logits(torch, base, base[:-1])['passed']
with tempfile.TemporaryDirectory(prefix='distribution-r2-', dir=ROOT / 'controls') as tmp:
    root = Path(tmp)
    rows = {}
    good_pair = m.compare_trajectories(torch, [base, base], [base + 10., base + 10.], [1,2], [1,2])
    m.persist_pair_comparison(root, 128, good_pair, rows)
    assert good_pair['passed'] and not good_pair['original_gate_passed']
    assert json.loads((root / 'comparisons-128.json').read_text())['original_gate_passed'] is False
    bad_pair = m.compare_trajectories(torch, [base, base], [base, perturbed], [1,2], [1,3])
    assert bad_pair['compared_positions'] == [0,1]
    try:
        m.persist_pair_comparison(root, 512, bad_pair, rows)
    except ValueError:
        assert json.loads((root / 'comparisons-512.json').read_text()) == bad_pair
        assert json.loads((root / 'comparisons.json').read_text())['512'] == bad_pair
    else:
        raise AssertionError('Changed distribution accepted')
assert m.PREPARATION_BUDGET['previous_actual_tokens'] + m.GATES['maximum_total_tokens'] + m.PREPARATION_BUDGET['interleave_maximum_tokens'] == 97792 <= 100000
result = {'status':'passed', 'version':m.VERSION, 'controls': ['constant_shift_new_pass_original_fail', 'exact_actual_temperature_0.7', 'probability_difference_rejects', 'KL_rejects', 'nonfinite_and_shape_rejected', 'old_gate_saved_per_pair', 'failed_pair_written_before_raise', 'common_prefix_positions_unchanged', 'preparation_budget'], 'constant_shift':shift, 'probability_perturbation':observed, 'model_calls':0, 'GPU_calls':0}
(ROOT / 'controls/distribution-result-r2.json').write_text(json.dumps(result, indent=2) + '\n')
assert json.loads((ROOT / 'controls/plan-fields-r2.json').read_text())['gates'] == m.GATES
print(json.dumps({'status':'passed', 'controls':len(result['controls']), 'model_calls':0, 'GPU_calls':0}))
