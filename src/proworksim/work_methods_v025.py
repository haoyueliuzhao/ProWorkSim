"""Complete-work validity and finite actual-method mapping for the v025 A/B pool.

This composes existing immutable-evidence business predicates, not scalar reward
or a second business oracle. Method labels are host diagnostics, never prompts.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .episode import assess_historical_episode
from .online_rewards import _ref
from .retail_rewards import RetailEvidence
from .storage import digest, read_json
from .team_rollout import work_validity
from .team_validity import assess_record_permission
from .templates import retail_collaboration_v021 as predicates

VERSION = 'complete-work-evidence-v0.25'
VALIDITY_SPEC_ID = 'retail-complete-record-permission-basis-delivery-v0.25'
MAPPING_SPEC_ID = 'retail-complete-actual-method-v0.25'
CLASS_ORDER = {'joint_a': ['a_active_handoff', 'a_requested_handoff'],
               'joint_b': ['b_self_repair', 'b_feedback_repair']}


def _event_ref(event):
    return {'sequence': event['sequence'], 'actor': event.get('worker_id'),
            'action': event['payload']['action'],
            'command_id': event['payload']['response'].get('command_id')}


def _public_observation_at_action(e, action):
    """Actual role-local model input, not an end-state or an intended prompt."""
    call_id = action['payload'].get('model_call_id')
    attempts = [event for event in e.events if event.get('worker_id') == action['worker_id']
                and event['kind'] == 'model_attempt' and event['payload'].get('call_id') == call_id
                and event['payload'].get('stage') == 'finished' and event['payload'].get('status') == 'success']
    if len(attempts) != 1:
        return None
    for message in reversed(attempts[0]['payload']['request']['messages']):
        if message.get('role') != 'user' or not isinstance(message.get('content'), str):
            continue
        try:
            value = json.loads(message['content'])
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get('observation'), dict):
            return value['observation']
    return None


def _a_evidence(e):
    final = e.item['submissions'][-1] if e.item['submissions'] else None
    fixed = predicates._actual_fixed_build(e, final, current=True)
    final_basis = tuple(fixed['source_references']['basis']) if fixed else None
    handoffs = {}
    for call in predicates._calls(e, 'provider', 'handoff_information'):
        args, result = call['payload']['arguments'], call['payload']['response']['result']
        hid = result.get('handoff_id')
        handoff = e.state.get('handoffs', {}).get(hid, {})
        ref = _ref(handoff.get('reference'))
        deliveries = [event for event in e.events if event['kind'] == 'environment_event'
                      and event['payload'].get('event_id') == handoff.get('event_id')
                      and event['payload'].get('outcome') == 'applied'
                      and event['payload'].get('payload', {}).get('handoff_id') == hid]
        if (hid in e.start.get('handoffs', {}) or hid in handoffs
                or handoff.get('origin') != 'member_action' or handoff.get('sender') != 'provider'
                or handoff.get('recipients') != ['implementer'] or handoff.get('route_id') != 'basis'
                or handoff.get('work_item_id') != e.wid
                or handoff.get('requirement_version') != e.item['requirement_version']
                or handoff.get('status') != 'delivered' or handoff.get('response_status') != 'delivered'
                or not ref or not e.applicable_basis(ref)
                or not e.read_before('provider', ref, call['sequence']) or not deliveries):
            continue
        used = bool(fixed and ref == final_basis and call['sequence'] < fixed['build_sequence']
                    and any(event['sequence'] < fixed['build_sequence'] for event in deliveries)
                    and e.read_inputs(fixed['build_sequence'], final))
        rid = handoff.get('request_id')
        requests = [request for request in predicates._calls(e, 'implementer', 'request_information')
                    if request['sequence'] < call['sequence']
                    and request['payload']['arguments'].get('route_id') == 'basis'
                    and request['payload']['arguments'].get('work_id') == e.wid
                    and request['payload']['response']['result'].get('request_id') == rid] if rid else []
        request_bound = bool(rid and args.get('request_id') == rid and len(requests) == 1)
        handoffs[hid] = {'handoff_id': hid, 'reference': list(ref), 'request_id': rid,
                        'request_bound': request_bound,
                        'request': _event_ref(requests[0]) if len(requests) == 1 else None,
                        'handoff': _event_ref(call), 'delivery_sequences': [d['sequence'] for d in deliveries],
                        'actually_used_in_current_fixed_product': used}
    used = [h for h in handoffs.values() if h['actually_used_in_current_fixed_product']]
    return {'task': 'joint_a', 'fixed_current_product': fixed,
            'qualifying_handoffs': list(handoffs.values()), 'used_handoffs': used,
            'basis_valid': bool(used and fixed), 'delivery_valid': bool(fixed and used),
            'existing_predicates': ['RetailEvidence.read_inputs/read_before/applicable_basis',
                                    'retail_collaboration_v021._actual_fixed_build', 'actual applied handoff receipts']}


def _b_evidence(e):
    prepared = e.start['work_items'][e.wid]['submissions']
    if not prepared:
        raise ValueError('B requires an actual fixed incorrect initial submission')
    initial_id = prepared[-1]['submission_id']
    original = next(sub for sub in e.item['submissions'] if sub['submission_id'] == initial_id)
    initial_quality = predicates._quality(e, original)
    final = e.item['submissions'][-1] if e.item['submissions'] else None
    fixed = predicates._actual_fixed_build(e, final, current=True)
    judgments = predicates._judgments(e)
    approvals = [j for j in judgments if final and j['submission_id'] == final['submission_id']
                 and j['action'] == 'approve' and j['valid']]
    issues = [j for j in judgments if j['action'] == 'raise_issue' and j['valid']]
    withdrawals = predicates._calls(e, 'implementer', 'withdraw', initial_id)
    withdrawal = withdrawals[0] if withdrawals else None
    before = withdrawal['sequence'] if withdrawal else float('-inf')
    inspected = predicates._implementation_inspected(e, original, before) if withdrawal else False
    treatments = [predicates._issue_treatment(e, issue, final) for issue in issues] if final else []
    all_judgments_valid = bool(judgments and all(j['valid'] for j in judgments))
    final_review = bool(approvals and all_judgments_valid)
    repair_sequence = bool(fixed and withdrawal and before < fixed['build_sequence'] < fixed['submit_sequence'])
    observed = _public_observation_at_action(e, withdrawal) if withdrawal else None
    feedback_observed = bool(issues and observed is not None and all(
        observed.get('issues', {}).get(j['issue_id'], {}).get('submission_id') == initial_id for j in issues))
    feedback_path = bool(issues and feedback_observed and all(j['submission_id'] == initial_id and j['sequence'] < before for j in issues)
                         and all(treatments)
                         and all(any(t['decision_sequence'] < approval['sequence'] for approval in approvals) for t in treatments))
    self_path = bool(not issues and inspected and repair_sequence)
    basis = bool(not initial_quality['passed'] and inspected and fixed and final_review
                 and (self_path or feedback_path))
    delivery = bool(not initial_quality['passed'] and fixed and repair_sequence and final_review
                    and (self_path or feedback_path))
    return {'task': 'joint_b', 'initial_submission_id': initial_id,
            'initial_independent_quality': initial_quality['status'], 'initial_was_incorrect': not initial_quality['passed'],
            'implementation_inspected_before_withdrawal': bool(inspected),
            'withdrawal': _event_ref(withdrawal) if withdrawal else None,
            'fixed_current_product': fixed, 'judgments': judgments, 'issues': issues,
            'issue_treatments': treatments, 'final_approvals': approvals,
            'actual_feedback_presented_before_withdrawal': feedback_observed,
            'all_judgments_valid': all_judgments_valid, 'self_repair_path': self_path,
            'feedback_repair_path': feedback_path, 'basis_valid': basis, 'delivery_valid': delivery,
            'existing_predicates': ['RetailEvidence.read_inputs/read_before/review_reads',
                                    'retail_collaboration_v021._quality/_actual_fixed_build/_judgments',
                                    'retail_collaboration_v021._implementation_inspected/_issue_treatment']}


def assess_complete_work(episode, *, members, independent_capture, window=None):
    """Four dimensions remain explicit; legal refusals do not remove base data."""
    from .templates.retail_collaboration_v025 import case_spec, reward_spec

    root = Path(episode).resolve()
    if root.name == 'manifest.json':
        root = root.parent
    manifest = read_json(root / 'manifest.json')
    ref = {'episode_id': manifest['episode_id'], 'manifest_sha256': digest((root / 'manifest.json').read_bytes())}
    partial = assess_record_permission(root, members=members, independent_capture=independent_capture,
        spec_id=VALIDITY_SPEC_ID, allow_rejected_actions=True, allow_repair=True, window=window)
    checks = [copy.deepcopy(check) for dimension in ('record', 'permission')
              for check in partial['components'][dimension]['checks']]
    semantic = {'version': VERSION, **ref, 'known': False, 'reason': None}
    try:
        case = case_spec(manifest['scenario']['variation']['online_case']['case_id'])
        if (manifest['status'] != 'closed' or manifest['scenario']['variation']['online_case'] != case
                or manifest['scenario']['variation']['online_reward'] != reward_spec(case)
                or case['task'] not in CLASS_ORDER):
            raise ValueError('Only exact frozen A/B work contracts are mapped')
        historical = assess_historical_episode(root)
        if historical.get('assessment_execution', {}).get('status') != 'complete':
            raise ValueError('Historical independent assessment unavailable')
        e = RetailEvidence(root, reward_spec(case), historical)
        if e.start['work_items'][e.wid]['requirements'].get('online_scope') != reward_spec(case):
            raise ValueError('Actual public scope differs from the declared evidence contract')
        facts = _a_evidence(e) if case['task'] == 'joint_a' else _b_evidence(e)
        semantic.update(known=True, case_id=case['case_id'], facts=facts)
        for dimension in ('basis', 'delivery'):
            checks.append({'dimension': dimension, 'value': facts[dimension+'_valid'],
                           'reason': 'Existing independently checked actual references and full role obligations, not reward/completed flags',
                           'evidence': {**ref, 'facts': copy.deepcopy(facts)}})
    except (KeyError, OSError, TypeError, ValueError) as error:
        semantic['reason'] = {'type': type(error).__name__, 'message': str(error)}
        for dimension in ('basis', 'delivery'):
            checks.append({'dimension': dimension, 'value': None,
                           'reason': 'Full semantic evidence is unknown', 'evidence': {**ref, 'error': semantic['reason']}})
    return {'validity': work_validity(checks, spec_id=VALIDITY_SPEC_ID), 'semantic_evidence': semantic}


def map_complete_method(rollout, semantic):
    """Only real information/repair relations define classes; ambiguity stays out."""
    result = {'version': VERSION, 'rollout_id': rollout['rollout_id'], 'spec_id': MAPPING_SPEC_ID,
              'status': 'unmapped', 'class_id': None, 'evidence': copy.deepcopy(semantic),
              'reason': 'Full independently valid work and an unambiguous current method required'}
    if semantic.get('episode_id') != rollout['rollout_id'] or semantic.get('manifest_sha256') != rollout['manifest_sha256']:
        raise ValueError('Semantic mapping evidence belongs to a different actual episode')
    if rollout['work_validity']['value'] is not True or semantic.get('known') is not True:
        return result
    facts = semantic['facts']
    category = None
    if facts['task'] == 'joint_a':
        used = facts['used_handoffs']
        if len(used) != 1:
            result['reason'] = 'Multiple applicable current handoffs leave the realized method ambiguous'
            return result
        handoff = used[0]
        if handoff['request_id'] is None:
            category = 'a_active_handoff'
        elif handoff['request_bound']:
            category = 'a_requested_handoff'
        else:
            result['reason'] = 'Handoff request reference lacks its unique actual earlier requester action'
    elif facts['task'] == 'joint_b':
        if facts['self_repair_path'] and not facts['feedback_repair_path']:
            category = 'b_self_repair'
        elif facts['feedback_repair_path'] and not facts['self_repair_path']:
            category = 'b_feedback_repair'
    if category:
        result.update(status='mapped', class_id=category,
                      reason='Frozen actual information dependency and complete work path; not causal member contribution')
    return result
