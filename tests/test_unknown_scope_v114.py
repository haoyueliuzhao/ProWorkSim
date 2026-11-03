"""Necessary recovery identity/capacity controls, with no model or resource execution."""
import copy
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v114 as scope
from proworksim import software_benchmark_episode_recovery_v114 as episode
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_alignment_contract_v110 import VERSION as ALIGNMENT_VERSION


def test_exact_recovery_plan_separates_four_first_calls_from_four_existing_candidates():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    assert {r['slot_index'] for r in plan['generation_rows']}=={7238,7239,7266,7267}
    assert {r['row']['slot_index'] for r in plan['score_recoveries']}=={7232,7244,7251,7283}
    assert {r['kind'] for r in plan['score_recoveries']}=={'original_locked','recovered_stopped_code'}
    assert plan['resource_role_counts']=={'actor':4,'controller':4,'volume':4,'score':8,'delivery_score':2,'control':8}
    assert scope.CONSTRAINTS['maximum_containers']==26
    assert scope.CONSTRAINTS['maximum_named_volumes']==4
    altered=copy.deepcopy(plan)
    altered['generation_rows'][0]=next(r for r in plan['rows'] if r['slot_index']==7244)
    with pytest.raises(PermissionError):
        scope.validate_plan(altered)


def test_actual_episode_rejects_model_replay_before_resource_admission(monkeypatch):
    auth={'status':'approved','execution_alignment_version':ALIGNMENT_VERSION,
          'source_index':{'fixture':True},'plan':reference(scope.PLAN_FILE)}
    monkeypatch.setattr(scope,'require_allowed',lambda *_a,**_kw:auth)
    impl=episode.build_episode()
    plan=scope.load(auth['plan'])
    for row in plan['generation_rows']:
        _,_,limits=impl._row_and_config(row,False)
        assert limits['input_plus_output_tokens']==5_000_000
    for spec in plan['score_recoveries']:
        with pytest.raises(PermissionError,match='resampled'):
            impl._row_and_config(spec['row'],False)
    assert impl.integration_points['effective_deadline']==1


def test_four_pair_and_two_grader_capacity_is_forty_cpu_and_192_gib(monkeypatch):
    lanes=[set(scope.cpu_set('coordinator').split(','))]
    lanes.extend(set(scope.cpu_set(role,index).split(','))
                 for index in range(4) for role in ('actor','controller'))
    lanes.extend(set(scope.cpu_set('grader',index).split(',')) for index in range(2))
    assert sum(map(len,lanes))==len(set().union(*lanes))==40
    monkeypatch.setattr(scope,'dispatch_view',lambda:SimpleNamespace(physical_capacity=lambda:{
        'passed':True,'memory_available_bytes':1024*scope.GIB,'disk_free_bytes':2048*scope.GIB}))
    active=[{'spec':{'role':'actor'},'reserved_cpu':6,'reserved_memory_bytes':32*scope.GIB} for _ in range(4)]
    active.append({'spec':{'role':'score'},'reserved_cpu':4,'reserved_memory_bytes':16*scope.GIB})
    value=scope._budget(active,4,16*scope.GIB)
    assert value['reserved_cpu_after']==40 and value['reserved_memory_bytes_after']==192*scope.GIB
    with pytest.raises(scope.ResourceBusy):
        scope._budget(active,6,32*scope.GIB)
