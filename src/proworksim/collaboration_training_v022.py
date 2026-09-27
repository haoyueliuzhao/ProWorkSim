"""Minimum real-token bridge for separately reserved v0.22 training worlds.

No E/W1 or program-witness trajectory can be admitted by changing a flag. This
module exports actual closed current-policy episodes to existing TeamRollout and
MemberView; it does not invent targets, select successful actions or act for staff.
"""
import copy
from pathlib import Path

from .member_views import member_view
from .online_support import bind_rollout, expected_window
from .storage import digest, json_bytes, read_json
from .team_rollout import export_team_rollout
from .team_validity import assess_record_permission

VERSION = 'collaboration-token-projection-v0.22'


def training_admission(catalog, source_pin, *, arm='compact_work'):
    from .templates.retail_collaboration_v022 import PIN_PATH, registry

    if catalog != registry() or arm != 'compact_work':
        raise ValueError('The bridge has one predeclared new catalog and compact presentation')
    cases = catalog['reserved_training']
    if [c['task'] for c in cases] != ['implement', 'review', 'joint_a', 'joint_b']:
        raise ValueError('Four independent reserved responsibility scopes required')
    if any(c['purpose'] != 'reserved_training' or c['model_training_eligible'] is not False for c in cases):
        raise ValueError('A mutable training flag does not certify the actual projection')
    source_pin = Path(source_pin).resolve()
    if source_pin.read_bytes() != PIN_PATH.read_bytes():
        raise ValueError("Training source pin differs from the template frozen material")
    source = read_json(source_pin)
    entries = {x['slice_id']: x for x in source['slices']}
    groups = [set(entries[c['slice_id']]['source_rows']) for c in cases]
    if any(a & b for i, a in enumerate(groups) for b in groups[i+1:]):
        raise ValueError('Reserved train materials overlap within this bridge')
    return {'version': VERSION, 'catalog_sha256': digest(json_bytes(catalog)),
            'source_pin': {'path': str(source_pin), 'sha256': digest(source_pin.read_bytes())},
            'case_ids': [c['case_id'] for c in cases], 'case_sha256': {c['case_id']: digest(json_bytes(c)) for c in cases},
            'arm': arm, 'harness': 'native_v22_compact_work', 'max_actor_steps': 1, 'max_critic_steps': 1,
            'credit_assignment': 'terminal_mc', 'composition': 'Q=B',
            'purpose': 'New independent train worlds; conditional N1/W1 gates are enforced by the bridge launcher',
            'normalization': 'All four scheduled slots x actual active members x each member all actual output tokens',
            'old_E_W1_and_CPU_trajectories_allowed': False}


def member_token_admission(views):
    """Keep missing token evidence distinct from known zero-reward/no-generation."""
    members = {}
    allowed_stops = {'not_started_direct_context_limit', 'not_started_budget_stop'}
    for member, view in views.items():
        decisions = view['decisions']
        actual_count = sum(row['actual_response'] is not None for row in decisions)
        known_no_generation = (actual_count == 0 and bool(decisions)
            and all(not row['actor_required'] and row['generation_status'] in allowed_stops
                    for row in decisions)
            and not view['complete_actor_trajectory']
            and all(row['reason'] in {'known_direct_no_generation_context_limit',
                                     'no_unique_successful_actual_completion'}
                    for row in view['diagnostics']))
        status = ('complete_actual_generation' if view['complete_actor_trajectory'] else
                  'known_no_generation' if known_no_generation else 'incomplete_or_unknown_tokens')
        members[member] = {'status': status, 'actual_completion_count': actual_count,
            'own_action_tokens': view['own_action_tokens'],
            'complete_actor_trajectory': view['complete_actor_trajectory'],
            'known_no_generation': known_no_generation,
            'diagnostics': copy.deepcopy(view['diagnostics'])}
    count = sum(row['own_action_tokens'] for row in members.values()
                if row['complete_actor_trajectory'])
    return {'token_projection_members': members,
            'has_complete_trainable_actual_members': bool(members) and all(
                row['status'] in {'complete_actual_generation', 'known_no_generation'}
                for row in members.values()),
            'has_actual_trainable_tokens': count > 0,
            'actual_trainable_token_count': count,
            'token_qualification_scope': 'Known pre-generation stops are explicit exceptions, not generated targets; missing token evidence is never a zero-signal observation. Probability and backward qualification remain separate.'}


