"""Fresh-process sidecar-only recovery; cannot execute world or model actions."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim.software_role_baseline_runtime_v203_2_1 import Sidecar

mode = sys.argv[1]
folder = ROOT / 'runs/software-benchmark-v203-2-1/sdk-controls-r1' / mode
capture = folder / 'model-ledger/passive-observer'
primary_files = list((folder / 'primary').glob('*.json'))
before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in primary_files}
summary_before = json.loads((capture / 'capture-summary.json').read_text())
sidecar = Sidecar(capture, summary_before['episode_id'])
assert sidecar.fault_count == summary_before['observer_fault_count']
rows = list(sidecar.journal.records())
returned = next((row for row in rows if row['kind'] == 'MODEL_RESPONSE'), None)
duplicate = None
if returned is not None:
    duplicate = sidecar.record(returned['kind'], returned['key'], returned['payload'])
    assert duplicate['duplicate'] and duplicate['sequence'] == returned['sequence']
counts = {}
for row in sidecar.journal.pending():
    counts[row['kind']] = counts.get(row['kind'], 0) + 1
sidecar.journal.save_projection('default', rows[-1]['sequence'], {'kind_counts': counts}, expected_cursor=0)
proof = sidecar.journal.integrity()
assert proof['default_pending'] == 0 and proof['known_conflicting_appends'] == 0
sidecar.journal.close()
after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in primary_files}
assert before == after
result = {'passed': True, 'mode': mode, 'fresh_process': True, 'fault_count_after_reopen': sidecar.fault_count,
          'same_key_retry': duplicate, 'projection_kind_counts': counts, 'integrity_after_projection': proof,
          'primary_request_response_action_and_boundary_files_unchanged': True,
          'new_world_actions': 0, 'new_model_requests': 0,
          'missing_precommit_observations_not_reconstructed': True}
(folder / 'recovery.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, sort_keys=True))
