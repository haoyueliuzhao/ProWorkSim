"""Fixed, randomized development inventory; one sequential queue per backend.

All requests remain in the original model experiment recorder. This host neither
solves business work nor supplies missing actions, tokens, rewards or classes.
"""

import argparse
import concurrent.futures
import hashlib
import json
import random
import time
from pathlib import Path

from model_development_experiment import now, resources, run_case
from proworksim.audit import code_identity
from proworksim.runtime import load_env
from proworksim.storage import atomic_write, json_bytes


def execute(protocol_path, destination):
    path, root = Path(protocol_path), Path(destination)
    protocol = json.loads(path.read_text())
    rows = protocol['episodes']
    if not rows or len({row['episode_name'] for row in rows}) != len(rows):
        raise ValueError('Freeze a nonempty distinct raw episode inventory')
    root.mkdir(parents=True, exist_ok=False)
    identity = code_identity()
    if identity['code_dirty'] and not protocol.get('development_pilot', False):
        raise ValueError('Formal collection requires clean committed source')
    shuffled = list(rows)
    random.Random(protocol['order_seed']).shuffle(shuffled)
    queues = {}
    for ordinal, row in enumerate(shuffled):
        queues.setdefault(row.get('execution_queue', row['backend']), []).append((ordinal, row))
    report = {
        'version': 'id-vtdo-model-batch-v0.12', 'source_before': identity,
        'started_at': now(), 'resource_before': resources(),
        'protocol_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'planned': len(rows), 'scope': protocol['scope'], 'cases': [],
        'randomized_admission_order': [r['episode_name'] for r in shuffled],
        'queue_rule': 'Sequential within each backend, independent backends concurrent. Completion times are not randomized. One shared local RNG, actual ledger retained.',
    }
    atomic_write(root / 'protocol.json', json_bytes(protocol))
    atomic_write(root / 'inventory.json', json_bytes(shuffled))
    start = time.monotonic()

    def backend_queue(pair):
        backend, queue = pair
        results = []
        for ordinal, row in queue:
            try:
                result = run_case(row, protocol, root)
            except Exception as error:
                result = {'episode_name': row['episode_name'], 'backend': row['backend'],
                          'status': 'experiment_error', 'error': {'type': type(error).__name__, 'message': str(error)}}
            result['admission_ordinal'] = ordinal
            result['inventory_row'] = row
            results.append(result)
            atomic_write(root / ('progress-' + backend + '.json'), json_bytes(results))
            print(json.dumps({'episode_name': row['episode_name'], 'status': result['status'],
                              'reward': result.get('reward', {}).get('reward'),
                              'model_meters': result.get('model_meters')}, ensure_ascii=False), flush=True)
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(queues)) as pool:
        for results in pool.map(backend_queue, queues.items()):
            report['cases'].extend(results)
    report['cases'].sort(key=lambda row: row['admission_ordinal'])
    report.update(ended_at=now(), elapsed_seconds=time.monotonic() - start,
                  source_after=code_identity(), resource_after=resources())
    report['status_counts'] = {name: sum(r['status'] == name for r in report['cases'])
                               for name in sorted({r['status'] for r in report['cases']})}
    report['completed_independent_correct'] = [r['episode_name'] for r in report['cases']
        if r['status'] == 'completed' and r.get('reward', {}).get('eligible') is True
        and r.get('reward', {}).get('reward') == 1]
    atomic_write(root / 'report.json', json_bytes(report))
    print(json.dumps({'recorded': len(report['cases']), 'status_counts': report['status_counts'],
                      'completed_independent_correct': report['completed_independent_correct']}), flush=True)
    if not protocol.get('development_pilot', False) and report['source_before'] != report['source_after']:
        raise RuntimeError('Source changed during formal collection; original results retained')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--env-file', default='.env')
    args = parser.parse_args()
    load_env(args.env_file)
    execute(args.protocol, args.output)


if __name__ == '__main__':
    main()
