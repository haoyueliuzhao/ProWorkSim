"""One narrow CPU control for the new deferred watcher; no real scoring."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import types

STAGE = Path('/tmp/v054-deferred-scoring-r1')
path = STAGE / 'tools/watch_deferred_scoring_v054.py'
spec = importlib.util.spec_from_file_location('deferred_watch_control', path)
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)
root = STAGE / 'control/watch-fixtures'
root.mkdir()
watcher.ROOT = root
for name in watcher.SOURCE_FILES:
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(name)
runs = root / 'runs/software-benchmark-v054'
runs.mkdir(parents=True)
policy = runs / 'policy.json'
policy.write_text('{}')
marker = runs / 'primary-completion.json'
output = runs / 'output'
seal = {'version': watcher.VERSION, 'repository': str(root), 'poll_seconds': 30,
        'maximum_driver_dispatches': 1, 'new_model_calls': 0,
        'python_executable': str(root / '.venv/bin/python'),
        'sources': [watcher.ref(root / p) for p in watcher.SOURCE_FILES],
        'fault_policy': watcher.ref(policy), 'primary_completion': str(marker), 'output': str(output)}
seal_path = runs / 'seal.json'
seal_ref = watcher.write_new(seal_path, seal)
checks = {}
calls = []
fake = types.ModuleType('proworksim.software_benchmark_deferred_scoring_v054')
fake.validate_primary = lambda value: calls.append(('validate', value))
def run_deferred(path, directory):
    calls.append(('run', str(path)))
    return watcher.write_new(directory / 'synthetic-summary.json', {'synthetic': True})
fake.run_deferred = run_deferred
sys.modules[fake.__name__] = fake

assert watcher.dispatch_if_complete(seal, seal_ref)['status'] == 'waiting_for_primary_completion'
assert not calls and not (output / 'watch-trigger.json').exists()
checks['absent_terminal_marker_never_dispatches'] = True

def rejected(fn):
    try:
        fn()
    except ValueError:
        return True
    raise AssertionError('expected rejection')

changed = root / watcher.SOURCE_FILES[0]
old = changed.read_bytes()
changed.write_bytes(b'changed')
checks['source_hash_change_rejected_before_import_or_dispatch'] = rejected(lambda: watcher.dispatch_if_complete(seal, seal_ref))
changed.write_bytes(old)
marker.write_text(json.dumps({'overlay_policy': {'path': 'wrong'}}))
checks['different_original_fault_policy_rejected'] = rejected(lambda: watcher.dispatch_if_complete(seal, seal_ref))
assert not calls
marker.write_text(json.dumps({'overlay_policy': seal['fault_policy']}))
result = watcher.dispatch_if_complete(seal, seal_ref)
assert result['status'] == 'deferred_driver_finished'
assert [x[0] for x in calls] == ['validate', 'run']
assert (output / 'watch-trigger.json').exists()
checks['validated_terminal_dispatches_exactly_once'] = True
assert watcher.dispatch_if_complete(seal, seal_ref) == result
assert len(calls) == 2
checks['completed_watch_restart_never_dispatches_twice'] = True

interrupted = copy.deepcopy(seal)
interrupted['output'] = str(runs / 'interrupted')
Path(interrupted['output']).mkdir()
watcher.write_new(Path(interrupted['output']) / 'watch-trigger.json', {'prior': True})
assert watcher.dispatch_if_complete(interrupted, seal_ref)['status'] == 'previous_dispatch_not_replayed'
assert len(calls) == 2
checks['interrupted_trigger_is_never_replayed'] = True
wrong_interval = copy.deepcopy(seal)
wrong_interval['poll_seconds'] = 60
checks['only_thirty_second_wait_accepted'] = rejected(lambda: watcher.verify_seal(wrong_interval))
checks['systemd_launch_seal_sha_mismatch_rejected'] = rejected(lambda: watcher.watch(seal_path, '0' * 64))
assert len(calls) == 2
receipt = {'version': 'v054-deferred-watch-cpu-control-r1', 'passed': True, 'checks': checks,
           'source': watcher.ref(path), 'control': watcher.ref(__file__), 'model_calls': 0,
           'scorer_invocations': 0, 'GPU_queries': 0, 'formal_slots_claimed': 0,
           'production_files_modified': False, 'driver_used': 'synthetic in-memory stub only'}
out = STAGE / 'control/watch-receipt.json'
watcher.write_new(out, receipt)
print(json.dumps(watcher.ref(out)))
