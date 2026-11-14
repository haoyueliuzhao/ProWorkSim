"""Frozen five-organization evaluation contract; no resources or API are started."""
from __future__ import annotations

import copy
import re

from . import software_benchmark_alignment_contract_v130 as single
from .software_fixed_organization_v104 import catalog, validate_organization
from .storage import digest, json_bytes

VERSION = 'v131-five-fixed-organization-evaluation-r1'
GROUP_IDS = ('CHIEF', 'PIPELINE', 'REVIEW', 'SPRINT', 'MATRIX')
TEAM_TOKEN_BUDGET = 5_000_000
GROUP_CASH_CAP_CNY = '100.00'


def organization(group):
    if group not in GROUP_IDS:
        raise ValueError('Only the five previously implemented organizations are selected')
    return copy.deepcopy(validate_organization(next(row for row in catalog() if row['id'] == group)))


def shared_strategy(group):
    spec = organization(group)
    base = single.shared_strategy()
    base.update(version=VERSION)
    base['final_review'].update(scope='once_per_member_per_episode',
        maximum=spec['member_count'], maximum_per_member=1, shared_pool=True)
    base['history'].update(scope='one_private_conversation_per_member',
        other_members_private_history_visible=False)
    base['organization'] = {'id': group, 'member_count': spec['member_count'],
        'specification_sha256': digest(json_bytes(spec)), 'dynamic_membership': False,
        'schedule': 'persisted_eligibility_then_fair_round_robin_single_writer',
        'sprint_opportunities': 24 if group == 'SPRINT' else None,
        'sprint_quota_frozen': group == 'SPRINT',
        'member_done_is_team_done': False,
        'team_stop': 'no_reachable_member_or_budget_or_deadline_or_organization_blocked',
        'delivery_member': 'member_001', 'best_of_members': False}
    return base


def condition(group):
    spec = organization(group)
    base = single.condition('PROJECT')
    name = f'DEEPSEEK_NT_{group}_TEAM_B5000K'
    base.update(version='v131-fixed-organization-condition-r1',
        condition_id=name, group_id=group, organization_id=group,
        single_agent=False, fixed_members=spec['fixed_members'], member_count=spec['member_count'],
        fixed_organization=spec, execution_strategy=shared_strategy(group),
        code_endpoint='member_001_terminal_code', delivery_endpoint='member_001_last_legal_delivery')
    base['episode_limits']['input_plus_output_tokens'] = TEAM_TOKEN_BUDGET
    base['retained_interface_differences'].update(tool_family='managed_fixed_organization',
        organization_contracts_enforced=True)
    return base


def validate_condition(value):
    if not isinstance(value, dict) or value != condition(value.get('organization_id')):
        raise ValueError('The frozen organization, model, shared budget or strategy changed')
    return {**value['episode_limits'], 'context_limit': value['inference']['total_context']}


def validate_plan_identity(row):
    group = row.get('organization_id')
    expected = condition(group)
    task, seed = row.get('instance_id'), row.get('seed')
    if (not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+', task)
            or type(seed) is not int or seed < 0
            or row.get('group_id') != group or row.get('condition_id') != expected['condition_id']
            or row.get('slot_id') != f"v131:{task}:{expected['condition_id']}:{seed}"
            or row.get('arm') != 'PROJECT' or row.get('execution_arm') != 'PROJECT'
            or row.get('fixed_members') != expected['fixed_members']):
        raise ValueError('Bind the new task, organization, fixed registry and seed identity')
    return row


def validate_controller_identity(config, arm='PROJECT'):
    group = config.get('organization_id')
    task = config.get('public_task', {}).get('instance_id')
    row = {**config, 'instance_id': task, 'arm': arm}
    validate_plan_identity(row)
    if (arm != 'PROJECT' or config.get('execution_alignment') != shared_strategy(group)
            or not re.fullmatch(r'[0-9a-f]{64}', config.get('public_test_contract_sha256', ''))):
        raise ValueError('Bind the exact team execution and public-test contracts')
    return config


def initial_message(problem_statement, *, public_context=''):
    return single.initial_message(problem_statement, public_context=public_context)
