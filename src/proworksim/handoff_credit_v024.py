"""Causal handoff settlement on actual WorldCore history, outside actor inputs.

The early event is selected from facts available at delivery. End-of-episode
business success is used only for the terminal reconciliation, including a
negative correction. This is a new time-credit surrogate, not ID-VTDO.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

from .episode import assess_historical_episode
from .online_rewards import _ref, _rows
from .online_signals import joint_return
from .retail_rewards import RetailEvidence
from .storage import digest, json_bytes

VERSION = 'actual-handoff-credit-v0.24'
HANDOFF_AMOUNT = .2
CREDIT_MODES = {'mc': 'terminal_mc', 'handoff_rtg': 'joint_reward_to_go'}


def first_applicable_handoff(evidence):
    """Locate earliest actual delivery without querying terminal outcome facts.

    Immutable end-captured receipts/documents authenticate the past; mutable
    terminal handoff status, final requirement and reward components are not
    inputs to event selection. Preparation receipts and pending old handoffs
    cannot become current-episode credit.
    """
    spec = evidence.spec
    if spec['task'] != 'joint_a':
        return None
    terms = [(t['term_id'], t['weight']) for t in spec['terms']]
    if ('applicable_basis_delivered', HANDOFF_AMOUNT) not in terms:
        raise ValueError('The frozen A handoff term must remain exactly 0.2')
    provider, wid = spec.get('basis_provider', 'provider'), spec['work_id']
    required = evidence.start['work_items'][wid]['requirement_version']
    start_handoffs = evidence.start.get('handoffs', {})
    history = {e['event_id']: e for e in evidence.state['event_history']}
    basis_object = evidence.start['workspaces'][spec['project_id']]['basis']

    def applicable(reference):
        if reference is None or reference[0] != basis_object:
            return False
        meta = _rows(evidence.document(reference)['tables']['basis_meta'])
        return len(meta) == 1 and meta[0]['period'] == spec['period'] and meta[0]['edition'] == 'approved'

    successful = [e for e in evidence.successful
                  if e['worker_id'] == provider and e['payload']['action'] == 'handoff_information']
    for event in sorted(evidence.events, key=lambda e: e['sequence']):
        if event['kind'] != 'environment_event':
            continue
        applied = event['payload']
        if applied.get('kind') != 'manual_handoff' or applied.get('outcome') != 'applied':
            continue
        if history.get(applied.get('event_id')) != applied:
            raise ValueError('Recorded delivery differs from its actual WorldCore event receipt')
        detail = applied.get('payload', {})
        hid = detail.get('handoff_id')
        reference = _ref(detail.get('reference'))
        if (hid in start_handoffs or detail.get('origin') != 'member_action'
                or detail.get('route_id') != 'basis' or detail.get('sender') != provider
                or detail.get('recipients') != ['implementer'] or detail.get('work_item_id') != wid
                or detail.get('requirement_version') != required
                or detail.get('project_id') != spec['project_id']
                or detail.get('response_status') != 'delivered'
                or not applicable(reference)):
            continue
        calls = [call for call in successful if call['sequence'] < event['sequence']
                 and call['payload']['response']['result'].get('handoff_id') == hid
                 and call['payload']['response']['result'].get('event_id') == applied['event_id']
                 and call['payload']['response']['result'].get('created') is True
                 and _ref(call['payload']['arguments'].get('reference')) == reference]
        if len(calls) != 1:
            continue
        call = calls[0]
        reads = evidence.read_before(provider, reference, call['sequence'])
        if not reads:
            continue
        return {'term_id': 'applicable_basis_delivered', 'sequence': event['sequence'],
                'amount': HANDOFF_AMOUNT, 'settlement': 'event',
                'source': {'handoff_id': hid, 'event_id': applied['event_id'],
                    'event_sha256': digest(json_bytes(applied)), 'reference': list(reference),
                    'command_id': call['payload']['response']['command_id'],
                    'action_sequence': call['sequence'],
                    'read_sequences': [row['sequence'] for row in reads],
                    'read_command_ids': [row['payload']['response']['command_id'] for row in reads],
                    'selection_uses_terminal_outcome': False}}
    return None


def ledger_from_evidence(evidence, reward):
    if (reward.get('eligible') is not True or type(reward.get('reward')) not in (float, int)
            or not math.isfinite(reward['reward']) or not evidence.events):
        raise ValueError('Known finite terminal reward and actual episode events required')
    if (reward.get('episode_id') != evidence.manifest['episode_id']
            or reward.get('manifest_sha256') != digest((evidence.root / 'manifest.json').read_bytes())):
        raise ValueError('Credit ledger must bind the exact original closed episode')
    terminal = max(event['sequence'] for event in evidence.events)
    handoff = first_applicable_handoff(evidence)
    paid = handoff['amount'] if handoff else 0
    events = [handoff] if handoff else []
    events.append({'term_id': 'terminal_contract_reconciliation', 'sequence': terminal,
        'amount': round(float(reward['reward']) - paid, 10), 'settlement': 'terminal',
        'source': {'episode_manifest_sha256': reward['manifest_sha256'],
                   'terminal_reward': reward['reward'], 'previously_paid': paid}})
    ledger = {'version': VERSION, 'events': events, 'terminal_sequence': terminal,
        'total': reward['reward'], 'changes_terminal_reward': False,
        'preparation_credit': False, 'duplicate_delivery_credit': False,
        'selection_uses_terminal_outcome': False,
        'rule': 'First applicable current-episode applied handoff settles 0.2; terminal settles R minus 0.2 without clipping. Other tasks settle only R at terminal.'}
    # Reuse the learner's original conservation/location gate, including negatives.
    joint_return({**reward, 'ledger': ledger}, min(e['sequence'] for e in evidence.events),
                 'joint_reward_to_go', evidence.events)
    return ledger


def attach_ledger(reward, episode):
    """Return one shared historical reward for both consumption recipes."""
    root = Path(episode).resolve()
    assessment = assess_historical_episode(root)
    if assessment.get('assessment_execution', {}).get('status') != 'complete':
        raise ValueError('Actual immutable episode evidence required for credit ledger')
    evidence = RetailEvidence(root, reward['spec'], assessment)
    result = copy.deepcopy(reward)
    result['ledger'] = ledger_from_evidence(evidence, reward)
    result['credit'] = 'Same factual ledger and terminal R for both branches; consumption declares MC or Handoff-RTG.'
    return result
