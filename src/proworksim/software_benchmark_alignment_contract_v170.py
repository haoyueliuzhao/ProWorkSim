"""Exact thirteen independent recovery identities; all treatment settings stay v157."""
from __future__ import annotations
import copy
from . import software_benchmark_alignment_contract_v157 as original
VERSION=original.VERSION
GROUP_IDS=original.GROUP_IDS
TEAM_TOKEN_BUDGET=original.TEAM_TOKEN_BUDGET
organization=original.organization
initial_message=original.initial_message
shared_strategy=original.shared_strategy
condition=original.condition
validate_condition=original.validate_condition
RECOVERY_SUFFIX=':completion-recovery-v170'
RECOVERY_IDENTITIES=[{'instance_id': 'psf__requests-1142', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560005, 'original_slot_id': 'v157:psf__requests-1142:REVIEW2_C0:2026110801560005', 'recovery_slot_id': 'v157:psf__requests-1142:REVIEW2_C0:2026110801560005:completion-recovery-v170', 'original_slot_index': 15715, 'slot_index': 17000}, {'instance_id': 'sphinx-doc__sphinx-7462', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560006, 'original_slot_id': 'v157:sphinx-doc__sphinx-7462:REVIEW2_C0:2026110801560006', 'recovery_slot_id': 'v157:sphinx-doc__sphinx-7462:REVIEW2_C0:2026110801560006:completion-recovery-v170', 'original_slot_index': 15718, 'slot_index': 17001}, {'instance_id': 'pydata__xarray-3151', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560009, 'original_slot_id': 'v157:pydata__xarray-3151:REVIEW2_C0:2026110801560009', 'recovery_slot_id': 'v157:pydata__xarray-3151:REVIEW2_C0:2026110801560009:completion-recovery-v170', 'original_slot_index': 15729, 'slot_index': 17002}, {'instance_id': 'pytest-dev__pytest-5631', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C2_V157_B5000K', 'group_id': 'C2', 'seed': 2026110801560010, 'original_slot_id': 'v157:pytest-dev__pytest-5631:REVIEW2_C2:2026110801560010', 'recovery_slot_id': 'v157:pytest-dev__pytest-5631:REVIEW2_C2:2026110801560010:completion-recovery-v170', 'original_slot_index': 15730, 'slot_index': 17003}, {'instance_id': 'pytest-dev__pytest-5631', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560010, 'original_slot_id': 'v157:pytest-dev__pytest-5631:REVIEW2_C0:2026110801560010', 'recovery_slot_id': 'v157:pytest-dev__pytest-5631:REVIEW2_C0:2026110801560010:completion-recovery-v170', 'original_slot_index': 15731, 'slot_index': 17004}, {'instance_id': 'pytest-dev__pytest-5631', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C1_V157_B5000K', 'group_id': 'C1', 'seed': 2026110801560010, 'original_slot_id': 'v157:pytest-dev__pytest-5631:REVIEW2_C1:2026110801560010', 'recovery_slot_id': 'v157:pytest-dev__pytest-5631:REVIEW2_C1:2026110801560010:completion-recovery-v170', 'original_slot_index': 15732, 'slot_index': 17005}, {'instance_id': 'django__django-17087', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560020, 'original_slot_id': 'v157:django__django-17087:REVIEW2_C0:2026110801560020', 'recovery_slot_id': 'v157:django__django-17087:REVIEW2_C0:2026110801560020:completion-recovery-v170', 'original_slot_index': 15760, 'slot_index': 17006}, {'instance_id': 'django__django-17087', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C2_V157_B5000K', 'group_id': 'C2', 'seed': 2026110801560020, 'original_slot_id': 'v157:django__django-17087:REVIEW2_C2:2026110801560020', 'recovery_slot_id': 'v157:django__django-17087:REVIEW2_C2:2026110801560020:completion-recovery-v170', 'original_slot_index': 15761, 'slot_index': 17007}, {'instance_id': 'django__django-17087', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C1_V157_B5000K', 'group_id': 'C1', 'seed': 2026110801560020, 'original_slot_id': 'v157:django__django-17087:REVIEW2_C1:2026110801560020', 'recovery_slot_id': 'v157:django__django-17087:REVIEW2_C1:2026110801560020:completion-recovery-v170', 'original_slot_index': 15762, 'slot_index': 17008}, {'instance_id': 'matplotlib__matplotlib-22871', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C2_V157_B5000K', 'group_id': 'C2', 'seed': 2026110801560022, 'original_slot_id': 'v157:matplotlib__matplotlib-22871:REVIEW2_C2:2026110801560022', 'recovery_slot_id': 'v157:matplotlib__matplotlib-22871:REVIEW2_C2:2026110801560022:completion-recovery-v170', 'original_slot_index': 15766, 'slot_index': 17009}, {'instance_id': 'matplotlib__matplotlib-22871', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C1_V157_B5000K', 'group_id': 'C1', 'seed': 2026110801560022, 'original_slot_id': 'v157:matplotlib__matplotlib-22871:REVIEW2_C1:2026110801560022', 'recovery_slot_id': 'v157:matplotlib__matplotlib-22871:REVIEW2_C1:2026110801560022:completion-recovery-v170', 'original_slot_index': 15767, 'slot_index': 17010}, {'instance_id': 'matplotlib__matplotlib-22871', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560022, 'original_slot_id': 'v157:matplotlib__matplotlib-22871:REVIEW2_C0:2026110801560022', 'recovery_slot_id': 'v157:matplotlib__matplotlib-22871:REVIEW2_C0:2026110801560022:completion-recovery-v170', 'original_slot_index': 15768, 'slot_index': 17011}, {'instance_id': 'pydata__xarray-7233', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C1_V157_B5000K', 'group_id': 'C1', 'seed': 2026110801560023, 'original_slot_id': 'v157:pydata__xarray-7233:REVIEW2_C1:2026110801560023', 'recovery_slot_id': 'v157:pydata__xarray-7233:REVIEW2_C1:2026110801560023:completion-recovery-v170', 'original_slot_index': 15769, 'slot_index': 17012}]
BY_SLOT={r['recovery_slot_id']:r for r in RECOVERY_IDENTITIES}

def identity_for(slot_id,instance_id=None):
    item=BY_SLOT.get(slot_id)
    if item is None or instance_id not in (None,item['instance_id']):
        raise ValueError('Only thirteen explicitly named independent technical attempts may enter')
    return copy.deepcopy(item)

def validate_plan_identity(row):
    item=identity_for(row.get('slot_id'),row.get('instance_id'))
    if any(row.get(k)!=item[k] for k in ('seed','condition_id','group_id')):
        raise ValueError('Independent recovery changed task, seed or communication condition')
    if 'slot_index' in row and row['slot_index']!=item['slot_index']:
        raise ValueError('Independent physical resource identity changed')
    original.validate_plan_identity({**row,'slot_id':item['original_slot_id']})
    return row

def validate_controller_identity(config,arm='PROJECT'):
    identity_for(config.get('slot_id'),config.get('public_task',{}).get('instance_id'))
    validate_plan_identity({**config,'instance_id':config.get('public_task',{}).get('instance_id'),'arm':arm})
    item=identity_for(config['slot_id'])
    original.validate_controller_identity({**config,'slot_id':item['original_slot_id']},arm)
    return config
