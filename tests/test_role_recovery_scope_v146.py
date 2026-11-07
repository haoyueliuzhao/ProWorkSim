"""No-runtime checks for new identities, bounded inventory and retry gates."""
import copy

import pytest

from proworksim import software_benchmark_alignment_contract_v146 as alignment
from proworksim import software_benchmark_scope_v146 as scope


def plan():
    return scope.load(scope.reference(scope.PLAN_FILE))


def test_frozen_recovery_enumerates_conditional_rounds_without_adding_budget():
    value=scope.validate_plan(plan())
    assert len([r for r in value['rows'] if r['recovery_round']==1]) == 21
    assert len([r for r in value['rows'] if r['recovery_round']==2]) == 21
    assert value['resource_role_counts'] == {'actor':42,'controller':42,'volume':42,'score':84,'delivery_score':84}
    assert scope.CONSTRAINTS['maximum_containers']==252
    assert scope.CASH_CAP_CNY=='99.1863482'
    assert scope.ORIGINAL_TOTAL_CAP_CNY=='450.00'
    assert scope.CONSTRAINTS['maximum_combined_reserved_memory_bytes']==456*scope.GIB


def test_new_attempt_cannot_change_old_model_condition_seed_or_roster():
    row=plan()['rows'][0]
    alignment.validate_plan_identity(row)
    for key,value in [('fixed_members',['member_002']),('seed',row['seed']+1),
                      ('slot_id',row['original_slot_id']),('recovery_round',2)]:
        bad={**row,key:value}
        with pytest.raises(ValueError):
            alignment.validate_plan_identity(bad)


def test_environment_controls_cannot_be_silently_added():
    value=copy.deepcopy(plan())
    value['resources']['control-unplanned']={'role':'control'}
    with pytest.raises(PermissionError):
        scope.validate_plan(value)


def test_cpu_partitions_fit64_cores_without_overlap():
    pools=[scope.cpu_set('coordinator')]
    pools.extend(scope.cpu_set(role,lane) for lane in range(8) for role in ('actor','controller'))
    pools.extend(scope.cpu_set('grader',lane) for lane in range(2))
    cpus=[int(c) for p in pools for c in p.split(',')]
    assert len(cpus)==len(set(cpus))==64


def test_conditional_generation_cannot_start_without_admission_proof(tmp_path,monkeypatch):
    monkeypatch.setattr(scope,'API_ROOT',tmp_path)
    row=next(r for r in plan()['rows'] if r['recovery_round']==2)
    with pytest.raises(FileNotFoundError):
        scope.validate_second_attempt_admission(row['slot_id'])
