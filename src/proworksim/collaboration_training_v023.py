"""Actual-token projection for four fixed six-slot Q=B learning windows.

Only newly pinned training worlds can enter this projection. Repeated A/B slots
are separate actual episodes of the same exact case, not synthesized targets.
"""
import copy
from collections import Counter
from pathlib import Path

from .collaboration_training_v022 import member_token_admission, projection_summary
from .online_support import bind_rollout, expected_window
from .storage import digest, json_bytes, read_json
from .team_rollout import export_team_rollout
from .team_validity import assess_record_permission

VERSION = 'collaboration-token-projection-v0.23'
HARNESS = 'native_v23_compact_work'
TASK_COUNTS = {'joint_a': 2, 'joint_b': 2, 'implement': 1, 'review': 1}


def training_admission(catalog, source_pin, *, arm='compact_work'):
    from .templates.retail_collaboration_v023 import PIN_PATH, registry

    if catalog != registry() or arm != 'compact_work':
        raise ValueError('The pilot requires the exact frozen v023 catalog and compact presentation')
    source_pin = Path(source_pin).resolve()
    if source_pin.read_bytes() != PIN_PATH.read_bytes():
        raise ValueError('Training source pin differs from the template frozen material')
    cases = {c['case_id']: c for c in catalog['all_cases']}
    windows = catalog['training_windows']
    if len(windows) != 4 or [w['window_index'] for w in windows] != list(range(4)):
        raise ValueError('Exactly four predeclared training windows required')
    source = read_json(source_pin)
    slices = {s['slice_id']: s for s in source['slices']}
    used_cases = []
    contracts = {}
    for window in windows:
        slots = window['slots']
        if len(slots) != 6 or len({s['slot_id'] for s in slots}) != 6:
            raise ValueError('All six scheduled slots must remain in each window')
        if Counter(cases[s['case_id']]['task'] for s in slots) != Counter(TASK_COUNTS):
            raise ValueError('Every window requires exactly A2+B2+implement1+review1')
        for task in TASK_COUNTS:
            ids = {s['case_id'] for s in slots if cases[s['case_id']]['task'] == task}
            if len(ids) != 1:
                raise ValueError('A/B repetitions must use the same exact predeclared case')
        for slot in slots:
            case = cases[slot['case_id']]
            if case['purpose'] != 'pilot_training' or case['window_index'] != window['window_index']:
                raise ValueError('Evaluation or another window material cannot become a training slot')
        used_cases.extend(dict.fromkeys(s['case_id'] for s in slots))
        contracts[window['window_id']] = copy.deepcopy(window)
    if len(set(used_cases)) != 16:
        raise ValueError('Each new window needs four previously unused training materials')
    train = {cid: cases[cid] for cid in used_cases}
    evaluation = catalog['evaluation_cases']
    all_materials = list(train.values()) + evaluation
    for field in ('customers', 'invoice_ids', 'source_rows'):
        groups = [set(slices[c['slice_id']][field]) for c in all_materials]
        if any(a & b for i, a in enumerate(groups) for b in groups[i+1:]):
            raise ValueError('Training and evaluation materials overlap: ' + field)
    return {'version': VERSION, 'catalog_sha256': digest(json_bytes(catalog)),
            'source_pin': {'path': str(source_pin), 'sha256': digest(source_pin.read_bytes())},
            'case_ids': list(train), 'case_sha256': {cid: digest(json_bytes(c)) for cid, c in train.items()},
            'window_contracts': contracts, 'arm': arm, 'harness': HARNESS,
            'max_actor_steps': 4, 'max_critic_steps': 4, 'max_steps_per_window': 1,
            'credit_assignment': 'terminal_mc', 'composition': 'Q=B',
            'normalization': 'All six scheduled slots x actual active members x each member all actual output tokens',
            'old_E_W1_CPU_and_evaluation_trajectories_allowed': False,
            'id_vtdo_reconfiguration_eligible': False}


def validate_window_declaration(declaration, admission):
    expected = admission['window_contracts'].get(declaration.get('window_id'))
    actual = declaration.get('slots', [])
    if (expected is None or len(actual) != 6
            or declaration.get('gamma_identity', {}).get('harness') != HARNESS):
        raise ValueError('Training declaration must retain the exact six-slot window and harness')
    target = [(s['slot_id'], s['case_id']) for s in expected['slots']]
    if [(s['slot_id'], s['xi_id']) for s in actual] != target:
        raise ValueError('Training slot order/cases differ from the frozen six-slot window')
    if declaration['gamma_identity'].get('seeds') != [s['sampling_seed'] for s in expected['slots']]:
        raise ValueError('Training seeds differ from the frozen slot order')
    from .templates.retail_collaboration_v023 import case_spec
    for slot in actual:
        case = case_spec(slot['xi_id'])
        if slot['active_members'] != case['active_roles']:
            raise ValueError('Actual active members differ from the fixed slot denominator')
        for member in case['active_roles']:
            config = slot['policies'][member]['config']
            if (config['budget']['max_decisions'] != case['role_decision_limits'][member]
                    or config['max_context_tokens'] != 16384 or config['max_output_tokens'] != 2048
                    or config['temperature'] != .7):
                raise ValueError('Full responsibility opportunities and frozen context/output budgets are required')
    return expected


