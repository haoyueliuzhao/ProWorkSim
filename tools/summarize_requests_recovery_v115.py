"""Read recovery progress without mixing rescored candidates into new token means."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v115 as scope
from proworksim.software_benchmark_host_api_v115 import DeepSeekRuntime, budget_status
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v115-only-four-first-requests-report-r1'


def run(*, output=None):
    plan = scope.load(reference(scope.PLAN_FILE))
    path = scope.API_ROOT/'run-summary.json'
    summary = scope.load(reference(path)) if path.exists() else {}
    generation = summary.get('new_generation', {}).get('generation', {})
    if not generation:
        progress = scope.API_ROOT/'progress.json'
        if progress.exists():
            latest = scope.load(reference(progress))
            generation = latest.get('generation_queue', {}).get('generation', {})
    records = []
    for row in plan['generation_rows']:
        usage = DeepSeekRuntime.usage_for_slot(row)
        calls = usage['calls']
        state = generation.get(row['slot_id'], {}).get('status', 'pending')
        records.append({'slot_id': row['slot_id'], 'slot_index': row['slot_index'], 'arm': row['arm'],
            'generation_state': state, 'known_actual_tokens': sum(c['prompt_tokens']+c['completion_tokens'] for c in calls),
            'known_model_calls': len(calls), 'purpose_counts': dict(Counter(c['purpose'] for c in calls)),
            'usage_complete': usage.get('usage_capture_complete') is True,
            'uncertain_reserved_tokens': sum(c['reserved_tokens'] for c in usage['unresolved_calls']),
            'counts_as_new_generation': True})
    groups = {}
    for arm in ('REF', 'PROJECT'):
        items = [r for r in records if r['arm'] == arm]
        closed = [r for r in items if r['generation_state'] in {'closed', 'technical_unknown'} and r['usage_complete']]
        groups[arm] = {'planned_first_generations': len(items),
            'known_actual_tokens_lower_bound': sum(r['known_actual_tokens'] for r in items),
            'completed_usage_tasks': len(closed),
            'mean_actual_tokens_closed_subset': sum(r['known_actual_tokens'] for r in closed)/len(closed) if closed else None,
            'mean_actual_tokens_all_first_generations': sum(r['known_actual_tokens'] for r in items)/len(items)
                if items and len(items) == len(closed) else None}
    score_only = summary.get('recovered_scores', {})
    if not score_only:
        for spec in plan['score_recoveries']:
            saved = scope.API_ROOT/f"score-recovery-{spec['row']['slot_index']}.json"
            if saved.exists():
                score_only[spec['row']['slot_id']] = scope.load(reference(saved))
    result = {'version': VERSION, 'plan': reference(scope.PLAN_FILE), 'first_generations': records,
        'generation_groups': groups, 'preserved_candidate_scores': score_only,
        'planned_preserved_candidate_scores': len(plan['score_recoveries']),
        'old_generations_imported_as_new': 0, 'new_neutral_calls': 0,
        'cash': budget_status(), 'original_results_overwritten': False,
        'endpoint_rule': 'original_locked rescoring and recovered_stopped_code supplements remain separately labeled',
        'score_only_candidates_excluded_from_new_token_means': True,
        'model_calls_by_reporter': 0, 'Docker_operations': 0}
    target = Path(output) if output is not None else scope.API_ROOT/'reporting/summary.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(target, json_bytes(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    print(json.dumps(run(output=parser.parse_args().output), ensure_ascii=False))
