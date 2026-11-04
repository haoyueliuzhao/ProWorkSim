"""File-evidence gate: never overlap independent recovery with the v121 owner.

No Docker/service query or mutation is performed. A completion receipt can be
prepared only after every prior task and scoring job is terminal and all owned
resources have trustworthy cleanup plus an owner release.
"""
from __future__ import annotations

from pathlib import Path

from . import software_benchmark_scope_v123 as scope
from .software_benchmark_candidates_v054 import reference

VERSION = 'v123-prior-v121-completion-gate-r1'
TERMINAL_GENERATION = {'closed', 'technical_unknown', 'not_started', 'cancelled'}
TERMINAL_DELIVERY = {'no_legal_delivery', 'same_tree_official_result_reused',
                     'technical_unknown', 'official_attempt_completed'}


class PriorStageIncomplete(RuntimeError):
    pass


def _read(path):
    path = Path(path)
    if not path.is_file():
        raise PriorStageIncomplete('Prior v121 completion evidence is not ready: '+str(path))
    ref = reference(path)
    return ref, scope.load(ref)


def _quiet(path, *, pair=False, slot_id=None):
    ref, value = _read(path)
    if (value.get('quiescent') is not True or value.get('cleanup_errors') != []
            or value.get('create_result_unknown') is not False
            or pair and (value.get('all_owned_objects_removed') is not True or value.get('retained_objects') != [])
            or slot_id is not None and value.get('slot_id') not in (None, slot_id)):
        raise PriorStageIncomplete('Prior owned resource cleanup is not trustworthy: '+str(path))
    return ref


def inspect_prior_completion():
    plan_ref, plan = _read(scope.PRIOR_PLAN_FILE)
    summary_ref, summary = _read(scope.PRIOR_API_ROOT/'run-summary.json')
    rows = {row['slot_id']: row for row in plan['rows']}
    generations = summary.get('generation', {})
    if (len(rows) != 27 or set(generations) != set(rows) or summary.get('plan') != plan_ref
            or not isinstance(summary.get('finished_unix'), (int, float))
            or summary.get('pending_grading_jobs') != [] or summary.get('unentered_generation') != []
            or summary.get('retained_objects') != []):
        raise PriorStageIncomplete('Prior27 generation and grading queues have not fully terminated')
    release_ref, release = _read(scope.PRIOR_API_ROOT/'coordinator-capacity-released.json')
    claim_ref, _claim = _read(scope.PRIOR_API_ROOT/'coordinator-capacity.json')
    active = list((scope.PRIOR_BATCH_ROOT/'resource-claims').glob('active-*.json'))
    if release.get('released') is not True or release.get('claim') != claim_ref or active:
        raise PriorStageIncomplete('The prior owner or owned resource reservations are still active')
    quiet, scoring = [], []
    for slot, row in rows.items():
        generation = generations[slot]
        if generation.get('status') not in TERMINAL_GENERATION or generation.get('retained_objects', []):
            raise PriorStageIncomplete('A prior generation is not terminal: '+slot)
        folder = scope.PRIOR_BATCH_ROOT/'episodes'/str(row['slot_index'])
        if generation.get('result'):
            result = scope.load(generation['result'])
            if (result.get('slot_id') != slot or result.get('instance_id') != row['instance_id']
                    or result.get('configuration') != row['configuration']):
                raise PriorStageIncomplete('A prior result does not match its planned attempt')
        if (generation.get('entered') is True or
                (scope.PRIOR_BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists()):
            quiet.append(_quiet(folder/'quiescence.json', pair=True))
        if generation['status'] == 'closed':
            code = summary.get('scores', {}).get(slot)
            delivery = summary.get('deliveries', {}).get(slot)
            if (not isinstance(code, dict) or not isinstance(delivery, dict)
                    or delivery.get('status') not in TERMINAL_DELIVERY
                    or not code.get('request') and code.get('status') != 'technical_unknown'):
                raise PriorStageIncomplete('A prior closed candidate lacks terminal code/delivery records')
        for name, prefix in (('scores', 'score-'), ('deliveries', 'delivery-score-')):
            outcome = summary.get(name, {}).get(slot, {})
            grade = scope.PRIOR_BATCH_ROOT/'grading'/(prefix+str(row['slot_index']))
            request_path = grade/'request.json'
            consumed = any((grade/file).exists() for file in ('started.json','capacity-claim.json','initial-container.json'))
            consumed = consumed or (scope.PRIOR_BATCH_ROOT/'resource-claims'/(prefix+str(row['slot_index'])+'.json')).exists()
            if outcome.get('request') or consumed:
                request_ref, request = _read(request_path)
                if (outcome.get('request', request_ref) != request_ref
                        or request.get('slot_id') != slot or request.get('instance_id') != row['instance_id']):
                    raise PriorStageIncomplete('A prior scoring request belongs to another attempt')
                completed_ref, completed = _read(grade/'completion.json')
                if (completed.get('request') != request_ref or completed.get('status') != 'process_exited'
                        or type(completed.get('returncode')) is not int):
                    raise PriorStageIncomplete('A prior scoring process has not closed')
                quiet.append(_quiet(grade/'quiescence.json', slot_id=slot))
                scoring.append({'request': request_ref, 'completion': completed_ref})
    return {'version': VERSION, 'passed': True, 'prior_plan': plan_ref,
        'prior_run_summary': summary_ref, 'prior_owner_release': release_ref,
        'generation_tasks_terminal': len(rows), 'scoring_attempts_terminal': len(scoring),
        'quiescences': quiet, 'scoring': scoring, 'active_prior_claims': [],
        'all_outcomes_need_not_be_successful': True, 'new_owner_started': False,
        'Docker_queries': 0, 'service_queries': 0}


def prepare_prior_completion():
    """Write no proof until actual prior completion is established."""
    proof = inspect_prior_completion()
    return scope.retain(scope.PRIOR_COMPLETION_FILE, proof)


def require_prior_completion():
    if not scope.PRIOR_COMPLETION_FILE.is_file():
        raise PriorStageIncomplete('The prior v121 stage must finish before creating the v123 owner')
    stored = scope.load(reference(scope.PRIOR_COMPLETION_FILE))
    current = inspect_prior_completion()
    if stored != current:
        raise PriorStageIncomplete('Prior completion evidence changed after preparation')
    return reference(scope.PRIOR_COMPLETION_FILE)
