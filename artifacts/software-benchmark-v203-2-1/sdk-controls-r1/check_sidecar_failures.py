"""Targeted constructor/finish failure controls for the actual runtime Sidecar."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim import software_role_baseline_runtime_v203_2_1 as managed
folder = ROOT / 'runs/software-benchmark-v203-2-1/sdk-controls-r1/sidecar-failures'
folder.mkdir(parents=True, exist_ok=False)
original = managed.ObserverJournal
try:
    def unavailable(*args, **kwargs):
        raise OSError('injected journal-open failure')
    managed.ObserverJournal = unavailable
    sidecar = managed.Sidecar(folder / 'initialize', 'episode')
    assert sidecar.record('INITIAL', 'initial', {}) is None
    finished = sidecar.finish('abnormal_or_incomplete')
    assert finished['observer_fault_count'] == 3
    assert sidecar.finish('abnormal_or_incomplete') is finished
finally:
    managed.ObserverJournal = original
reopened = managed.Sidecar(folder / 'initialize', 'episode')
assert reopened.fault_count == 3
reopened.journal.close()
closing = managed.Sidecar(folder / 'close', 'episode')
close = closing.journal.close
try:
    def unavailable_close():
        raise OSError('injected journal-close failure')
    closing.journal.close = unavailable_close
    value = closing.finish('bounded_work_closed')
    assert value['observer_fault_count'] == 1
finally:
    close()
result = {'passed': True, 'initialization_and_record_failures_did_not_raise': True,
          'fault_count_preserved_after_reopen': 3, 'finish_is_idempotent': True,
          'journal_close_failure_did_not_raise': True, 'world_actions': 0, 'model_calls': 0}
(folder / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
