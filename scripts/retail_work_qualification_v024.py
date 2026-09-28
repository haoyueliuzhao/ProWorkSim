"""Read-only qualification of new material routes and v24 visible identifiers."""
import argparse
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes, read_json
from proworksim.templates import retail_collaboration_v024 as world


def reference(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': digest(path.read_bytes())}


def report(root, identity_root):
    root, identity_root = Path(root), Path(identity_root)
    source = read_json(root/'report.json')
    manifest = read_json(world.PIN_PATH)
    if source['source_manifest_sha256'] != digest(world.PIN_PATH.read_bytes()):
        raise ValueError('CPU source pin differs')
    controls = []
    for row in source['controls']:
        required = [t for t in row['token_lengths'] if t['action'] not in {'staff_done', 'staff_wait'}]
        controls.append({'case_id': row['case_id'], 'task': row['task'], 'known': row['score']['eligible'],
            'completed': row['score']['completed'], 'reward': row['score']['reward'],
            'role_decisions': row['program_decisions'], 'role_limits': row['role_limits'],
            'within_role_budgets': row['within_role_budgets'],
            'maximum_required_prompt_tokens': max(t['prompt_tokens'] for t in required),
            'required_actions_fit': all(t['fits_prompt_and_reserved_output'] and t['program_output_within_limit'] for t in required),
            'actual_context_refusals': row['context_rejected_requests'],
            'only_post_completion_stop_refused': all(t['action'] == 'staff_done' for t in row['context_rejected_requests']),
            'episode_reference': row['episode_reference']})
    a = read_json(identity_root/'final-hash17/report.json')['cases']
    b = read_json(identity_root/'final-hash29/report.json')['cases']
    ids = []
    for x, y in zip(a, b, strict=True):
        if x['case_id'] != y['case_id']:
            raise ValueError('Identity controls mismatched')
        same = {key: x[key] == y[key] for key in ('messages_sha256', 'tools_sha256', 'official_input_tokens_sha256', 'world_tool_calls_sha256', 'visible_runtime_id')}
        separate = {key: x['actual_identity'][key] != y['actual_identity'][key] for key in ('actual_run_id', 'actual_instance_id', 'actual_branch_id', 'storage_directory')}
        separate['episode_id'] = x['actual_episode_id'] != y['actual_episode_id']
        ix = f'case-{x["case_index"]:02d}/preparation.json'
        same['canonical_prepared_business_state'] = read_json(identity_root/'final-hash17'/ix)['prepared_business_state_sha256'] == read_json(identity_root/'final-hash29'/ix)['prepared_business_state_sha256']
        ids.append({'case_id': x['case_id'], 'case_index': x['case_index'], 'same': same, 'separate': separate,
                    'both_completed': all(z['score']['eligible'] and z['score']['completed'] for z in (x, y)),
                    'requests_per_process': x['requests'], 'messages_sha256': x['messages_sha256'],
                    'input_tokens_sha256': x['official_input_tokens_sha256'],
                    'passed': all(same.values()) and all(separate.values()) and all(z['score']['eligible'] and z['score']['completed'] for z in (x, y))})
    result = {'version': 'retail-work-qualification-v0.24', 'scope': 'CPU existence routes and deterministic host identifiers only; no model, teacher labels or learning evidence.',
        'model_calls': 0, 'gpu_calls': 0, 'parameter_updates': 0,
        'source_manifest': reference(world.PIN_PATH), 'catalog': reference(world.PIN_PATH.parent/'catalog.json'),
        'source': {'materials': len(manifest['slices']), 'customers': sum(len(s['customers']) for s in manifest['slices']),
            'complete_invoices': sum(len(s['invoice_ids']) for s in manifest['slices']), 'original_rows': sum(s['rows'] for s in manifest['slices']),
            'excluded_customers': len(manifest['excluded_customers']), 'excluded_invoices': len(manifest['excluded_invoices']),
            'excluded_source_rows': len(manifest['excluded_source_rows']), 'max_complete_invoice_rows': 3,
            'source_families': 1, 'source_independence_claim': False},
        'controls': controls, 'route_report': reference(root/'report.json'), 'identity_controls': ids,
        'identity_report_references': [reference(identity_root/f'final-hash{s}/report.json') for s in (17,29)],
        'hash_seeds': [17,29], 'context_capacity': 16384, 'reserved_output_tokens': 2048,
        'maximum_required_prompt_tokens': max(r['maximum_required_prompt_tokens'] for r in controls),
        'actual_post_completion_stop_refusals': sum(len(r['actual_context_refusals']) for r in controls),
        'limitations': ['finite hand-written program existence, not a model success probability or teacher corpus', 'only A and changed maintenance independently repeated across hash seeds; reference/version/permission and receipt forgery negatives covered separately by targeted tests', 'no cross-hardware generation bit-determinism claim', 'all source materials remain one UCI family'],
        'development_records_retained': ['runs/retail-work-v024-qualified', 'runs/retail-work-v024-identity/hash17', 'runs/retail-work-v024-identity/hash29', 'runs/retail-work-v024-identity/corrected-hash17', 'runs/retail-work-v024-identity/corrected-hash29', 'runs/retail-work-v024-identity/canonical-hash17', 'runs/retail-work-v024-identity/canonical-hash29']}
    result['passed'] = len(controls) == 14 and all(r['known'] and r['completed'] and r['within_role_budgets'] and r['required_actions_fit'] and r['only_post_completion_stop_refused'] for r in controls) and len(ids) == 2 and all(r['passed'] for r in ids)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='runs/retail-work-v024-native-qualified')
    p.add_argument('--identity-root', default='runs/retail-work-v024-identity')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    result = report(a.root, a.identity_root)
    atomic_write(Path(a.output), json_bytes(result))
    print({k: result[k] for k in ('passed', 'maximum_required_prompt_tokens', 'actual_post_completion_stop_refusals')})
    raise SystemExit(0 if result['passed'] else 1)
