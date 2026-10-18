"""Three new pure resume contracts; no old host/SDK/model controls are replayed."""
import copy

import pytest

from scripts import software_bridge_v052 as bridge
from scripts import software_bridge_v052_resume as resume


def original_rows():
    rows = []
    for index, task in enumerate(bridge.TASKS):
        order = ['OH_ref', 'PS1'] if index % 2 == 0 else ['PS1', 'OH_ref']
        for condition in order:
            rows.append({'slot_id': f'v052-{task}-{condition}', 'task_id': task, 'condition': condition,
                'seed': 202610180521 + index, 'first_member': 'member_001',
                'condition_order_for_task': order, 'generation_tokens': 500000,
                'decisions': 128, 'attempts': 128,
                'project_public_tests': 32 if condition == 'PS1' else None})
    return rows


def terminal_supervisor(rows):
    states = {}
    for index, row in enumerate(rows):
        name = row['slot_id']
        if name in resume.PENDING:
            states[name] = {'status': 'not_started', 'attempts': []}
        else:
            status = 'stopped' if name in resume.INTERRUPTED else 'complete'
            states[name] = {'status': status, 'attempts': [{'started_at': 1, 'ended_at': 2,
                'exit_code': -15 if status == 'stopped' else 0, 'output': '/synthetic/' + str(index)}]}
    return {'status': 'paused', 'ended_at': 3, 'states': states}


def test_original_three_only_excludes_every_entered_and_artifact_counterexample(tmp_path):
    rows = original_rows()
    supervisor = terminal_supervisor(rows)
    selected = resume.select_rows(rows, supervisor)
    assert tuple(row['slot_id'] for row in selected) == resume.PENDING
    assert not set(resume.INTERRUPTED) & {row['slot_id'] for row in selected}
    assert selected == rows[-3:]
    assert sum(row['generation_tokens'] for row in selected) == 1500000
    # A stopped sample cannot be renamed as fresh, even with empty attempts.
    bad = copy.deepcopy(supervisor)
    bad['states'][resume.INTERRUPTED[0]] = {'status': 'not_started', 'attempts': []}
    with pytest.raises(ValueError, match='exact original three'):
        resume.select_rows(rows, bad)
    bad = copy.deepcopy(supervisor)
    bad['states'][resume.INTERRUPTED[0]]['attempts'][0]['ended_at'] = None
    with pytest.raises(ValueError, match='incompletely closed'):
        resume.select_rows(rows, bad)
    resume.never_entered(tmp_path, selected)
    (tmp_path / 'slots' / resume.PENDING[0]).mkdir(parents=True)
    with pytest.raises(ValueError, match='execution artifacts'):
        resume.never_entered(tmp_path, selected)


def test_original_worker_code_private_namespaces_and_single_supervisor_literal():
    old_bridge_frozen = bridge.frozen
    old_completion = bridge.original_host.worker_completion
    old_classify = bridge.original_host.classify_closed
    old_limits = copy.deepcopy(bridge.LIMITS)
    worker, supervisor, proof, billing = resume.algorithm_binding()
    assert worker.__code__ is bridge.worker.__code__
    assert billing.__code__ is bridge.ledger.__code__
    assert worker.__globals__ is not bridge.__dict__
    assert worker.__globals__['frozen'] is resume.frozen
    assert worker.__globals__['CONTRACT'] == bridge.CONTRACT
    assert worker.__globals__['CONTRACT'] is not bridge.CONTRACT
    private_completion = supervisor.__globals__['worker_completion']
    assert private_completion.__code__ is old_completion.__code__
    assert private_completion.__globals__ is not bridge.original_host.__dict__
    assert private_completion.__globals__['classify_closed'] is bridge.classify_closed
    assert supervisor.__globals__['frozen'] is resume.frozen
    assert supervisor.__globals__['ledger'] is resume.ledger
    assert proof['changed_worker_module_literals'] == 1
    assert proof['worker_code_unchanged'] and proof['ledger_code_unchanged'] and proof['worker_completion_code_unchanged']
    assert proof['old_module_globals_modified'] is False
    assert bridge.frozen is old_bridge_frozen
    assert bridge.original_host.worker_completion is old_completion
    assert bridge.original_host.classify_closed is old_classify
    assert bridge.LIMITS == old_limits


