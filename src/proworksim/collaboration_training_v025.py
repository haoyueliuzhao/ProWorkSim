"""Actual current-window records, full-work methods and per-situation support.

Complete work gates reconfiguration, not the base RL mask. All sixteen original
slots stay in the learner denominator; continuation diagnostics keep M=1/xi.
"""
import copy
from pathlib import Path

from .collaboration_training_v022 import member_token_admission as _member_token_admission
from .collaboration_training_v022 import projection_summary
from .handoff_credit_v024 import attach_ledger
from .online_support import bind_rollout, diagnose_window, expected_window
from .storage import digest, json_bytes, read_json
from .team_rollout import export_team_rollout
from .work_methods_v025 import (
    CLASS_ORDER, MAPPING_SPEC_ID, assess_complete_work, map_complete_method,
)

VERSION = 'collaboration-token-projection-v0.25'
HARNESS = 'native_v24_compact_work'
PURPOSES = ('composition_training', 'continuation_training')
SELECTION_ORDER = (('joint_a', 'implementer'), ('joint_a', 'provider'))
CONFIGURABLE_TASKS = ('joint_a',)
B_CONFIGURATION_EXCLUSION = ('The evidence-feedback B CPU route was not qualified within the unchanged context budget before model sampling. '
                             'Both B member blocks remain Q=B this round even if actual B support later has two classes; '
                             'failure of the tested witness is not proof the route is impossible.')


def training_admission(catalog, source_pin, *, arm='compact_work', purpose='composition_training'):
    from .templates.retail_collaboration_v025 import PIN_PATH, registry

    if catalog != registry() or arm != 'compact_work' or purpose not in PURPOSES:
        raise ValueError('Exact frozen v025 catalog, compact presentation and declared purpose required')
    source_pin = Path(source_pin).resolve()
    if source_pin.read_bytes() != PIN_PATH.read_bytes():
        raise ValueError('Training source pin differs from the frozen new material')
    source = read_json(source_pin)
    source_slices = {s['slice_id']: s for s in source['slices']}
    for field in ('customers', 'invoice_ids', 'source_rows'):
        groups = [set(source_slices[c['slice_id']][field]) for c in catalog['all_cases']]
        if any(a & b for i, a in enumerate(groups) for b in groups[i+1:]):
            raise ValueError('Training/development/confirmation/continuation material overlaps: ' + field)
    if purpose == 'composition_training':
        cases, slots = catalog['training_cases'], catalog['training_window']['slots']
        ids = [catalog['training_window']['window_id']]
        repeats = 8
    else:
        cases, slots = catalog['continuation_cases'], catalog['continuation_slots']
        ids, repeats = ['v025-next-base', 'v025-next-configured'], 1
    if (len(cases) != 2 or {c['task'] for c in cases} != {'joint_a', 'joint_b'}
            or len(slots) != 2*repeats or len({s['slot_id'] for s in slots}) != len(slots)
            or [s['task'] for s in slots] != ['joint_a', 'joint_b']*repeats):
        raise ValueError('Two exact A/B situations and complete interleaved inventory required')
    for case in cases:
        here = [s for s in slots if s['case_id'] == case['case_id']]
        if (case['purpose'] != purpose or len(here) != repeats
                or len({s['seed'] for s in here}) != repeats
                or any(s['seed'] != s['sampling_seed'] or s['task'] != case['task'] for s in here)
                or case['task'] == 'joint_b' and case['prepared_submission'] != 'wrong_count'):
            raise ValueError('Exact situation/seed/incorrect B initial state contract differs')
    return {'version': VERSION, 'purpose': purpose, 'arm': arm, 'harness': HARNESS,
            'mapping_spec_id': MAPPING_SPEC_ID, 'min_class_count': 2,
            'catalog_sha256': digest(json_bytes(catalog)),
            'source_pin': {'path': str(source_pin), 'sha256': digest(source_pin.read_bytes())},
            'case_ids': [c['case_id'] for c in cases],
            'case_sha256': {c['case_id']: digest(json_bytes(c)) for c in cases},
            'window_contracts': {wid: {'window_id': wid, 'slots': copy.deepcopy(slots)} for wid in ids},
            'raw_slots_per_situation': repeats, 'raw_window_slots': len(slots),
            'normalization': 'All original scheduled slots x actual active members x each member all actual output tokens',
            'credit_assignment': 'terminal_mc', 'optimizer_update_allowed': purpose == 'composition_training',
            'base_RL_requires_method_support': False,
            'reconfiguration_eligibility': 'Full independently evidenced record/permission/basis/delivery, mapped actual method, complete own-token view and >=2 current samples per class within exact xi',
            'old_trajectory_or_fixture_support_allowed': False,
            'selection_order': [list(v) for v in SELECTION_ORDER], 'class_order': copy.deepcopy(CLASS_ORDER),
            'configurable_tasks': list(CONFIGURABLE_TASKS), 'b_configuration_exclusion': B_CONFIGURATION_EXCLUSION}


