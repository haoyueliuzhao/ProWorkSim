#!/usr/bin/env python3
"""Prepare public-only communication pilot drafts; never dispatch or authorize P1.

The strict 24/12/max2 request is impossible for Verified (Flask has one task).
This tool preserves that finding and a 1/3 alternative. An explicit user decision
may approve the already prepared alternative, without any execution authority.
Only historical request identities/statuses are read, never model scores/patches.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import random
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from proworksim.software_communication_pilot_v156 import (
    VERSION, CONDITIONS, COMPRESSOR_SETTINGS, PULL_SCHEMA, PROMPT_VERSIONS,
    PROMPT_SHA256, SYSTEM_PROMPTS,
)

SELECTION_SEED = 202611080156
ORDER_SEED = 202611080157
EPISODE_SEED = 2026110801560000
SOURCE = ROOT/'artifacts/software-benchmark-v054/source/public-tasks.json'
IDENTITIES = ROOT/'artifacts/software-benchmark-v054/manifests/identities.json'
PUBLIC_TESTS = ROOT/'config/v054-public-test-registry.json'
PREVIOUS_PANEL = ROOT/'artifacts/software-benchmark-v142/pilot-design-r1/panel.json'
LEDGER = ROOT/'runs/software-benchmark-v055/budget-r1/ledger.sqlite3'
SCORER = ROOT/'artifacts/software-benchmark-v054/scorer/installation-manifest-r5.json'
OUTPUT = ROOT/'artifacts/software-benchmark-v156/communication-design-r1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def record(path):
    raw = Path(path).read_bytes()
    return {'path': str(Path(path).resolve().relative_to(ROOT)), 'bytes': len(raw), 'sha256': digest(raw)}


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)+'\n')


def history_exposure(tasks):
    ids = {r['instance_id'] for r in tasks}
    matcher = re.compile('(?:'+'|'.join(re.escape(i) for i in sorted(ids, key=lambda i: (-len(i), i)))+r')(?!\d)')
    with sqlite3.connect('file:'+str(LEDGER)+'?mode=ro', uri=True) as db:
        rows = db.execute("SELECT DISTINCT slot_id FROM requests WHERE status IN ('settled','uncertain')").fetchall()
    seen = {m.group(0) for (slot,) in rows for m in matcher.finditer(slot or '')}
    # All 500 positive hits are sufficient; absence alone would not prove an
    # unexecuted task and would require additional indexes, not score inspection.
    return {'source': str(LEDGER.relative_to(ROOT)),
        'query': "SELECT DISTINCT slot_id FROM requests WHERE status IN ('settled','uncertain')",
        'columns_read': ['slot_id', 'status'], 'scores_or_patch_content_read': False,
        'positive_execution_identity_count': len(seen),
        'executed_task_ids': sorted(seen), 'unproven_task_ids': sorted(ids-seen),
        'all_public_pool_previously_exposed': seen == ids,
        'missing_identity_does_not_prove_unexecuted': True,
        'query_result_sha256': digest(json.dumps(sorted(seen), separators=(',', ':')).encode())}


def candidates(tasks, previous_ids, seen):
    """Seeded within-repo draws; prefer fewer exposures without using results."""
    by_repo = defaultdict(list)
    unique, duplicates = set(), []
    for row in sorted(tasks, key=lambda r: r['instance_id']):
        key = (row['repo'], row['base_commit'], digest(row['problem_statement'].encode()))
        if key in unique:
            duplicates.append(row['instance_id'])
            continue
        unique.add(key)
        by_repo[row['repo']].append(row)
    rng = random.Random(SELECTION_SEED)
    for repo in sorted(by_repo):
        rng.shuffle(by_repo[repo])
        # Stable sort preserves seeded random order inside each exposure stratum.
        by_repo[repo].sort(key=lambda r: (r['instance_id'] in seen, r['instance_id'] in previous_ids))
    return by_repo, duplicates


def make_draft(by_repo, registry, previous_ids, seen, *, alternative):
    allocation = {repo: min(2, len(rows)) for repo, rows in by_repo.items()}
    if alternative:
        eligible = sorted(repo for repo, rows in by_repo.items() if len(rows) >= 3)
        random.Random(SELECTION_SEED+1).shuffle(eligible)
        allocation[eligible[0]] += 1
    selected = {repo: rows[:allocation[repo]] for repo, rows in by_repo.items()}
    wave1 = [selected[repo][0] for repo in sorted(selected)]
    wave2 = [r for repo in sorted(selected) for r in selected[repo][1:]]
    rng = random.Random(ORDER_SEED)
    rng.shuffle(wave1); rng.shuffle(wave2)
    panels, schedule = [], []
    permutations = list(itertools.permutations(CONDITIONS))
    for wave, task_rows in enumerate((wave1, wave2), 1):
        orders = (permutations*2)[:len(task_rows)]
        rng.shuffle(orders)
        for position, (row, order) in enumerate(zip(task_rows, orders)):
            tid = row['instance_id']; public = registry[tid]
            index = len(panels); seed = EPISODE_SEED+index
            source_identity = public.get('source_identity', {})
            panels.append({**row, 'task_index': index, 'wave': wave,
                'wave_position': position, 'task_seed': seed, 'condition_order': list(order),
                'problem_statement_sha256': digest(row['problem_statement'].encode()),
                'historically_executed': tid in seen, 'in_v155_40_task_panel': tid in previous_ids,
                'public_test': {k: public[k] for k in ('source', 'cwd', 'argv', 'public_python', 'source_identity')},
                'actor_image_identity': source_identity.get('actor_image_id'),
                'task_specific_current_runtime_qualification': 'pending_P0_no_container_created'})
            for order_index, condition in enumerate(order):
                schedule.append({'logical_index': len(schedule), 'task_index': index, 'wave': wave,
                    'instance_id': tid, 'repo': row['repo'], 'condition': condition,
                    'condition_order_index': order_index, 'seed': seed, 'provider_seed_sent': False,
                    'slot_id': f'v156:{tid}:REVIEW2_{condition}:{seed}',
                    'fixed_members': ['member_001', 'member_002'], 'budget_tokens': 5_000_000,
                    'independent_initial_state': True})
    return {'version': VERSION+'-panel-draft',
        'status': 'pending_user_panel_choice_and_P0_admission', 'frozen_for_model_execution': False,
        'alternative': 'Flask1_one_other_repo3_others2' if alternative else 'strict_max2_23_tasks',
        'distinct_tasks': len(panels), 'repositories': len(selected),
        'repository_counts': allocation, 'waves': [
            {'wave': i, 'tasks': len(w), 'repositories': len({r['repo'] for r in w}),
             'condition_orders': dict(Counter('/'.join(x['condition_order']) for x in panels if x['wave'] == i))}
            for i, w in enumerate((wave1, wave2), 1)],
        'planned_team_episodes': len(schedule), 'planned_member_seats': 2*len(schedule),
        'generation_token_upper_bound': len(schedule)*5_000_000,
        'token_upper_bound_is_expected_consumption': False,
        'selection_seed': SELECTION_SEED, 'condition_order_seed': ORDER_SEED,
        'selection_uses_scores': False, 'independent_confirmation_set': False,
        'statistical_scope': 'historically exposed development panel; not an independent confirmation',
        'old_40_overlap': sum(r['in_v155_40_task_panel'] for r in panels),
        'historically_executed_selected': sum(r['historically_executed'] for r in panels),
        'constraints_not_met': (['per_repository_max_2', 'wave_2_covers_12_repositories'] if alternative
                                else ['24_distinct_tasks', 'two_waves_of_12_tasks', 'wave_2_covers_12_repositories']),
        'sources': {'public_tasks': record(SOURCE), 'public_identity': record(IDENTITIES),
                    'public_tests': record(PUBLIC_TESTS), 'prior_panel_identity': record(PREVIOUS_PANEL),
                    'scorer_installation_reference': record(SCORER)},
        'scorer_final_runtime_binding': 'pending_frozen_runner',
        'tasks': panels, 'rows': schedule, 'cash_budget_authorized': False,
        'real_model_calls': 0, 'containers_created': 0, 'training_steps': 0,
        'dispatch_enabled': False}


def prepare(output=OUTPUT):
    tasks = json.loads(SOURCE.read_text())
    source_identities = json.loads(IDENTITIES.read_text())
    registry = {r['instance_id']: r for r in json.loads(PUBLIC_TESTS.read_text())['entries']}
    previous = set(json.loads(PREVIOUS_PANEL.read_text())['task_ids'])
    history = history_exposure(tasks)
    seen = set(history['executed_task_ids'])
    by_repo, duplicate_ids = candidates(tasks, previous, seen)
    counts = {repo: len(rows) for repo, rows in sorted(by_repo.items())}
    maximum = sum(min(2, n) for n in counts.values())
    feasibility = {'version': VERSION+'-sampling-feasibility', 'source': source_identities['source'],
        'requested': {'distinct_tasks': 24, 'repositories': 12, 'maximum_per_repository': 2,
                      'waves': 2, 'tasks_per_wave': 12, 'repositories_per_wave': 12},
        'available_task_count': len(tasks), 'repository_counts': counts,
        'strict_requirements_feasible': maximum >= 24 and len(counts) >= 12,
        'maximum_tasks_under_per_repo_2': maximum, 'deduplicated_ids': duplicate_ids,
        'blocking_reason': 'SWE-bench Verified test has only one pallets/flask task among its 12 repositories.',
        'candidate_alternative': 'Flask1 + deterministic extra task from one repo + remaining repos2',
        'alternative_requires_user_choice': True, 'user_choice_received_by_this_preparer': False,
        'all_500_historically_executed': history['all_public_pool_previously_exposed'],
        'unexposed_confirmatory_sampling_available': False,
        'scope': 'public metadata and historical request identities only; no hidden repairs or outcomes'}
    config = {'version': VERSION, 'status': 'implementation_and_drafts_only',
        'organization': 'REVIEW2', 'members': {'member_001': 'developer_rework_final_delivery',
                                            'member_002': 'independent_reviewer'},
        'agent': {'model': 'deepseek-flash', 'thinking': False, 'temperature': 1.0, 'top_p': 1.0,
                  'context_tokens': 131072, 'max_input_tokens': 98304, 'max_output_tokens': 32768},
        'history': {'condenser': 'LLMSummarizingCondenser', 'max_size': 80, 'keep_first': 4},
        'team': {'total_input_plus_output_tokens': 5_000_000, 'http_attempts': 512,
                 'agent_decisions': 512, 'soft_seconds': 21600, 'hard_seconds': 23400,
                 'request_seconds': 1800, 'shared_single_pool_for': ['agent', 'condenser', 'compressor']},
        'compressor': {**COMPRESSOR_SETTINGS, 'max_physical_attempts_per_message': 3,
            'service_is_agent': False, 'output_schema': 'fact-ID selection only',
            'rendered_summary_tokens_max': 512, 'L0_outside_summary_limit_but_in_team_input': True,
            'critical_or_unknown_facts_never_dropped': True,
            'source_requires_trusted_complete_structured_fact_partition': True,
            'unstructured_source': 'raw_fallback', 'invalid_summary': 'raw_fallback_without_refund',
            'prompt_versions': PROMPT_VERSIONS, 'prompt_sha256': PROMPT_SHA256,
            'prompts': SYSTEM_PROMPTS, 'tools': []},
        'conditions': {'C0': 'raw; no compressor request', 'C1': 'generic structured extractive summary',
                       'C2': 'recipient-role selected L0+L1; L2/L3 explicit authorized pull'},
        'common_pull_schema': PULL_SCHEMA,
        'controlled_invariants': ['members', 'roles', 'routes', 'message_triggers', 'permissions',
                                 'history_summarizer', 'public_tests', 'candidate_lock', 'scorer'],
        'remaining_gates': ['user_sampling_choice', 'P0_integration_and_exact_source_token_controls',
                            'actual_payload_provenance', 'cash_budget', 'frozen_runtime_binding', 'P1_confirmation'],
        'P1_budget_CNY': None, 'real_transport_enabled': False, 'dispatch_enabled': False,
        'new_model_calls': 0, 'new_containers': 0, 'training_steps': 0}
    output = Path(output)
    dump(output/'feasibility.json', feasibility)
    dump(output/'history-exposure.json', history)
    dump(output/'strict-23-candidate.json', make_draft(by_repo, registry, previous, seen, alternative=False))
    draft = make_draft(by_repo, registry, previous, seen, alternative=True)
    dump(output/'recommended-24-candidate.json', draft)
    if (output/'approved-panel.json').exists():
        config['remaining_gates'].remove('user_sampling_choice')
        config['status'] = 'implementation_and_approved_public_panel_only'
        config['user_sampling_choice'] = 'approved: user-panel-decision.json'
    dump(output/'mechanism-config.json', config)
    return {'output': str(output), 'strict_feasible': feasibility['strict_requirements_feasible'],
            'strict_maximum': maximum, 'candidate_tasks': draft['distinct_tasks'],
            'candidate_repo_counts': draft['repository_counts'],
            'candidate_old40_overlap': draft['old_40_overlap'],
            'all_500_previously_executed': history['all_public_pool_previously_exposed'],
            'frozen_for_model_execution': False, 'model_calls': 0}


def approve_existing(output, decision_path):
    """Freeze only the existing candidate identities/order, never sample again."""
    output, decision_path = Path(output), Path(decision_path)
    decision = json.loads(decision_path.read_text())
    if (decision.get('selected_option') != 'Verified24_Flask1_one_other3_others2'
            or decision.get('user_quote_is_verbatim') is not True
            or not decision.get('user_quote') or not decision.get('question_item_id')):
        raise ValueError('A concrete explicit user sampling decision is required')
    candidate_path = output/'recommended-24-candidate.json'
    draft = json.loads(candidate_path.read_text())
    counts = draft['repository_counts']
    if (draft['distinct_tasks'] != 24 or len(draft['tasks']) != 24 or len(draft['rows']) != 72
            or counts.get('pallets/flask') != 1 or counts.get('psf/requests') != 3
            or sum(counts.values()) != 24 or sorted(counts.values()) != [1]+[2]*10+[3]):
        raise ValueError('The previously prepared Requests3 candidate has changed')
    if (len({r['instance_id'] for r in draft['tasks']}) != 24
            or draft['selection_seed'] != SELECTION_SEED or draft['condition_order_seed'] != ORDER_SEED):
        raise ValueError('Original candidate identities or seeds changed')
    projection = {k: draft[k] for k in ('tasks', 'rows', 'repository_counts', 'waves',
                                      'selection_seed', 'condition_order_seed', 'sources')}
    projection_hash = digest(json.dumps(projection, sort_keys=True, ensure_ascii=False,
                                       separators=(',', ':')).encode())
    approved = {**draft,
        'version': VERSION+'-approved-public-panel-r1', 'status': 'approved_panel_not_started',
        'public_task_identity_frozen': True, 'frozen_for_model_execution': False,
        'freeze_scope': ['public_task_identity', 'base_commit', 'issue_text', 'public_test_metadata',
                         'public_source_hashes', 'seeds', 'two_waves', 'condition_order'],
        'frozen_projection_sha256': projection_hash,
        'prepared_candidate': record(candidate_path), 'user_panel_decision': record(decision_path),
        'user_panel_decision_scope': 'sampling constraints only; no P1 cash or model dispatch authority',
        'approved_protocol_deviations': [
            'pallets/flask has one task; psf/requests has three; other ten repositories have two',
            'wave 1 covers 12 repositories; wave 2 covers 11 repositories, with two Requests tasks'],
        'unapproved_protocol_deviations': [],
        'historical_exposure': 'All 500 Verified tasks have prior settled/uncertain model request identities; '
                               'this is an exposed development pilot, not an independent confirmation.',
        'P0_admission_passed': False, 'cash_budget_authorized': False, 'cash_authority': None,
        'cash_budget_CNY': None, 'execution_status': 'not_started', 'dispatch_enabled': False,
        'real_model_calls': 0, 'containers_created': 0, 'training_steps': 0,
        'remaining_execution_gates': ['P0_actual_runtime_and_exact_provenance_admission',
                                     'cash_budget', 'frozen_runtime_binding', 'P1_confirmation']}
    path = output/'approved-panel.json'
    encoded = json.dumps(approved, ensure_ascii=False, sort_keys=True, indent=2)+'\n'
    if path.exists() and path.read_text() != encoded:
        raise ValueError('An approved public panel is immutable; use a new explicit version')
    if not path.exists():
        with path.open('x') as handle:
            handle.write(encoded)
    return {'approved_panel': record(path), 'frozen_projection_sha256': projection_hash,
            'execution_status': 'not_started', 'cash_authority': None, 'P0_admission_passed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--approve-decision', type=Path,
                        help='Approve the already prepared candidate; does not resample or authorize execution')
    args = parser.parse_args()
    result = approve_existing(args.output, args.approve_decision) if args.approve_decision else prepare(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