def test_resume_release_budget_unknown_pause_and_initial_nulls(tmp_path):
    rows = original_rows()
    selected = resume.select_rows(rows, terminal_supervisor(rows))
    refs = {key: {'path': '/synthetic/' + key, 'sha256': key, 'bytes': 1} for key in resume.PREDECESSOR_KEYS}
    release = {'version': 'v052-bridge-resume-r1-release-v1', 'stage': resume.STAGE,
        'released': True, 'user_resume_authorized': True, 'unresolved_blockers': [],
        'checks': dict.fromkeys(resume.RELEASE_CHECKS, True), **refs,
        'selected_slot_ids': list(resume.PENDING), 'original_interrupted_remain_unknown': True,
        'exact_resume_state_available_for_interrupted': False, 'old_remaining_budget_transfer': 0,
        'resources': {'allowed_gpu_indices': list(range(8)), 'max_residents': 4, 'idle_only_admission': False},
        'signal_observation': {'scope': 'supervisor_only', 'follow_forks': False, 'worker_wrapped': False, 'restart': 'no'},
        'supporting_references': dict.fromkeys(('signal_observation_control', 'interruption_audit', 'partial_accounting_audit'), {})}
    resume.gates(release, refs)
    with pytest.raises(ValueError, match='explicit user-resume'):
        resume.gates({**release, 'user_resume_authorized': False}, refs)
    old = {key: {'synthetic': key} for key in resume.PRESERVED_KEYS}
    old.update(rows=rows, contract=copy.deepcopy(bridge.CONTRACT), limits=copy.deepcopy(bridge.LIMITS),
               source_files={'src/proworksim/example.py': 'original'}, source_commit={'code_commit': resume.ORIGINAL_COMMIT})
    plan = copy.deepcopy(old)
    plan.update(rows=selected, original_rows=rows, **resume.BOUND, old_remaining_budget_transfer=0,
        first_exposure_or_entered_retry_exceptions=False, interrupted_slots_remain_unknown=list(resume.INTERRUPTED),
        excluded_entered_slots=[row['slot_id'] for row in rows if row['slot_id'] not in resume.PENDING])
    resume.scientific_contract(plan, old, selected)
    for field, value in [('maximum_actual_tokens', 6000000), ('old_remaining_budget_transfer', 1),
                         ('source_files', {'src/proworksim/example.py': 'changed'})]:
        with pytest.raises(ValueError):
            resume.scientific_contract({**plan, field: value}, old, selected)
    initial = resume.ledger(tmp_path, selected)
    assert initial['logical_inventory'] == initial['new_inventory'] == 3
    assert initial['original_unique_inventory'] == 12
    assert initial['prior_costs_included'] is False
    assert all(row['R_code'] is row['Q_task_terminal'] is row['R_joint'] is None for row in initial['outcomes'])
    complete = resume.algorithm_binding()[1].__globals__['worker_completion']
    row = selected[-1]
    reference = {'path': '/synthetic/new-plan', 'sha256': 'new', 'bytes': 1}
    attempt = {'exit_code': 0, 'reason': None}
    report = {'status': 'closed', 'row': row, 'source_plan': reference, 'verdict': {'decision': 'continue'},
        'result': {'R_code': None, 'R_joint': None, 'project_delivery_endpoint': 'not_applicable'},
        'accounting': {'all_started_settled': True, 'integrity_errors': [], 'known_actual_tokens': 0},
        'guard': {'passed': True}, 'episode_guard': dict.fromkeys(
            ('learning_unchanged', 'rng_restored_exactly', 'software_binding_unchanged', 'actor_identity_unchanged'), True),
        'measurement': {'decision': 'pending'}}
    assert complete(row, attempt, report, plan_ref=reference, slot_started=True, cleanup_passed=True) == 'stopped'
    report['result']['R_code'] = 0
    report['result']['stop_reason'] = 'full_native_context_preexecution_rejection'
    report['measurement']['decision'] = 'continue'
    assert complete(row, attempt, report, plan_ref=reference, slot_started=True, cleanup_passed=True) == 'complete'
    assert complete(row, {'exit_code': -15, 'reason': None}, {}, plan_ref=reference,
                    slot_started=True, cleanup_passed=True) == 'stopped'
