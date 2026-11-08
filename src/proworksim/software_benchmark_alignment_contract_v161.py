"""Exact fourteen independent recovery identities; all treatment settings stay v157."""
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
RECOVERY_SUFFIX=':independent-technical-recovery-r1'
RECOVERY_IDENTITIES=[{'instance_id': 'astropy__astropy-14369', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C1_V157_B5000K', 'group_id': 'C1', 'seed': 2026110801560000, 'original_slot_id': 'v157:astropy__astropy-14369:REVIEW2_C1:2026110801560000', 'recovery_slot_id': 'v157:astropy__astropy-14369:REVIEW2_C1:2026110801560000:independent-technical-recovery-r1', 'original_slot_index': 15700, 'slot_index': 16100}, {'instance_id': 'astropy__astropy-14369', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560000, 'original_slot_id': 'v157:astropy__astropy-14369:REVIEW2_C0:2026110801560000', 'recovery_slot_id': 'v157:astropy__astropy-14369:REVIEW2_C0:2026110801560000:independent-technical-recovery-r1', 'original_slot_index': 15701, 'slot_index': 16101}, {'instance_id': 'astropy__astropy-14369', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C2_V157_B5000K', 'group_id': 'C2', 'seed': 2026110801560000, 'original_slot_id': 'v157:astropy__astropy-14369:REVIEW2_C2:2026110801560000', 'recovery_slot_id': 'v157:astropy__astropy-14369:REVIEW2_C2:2026110801560000:independent-technical-recovery-r1', 'original_slot_index': 15702, 'slot_index': 16102}, {'instance_id': 'sympy__sympy-17318', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C2_V157_B5000K', 'group_id': 'C2', 'seed': 2026110801560001, 'original_slot_id': 'v157:sympy__sympy-17318:REVIEW2_C2:2026110801560001', 'recovery_slot_id': 'v157:sympy__sympy-17318:REVIEW2_C2:2026110801560001:independent-technical-recovery-r1', 'original_slot_index': 15704, 'slot_index': 16103}, {'instance_id': 'sympy__sympy-17318', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560001, 'original_slot_id': 'v157:sympy__sympy-17318:REVIEW2_C0:2026110801560001', 'recovery_slot_id': 'v157:sympy__sympy-17318:REVIEW2_C0:2026110801560001:independent-technical-recovery-r1', 'original_slot_index': 15705, 'slot_index': 16104}, {'instance_id': 'scikit-learn__scikit-learn-25102', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C2_V157_B5000K', 'group_id': 'C2', 'seed': 2026110801560002, 'original_slot_id': 'v157:scikit-learn__scikit-learn-25102:REVIEW2_C2:2026110801560002', 'recovery_slot_id': 'v157:scikit-learn__scikit-learn-25102:REVIEW2_C2:2026110801560002:independent-technical-recovery-r1', 'original_slot_index': 15706, 'slot_index': 16105}, {'instance_id': 'scikit-learn__scikit-learn-25102', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C1_V157_B5000K', 'group_id': 'C1', 'seed': 2026110801560002, 'original_slot_id': 'v157:scikit-learn__scikit-learn-25102:REVIEW2_C1:2026110801560002', 'recovery_slot_id': 'v157:scikit-learn__scikit-learn-25102:REVIEW2_C1:2026110801560002:independent-technical-recovery-r1', 'original_slot_index': 15707, 'slot_index': 16106}, {'instance_id': 'scikit-learn__scikit-learn-25102', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560002, 'original_slot_id': 'v157:scikit-learn__scikit-learn-25102:REVIEW2_C0:2026110801560002', 'recovery_slot_id': 'v157:scikit-learn__scikit-learn-25102:REVIEW2_C0:2026110801560002:independent-technical-recovery-r1', 'original_slot_index': 15708, 'slot_index': 16107}, {'instance_id': 'mwaskom__seaborn-3187', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560003, 'original_slot_id': 'v157:mwaskom__seaborn-3187:REVIEW2_C0:2026110801560003', 'recovery_slot_id': 'v157:mwaskom__seaborn-3187:REVIEW2_C0:2026110801560003:independent-technical-recovery-r1', 'original_slot_index': 15709, 'slot_index': 16108}, {'instance_id': 'mwaskom__seaborn-3187', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C2_V157_B5000K', 'group_id': 'C2', 'seed': 2026110801560003, 'original_slot_id': 'v157:mwaskom__seaborn-3187:REVIEW2_C2:2026110801560003', 'recovery_slot_id': 'v157:mwaskom__seaborn-3187:REVIEW2_C2:2026110801560003:independent-technical-recovery-r1', 'original_slot_index': 15710, 'slot_index': 16109}, {'instance_id': 'mwaskom__seaborn-3187', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C1_V157_B5000K', 'group_id': 'C1', 'seed': 2026110801560003, 'original_slot_id': 'v157:mwaskom__seaborn-3187:REVIEW2_C1:2026110801560003', 'recovery_slot_id': 'v157:mwaskom__seaborn-3187:REVIEW2_C1:2026110801560003:independent-technical-recovery-r1', 'original_slot_index': 15711, 'slot_index': 16110}, {'instance_id': 'matplotlib__matplotlib-20676', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C1_V157_B5000K', 'group_id': 'C1', 'seed': 2026110801560004, 'original_slot_id': 'v157:matplotlib__matplotlib-20676:REVIEW2_C1:2026110801560004', 'recovery_slot_id': 'v157:matplotlib__matplotlib-20676:REVIEW2_C1:2026110801560004:independent-technical-recovery-r1', 'original_slot_index': 15712, 'slot_index': 16111}, {'instance_id': 'matplotlib__matplotlib-20676', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C2_V157_B5000K', 'group_id': 'C2', 'seed': 2026110801560004, 'original_slot_id': 'v157:matplotlib__matplotlib-20676:REVIEW2_C2:2026110801560004', 'recovery_slot_id': 'v157:matplotlib__matplotlib-20676:REVIEW2_C2:2026110801560004:independent-technical-recovery-r1', 'original_slot_index': 15713, 'slot_index': 16112}, {'instance_id': 'matplotlib__matplotlib-20676', 'condition_id': 'DEEPSEEK_NT_REVIEW2_C0_V157_B5000K', 'group_id': 'C0', 'seed': 2026110801560004, 'original_slot_id': 'v157:matplotlib__matplotlib-20676:REVIEW2_C0:2026110801560004', 'recovery_slot_id': 'v157:matplotlib__matplotlib-20676:REVIEW2_C0:2026110801560004:independent-technical-recovery-r1', 'original_slot_index': 15714, 'slot_index': 16113}]
BY_SLOT={r['recovery_slot_id']:r for r in RECOVERY_IDENTITIES}

def identity_for(slot_id,instance_id=None):
    item=BY_SLOT.get(slot_id)
    if item is None or instance_id not in (None,item['instance_id']):
        raise ValueError('Only fourteen explicitly named independent technical attempts may enter')
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