def validate_window_declaration(declaration, admission):
    expected = admission['window_contracts'].get(declaration.get('window_id'))
    gamma, actual = declaration.get('gamma_identity', {}), declaration.get('slots', [])
    if (expected is None or len(actual) != admission['raw_window_slots']
            or gamma.get('harness') != HARNESS or gamma.get('purpose') != admission['purpose']
            or declaration.get('min_class_count') != 2):
        raise ValueError('Window purpose, native harness or fixed support inventory changed')
    if [(s['slot_id'], s['xi_id']) for s in actual] != [(s['slot_id'], s['case_id']) for s in expected['slots']]:
        raise ValueError('All exact planned slots must retain their original situation/order')
    if gamma.get('seeds') != [s['sampling_seed'] for s in expected['slots']]:
        raise ValueError('Window sampling seeds differ from the frozen order')
    from .templates.retail_collaboration_v025 import case_spec
    for slot in actual:
        case = case_spec(slot['xi_id'])
        if slot['mapping_spec_id'] != MAPPING_SPEC_ID or slot['active_members'] != case['active_roles']:
            raise ValueError('Mapper or actual active member inventory changed')
        for member in case['active_roles']:
            config = slot['policies'][member]['config']
            if (config['budget']['max_decisions'] != case['role_decision_limits'][member]
                    or config['max_context_tokens'] != 16384 or config['max_output_tokens'] != 2048
                    or config['temperature'] != .7):
                raise ValueError('Original full role opportunities and sampling recipe required')
    return expected


def export_training_episode(prepared, episode, *, declaration, slot_id, captured, admission):
    from .templates.retail_collaboration_v025 import assess_episode, case_spec, registry

    canonical = training_admission(registry(), admission['source_pin']['path'],
                                   arm=admission.get('arm'), purpose=admission.get('purpose'))
    if admission != canonical:
        raise ValueError('Training admission differs from the exact frozen purpose/source binding')
    contract = validate_window_declaration(declaration, admission)
    case = prepared.case
    slots = [s for s in contract['slots'] if s['slot_id'] == slot_id]
    if (len(slots) != 1 or slots[0]['case_id'] != case.get('case_id')
            or case != case_spec(case['case_id']) or case['purpose'] != admission['purpose']
            or admission['case_sha256'].get(case['case_id']) != digest(json_bytes(case))):
        raise ValueError('Actual case differs from its exact planned training/continuation slot')
    declared = next(s for s in declaration['slots'] if s['slot_id'] == slot_id)
    if list(declared['active_members']) != list(prepared.active_roles):
        raise ValueError('Active member denominator differs from the actual role inventory')
    root = Path(episode).resolve()
    manifest = read_json(root / 'manifest.json')
    variation = manifest['scenario']['variation']
    if variation['online_case'] != case or variation['online_reward'] != prepared.reward_spec:
        raise ValueError('Historical world/reward declaration differs from the actual case')
    assessment = assess_episode(root)
    manifest_sha = digest((root / 'manifest.json').read_bytes())
    if assessment.get('episode_manifest_sha256') not in {None, manifest_sha}:
        raise ValueError('Independent assessment changed the original historical boundary')
    reward = {'version': VERSION, 'episode_id': manifest['episode_id'], 'manifest_sha256': manifest_sha,
              'spec': copy.deepcopy(prepared.reward_spec), 'scope': case['task'],
              'eligible': assessment['eligible'], 'reward': assessment['reward'],
              'completed': assessment['completed'], 'components': copy.deepcopy(assessment['components']),
              'independent_assessability': assessment['independent_assessability'],
              'record_trust': assessment['record_trust'], 'exclusions': copy.deepcopy(assessment['exclusions']),
              'source_assessment_sha256': digest(json_bytes(assessment)),
              'credit': 'Unchanged terminal MC contract; event ledger is preserved as factual diagnostics'}
    if reward['eligible']:
        reward = attach_ledger(reward, root)
    members = {r['role_id']: {'actor_id': r['actor'], 'origin': 'target_model'} for r in prepared.scenario['roles']}
    window = expected_window(declaration, slot_id)
    work = assess_complete_work(root, members=members, independent_capture=captured, window=window)
    rollout = export_team_rollout(root, window=window, members=members, validity=work['validity'], reward=reward)
    mapping = map_complete_method(rollout, work['semantic_evidence'])
    reconfiguration = admission['optimizer_update_allowed'] and work['validity']['value'] is True and mapping['status'] == 'mapped'
    rollout['online_scope'] = {'version': VERSION, 'task': case['task'], 'purpose': admission['purpose'],
        'reward_spec': copy.deepcopy(prepared.reward_spec), 'admission_sha256': digest(json_bytes(admission)),
        'preparation_credit': False, 'composition_reconfiguration_eligible': bool(reconfiguration),
        'optimizer_update_allowed': admission['optimizer_update_allowed'],
        'scope': 'Whole-work semantic eligibility is separate from member actual-token support and base RL.'}
    views = bind_rollout(declaration, slot_id, rollout, mapping=mapping)['member_views']
    for view in views.values():
        for decision in view['decisions']:
            if decision['actor_trainable']:
                trace = decision['tokens']
                if decision['loss_mask'] != [0]*len(trace['input_ids']) + [1]*len(trace['output_ids']):
                    raise ValueError('Only this member own actual generated tokens receive actor targets')
    return {'slot_id': slot_id, 'rollout': rollout, 'reward': reward,
            'active_members': list(prepared.active_roles), 'mapping': mapping}, {
                'version': VERSION, 'assessment': assessment, 'work_validity': work['validity'],
                'method_mapping': mapping, 'member_views': views, **member_token_admission(views),
                'record_validity': work['validity']['components']['record']['value'],
                'business_reward_known': assessment['eligible'], 'training_probability_qualified': False,
                'scope': 'Actual current-model token binding; existing learner keeps its original probability gate. Failure/unmapped/low-frequency work remains eligible for base RL when its own evidence is complete.'}


