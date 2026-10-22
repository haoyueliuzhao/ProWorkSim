"""Independent all-arm client binding for the reviewed r4 monetary policy.

Only a private future coordinator/controller process changes module bindings;
all on-disk r1/r3 implementation files and existing workers remain untouched.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from . import software_benchmark_deepseek_api_v055 as old_api
from . import software_benchmark_deepseek_api_v055_r4 as new_api
from .software_benchmark_candidates_v054 import checked,reference
from .software_benchmark_queue_v055 import ROOT,load

VERSION='v055-all-arm-budget-policy-activation-r4'
ARMS={'REF','MATCH','PROJECT'}


def policy_sha256():
    raw=json.dumps({**new_api.POLICY,'max_concurrency':64},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_activation(ref):
    value=load(ref)
    if (value.get('version')!=VERSION or value.get('admitted') is not True or set(value.get('arms',[]))!=ARMS
            or value.get('budget_policy_sha256')!=policy_sha256()
            or not isinstance(value.get('runtime_revision'),str) or not value['runtime_revision']
            or load(value['qualification']).get('passed') is not True):
        raise ValueError('All-arm r4 monetary runtime lacks its independent qualified identity')
    for item in value['files']:checked(item)
    for field,name in (('generation_entrypoint','run_deepseek_episode_v055_r4.py'),
                       ('controller_entrypoint','run_deepseek_controller_v055_r4.py')):
        path=checked(value[field])
        if value[field] not in value['files'] or path.name!=name or not path.is_relative_to(ROOT/'tools'):
            raise ValueError('Monetary runtime entry is outside its immutable source seal')
    previous=load(value['previous_native_activation'])
    if (previous.get('version')!='v055-native-solver-activation-r3' or previous.get('admitted') is not True
            or set(previous.get('arms',[]))!={'REF','MATCH'}):
        raise ValueError('Original qualified native reasoning runtime must be retained')
    expected=ROOT/'tools/run_deepseek_controller_v055.py'
    if value['original_project_controller']!=reference(expected):
        raise ValueError('Project scientific controller implementation changed')
    if reference(new_api.__file__) not in value['files']:
        raise ValueError('Actual new API implementation is not frozen in activation')
    return value


def controller_target(config,activation):
    if (config['arm'] not in ARMS or config['runtime_revision']!=activation['runtime_revision']):
        raise ValueError('Future controller arm/revision differs from activation')
    if config['arm']=='PROJECT':return checked(activation['original_project_controller'])
    previous=load(activation['previous_native_activation'])
    return checked(previous['controller_entrypoint'])


@contextmanager
def bind_controller_client():
    before=old_api.DeepSeekClient
    old_api.DeepSeekClient=new_api.DeepSeekClient
    try:yield {'client':new_api.DeepSeekClient,'ledger':new_api.BudgetLedger}
    finally:old_api.DeepSeekClient=before