def export_training_episode(prepared, episode, *, declaration, slot_id, captured, admission):
    from .templates.retail_collaboration_v022 import assess_episode, case_spec, registry

    canonical_admission = training_admission(registry(), admission['source_pin']['path'],
                                             arm=admission.get('arm'))
    if admission != canonical_admission:
        raise ValueError('Training admission differs from the canonical frozen binding')
    case = prepared.case
    specs = declaration.get('slots', [])
    if (len(specs) != 4 or sorted(row['xi_id'] for row in specs) != sorted(admission['case_ids'])
            or declaration.get('gamma_identity', {}).get('harness') != admission['harness']):
        raise ValueError('Training window must retain all four scheduled reserved cases and their harness')
    slots = [row for row in specs if row['slot_id'] == slot_id]
    if len(slots) != 1 or slots[0]['xi_id'] != case.get('case_id'):
        raise ValueError('Scheduled training slot differs from the actual reserved case')
    if (admission.get('version') != VERSION or case.get('case_id') not in admission.get('case_ids', [])
            or case.get('purpose') != 'reserved_training' or case != case_spec(case['case_id'])
            or admission['case_sha256'].get(case['case_id']) != digest(json_bytes(case))
            or admission['catalog_sha256'] != digest(json_bytes(registry()))):
        raise ValueError('Only exact newly reserved train worlds may enter the token bridge')
    pin = Path(admission['source_pin']['path'])
    if digest(pin.read_bytes()) != admission['source_pin']['sha256']:
        raise ValueError('Frozen training source changed')
    root = Path(episode).resolve()
    manifest = read_json(root / 'manifest.json')
    variation = manifest['scenario']['variation']
    if variation['online_case'] != case or variation['online_reward'] != prepared.reward_spec:
        raise ValueError('Episode work/reward contract differs from declared training case')
    assessment = assess_episode(root)
    manifest_sha = digest((root / 'manifest.json').read_bytes())
    if assessment.get('episode_manifest_sha256') not in {None, manifest_sha}:
        raise ValueError('Independent business assessment changed historical boundary')
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
    # Basis/delivery V remain unknown here. Independent reward can train base RL;
    # a scalar, completion flag or descriptive mapper never manufactures V/support.
    rollout = export_team_rollout(root, window=window, members=members, validity=validity, reward=reward)
    rollout['online_scope'] = {'version': VERSION, 'task': case['task'],
        'reward_spec': copy.deepcopy(prepared.reward_spec), 'admission_sha256': digest(json_bytes(admission)),
        'preparation_credit': False, 'composition_reconfiguration_eligible': False,
        'scope': 'Minimum base Q=B projection only; no independent complete work-validity mapper for reconfiguration.'}
    bound = bind_rollout(declaration, slot_id, rollout)
    views = bound['member_views']
    for member, view in views.items():
        for decision in view['decisions']:
            if decision['actor_trainable']:
                trace = decision['tokens']
                if decision['loss_mask'] != [0]*len(trace['input_ids']) + [1]*len(trace['output_ids']):
                    raise ValueError('Only this member actual generated tokens may receive actor targets')
    return {'slot_id': slot_id, 'rollout': rollout, 'reward': reward,
            'active_members': list(prepared.active_roles)}, {
                'version': VERSION, 'assessment': assessment, 'member_views': views,
                **member_token_admission(views),
                'record_validity': validity['components']['record']['value'],
                'business_reward_known': assessment['eligible'],
                'training_probability_qualified': False,
                'scope': 'Token/identity/outcome projection only; learner still checks every actual probability and gradient.'}


def projection_summary(entry):
    views = {m: member_view(entry['rollout'], m) for m in entry['active_members']}
    return {'slot_id': entry['slot_id'], 'reward': entry['reward']['reward'],
            **member_token_admission(views),
            'members': {m: {'complete_actor_trajectory': v['complete_actor_trajectory'],
                            'own_action_tokens': v['own_action_tokens'],
                            'generation_statuses': [x['generation_status'] for x in v['decisions']]}
                        for m, v in views.items()},
            'normalization_preserves_scheduled_slot': True}
