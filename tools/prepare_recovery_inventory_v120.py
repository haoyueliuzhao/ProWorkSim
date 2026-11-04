"""Read-only v119 recovery inventory; no API, resource, scoring or ledger mutation."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT/'runs/software-benchmark-v118/project-repaired-r1'
OUTPUT = ROOT/'artifacts/software-benchmark-v120/recovery-inventory-r1'
LEDGER = ROOT/'runs/software-benchmark-v105/nonthinking-interface-r1/api-ledger.sqlite'
NEUTRAL = 'v118:neutral:project-tools:r1'


def read(path):
    return json.loads(Path(path).read_bytes())


def cny(amount):
    return str(Decimal(amount)/Decimal(1_000_000_000))


def main():
    if OUTPUT.exists():
        raise ValueError('Keep the first closed-run inventory immutable')
    plan_path = BATCH/'execution-plan-v119.json'
    summary_path = BATCH/'api-coordinator-v119/run-summary.json'
    plan, final = read(plan_path), read(summary_path)
    if (len(plan['rows']) != 50 or not final.get('finished_unix')
            or final.get('pending_grading_jobs') or final.get('retained_objects')):
        raise ValueError('Inventory needs the stopped original fifty-task queue')
    slots = {row['slot_id']: row for row in plan['rows']}
    with sqlite3.connect(LEDGER.as_uri()+'?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        db.row_factory = sqlite3.Row
        policy = json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
        records = [dict(row) for row in db.execute('SELECT request_id,slot_id,condition,usage_id,status,'
            'request_sha256,reserved_nanoyuan,settled_nanoyuan,usage_json,response_id,failure_json,'
            'prompt_upper_bound,max_output_tokens FROM requests ORDER BY request_id')]
    for item in records:
        item['usage'] = json.loads(item.pop('usage_json')) if item['usage_json'] is not None else None
        item['failure'] = json.loads(item.pop('failure_json')) if item['failure_json'] is not None else None
    by_slot = defaultdict(list)
    for item in records:
        by_slot[item['slot_id']].append(item)
    selected = [item for item in records if item['slot_id'] in slots or item['slot_id'] == NEUTRAL]
    active = sorted(str(path) for path in (BATCH/'resource-claims').glob('active-*.json'))
    owner_release = BATCH/'api-coordinator-v119/coordinator-capacity-released.json'
    if active or read(owner_release).get('released') is not True:
        raise ValueError('Owned resource records still show an active claim')
    rows = []
    for row in plan['rows']:
        index, slot = row['slot_index'], row['slot_id']
        folder = BATCH/'episodes'/str(index)
        result_path = folder/'result.json'
        result = read(result_path) if result_path.exists() else None
        provider = by_slot[slot]
        if any(call['condition'] != row['condition_id'] for call in provider):
            raise ValueError('Provider row belongs to another original condition')
        ledger_dir = folder/'controller-output/model-ledger'
        local_path = ledger_dir/'ledger.json'
        local = read(local_path) if local_path.exists() else None
        request_files = sorted(ledger_dir.glob('request-*.json'))
        response_files = sorted(ledger_dir.glob('response-*.json'))
        transport_path = folder/'model-transport.json'
        transport = read(transport_path) if transport_path.exists() else None
        claims, releases = {}, {}
        for role in ('actor', 'controller', 'volume'):
            claim = BATCH/'resource-claims'/f'{role}-{index}.json'
            release = BATCH/'resource-claims'/f'{role}-{index}.released.json'
            if claim.exists():
                claims[role] = reference(claim)
                if not release.exists() or read(release).get('claim') != claims[role]:
                    raise ValueError('An entered environment claim lacks its exact release')
                releases[role] = reference(release)
        quiet_path = folder/'quiescence.json'
        quiet = read(quiet_path) if quiet_path.exists() else None
        if claims and (quiet is None or quiet.get('quiescent') is not True
                       or quiet.get('cleanup_errors') or quiet.get('retained_objects')
                       or quiet.get('create_result_unknown') is not False):
            raise ValueError('An entered environment lacks trustworthy recorded cleanup')
        if provider:
            category = 'provider_attempt_consumed'
            if result is None or result.get('status') != 'technical_unknown':
                raise ValueError('Consumed failed attempts must retain their original result')
        elif claims:
            category = 'zero_provider_calls_environment_consumed'
            if (result is None or request_files or response_files
                    or local is not None and (local['attempts'] or local['decisions'] or local['calls'])
                    or transport is not None and (transport['generation_requests'] or transport['requests'])):
                raise ValueError('A zero-call classification lacks complete local/provider evidence')
        else:
            category = 'never_dispatched'
            if (result is not None or slot not in final['unentered_generation'] or local is not None
                    or request_files or response_files or (folder/'execution-intent.json').exists()):
                raise ValueError('A never-dispatched task already consumed a local attempt or environment')
        known = [call for call in provider if call['usage'] is not None]
        tokens = {key: sum(call['usage'][key] for call in known)
                  for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
        usage_complete = all(call['status'] == 'settled' and call['usage'] is not None for call in provider)
        rows.append({'row': row, 'classification': category,
            'original_generation_status': result['status'] if result else 'not_started',
            'original_result': reference(result_path) if result else None,
            'original_error': result.get('error') if result else None,
            'original_model_dispatch_started_flag': result.get('model_dispatch_started') if result else False,
            'provider_request_count': len(provider),
            'provider_settled_request_count': sum(call['status'] == 'settled' for call in provider),
            'provider_request_statuses': dict(Counter(call['status'] for call in provider)),
            'provider_request_ids': [call['request_id'] for call in provider],
            'usage_complete': usage_complete, 'known_tokens': tokens,
            'settled_cost_nanoyuan': sum(call['settled_nanoyuan'] or 0 for call in provider),
            'unresolved_reservation_nanoyuan': sum(call['reserved_nanoyuan'] for call in provider
                                                   if call['status'] != 'settled'),
            'controller_ledger': reference(local_path) if local else None,
            'controller_attempts': local.get('attempts') if local else None,
            'controller_decisions': local.get('decisions') if local else None,
            'controller_known_actual_tokens': local.get('known_actual_tokens') if local else None,
            'archived_request_files': len(request_files), 'archived_response_files': len(response_files),
            'transport': reference(transport_path) if transport else None,
            'transport_generation_requests': transport.get('generation_requests') if transport else None,
            'environment_claims_consumed': claims, 'environment_claims_released': releases,
            'recorded_created_and_removed_roles': quiet.get('removed_roles', []) if quiet else [],
            'quiescence': reference(quiet_path) if quiet else None,
            'eligible_for_first_provider_generation_after_new_version_freeze': not provider,
            'needs_new_physical_environment_keys': bool(claims) and not provider,
            'independent_model_retry_requires_explicit_authorization': bool(provider),
            'original_attempt_may_be_overwritten': False})
    qualifications = []
    for task, state in sorted(final['qualifications'].items()):
        value = json.loads(checked(state['qualification']).read_bytes())
        if state['status'] != 'qualified' or value.get('passed') is not True or value['instance_id'] != task:
            raise ValueError('The stopped run did not qualify every planned environment')
        qualifications.append({'instance_id': task, **state})
    if len(qualifications) != 50:
        raise ValueError('Do not shrink the fifty-task qualification panel')
    fresh_controls = []
    for task in ('psf__requests-1766', 'psf__requests-1921'):
        proof = next(x for x in qualifications if x['instance_id'] == task)
        qualified = json.loads(checked(proof['qualification']).read_bytes())
        for record in qualified['controls']:
            receipt, quiet = (json.loads(checked(record[key]).read_bytes()) for key in ('receipt', 'quiescence'))
            expected = record['patch_kind'] == 'gold'
            if (receipt.get('status') != 'official_report' or receipt.get('resolved') is not expected
                    or quiet.get('quiescent') is not True or quiet.get('cleanup_errors')):
                raise ValueError('A prior live TLS control is not a completed valid original control')
            fresh_controls.append({'instance_id': task, **record, 'resolved': expected})
    settled = sum(call['settled_nanoyuan'] or 0 for call in records)
    unresolved = [call for call in records if call['status'] != 'settled']
    committed = settled+sum(call['reserved_nanoyuan'] for call in unresolved)
    batch_settled = sum(call['settled_nanoyuan'] or 0 for call in selected)
    formal = [call for call in selected if call['slot_id'] in slots]
    auxiliary = [call for call in selected if call['slot_id'] == NEUTRAL]
    cash = {'formal_settled_CNY': cny(sum(call['settled_nanoyuan'] or 0 for call in formal)),
        'formal_unresolved_reserved_CNY': cny(sum(call['reserved_nanoyuan'] for call in formal if call['status'] != 'settled')),
        'preparation_settled_CNY': cny(sum(call['settled_nanoyuan'] or 0 for call in auxiliary)),
        'batch_settled_CNY': cny(batch_settled), 'cumulative_settled_CNY': cny(settled),
        'cumulative_unresolved_reserved_CNY': cny(sum(call['reserved_nanoyuan'] for call in unresolved)),
        'cumulative_committed_upper_CNY': cny(committed), 'cap_CNY': cny(policy['cap_nanoyuan']),
        'remaining_CNY': cny(policy['cap_nanoyuan']-committed),
        'reservation_is_actual_spend': False, 'old_uncertain_reservations_retained': True,
        'all_unresolved_requests': unresolved}
    counts = dict(Counter(row['classification'] for row in rows))
    assert counts == {'provider_attempt_consumed': 27, 'zero_provider_calls_environment_consumed': 4,
                      'never_dispatched': 19}, counts
    summary = {'version': 'v120-readonly-v119-recovery-inventory-r1',
        'recorded_utc': datetime.now(timezone.utc).isoformat(), 'classifications': counts,
        'planned_tasks': 50, 'first_generation_eligible': 23,
        'called_attempts_preserved_without_replay': 27,
        'formal_provider_requests': len(formal), 'formal_settled_requests': sum(r['status'] == 'settled' for r in formal),
        'formal_request_statuses': dict(Counter(r['status'] for r in formal)),
        'known_formal_tokens': {key: sum(row['known_tokens'][key] for row in rows)
                               for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
        'formal_scoring_requests': len(final.get('scores', {})), 'qualified_environments': len(qualifications),
        'completed_valid_TLS_controls': len(fresh_controls), 'active_resource_claims': active,
        'owner_released': reference(owner_release), 'cash': cash,
        'ledger_snapshot': {'path': str(LEDGER), 'read_only': True, 'query_only': True,
            'transaction': 'single read snapshot', 'all_request_rows': len(records),
            'records_sha256': digest(json_bytes(records)), 'selected_rows': len(selected)},
        'sources': {'plan': reference(plan_path), 'closed_coordinator_summary': reference(summary_path),
            'final_usage_summary': reference(BATCH/'api-coordinator-v119/actual-usage-summary.json'),
            'source': reference(__file__)},
        'no_new_runtime_authorization_granted': True, 'ledger_rows_changed': False,
        'original_results_changed': False, 'model_calls': 0, 'Docker_operations': 0}
    OUTPUT.mkdir(parents=True, exist_ok=False)
    write_new(OUTPUT/'ledger-rows.json', {'version': summary['version'], 'records': selected})
    write_new(OUTPUT/'qualifications.json', {'version': summary['version'], 'qualifications': qualifications,
        'completed_TLS_controls': fresh_controls, 'new_control_execution_required_by_this_inventory': False,
        'future_reuse_still_requires_exact_environment_and_source_binding': True})
    write_new(OUTPUT/'inventory.json', {'version': summary['version'], 'rows': rows})
    write_new(OUTPUT/'first-generation-eligible.json', {'version': summary['version'],
        'rows': [row for row in rows if row['eligible_for_first_provider_generation_after_new_version_freeze']],
        'new_model_generations_launched': 0})
    write_new(OUTPUT/'consumed-generation-hold.json', {'version': summary['version'],
        'rows': [row for row in rows if row['classification'] == 'provider_attempt_consumed'],
        'automatic_model_resampling_authorized': False})
    write_new(OUTPUT/'summary.json', summary)
    print(json.dumps({'summary': str(OUTPUT/'summary.json'), 'classifications': counts, 'cash': cash}, ensure_ascii=False))


if __name__ == '__main__':
    main()
