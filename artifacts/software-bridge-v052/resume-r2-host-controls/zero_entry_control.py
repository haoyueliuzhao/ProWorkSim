"""One zero-entry admission control with started/cost/trace rejection cases."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

PROJECT = Path('/data1/zhuxinrui/projects/ProWorkSim')
SOURCE = PROJECT / 'runs/software-bridge-v052-resume-r1/source'
sys.path[:0] = [str(SOURCE / 'src'), str(SOURCE)]
MODULE = PROJECT / 'scripts/software_bridge_v052_resume_r2.py'
spec = importlib.util.spec_from_file_location('scripts.software_bridge_v052_resume_r2', MODULE)
resume = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume)
OUT = PROJECT / 'artifacts/software-bridge-v052/resume-r2-host-controls'
PROOF = PROJECT / 'artifacts/software-bridge-v052/resume-r1-zero-entry-audit.json'

def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

original = json.loads(PROOF.read_text())
assert resume.zero_model_predecessor(PROJECT, reference(PROOF)) == original
results = []
for case in ('started', 'model_cost', 'trace_mismatch'):
    counterexample = copy.deepcopy(original)
    if case == 'started':
        counterexample['rows'][0]['slot_entered'] = True
    elif case == 'model_cost':
        counterexample['original_ledger']['known_actual_tokens'] = 1
    else:
        counterexample['sources']['supervisor-signals.strace']['sha256'] = '0' * 64
    path = OUT / (case + '-counterexample.json')
    path.write_text(json.dumps(counterexample, sort_keys=True, indent=2) + '\n')
    try:
        resume.zero_model_predecessor(PROJECT, reference(path))
    except (ValueError, RuntimeError) as error:
        results.append({'case': case, 'rejected': True, 'error': str(error), 'proof': reference(path)})
    else:
        results.append({'case': case, 'rejected': False, 'proof': reference(path)})
record = {'version': 'v052-r2-zero-entry-admission-control-v1', 'passed': all(row['rejected'] for row in results),
    'valid_existing_receipt_accepted': True, 'counterexamples': results, 'original_receipt': reference(PROOF),
    'host_source': reference(MODULE), 'new_model_calls': 0, 'new_tokenizer_calls': 0,
    'source_or_initial_input_requalifications': 0, 'old_control_reruns': 0}
print(json.dumps(record, sort_keys=True))
if not record['passed']:
    raise SystemExit(1)
