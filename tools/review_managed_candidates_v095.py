"""Bounded offline review of the explicit historical managed-lock inventory."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_managed_recovery_v095 import ROOT, OUTPUT, recover


def review(index):
    try:
        existing = OUTPUT/str(index)/'recovered-result.json'
        ref = reference(existing) if existing.is_file() else recover(index)
        return {'slot_index': index, 'status': 'recovered_locked_candidate', 'recovered_result': ref}
    except Exception as error:
        return {'slot_index': index, 'status': 'requires_further_evidence_review',
                'error_type': type(error).__name__, 'reason': str(error)}


if __name__ == '__main__':
    source = ROOT/'artifacts/software-benchmark-v095/historical-exception-inventory-r1/candidate-review-handoff.json'
    handoff = json.loads(source.read_bytes())
    indices = [row['slot_index'] for row in handoff['candidate_rows']]
    rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {pool.submit(review, index): index for index in indices}
        for future in as_completed(pending):
            row = future.result()
            rows.append(row)
            print(json.dumps({'slot_index': row['slot_index'], 'status': row['status']}), flush=True)
    path = ROOT/'artifacts/software-benchmark-v095/candidate-recovery-batch-r1/summary.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    write_new(path, {'version': 'v095-explicit-historical-managed-candidate-review-r1',
        'inventory': reference(source), 'rows': sorted(rows, key=lambda r: r['slot_index']),
        'model_calls': 0, 'Docker_operations': 0, 'scoring_calls': 0,
        'old_results_overwritten': False, 'maximum_parallel_offline_reviews': 2})
