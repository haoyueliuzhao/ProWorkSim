"""Separate original pilot outcomes from stopped-code supplements; no reruns."""
from __future__ import annotations

import json
from pathlib import Path

from proworksim import software_benchmark_rescore_v145 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def summarize():
    original_ref = reference(scoring.previous.scope.API_ROOT/'task-outcomes.json')
    supplement_ref = reference(scoring.RUN/'summary.json')
    original = scoring.load(original_ref)['rows']
    supplement = scoring.load(supplement_ref)['outcomes']
    by_slot = {row['slot_index']: row for row in supplement}
    expected = {int(Path(r['generation_result']['path']).parent.name)
                for r in original if r['generation_status'] == 'technical_unknown'}
    if set(by_slot) != expected or len(supplement) != len(expected):
        raise ValueError('Every original unknown must occur exactly once in the supplemental record')
    rows = []
    for row in original:
        index = int(Path(row['generation_result']['path']).parent.name)
        extra = by_slot.get(index)
        valid = extra is not None and extra.get('status') == 'scored'
        if valid:
            receipt = scoring.load(extra['receipt'])
            request = scoring.load(extra['request'])
            identity = scoring.load(receipt['identity'])
            quiet_ref = reference(Path(request['directory'])/'quiescence.json')
            quiet = scoring.load(quiet_ref)
            if (receipt.get('status') != 'official_report' or type(receipt.get('resolved')) is not bool
                    or receipt.get('resolved') is not extra.get('resolved')
                    or identity.get('request') != extra['request']
                    or identity.get('candidate_lock') != request['candidate_lock']
                    or receipt.get('slot_id') != row['slot_id']
                    or receipt.get('endpoint') != 'recovered_stopped_code'
                    or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []):
                raise ValueError('Supplement lacks exact official identity or owned cleanup proof')
        rows.append({'slot_index': index, 'instance_id': row['instance_id'], 'group_id': row['group_id'],
            'original_generation_status': row['generation_status'], 'original_code': row['resolved'],
            'original_legal_delivery': row['legal_delivery'],
            'supplemental_code': extra.get('resolved') if valid else None,
            'supplemental_status': extra.get('status') if extra else 'not_applicable',
            'supplemental_receipt': extra.get('receipt') if extra else None,
            'measured_code': extra['resolved'] if valid else row['resolved'],
            'measurement_kind': 'recovered_stopped_code' if extra else 'original_final_code',
            'actual_tokens_known_lower_bound': row['actual_tokens_known'],
            'usage_complete': row['usage_complete']})
    groups = {}
    for group in ('S1','FREE2','REVIEW2'):
        items = [r for r in rows if r['group_id'] == group]
        measured = [r for r in items if type(r['measured_code']) is bool]
        complete_usage = [r for r in items if r['usage_complete']]
        groups[group] = {'planned': len(items),
            'original_normal_episodes': sum(r['original_generation_status'] == 'closed' for r in items),
            'original_generation_unknown_preserved': sum(r['original_generation_status'] == 'technical_unknown' for r in items),
            'original_code_passed': sum(r['original_code'] is True for r in items),
            'original_legal_delivery_passed': sum(r['original_legal_delivery'] is True for r in items),
            'supplemental_code_passed': sum(r['supplemental_code'] is True for r in items),
            'supplemental_code_failed': sum(r['supplemental_code'] is False for r in items),
            'code_measurements': len(measured),
            'code_passed_including_supplements': sum(r['measured_code'] is True for r in items),
            'code_rate_including_supplements': (sum(r['measured_code'] is True for r in items)/len(items)
                                               if len(measured) == len(items) else None),
            'actual_tokens_known_lower_bound': sum(r['actual_tokens_known_lower_bound'] for r in items),
            'complete_usage_episodes': len(complete_usage),
            'mean_tokens_complete_usage_only': sum(r['actual_tokens_known_lower_bound'] for r in complete_usage)/len(complete_usage),
            'mean_tokens_all_planned': (sum(r['actual_tokens_known_lower_bound'] for r in items)/len(items)
                                        if len(complete_usage) == len(items) else None)}
    return {'version': 'v145-original-and-stopped-code-separated-summary-r1',
        'original_outcomes': original_ref, 'supplemental_scoring': supplement_ref,
        'groups': groups, 'rows': rows, 'new_model_calls': 0,
        'original_results_rewritten': False, 'normal_generation_unknowns_removed': False,
        'code_comparison_requires_explicit_stopped_endpoint_label': True,
        'supplement_is_not_normal_completion_or_a_new_model_attempt': True}


if __name__ == '__main__':
    output = scoring.ROOT/'artifacts/software-benchmark-v145/recovery-results-r1'
    output.mkdir(parents=True, exist_ok=True)
    value = summarize()
    ref = write_new(output/'summary.json', value)
    print(json.dumps({'summary': ref, 'groups': value['groups']}, ensure_ascii=False, indent=2))
