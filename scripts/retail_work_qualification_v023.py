"""Read-only aggregate of v0.23 actual CPU work-route qualification."""
import argparse
from collections import Counter
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.templates import retail_collaboration_v023 as world


def reference(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': digest(path.read_bytes())}


def report(root):
    root = Path(root)
    catalog, manifest = world.registry(), read_json(world.PIN_PATH)
    identity = read_json(root/'canonical-identity-report.json')
    identity_by_case = {r['case_id']: r for r in identity['cases']}
    controls = []
    for part in ('evaluation-ab', 'maintenance', 'training'):
        raw = read_json(root/part/'report.json')
        if raw['source_manifest_sha256'] != digest(world.PIN_PATH.read_bytes()):
            raise ValueError('CPU controls used different material source pin')
        for row in raw['controls']:
            case = world.case_spec(row['case_id'])
            index = next(i for i, c in enumerate(catalog['all_cases']) if c['case_id'] == case['case_id'])
            requests = read_json(root/part/f'case-{index:02d}'/'requests.json')
            import json
            attempts = dict(Counter(json.loads(r['messages'][-1]['content'])['observation']['actor_id'] for r in requests))
            lengths = row['token_lengths']
            rejected = row['context_rejected_requests']
            within = all(n <= case['role_decision_limits'][role] for role, n in attempts.items())
            canonical = identity_by_case[row['case_id']]['canonical_prepared_business_state_sha256']
            entry = {'case_id': row['case_id'], 'task': row['task'], 'material_sha256': case['material_sha256'],
                     'purpose': case['purpose'], 'prepared_submission': case['prepared_submission'],
                     'maintenance_condition': case['maintenance'], 'completed': row['score']['completed'],
                     'known': row['score']['eligible'], 'reward': row['score']['reward'],
                     'generation_opportunities_used_by_program': row['program_decisions'],
                     'request_attempts_including_actual_context_refusals': attempts, 'role_limits': case['role_decision_limits'],
                     'within_role_budgets': within,
                     'maximum_executed_prompt_tokens': max(t['prompt_tokens'] for t in lengths if t['fits_prompt_and_reserved_output']),
                     'maximum_required_business_action_prompt_tokens': max(t['prompt_tokens'] for t in lengths if t['action'] not in {'staff_wait', 'staff_done'} and t['fits_prompt_and_reserved_output']),
                     'maximum_program_output_tokens': max(t['program_output_tokens'] for t in lengths),
                     'post_completion_context_refusals': [{'role': t['role'], 'action': t['action'], 'prompt_tokens': t['prompt_tokens']} for t in rejected],
                     'only_nonessential_stop_requests_refused': all(t['action'] == 'staff_done' for t in rejected),
                     'canonical_prepared_business_state_sha256': canonical,
                     'legacy_order_sensitive_prepared_sha256': row['prepared_business_state_sha256'],
                     'policy_identities_sha256': row['policy_identities_sha256'],
                     'control_reference': reference(root/part/f'case-{index:02d}'/'control.json'),
                     'episode_reference': row['episode_reference']}
            entry['passed'] = bool(entry['known'] and entry['completed'] and within and entry['only_nonessential_stop_requests_refused'])
            controls.append(entry)
    negatives = read_json(root/'negative-controls/report.json')
    receipts = read_json(root/'maintenance-receipt-registration.json')
    result = {'version': 'retail-work-qualification-v0.23', 'scope': 'CPU actual WorldCore/native tools/compact/official tokenizer existence witnesses, never model generation, training labels or method support.',
              'model_calls': 0, 'gpu_calls': 0, 'parameter_updates': 0, 'api_cost_usd': 0,
              'source_pin': reference(world.PIN_PATH), 'catalog': reference(world.PIN_PATH.parent/'catalog.json'),
              'source': {'source_families': 1, 'new_materials': len(manifest['slices']),
                         'new_customers': sum(len(s['customers']) for s in manifest['slices']),
                         'complete_invoices': sum(len(s['invoice_ids']) for s in manifest['slices']),
                         'original_rows': sum(s['rows'] for s in manifest['slices']),
                         'excluded_old_customers': len(manifest['excluded_customers']),
                         'excluded_old_invoices': len(manifest['excluded_invoices']),
                         'excluded_old_rows': len(manifest['excluded_source_rows']),
                         'maximum_rows_per_complete_invoice': 3,
                         'scope': 'Small complete-invoice material within the same UCI source, not independent source generalization.'},
              'controls': controls, 'positive_cases': len(controls), 'passed_positive_cases': sum(r['passed'] for r in controls),
              'maximum_required_business_action_prompt_tokens': max(r['maximum_required_business_action_prompt_tokens'] for r in controls),
              'maximum_successful_request_prompt_tokens': max(r['maximum_executed_prompt_tokens'] for r in controls),
              'context_capacity': 16384, 'reserved_output_tokens': 2048,
              'actual_post_completion_context_refusals': sum(len(r['post_completion_context_refusals']) for r in controls),
              'context_limit_interpretation': 'Every required business action passed prompt+2048<=16384. Extra staff_done requests after work completion were actually refused by the same token rule and never executed. They remain visible; this does not guarantee arbitrary model routes fit or find the witness.',
              'negative_controls': [{'case_id': r['case_id'], 'control': r['control'], 'known': r['score']['eligible'], 'completed': r['score']['completed'], 'reward': r['score']['reward'], 'passed': r['negative_control_passed'], 'episode_reference': r['episode_reference']} for r in negatives['controls']],
              'negative_report': reference(root/'negative-controls/report.json'),
              'repeated_initial_state_and_policy': reference(root/'canonical-identity-report.json'),
              'identity_cases': len(identity['cases']),
              'canonical_hash_correction': 'Mapping key order only. Actual independently built snapshots compare equal with all fields after the original documented diagnostics normalization, and immutable file bytes remain exact. Old JSON-order-sensitive hashes and raw controls are retained. No world action or score was replayed or backfilled.',
              'receipt_profile_checks': reference(root/'maintenance-receipt-registration.json'),
              'rejected_preflight_artifacts': ['runs/retail-work-v023-initial', 'runs/retail-work-v023-corrected', 'runs/retail-work-v023-tokenizer', 'runs/assets/uci-collaboration-v023-initial-max10'],
              'protocol_limits': ['finite preparation followed by a real policy event, not a full continuous company lifecycle', 'prepared old correct delivery earns no current credit', 'quality labels and CPU witness programs never enter the model observation or training dataset', 'one successful existence path, not shortest path or target-model success evidence', 'two repetitions remain one exact situation, not independent tasks']}
    result['passed'] = bool(len(controls) == 28 and all(r['passed'] for r in controls) and negatives['passed'] and identity['passed'] and receipts['passed'])
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='runs/retail-work-v023-qualified')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    r = report(a.root)
    atomic_write(Path(a.output), json_bytes(r))
    print({'passed': r['passed'], 'positive': r['passed_positive_cases'], 'negative': len(r['negative_controls']), 'repeat_identity': r['identity_cases']})
    raise SystemExit(0 if r['passed'] else 1)
