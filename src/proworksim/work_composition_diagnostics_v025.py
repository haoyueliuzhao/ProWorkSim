"""Sixteen-slot terminal-credit descriptions with actual member composition.

These reports do not change a reward, a target, a denominator or any action.
Terminal credit is associated with realized member behavior, not reinterpreted
as per-action causal attribution.
"""
import copy
import math
from collections import Counter, defaultdict
from pathlib import Path

from .storage import atomic_write, json_bytes, read_json

VERSION = 'work-composition-diagnostics-v0.25'
POST_UPDATE_PAIRS = (
    ('joint_a', 'provider'), ('joint_a', 'implementer'),
    ('joint_b', 'implementer'), ('joint_b', 'reviewer'),
    ('implement', 'implementer'), ('review', 'reviewer'),
)


def select_post_update_rows(rows, maximum):
    """First admitted decision for each of six fixed task/member pairs; missing pairs stay missing, without outcome-dependent replacement."""
    if type(maximum) is not int or not 0 <= maximum <= 6:
        raise ValueError('v023 permits at most six fixed task/member diagnostic contexts')
    selected = []
    for task, member in POST_UPDATE_PAIRS[:maximum]:
        index = next((i for i, row in enumerate(rows)
                      if row['task'] == task and row['member_id'] == member), None)
        if index is not None:
            selected.append(index)
    return selected


def action_stage(action):
    return {
        'read_alias': 'evidence_read', 'read_version': 'evidence_read',
        'read_object': 'evidence_read', 'read_messages': 'coordination_read',
        'inspect_submission': 'fixed_submission_inspection',
        'request_information': 'basis_request', 'handoff_information': 'basis_delivery',
        'adopt': 'reference_adoption', 'adopt_reference': 'reference_adoption', 'adopt_input': 'reference_adoption',
        'write_object': 'code_or_object_revision', 'sql_build': 'real_build_attempt', 'run_build': 'real_build_attempt',
        'submit': 'fixed_delivery_attempt', 'submit_work': 'fixed_delivery_attempt',
        'approve': 'formal_approval_attempt', 'raise_issue': 'formal_issue_attempt',
        'withdraw': 'repair_withdrawal', 'withdraw_submission': 'repair_withdrawal', 'respond_issue': 'issue_response',
        'decide_issue': 'issue_treatment_review', 'resolve_issue': 'issue_treatment_review', 'review_issue_response': 'issue_treatment_review',
    }.get(action, 'other_world_action')


def _actual_actions(events, call_id, member):
    result = []
    for event in events:
        payload = event['payload']
        if (event['kind'] == 'tool_call' and event.get('worker_id') == member
                and payload.get('model_call_id', payload.get('decision_id')) == call_id):
            response = payload.get('response', {})
            result.append({'sequence': event['sequence'], 'action': payload['action'],
                           'stage': action_stage(payload['action']), 'ok': response.get('ok'),
                           'action_id': response.get('action_id'),
                           'command_committed': response.get('command_committed'),
                           'error': copy.deepcopy(response.get('error'))})
    return result


