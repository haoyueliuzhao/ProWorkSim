"""Seal only unused original identities and measurement recovery after v131 stops."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import subprocess
import time

from proworksim import software_benchmark_scope_v132 as scope
from proworksim import software_benchmark_scope_v131 as prior
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_host_api_v132 import ledger_witness, prepare_schemas


def stopped_owner():
    intent = scope.ROOT/'runs/software-benchmark-v132/quiesce-r1/stop-intent.json'
    identity = json.loads(intent.read_text())['before']
    result = subprocess.run(['systemctl', '--user', 'show', scope.API_UNIT,
        '--property=ActiveState,SubState,MainPID'], text=True, capture_output=True, timeout=15, check=True)
    unit = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if unit.get('ActiveState') != 'inactive' or unit.get('MainPID') != '0':
        raise RuntimeError('Wait for the original lifecycle and archive children to finish')
    proc = Path('/proc')/str(identity['pid'])/'stat'
    same = proc.exists() and proc.read_text().split(') ', 1)[1].split()[19] == identity['pid_start_ticks']
    if same or prior.LEASE_FILE.exists():
        raise PermissionError('Original manager process or accounting lease remains')
    closed = prior.API_ROOT/'run-summary.json'
    released = prior.API_ROOT/'coordinator-capacity-released.json'
    if not closed.exists() or not released.exists():
        raise PermissionError('Original coordinator has no completed administrative closure')
    extras = []
    for p in (prior.BATCH_ROOT/'resource-claims').glob('active-*.json'):
        claim = json.loads(p.read_text())
        if claim.get('key') != 'score-9000':
            extras.append(claim.get('key', p.name))
    if extras:
        raise PermissionError('Unresolved original live claims: '+repr(extras))
    return {'version': 'v132-original-owner-stopped-r1', 'unix': time.time(), 'unit': unit,
        'original_owner_absent': True, 'original_unit_inactive': True,
        'original_identity': identity, 'stop_intent': reference(intent),
        'original_summary': reference(closed), 'original_owner_release': reference(released),
        'pending_original_score_claim_retained': reference(
            scope.ROOT/'runs/software-benchmark-v132/parent-handoff-r1/score-9000-reserved.json')}


def prepare():
    if scope.CONTINUATION_FILE.exists() or scope.SOURCE_FILE.exists() or scope.AUTH_FILE.exists():
        raise ValueError('Prepared recovery identities are immutable; inspect an existing preparation')
    original_auth = prior.require_grading_allowed('v131.run')
    grant = scope.load(reference(scope.USER_GRANT_FILE))
    if grant.get('user_reply') != '授权受控停止并交接修复':
        raise PermissionError('Explicit controlled handoff consent required')
    stopped = stopped_owner()
    scope.STATE_ROOT.mkdir(parents=True, exist_ok=True)
    stop_ref = write_new(scope.STATE_ROOT/'original-owner-stopped.json', stopped)
    plan = prior.validate_plan(prior.load(reference(prior.PLAN_FILE)))
    eligible, originals, unclosed = [], [], []
    for row in plan['rows']:
        path = prior.BATCH_ROOT/'episodes'/str(row['slot_index'])/'result.json'
        if path.exists():
            originals.append({'row': row, 'result': reference(path)})
        elif scope.never_consumed(row):
            eligible.append(row)
        else:
            unclosed.append({'row': row, 'reason': 'physical_identity_consumed_without_final_result'})
    witnesses = {g: ledger_witness(g) for g in scope.GROUP_IDS}
    value = {'version': scope.VERSION, 'original_plan': reference(prior.PLAN_FILE),
        'eligible_first_generation': eligible, 'original_results': originals,
        'consumed_without_result': unclosed, 'ledger_baseline': witnesses,
        'original_owner_stopped': stop_ref, 'new_model_retries': 0,
        'original_generation_attempts_and_costs_preserved': True,
        'group_cash_CNY_unchanged': {g: 100 for g in scope.GROUP_IDS},
        'original_API_qualification': reference(prior.PREPARATION_QUALIFICATION_FILE),
        'original_environment_qualifications': reference(prior.API_ROOT/'qualification-status.json')}
    write_new(scope.CONTINUATION_FILE, value)
    schema_binding = prepare_schemas()
    from launch_fixed_organization_recovery_v132 import specification
    scope.API_ROOT.mkdir(parents=True, exist_ok=True)
    unit = write_new(scope.API_ROOT/'coordinator-unit.json',
        {**specification(), 'ownership_token': secrets.token_hex(16)})
    proposal = {'version': scope.VERSION, 'status': 'prepared_for_authorized_recovery',
        'user_grant': reference(scope.USER_GRANT_FILE), 'original_authorization': reference(prior.AUTH_FILE),
        'original_plan': reference(prior.PLAN_FILE), 'continuation': reference(scope.CONTINUATION_FILE),
        'unit': unit, 'eligible_first_generations': len(eligible), 'original_results': len(originals),
        'consumed_without_result': len(unclosed), 'generation_token_upper_bound': len(eligible)*5_000_000,
        'new_model_retries': 0, 'new_neutral_calls': 0, 'new_diagnostic_containers': 0,
        'new_environment_control_containers': 0, 'new_object_identity_allowance': 0,
        'cash_cap_CNY_by_group': {g: 100 for g in scope.GROUP_IDS},
        'original_uncertain_reservations_preserved': True, 'constraints': scope.CONSTRAINTS,
        'manager_memory_high_bytes': scope.API_MEMORY_HIGH_BYTES, 'manager_memory_max_bytes': scope.API_MEMORY_BYTES,
        'manager_CPU_quota_percent': 800, 'manager_new_lifecycle_same_unit': scope.API_UNIT,
        'aggregate_parent_reused': scope.CONTAINER_PARENT, 'new_system_slices': 0,
        'maximum_heavy_archive_workers': 2, 'maximum_async_graders': 2,
        'scoring_source': 'Original locked candidates only; no stopped-worktree substitution',
        'system_mount_network_driver_changes': False, 'other_users_objects_touched': False}
    scope.PROPOSAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_new(scope.PROPOSAL_FILE, proposal)
    paths = sorted(set(scope.ROOT.glob('src/proworksim/*v132.py')) |
                   set(scope.ROOT.glob('tools/*v132.py')))
    files = [reference(p) for p in paths]
    from proworksim import software_benchmark_sdk_bundle_v132 as bundle
    files += [reference(scope.CONTINUATION_FILE), unit, reference(scope.USER_GRANT_FILE),
              schema_binding, reference(bundle.OUTPUT/'manifest.json')]
    source = write_new(scope.SOURCE_FILE, {'version': scope.VERSION,
        'original_frozen_sources': reference(prior.SOURCE_FILE), 'files': files,
        'old_production_sources_unchanged': True})
    auth = {'version': scope.VERSION, 'status': 'approved',
        'user_grant': reference(scope.USER_GRANT_FILE), 'original_authorization': reference(prior.AUTH_FILE),
        'proposal': reference(scope.PROPOSAL_FILE), 'source_index': source,
        'continuation': reference(scope.CONTINUATION_FILE), 'plan': reference(prior.PLAN_FILE),
        'execution_alignment_version': original_auth['execution_alignment_version'],
        'constraints': scope.CONSTRAINTS, 'new_model_retries': 0,
        'interpretation': 'Explicit authorized controlled handoff, existing500CNY and original1006/251 identities only'}
    write_new(scope.AUTH_FILE, auth)
    return {'authorization': reference(scope.AUTH_FILE), 'sources': source,
            'eligible_first_generations': len(eligible), 'original_results': len(originals),
            'new_model_retries': 0, 'Docker_operations': 0, 'new_API_calls': 0}


if __name__ == '__main__':
    if os.getuid() == 0:
        raise PermissionError('Preparation is ordinary-user only')
    print(json.dumps(prepare(), ensure_ascii=False))
