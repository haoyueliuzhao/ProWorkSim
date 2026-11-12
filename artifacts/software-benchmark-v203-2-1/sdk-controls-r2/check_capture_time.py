"""Only the timestamp/lookup revision; no repeated SDK/model/world execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim.software_role_baseline_runtime_v203_2_1 import Sidecar

RUN = ROOT / 'runs/software-benchmark-v203-2-1/sdk-controls-r2/timestamp-retry'
if len(sys.argv) > 1:
    sidecar = Sidecar(RUN, 'timestamp-cpu')
    result = sidecar.record('INITIAL', 'initial', {'phase': 'T0'})
    row = sidecar.journal.lookup('initial')
    assert isinstance(row['source']['capture_time'], float)
    if sys.argv[1] == 'retry':
        assert result['duplicate']
    else:
        assert not result['duplicate']
    if sys.argv[1] == 'retry':
        sidecar.record('RECEIPT', 'second', {'phase': 'T1'})
        assert sidecar.journal.lookup('second')['source']['capture_time'] >= row['source']['capture_time']
    sidecar.journal.close()
    print(json.dumps({'result': result, 'source': row['source'], 'fault_count': sidecar.fault_count}))
else:
    RUN.mkdir(parents=True, exist_ok=False)
    before = time.time()
    outputs = []
    for phase in ('first', 'retry'):
        result = subprocess.run([sys.executable, __file__, phase], capture_output=True, text=True, timeout=20, check=True)
        outputs.append(json.loads(result.stdout))
    after = time.time()
    assert outputs[0]['source'] == outputs[1]['source']
    assert before <= outputs[0]['source']['capture_time'] <= after
    assert all(value['fault_count'] == 0 for value in outputs)
    summary = {'passed': True, 'fresh_processes': 2, 'first_capture_time_reused': True,
               'source': outputs[0]['source'], 'duplicate_after_restart': outputs[1]['result'],
               'newer_event_has_later_capture_time': True, 'API_calls': 0, 'world_actions': 0,
               'old_r1_missing_times_not_backfilled': True,
               'sources': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                           for name in ['src/proworksim/software_role_baseline_runtime_v203_2_1.py',
                                        'src/proworksim/software_observer_journal_v203_2_1.py']}}
    Path(__file__).with_name('summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))
