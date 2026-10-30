"""Read-only, slot-deduplicated accounting of original and independent recovery cohorts."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'artifacts/software-benchmark-v102/deepseek-final-accounting-r1'
SOURCES = {
    'original_panel': 'runs/software-benchmark-v088/api-select-recovery-r1/api-coordinator/run-summary.json',
    'independent_generation': 'runs/software-benchmark-v094/physical-startup-recovery-r1/api-coordinator/run-summary.json',
    'rescore45': 'runs/software-benchmark-v095/core-rescore-final-r1/coordinator/run-summary.json',
    'recovered25': 'runs/software-benchmark-v098/recovered-candidates-r1/coordinator/run-summary.json',
    'rescore2': 'runs/software-benchmark-v099/two-task-rescore-r1/completed.json',
    'original_plan': 'runs/software-benchmark-v064/full-verified-r1/plan.json',
    'independent_plan': 'runs/software-benchmark-v094/physical-startup-recovery-r1/execution-plan.json',
}
_CACHE = {}


def reference(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def load(ref):
    identity = (ref['path'], ref['sha256'], ref['bytes'])
    if identity not in _CACHE:
        body = Path(ref['path']).read_bytes()
        if len(body) != ref['bytes'] or hashlib.sha256(body).hexdigest() != ref['sha256']:
            raise ValueError('Immutable evidence changed: '+ref['path'])
        _CACHE[identity] = json.loads(body)
    return _CACHE[identity]


def official(request_ref):
    request = load(request_ref)
    folder = Path(request['directory'])
    path = folder/'receipt.json'
    if not path.exists():
        return None
    receipt_ref = reference(path)
    receipt = load(receipt_ref)
    if receipt.get('status') != 'official_report':
        if receipt.get('resolved') is not None:
            raise ValueError('Unknown scoring cannot contain a claimed normal verdict')
        return None
    identity = load(receipt['identity'])
    quiet_ref, completion_ref = reference(folder/'quiescence.json'), reference(folder/'completion.json')
    quiet, completion = load(quiet_ref), load(completion_ref)
    task, slot = request['instance_id'], request['slot_id']
    report = receipt['official_result'][1][task]
    if (type(receipt.get('resolved')) is not bool or receipt.get('slot_id') != slot
            or receipt.get('resource_key') != request['resource_key'] or identity.get('request') != request_ref
            or any(identity.get(key) != request.get(key) for key in (
                'slot_id', 'configuration', 'candidate_lock', 'plan', 'scorer_manifest'))
            or report.get('resolved') is not receipt['resolved']
            or report.get('patch_successfully_applied') is not True or report.get('infra_failure', False)
            or completion.get('returncode') != 0 or quiet.get('quiescent') is not True
            or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False):
        raise ValueError('Official verdict lacks exact candidate identity or trustworthy completion: '+slot)
    return {'status': 'resolved' if receipt['resolved'] else 'unresolved', 'resolved': receipt['resolved'],
        'request': request_ref, 'receipt': receipt_ref, 'identity': receipt['identity'],
        'completion': completion_ref, 'quiescence': quiet_ref,
        'candidate_lock': request['candidate_lock'], 'generation_result': request['generation_result']}


def same_tree(code_lock, delivery_lock):
    left, right = load(code_lock), load(delivery_lock)
    if (left.get('tree_sha256') != right.get('tree_sha256')
            or left['patch_receipt']['base_tree_sha256'] != right['patch_receipt']['base_tree_sha256']):
        raise ValueError('Delivery reuse changed the code version')


def delivery(row, record, *, provenance, historical=False):
    if row['arm'] != 'PROJECT':
        raise ValueError('REF cannot acquire project delivery')
    source = load(record['receipt']) if historical else record
    status = source['status']
    if source.get('slot_id', row['slot_id']) != row['slot_id']:
        raise ValueError('Delivery belongs to a different attempt')
    if status == 'same_tree_official_result_reused':
        same_tree(source['code_candidate_lock'], source['delivery_candidate_lock'])
        if (row['code']['status'] not in {'resolved', 'unresolved'}
                or source.get('resolved') is not row['code']['resolved']
                or historical and source.get('code_scoring_receipt') != row['code']['receipt']):
            raise ValueError('Delivery does not reuse its own exact code verdict')
        proof = source.get('proof', {})
        if not historical and (proof.get('submitted') is not True or proof.get('same_tree') is not True):
            raise ValueError('Recovered delivery lacks verified same-version proof')
        row['delivery'] = {'status': row['code']['status'], 'resolved': row['code']['resolved'],
            'kind': status, 'evidence': provenance, 'code_receipt': row['code']['receipt']}
    elif status == 'no_legal_delivery':
        if source.get('resolved') is not False or historical and source.get('legal_submission') is not False:
            raise ValueError('Absent legal delivery is incorrectly recorded')
        row['delivery'] = {'status': 'unresolved', 'resolved': False, 'kind': status, 'evidence': provenance}
    else:
        row['delivery'] = {'status': 'technical_unknown', 'resolved': None, 'kind': status, 'evidence': provenance}


def stats(rows):
    by_arm = {}
    for arm in ('REF', 'PROJECT'):
        chosen = [r for r in rows if r['arm'] == arm]
        counts = Counter(r['code']['status'] for r in chosen)
        known = counts['resolved']+counts['unresolved']
        unresolved = counts['technical_unknown']+counts['not_started']
        value = {'planned': len(chosen), 'code_resolved': counts['resolved'], 'code_unresolved': counts['unresolved'],
            'code_technical_unknown': counts['technical_unknown'], 'not_started': counts['not_started'],
            'code_known': known, 'confirmed_success_fraction_of_plan': counts['resolved']/len(chosen),
            'known_subset_success_rate_diagnostic_only': counts['resolved']/known if known else None,
            'possible_full_panel_rate_interval': [counts['resolved']/len(chosen),
                (counts['resolved']+unresolved)/len(chosen)],
            'full_panel_point_estimate_available': unresolved == 0}
        if arm == 'PROJECT':
            d = Counter(r['delivery']['status'] for r in chosen)
            value['delivery'] = {'resolved': d['resolved'], 'unresolved': d['unresolved'],
                'technical_unknown': d['technical_unknown'], 'not_started': d['not_started'],
                'no_legal_delivery': sum(r['delivery'].get('kind') == 'no_legal_delivery' for r in chosen),
                'confirmed_delivery_fraction_of_plan': d['resolved']/len(chosen)}
        else:
            value['delivery'] = None
        by_arm[arm] = value
    return by_arm


def run():
    refs = {key: reference(ROOT/path) for key, path in SOURCES.items()}
    sources = {key: load(ref) for key, ref in refs.items()}
    original = sources['original_panel']
    all_rows = {r['slot_id']: r for r in sources['original_plan']['rows']}
    if len(original['generation']) != 1000:
        raise ValueError('The original panel denominator changed')
    panel = {}
    for slot, value in original['generation'].items():
        r = all_rows[slot]
        if r['model_key'] != 'DEEPSEEK' or r['input_plus_output_tokens'] != 5_000_000 or r['replicate'] != 0:
            raise ValueError('This accounting includes only original DeepSeek 5M first runs')
        state = 'not_started' if value['status'] == 'not_started' else 'technical_unknown'
        panel[slot] = {key: r[key] for key in ('slot_id', 'slot_index', 'instance_id', 'repo', 'condition_id', 'arm', 'seed')}
        panel[slot].update(original_generation_status=value['status'], original_generation_record=value,
            cohort='original_panel', code={'status': state, 'resolved': None},
            delivery={'status': state, 'resolved': None} if r['arm'] == 'PROJECT' else None)
    for slot, value in original['scores'].items():
        result = official(value['request'])
        if result:
            panel[slot]['code'] = {**result, 'source_batch': 'original_panel'}
    for slot, value in original['deliveries'].items():
        delivery(panel[slot], value, provenance=value['receipt'], historical=True)
    before = stats(list(panel.values()))
    independently_planned = {r['slot_id']: r for r in sources['independent_plan']['rows']}
    if len(independently_planned) != 44 or set(independently_planned) & set(panel):
        raise ValueError('Independent attempts must retain separate, non-overlapping identities')
    independent = {}
    for slot, r in independently_planned.items():
        if r['original_slot_id'] not in panel:
            raise ValueError('Recovery lacks its original administrative-cutoff mapping')
        independent[slot] = {key: r[key] for key in ('slot_id', 'slot_index', 'instance_id', 'repo', 'condition_id', 'arm', 'seed', 'original_slot_id')}
        independent[slot].update(cohort='independent_recovery_attempt',
            original_generation_status=sources['independent_generation']['generation'][slot]['status'],
            code={'status': 'technical_unknown', 'resolved': None},
            delivery={'status': 'technical_unknown', 'resolved': None} if r['arm'] == 'PROJECT' else None)
    upgrades = []
    for batch in ('rescore45', 'recovered25'):
        source = sources[batch]
        if source['not_started'] or source['shared_failure']:
            raise ValueError('Expected finished original-candidate rescoring')
        for key, value in source['results'].items():
            slot = value['slot_id']
            row = independent.get(slot) or panel.get(slot)
            if row is None or row['code']['status'] in {'resolved', 'unresolved'}:
                raise ValueError('An attempt is absent or already has a trustworthy official result')
            result = official(value['completion']['request'])
            if result is None or result['resolved'] is not value['official']['resolved']:
                raise ValueError('A rescoring summary is not backed by its official receipt')
            row['code'] = {**result, 'source_batch': batch}
            evidence = reference(Path(refs[batch]['path']).parent/(key+'.json'))
            if row['arm'] == 'PROJECT':
                delivery(row, value['delivery'], provenance=evidence)
            upgrades.append({'slot_id': slot, 'cohort': row['cohort'], 'batch': batch,
                'official_resolved': result['resolved'], 'source': evidence})
    for value in sources['rescore2']['outcomes']:
        request_ref = value['candidate_request']
        request = load(request_ref)
        row = panel[request['slot_id']]
        if row['code']['status'] in {'resolved', 'unresolved'}:
            raise ValueError('A completed original score cannot be selected again')
        result = official(request_ref)
        if result is None or result['resolved'] is not value['resolved']:
            raise ValueError('Two-task environment repair lacks trustworthy candidate result')
        qualification = load(value['qualification'])
        if qualification.get('passed') is not True:
            raise ValueError('Revised environment was not qualified')
        row['code'] = {**result, 'source_batch': 'rescore2', 'new_environment_qualification': value['qualification']}
        upgrades.append({'slot_id': row['slot_id'], 'cohort': row['cohort'], 'batch': 'rescore2',
            'official_resolved': result['resolved'], 'source': value['receipt']})
    if (len({x['slot_id'] for x in upgrades}) != 72
            or sum(x['cohort'] == 'original_panel' for x in upgrades) != 28
            or Counter(r['arm'] for r in panel.values()) != {'REF': 500, 'PROJECT': 500}
            or len({r['instance_id'] for r in panel.values()}) != 500):
        raise ValueError('Candidate/attempt deduplication or complete panel coverage failed')
    summary = {'version': 'v102-original-panel-and-independent-recovery-accounting-r1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'sources': refs,
        'original_panel_before_repairs': before, 'original_panel_after_candidate_repairs': stats(list(panel.values())),
        'independent_recovery_44': stats(list(independent.values())),
        'verified_official_original_results_before_repairs': 719,
        'new_score_receipts_verified': len(upgrades), 'original_panel_upgrades': 28,
        'independent_attempts_not_merged_into_original_panel': 44,
        'original_attempt_restored_candidates': 25, 'original_completed_score_unknowns_repaired': 3,
        'logical_task_count': 500, 'planned_original_attempts': 1000,
        'remaining_original_generation_unknown': 224, 'remaining_original_not_started': 29,
        'full_panel_denominator_preserved': True, 'all_slots_unique_within_cohort': True,
        'whole_archive_revalidation_or_tests_performed': False, 'model_calls': 0, 'Docker_operations': 0,
        'old_records_overwritten': False, 'statistics_source': reference(__file__),
        'measurement_limits': [
            'Known-subset rates are diagnostic, not the complete benchmark success rate.',
            'Technical unknown and not-started slots are not ordinary model failures.',
            'Independent recovery attempts use new model calls and never replace original first-run results.',
            'Same-tree delivery uses the already validated identical code candidate; absent legal delivery remains false.',
            'The two v099 scores use separately qualified environment-mechanism revisions, retained per row.']}
    OUTPUT.mkdir(parents=True, exist_ok=False)
    for name, value in [('summary.json', summary), ('original-panel-1000.json', list(panel.values())),
                        ('independent-recovery-44.json', list(independent.values())), ('score-upgrades-72.json', upgrades)]:
        with (OUTPUT/name).open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps({'summary': reference(OUTPUT/'summary.json'), 'original_panel': summary['original_panel_after_candidate_repairs'],
        'independent': summary['independent_recovery_44']}, ensure_ascii=False))


if __name__ == '__main__':
    run()