def member_token_admission(views):
    """Known empty member views are distinct from missing generated-token traces."""
    result = _member_token_admission(views)
    for member, view in views.items():
        if not view['decisions'] and not view['diagnostics'] and view['no_own_actions']:
            result['token_projection_members'][member].update(
                status='known_no_own_actions', known_no_generation=True,
                qualification='No recorded own generation/action; no synthetic target is inserted')
    result['has_complete_trainable_actual_members'] = bool(views) and all(
        row['status'] in {'complete_actual_generation', 'known_no_generation', 'known_no_own_actions'}
        for row in result['token_projection_members'].values())
    return result


def records_from_entries(entries):
    if len({e['slot_id'] for e in entries}) != len(entries):
        raise ValueError('Each original joint slot may occur once')
    return [{'slot_id': e['slot_id'], 'status': 'closed', 'rollout': e['rollout'], 'mapping': e['mapping']} for e in entries]


def diagnose_support(entries, declaration):
    from .templates.retail_collaboration_v025 import PIN_PATH, registry

    catalog = registry()
    purpose = declaration['gamma_identity'].get('purpose')
    admission = training_admission(catalog, PIN_PATH, purpose=purpose)
    validate_window_declaration(declaration, admission)
    records = records_from_entries(entries)
    diagnosed = diagnose_window(declaration, records)
    supports = {group['window']['xi_id']: group['support'] for group in diagnosed['groups']}
    cases = {c['case_id']: c for c in catalog['all_cases']}
    selected = None
    for task, member in SELECTION_ORDER:
        for xi, support in supports.items():
            if cases[xi]['task'] != task or support is None:
                continue
            block = support['blocks'].get(member)
            if block is None:
                continue
            if set(block['b']) - set(CLASS_ORDER[task]):
                raise ValueError('Unfrozen category cannot enter composition support')
            order = [category for category in CLASS_ORDER[task] if category in block['b']]
            if len(order) >= 2 and selected is None and admission['optimizer_update_allowed']:
                selected = {'xi_id': xi, 'member_id': member, 'task': task,
                            'class_order': order, 'perturb_class_id': order[0]}
    return {'version': VERSION, 'purpose': purpose, 'window_id': declaration['window_id'],
            'complete': diagnosed['complete'], 'current_joint_record_count': len(records),
            'actor_identity': copy.deepcopy(declaration['actor_identity']), 'raw_slot_count': len(declaration['slots']),
            'raw_slots_per_situation': admission['raw_slots_per_situation'], 'min_class_count': 2,
            'supports_by_xi': supports, 'selected_block': selected,
            'selection_order': [list(v) for v in SELECTION_ORDER], 'class_order': copy.deepcopy(CLASS_ORDER),
            'configurable_tasks': list(CONFIGURABLE_TASKS), 'b_configuration_exclusion': B_CONFIGURATION_EXCLUSION,
            'records': records, 'record_digests': [{'slot_id': r['slot_id'], 'rollout_id': r['rollout']['rollout_id'],
                'rollout_sha256': digest(json_bytes(r['rollout'])), 'mapping_sha256': digest(json_bytes(r['mapping']))} for r in records],
            'situations': [{k: v for k, v in group.items() if k not in {'support', 'Q_equals_B', 'baseline_only_materialization'}} for group in diagnosed['groups']],
            'optimizer_update_allowed': admission['optimizer_update_allowed'],
            'scope': 'Each exact xi retains its own current-policy M; no pooling of cases, policies, quality variants, old trajectories or program witnesses. records may be omitted from persisted summary and rebuilt from original entries.'}


__all__ = ['VERSION', 'HARNESS', 'training_admission', 'validate_window_declaration',
           'export_training_episode', 'member_token_admission', 'projection_summary',
           'records_from_entries', 'diagnose_support']
