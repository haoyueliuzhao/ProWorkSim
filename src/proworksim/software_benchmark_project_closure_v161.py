"""Exact original delivery logic with only the14 explicitly authorized new IDs."""
from types import FunctionType
from . import software_benchmark_project_closure_v157 as original
from .software_benchmark_alignment_contract_v161 import identity_for,condition,validate_plan_identity
VERSION=original.VERSION
DEPLOYMENT_VERSION='v161-independent-identity-same-delivery-contract-r1'

def validate_slot_identity(slot_id,instance_id):
    item=identity_for(slot_id,instance_id);expected=condition(item['group_id'])
    row={'slot_id':slot_id,'instance_id':instance_id,'condition_id':expected['condition_id'],
        'seed':item['seed'],'organization_id':'REVIEW2','group_id':item['group_id'],
        'arm':'PROJECT','execution_arm':'PROJECT','fixed_members':expected['fixed_members'],'member_count':2}
    validate_plan_identity(row)
    return row

def _bind(function,namespace):
    value=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    value.__kwdefaults__=function.__kwdefaults__
    return value

_base_validate=_bind(original._base_validate,{**original._base_validate.__globals__,
    'validate_slot_identity':validate_slot_identity})
_namespace={**vars(original),'__file__':__file__,'validate_slot_identity':validate_slot_identity,
    'validate_plan_identity':validate_plan_identity,'_base_validate':_base_validate}
validate_delivery_evidence=_bind(original.validate_delivery_evidence,_namespace)
_namespace['validate_delivery_evidence']=validate_delivery_evidence
export_managed_closure=_bind(original.export_managed_closure,_namespace)
