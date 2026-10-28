"""Read one combined progress view without double-counting the API handover."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
import json

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim.software_benchmark_deepseek_runtime_v066 import budget_status


def report():
    matrix = json.loads(policy.MATRIX_FILE.read_bytes())
    rows = {row['slot_id']: row for row in matrix['rows']}
    sources = {'QWEN': policy.COORDINATOR_RUN_ROOT,
               'DEEPSEEK': policy.ROOT / 'runs/software-benchmark-v067/api-continuation-r1/coordinator'}
    scopes, groups = {}, {}
    for model, folder in sources.items():
        progress = json.loads((folder / 'progress.json').read_bytes())
        cursor = json.loads((folder / 'cursor.json').read_bytes())
        groups_for_model = {key: value for key, value in matrix['groups'].items() if value['model_key'] == model}
        for key in groups_for_model:
            entries = {slot: value for slot, value in cursor['generation'].items()
                       if rows[slot]['group_id'] == key}
            active = [slot for slot in cursor['active_generation'] if rows[slot]['group_id'] == key]
            states = Counter(value['status'] for value in entries.values())
            entered = {slot for slot, value in entries.items() if value.get('entered') is True}
            entered.update(slot for slot in active if
                (policy.BATCH_ROOT / 'resource-claims' / f"actor-{rows[slot]['slot_index']}.json").exists())
            groups[key] = {'planned': 500, 'entered': len(entered),
                'generation_closed': states['closed'], 'technical_unknown': states['technical_unknown'],
                'active_or_waiting_generation': len(active), 'not_entered': 500-len(entered),
                'code_endpoints_recorded': sum(rows[slot]['group_id'] == key for slot in cursor['scores'])}
        scopes[model] = {'phase': progress['phase'], 'snapshot_unix': progress['unix'],
            'active_generation': progress.get('active_generation', 0),
            'active_grading': progress.get('active_grading', 0),
            'failure': progress.get('failure'),
            'provider_failures': progress.get('provider_failures', {}) if model == 'DEEPSEEK' else {},
            'reporting_root': str(folder)}
    totals = {key: sum(group[key] for group in groups.values()) for key in next(iter(groups.values()))}
    return {'version': 'v067-original-twelve-group-combined-progress-r1',
        'observed_at_Asia_Shanghai': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'scopes': scopes, 'groups': groups, 'totals': totals,
        'API_budget': budget_status(),
        'API_administrative_pause_in_primary_is_not_double_counted': True,
        'source_snapshots_are_not_a_single_atomic_cross_process_transaction': True,
        'code_endpoints_recorded_is_not_resolved_count_or_completion_rate': True}


if __name__ == '__main__':
    print(json.dumps(report(), ensure_ascii=False, indent=2))
