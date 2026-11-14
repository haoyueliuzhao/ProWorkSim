"""K0/K1/K2 differ only in role-context selection; all use REVIEW2 authority."""
from __future__ import annotations
import copy
import re
from . import software_benchmark_alignment_contract_v203_2_1 as baseline

VERSION = 'v203.2.3-role-context-common-review2-r1'
RUN_VERSION = 'v203.2.3'
GROUP_IDS = ('K0', 'K1', 'K2')
TEAM_TOKEN_BUDGET = 5_000_000


def organization(group):
    if group not in (*GROUP_IDS, 'REVIEW2'):
        raise ValueError('Unknown context condition or organization')
    return baseline.organization('REVIEW2')


def shared_strategy(group='REVIEW2'):
    organization(group)
    return baseline.shared_strategy('REVIEW2')


def condition(group):
    if group not in GROUP_IDS:
        raise ValueError('An explicit K0/K1/K2 context condition is required')
    value = copy.deepcopy(baseline.condition('REVIEW2'))
    value.update(version=VERSION, condition_id=group, group_id=group, organization_id='REVIEW2',
                 role_context_condition=group, role_context_budget_tokens=4096)
    return value


def validate_condition(value):
    if not isinstance(value, dict) or value != condition(value.get('group_id')):
        raise ValueError('The common REVIEW2 permissions, budget or context treatment changed')
    return {**value['episode_limits'], 'context_limit': value['inference']['total_context']}


def validate_plan_identity(row):
    expected = condition(row.get('group_id'))
    task, seed = row.get('instance_id'), row.get('seed')
    if (not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+', task)
            or type(seed) is not int or seed < 0 or row.get('organization_id') != 'REVIEW2'
            or row.get('condition_id') != expected['condition_id']
            or row.get('condition') != expected['condition_id']
            or row.get('slot_id') != f"{RUN_VERSION}:{task}:{expected['condition_id']}:{seed}"
            or row.get('arm') != 'PROJECT' or row.get('execution_arm') != 'PROJECT'
            or row.get('fixed_members') != ['member_001', 'member_002'] or row.get('member_count') != 2):
        raise ValueError('A context row must bind its frozen issue, condition, seed and REVIEW2 roster')
    return row


def validate_controller_identity(config, arm='PROJECT'):
    validate_plan_identity({**config, 'instance_id': config.get('public_task', {}).get('instance_id'), 'arm': arm})
    if (arm != 'PROJECT' or config.get('execution_alignment') != shared_strategy('REVIEW2')
            or not re.fullmatch(r'[0-9a-f]{64}', config.get('public_test_contract_sha256', ''))):
        raise ValueError('The controller strategy or public-test contract differs')
    return config


initial_message = baseline.initial_message