def summarize_work_signals(entries, update_output):
    """Write reward components, actual behavior and signed advantages per original call."""
    output = Path(update_output)
    admission = read_json(output / 'admission.json')
    report = read_json(output / 'report.json')
    rows = admission['decisions']
    composed = read_json(output / 'composition-admission.json')
    weights = {r['call_id']: r['weight'] for r in composed['rows']}
    if len(weights) != len(rows) or set(weights) != {r['call_id'] for r in rows}:
        raise ValueError('Exact original composition decision inventory required')
    entries_by_slot = {e['slot_id']: e for e in entries}
    if (len(entries_by_slot) != 16 or admission['slot_count'] != 16
            or [x['slot_id'] for x in admission['slots']] != [e['slot_id'] for e in entries]):
        raise ValueError('Diagnostics must retain all sixteen scheduled original slots')
    values, advantages = report.get('old_critic_values'), report.get('advantages')
    available = (isinstance(values, list) and isinstance(advantages, list)
                 and len(values) == len(rows) and len(advantages) == len(rows))
    if available and any(not math.isfinite(v) for v in values + advantages):
        raise ValueError('Reported critic values and advantages must be finite')
    decisions, groups = [], {}
    observed_advantages = Counter()
    for i, row in enumerate(rows):
        entry = entries_by_slot[row['slot_id']]
        actions = _actual_actions(entry['rollout']['events'], row['call_id'], row['member_id'])
        value, advantage = (values[i], advantages[i]) if available else (None, None)
        sign = ('positive' if advantage > 0 else 'negative' if advantage < 0 else 'zero') if available else 'unknown'
        if available and not math.isclose(row['reward'] - value, advantage, rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError('Advantage differs from the saved terminal return minus old critic')
        stages = sorted({a['stage'] for a in actions}) or ['no_executed_world_action']
        weight = len(row['tokens']['output_ids']) / row['actor_denominator']
        item = {'slot_id': row['slot_id'], 'task': row['task'], 'member_id': row['member_id'],
                'call_id': row['call_id'], 'past_public_stage': copy.deepcopy(row.get('stage')),
                'actual_actions': actions, 'realized_action_stages': stages,
                'terminal_reward': row['terminal_reward'], 'return_target': row['reward'],
                'reward_components': copy.deepcopy(entry['reward'].get('components', [])),
                'critic_before': value, 'advantage': advantage, 'advantage_sign': sign,
                'own_output_tokens': len(row['tokens']['output_ids']),
                'actor_denominator': row['actor_denominator'], 'critic_denominator': row['critic_denominator'],
                'nominal_token_average_weight': weight,
                'composition_weight': weights[row['call_id']],
                'configured_token_average_weight': weight * weights[row['call_id']],
                'advantage_times_nominal_weight': advantage * weight if available else None}
        decisions.append(item)
        observed_advantages[sign] += 1
        # The tuple is one realized action-stage set, so no decision's weight is
        # duplicated when a recorder happens to contain multiple action receipts.
        key = (row['slot_id'], row['task'], row['member_id'], tuple(stages))
        group = groups.setdefault(key, {'slot_id': row['slot_id'], 'task': row['task'],
            'member_id': row['member_id'], 'realized_action_stages': stages,
            'decisions': 0, 'own_output_tokens': 0,
            'advantages': {'positive': 0, 'negative': 0, 'zero': 0, 'unknown': 0},
            'nominal_token_average_weight': 0.0, 'signed_weighted_advantage': 0.0 if available else None,
            'call_ids': []})
        group['decisions'] += 1
        group['own_output_tokens'] += item['own_output_tokens']
        group['advantages'][sign] += 1
        group['nominal_token_average_weight'] += weight
        if available:
            group['signed_weighted_advantage'] += advantage * weight
        group['call_ids'].append(row['call_id'])
    slots = []
    for entry, admitted in zip(entries, admission['slots']):
        reward = entry['reward']
        rows_here = [d for d in decisions if d['slot_id'] == entry['slot_id']]
        slots.append({'slot_id': entry['slot_id'], 'task': reward.get('scope'),
            'active_members': entry['active_members'], 'reward_known': reward['eligible'],
            'reward': reward['reward'], 'completed': reward.get('completed'),
            'components': copy.deepcopy(reward.get('components', [])),
            'positive_reward_terms': [c['term_id'] for c in reward.get('components', [])
                                     if c.get('achieved') is True and c.get('score', 0) > 0],
            'admitted_decisions': len(rows_here), 'admission_exclusions': copy.deepcopy(admitted['exclusions']),
            'member_admission': copy.deepcopy(admitted['members']),
            'advantage_counts': dict(Counter(d['advantage_sign'] for d in rows_here)),
            'nominal_slot_weight': 1 / 16})
    sources = defaultdict(list)
    for slot in slots:
        if slot['advantage_counts'].get('positive', 0):
            for term in slot['positive_reward_terms']:
                sources[term].append(slot['slot_id'])
    result = {'version': VERSION, 'window_id': admission['window_id'],
        'status': 'observed' if available else 'advantages_unavailable', 'update_status': report['status'],
        'actor_steps_in_window': report.get('actor_optimizer_steps'),
        'critic_steps_in_window': report.get('critic_optimizer_steps'),
        'scheduled_slots': 16, 'composition': 'saved_member_conditioned_weights', 'credit_assignment': 'terminal_mc',
        'advantages': {k: observed_advantages[k] for k in ('positive', 'negative', 'zero', 'unknown')},
        'positive_signal_slots_by_achieved_reward_term': dict(sources),
        'slots': slots, 'groups': list(groups.values()), 'decisions': decisions,
        'extra_model_calls': 0, 'extra_actor_forwards': 0,
        'scope': 'Terminal reward is broadcast to each actual member output under the unchanged slot/member/token denominator. Association with an action stage is descriptive, not action-local reward or causal credit. A successful build tool receipt alone does not certify correct content; achieved reward terms remain the independent business evidence. Zero own advantage does not imply shared parameters cannot change that member behavior.'}
    atomic_write(output / 'work-signal-diagnostics.json', json_bytes(result))
    return result
