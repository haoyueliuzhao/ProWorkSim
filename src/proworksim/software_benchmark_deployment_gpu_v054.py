"""Deployment-only GPU selection; original numerical capacity thresholds stay fixed."""
from __future__ import annotations

import re

UUID = re.compile(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')


def validate_card_identity(card):
    if (type(card.get('index')) is not int or not 0 <= card['index'] <= 7
            or UUID.fullmatch(card.get('uuid', '')) is None):
        raise ValueError('An observed physical index 0..7 and exact GPU UUID are required')


def eligible_deployment_gpus(rows, mode):
    if mode not in {'REF', 'MATCH', 'PROJECT', 'MATCH_PROJECT'}:
        raise ValueError('Unknown frozen numerical mode')
    seen_indices, seen_uuids, eligible = set(), set(), []
    threshold = 66560 if mode == 'REF' else 46080
    for card in rows:
        validate_card_identity(card)
        if card['index'] in seen_indices or card['uuid'] in seen_uuids:
            raise ValueError('Ambiguous physical GPU observation')
        seen_indices.add(card['index'])
        seen_uuids.add(card['uuid'])
        if (type(card.get('free_mib')) is not int or type(card.get('total_mib')) is not int
                or not 0 <= card['free_mib'] <= card['total_mib']):
            raise ValueError('Actual memory values are required')
        if (mode == 'REF' and card['index'] != 7) or card['total_mib'] < 81920:
            continue
        if card['free_mib'] >= threshold and any(kind in card['name'] for kind in ('A100', 'A800')):
            eligible.append(card)
    # Co-resident jobs and utilization are deliberately not exclusion criteria.
    return sorted(eligible, key=lambda row: (-row['free_mib'], row['index']))


def select_deployment_card(rows, expected, mode):
    validate_card_identity(expected)
    matching = [row for row in rows if row.get('index') == expected['index']]
    if len(matching) != 1 or matching[0].get('uuid') != expected['uuid']:
        raise ValueError('Registered physical index now resolves to a different GPU UUID')
    eligible = eligible_deployment_gpus(rows, mode)
    for card in eligible:
        if card['uuid'] == expected['uuid']:
            return card
    raise BlockingIOError('The original numerical free-memory threshold is not currently met')


def eligible_match_cards(rows, policy):
    if (policy.get('minimum_free_mib') != 46080 or policy.get('minimum_total_mib') != 81920
            or policy.get('physical_gpus') != list(range(8))
            or policy.get('maximum_residents') != 8 or policy.get('allow_co_residency') is not True
            or policy.get('require_idle') is not False):
        raise ValueError('Dynamic deployment cannot change the numerical capacity gate')
    return [card for card in eligible_deployment_gpus(rows, 'MATCH_PROJECT')
            if card['name'] in policy['allowed_gpu_names']]


def raw_owner_resource_binding(card):
    select_deployment_card([card], card, 'MATCH_PROJECT')
    return {'version': 'software-learning-resources-v0.50-r3', 'gpu_index': card['index'],
            'gpu_uuid': card['uuid'], 'sampled_free_mib': card['free_mib'],
            'target_mib': min(73728, card['free_mib'] - 1024)}


def runtime_gpu_arguments(card):
    validate_card_identity(card)
    return ['--gpu', str(card['index'])]
