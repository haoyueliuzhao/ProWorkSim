"""Prepare and export the 21 sole stopped pilot candidates; no API or Docker."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import resource
import time

from proworksim import software_benchmark_stopped_recovery_v145 as recovery


def prepare():
    plan_ref = recovery.reference(recovery.BATCH/'deployment-v143/execution-plan.json')
    rows = [r for r in recovery.load(plan_ref)['rows'] if r['slot_index'] in recovery.TASKS]
    usage = recovery.provider_usage(rows)
    inventory = []
    for row in rows:
        folder = recovery.BATCH/'episodes'/str(row['slot_index'])
        result_ref = recovery.reference(folder/'result.json')
        result = recovery.load(result_ref)
        transfer = recovery.load(result['controller_output_transfer'])
        recovery.validate_original(row, result, recovery.load(result['writer_quiescence']),
            recovery.load(result['quiescence']), transfer, recovery.load(result['interrupted_worktree']),
            recovery.load(recovery.reference(folder/'baseline-snapshot-provenance.json')))
        child = recovery.load(result['controller_result'])
        actions = child.get('managed_boundary', {}).get('outcomes', [])
        selected_actions = Counter()
        for action in actions:
            name = action.get('decision', {}).get('action')
            if name in {'run_tests', 'fix_patch', 'submit_integration'} and action.get('response', {}).get('ok') is True:
                selected_actions[name] += 1
        blob = transfer['archive_storage']['blob']
        if Path(blob['path']).stat().st_size != blob['bytes']:
            raise ValueError('Retained controller archive size changed')
        inventory.append({'row': row, 'original_result': result_ref,
            'original_generation_status': result['status'], 'controller_archive': blob,
            'original_archive_roundtrip_verified': transfer['archive_storage']['round_trip_verified'],
            'new_full_archive_verification_pending': True,
            'unique_original_candidate_lock': result.get('candidate_lock'),
            'fixed_private_sessions': child.get('private_sessions'),
            'successful_public_actions': dict(selected_actions), 'provider_usage': usage[row['slot_index']],
            'supplemental_selection_rule': 'Only the committed member_001 current_version in the stopped controller world',
            'actor_test_tree_is_candidate': False, 'original_session_resume_proven': False,
            'new_api_calls': 0, 'new_scoring_calls': 0, 'original_records_modified': False})
    value = {'version': recovery.VERSION, 'created_unix': time.time(), 'source': recovery.reference(__file__),
        'recovery_module': recovery.reference(recovery.__file__), 'plan': plan_ref, 'rows': inventory,
        'count': len(inventory), 'original_technical_unknown_preserved': True,
        'new_model_attempts': 0, 'new_containers': 0, 'new_host_configuration': False}
    recovery.AUDIT.mkdir(parents=True, exist_ok=True)
    return recovery.write_new(recovery.AUDIT/'inventory.json', value)


def recover_all(inventory_ref):
    inventory = recovery.load(inventory_ref)
    if inventory['recovery_module'] != recovery.reference(recovery.__file__):
        raise ValueError('Prepared recovery implementation changed')
    receipts = []
    for item in inventory['rows']:
        row = item['row']
        index = row['slot_index']
        result = recovery.recover(index, item['provider_usage'])
        receipts.append({'slot_index': index, 'group_id': row['group_id'], 'result': result})
        print(json.dumps(receipts[-1], ensure_ascii=False), flush=True)
    return recovery.write_new(recovery.AUDIT/'export-results.json', {
        'version': recovery.VERSION, 'inventory': inventory_ref, 'finished_unix': time.time(),
        'results': receipts, 'new_api_calls': 0, 'new_scoring_calls': 0,
        'original_generation_statuses_changed': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recover-all', action='store_true')
    args = parser.parse_args()
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Ordinary user only')
    os.nice(10)
    available = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, available[:2])
    resource.setrlimit(resource.RLIMIT_AS, (16*1024**3, 16*1024**3))
    inventory_ref = prepare()
    print(json.dumps({'inventory': inventory_ref}), flush=True)
    if args.recover_all:
        print(json.dumps({'export_results': recover_all(inventory_ref)}), flush=True)