def export_training_episode(prepared, episode, *, declaration, slot_id, captured, admission):
    from .templates.retail_collaboration_v023 import assess_episode, case_spec, registry

    canonical = training_admission(registry(), admission['source_pin']['path'], arm=admission.get('arm'))
    if admission != canonical:
        raise ValueError('Training admission differs from the canonical frozen binding')
    window_spec = validate_window_declaration(declaration, admission)
    case = prepared.case
    slots = [s for s in window_spec['slots'] if s['slot_id'] == slot_id]
    if len(slots) != 1 or slots[0]['case_id'] != case.get('case_id'):
        raise ValueError('Actual case differs from its scheduled training slot')
    if (case.get('purpose') != 'pilot_training' or case != case_spec(case['case_id'])
            or admission['case_sha256'].get(case['case_id']) != digest(json_bytes(case))):
        raise ValueError('Only exact new training cases are admitted')
    spec = next(s for s in declaration['slots'] if s['slot_id'] == slot_id)
    if list(spec['active_members']) != list(prepared.active_roles):
        raise ValueError('Actual active members differ from the fixed slot denominator')
    root = Path(episode).resolve()
    manifest = read_json(root / 'manifest.json')
    variation = manifest['scenario']['variation']
    if variation['online_case'] != case or variation['online_reward'] != prepared.reward_spec:
        raise ValueError('Episode work/reward contract differs from the declared training case')
    assessment = assess_episode(root)
    manifest_sha = digest((root / 'manifest.json').read_bytes())
    if assessment.get('episode_manifest_sha256') not in {None, manifest_sha}:
        raise ValueError('Independent business assessment changed the historical boundary')
    reward = {'version': VERSION, 'episode_id': manifest['episode_id'], 'manifest_sha256': manifest_sha,
              'spec': copy.deepcopy(prepared.reward_spec), 'scope': case['task'],
              'eligible': assessment['eligible'], 'reward': assessment['reward'],
              'completed': assessment['completed'], 'components': copy.deepcopy(assessment['components']),
              'independent_assessability': assessment['independent_assessability'],
              'record_trust': assessment['record_trust'], 'exclusions': copy.deepcopy(assessment['exclusions']),
              'source_assessment_sha256': digest(json_bytes(assessment)),
              'credit': 'All realized scoped reward is terminal_mc; no invented event-time ledger'}
    members = {r['role_id']: {'actor_id': r['actor'], 'origin': 'target_model'} for r in prepared.scenario['roles']}
    window = expected_window(declaration, slot_id)
    validity = assess_record_permission(root, members=members, independent_capture=captured,
        spec_id=VERSION + ':record-permission', allow_rejected_actions=True, allow_repair=True, window=window)
    rollout = export_team_rollout(root, window=window, members=members, validity=validity, reward=reward)
    rollout['online_scope'] = {'version': VERSION, 'task': case['task'],
        'reward_spec': copy.deepcopy(prepared.reward_spec), 'admission_sha256': digest(json_bytes(admission)),
        'preparation_credit': False, 'composition_reconfiguration_eligible': False,
        'scope': 'Base Q=B actual-token projection; complete basis/delivery reconfiguration validity remains unestablished.'}
    views = bind_rollout(declaration, slot_id, rollout)['member_views']
    for view in views.values():
        for decision in view['decisions']:
            if decision['actor_trainable']:
                trace = decision['tokens']
                if decision['loss_mask'] != [0]*len(trace['input_ids']) + [1]*len(trace['output_ids']):
                    raise ValueError('Only this member actual generated tokens may receive actor targets')
    return {'slot_id': slot_id, 'rollout': rollout, 'reward': reward,
            'active_members': list(prepared.active_roles)}, {
                'version': VERSION, 'assessment': assessment, 'member_views': views,
                **member_token_admission(views), 'record_validity': validity['components']['record']['value'],
                'business_reward_known': assessment['eligible'], 'training_probability_qualified': False,
                'scope': 'Actual-token identity/outcome projection; existing learner checks all admitted original probabilities.'}


__all__ = ['VERSION', 'HARNESS', 'training_admission', 'validate_window_declaration',
           'export_training_episode', 'member_token_admission', 'projection_summary']
