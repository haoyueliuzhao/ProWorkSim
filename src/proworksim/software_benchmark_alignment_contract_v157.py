"""Frozen communication treatment on one unchanged REVIEW2 organization."""
from __future__ import annotations
import copy
import re
from . import software_benchmark_alignment_contract_v141 as original
VERSION = 'v157-review2-communication-pilot-alignment-r1'
GROUP_IDS = ('C0', 'C1', 'C2')
TEAM_TOKEN_BUDGET = 5_000_000
organization = original.organization
initial_message = original.initial_message

def shared_strategy(group='REVIEW2'):
    if group != 'REVIEW2':
        raise ValueError('Communication conditions do not change REVIEW2 organization')
    return original.shared_strategy('REVIEW2')

def condition(group):
    if group not in GROUP_IDS:
        raise ValueError('Unknown communication condition')
    value = copy.deepcopy(original.condition('REVIEW2'))
    value.update(version=VERSION, condition_id=f'DEEPSEEK_NT_REVIEW2_{group}_V157_B5000K',
        group_id=group, communication_condition=group)
    value['communication'] = {'condition':group, 'revision':'v157',
        'shared_team_budget_includes':['agent','condenser','compressor'],
        'provider_usage_authoritative':True, 'source_tokens_are_estimates':True,
        'routing_timing_role_permissions_history_algorithm_unchanged':True}
    return value

def validate_condition(value):
    if not isinstance(value,dict) or value != condition(value.get('group_id')):
        raise ValueError('Communication condition differs from the frozen configuration')
    return {**value['episode_limits'],'context_limit':value['inference']['total_context']}

def validate_plan_identity(row):
    expected=condition(row.get('group_id'))
    task,seed=row.get('instance_id'),row.get('seed')
    if (not isinstance(task,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+',task)
        or type(seed) is not int or seed<0 or row.get('organization_id')!='REVIEW2'
        or row.get('condition_id')!=expected['condition_id']
        or row.get('slot_id')!=f"v157:{task}:REVIEW2_{row['group_id']}:{seed}"
        or row.get('arm')!='PROJECT' or row.get('execution_arm')!='PROJECT'
        or row.get('fixed_members')!=expected['fixed_members'] or row.get('member_count')!=2):
        raise ValueError('Bind exact task, communication condition, seed and two-member REVIEW2 roster')
    if row.get('communication_condition',row['group_id'])!=row['group_id']:
        raise ValueError('Communication selector differs from the group')
    return row

def validate_controller_identity(config, arm='PROJECT'):
    validate_plan_identity({**config,'instance_id':config.get('public_task',{}).get('instance_id'),'arm':arm})
    if (arm!='PROJECT' or config.get('execution_alignment')!=shared_strategy()
        or not re.fullmatch('[0-9a-f]{64}',config.get('public_test_contract_sha256',''))):
        raise ValueError('Controller lost exact public tests or invariant REVIEW2 policy')
    return config
