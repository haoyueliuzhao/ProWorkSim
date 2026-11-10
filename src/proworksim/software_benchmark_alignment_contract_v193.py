"""Frozen four-policy S1 comparison, sharing actual tools and inference limits."""
import copy
import re
from . import software_benchmark_alignment_contract_v141 as previous

VERSION='v193-s1-context-policy-contract-r1'
GROUP_IDS=('M0','M1-5','M1-10','M1-5K')
RUN_VERSION='v193'
TEAM_TOKEN_BUDGET=5_000_000


def organization(group='S1'):
    if group not in ('S1',*GROUP_IDS):raise ValueError('Only S1 and its four context policies are defined')
    return previous.organization('S1')


def shared_strategy(group):
    if group not in GROUP_IDS:raise ValueError('Unknown context policy')
    from .software_benchmark_alignment_contract_v181 import shared_strategy as old_strategy
    from .software_context_critical_v191 import RULES
    value=old_strategy('M1-5' if group=='M1-5K' else group)
    value.update(version=VERSION)
    value['history'].update(context_condition=group,implementation='v193-private-history-with-v191-critical-events')
    if group=='M1-5K':
        value['history'].update(policy='observation_masking_with_critical_events',critical_event_rules=copy.deepcopy(RULES))

    return value


def condition(group):
    if group not in GROUP_IDS:raise ValueError('Unknown frozen condition')
    value=copy.deepcopy(previous.condition('S1'))
    value.update(version=VERSION,condition_id=f'DEEPSEEK_NT_S1_{group.replace("-","_")}_V193_B5000K',
        group_id=group,context_condition=group,organization_id='S1',execution_strategy=shared_strategy(group))
    return value


def validate_condition(value):
    if not isinstance(value,dict) or value!=condition(value.get('group_id')):raise ValueError('A frozen condition changed')
    return {**value['episode_limits'],'context_limit':value['inference']['total_context']}


def validate_plan_identity(row):
    expected=condition(row.get('group_id'));task,seed=row.get('instance_id'),row.get('seed')
    if (not isinstance(task,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+',task)
        or type(seed)is not int or seed<0 or row.get('organization_id')!='S1'
        or row.get('condition_id')!=expected['condition_id']
        or row.get('slot_id')!=f'v193:{task}:{expected["condition_id"]}:{seed}'
        or row.get('arm')!='PROJECT' or row.get('execution_arm')!='PROJECT'
        or row.get('fixed_members')!=['member_001'] or row.get('member_count')!=1):
        raise ValueError('Task, condition, S1 roster or independent identity changed')
    return row


def validate_controller_identity(config,arm='PROJECT'):
    validate_plan_identity({**config,'arm':arm,'instance_id':config.get('public_task',{}).get('instance_id')})
    if config.get('execution_alignment')!=shared_strategy(config['group_id']):raise ValueError('Controller context policy changed')
    return config


initial_message=previous.initial_message
