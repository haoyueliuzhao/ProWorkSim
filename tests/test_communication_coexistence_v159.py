import copy
from types import SimpleNamespace
import pytest
from proworksim import software_benchmark_scope_v159 as scope
from proworksim.software_benchmark_candidates_v054 import reference

def setup_budget(monkeypatch,old):
    monkeypatch.setattr(scope,'coexistence_status',lambda:{'reserved_old_cpu':26 if old else 0,
        'reserved_old_memory_bytes':176*scope.GIB if old else 0,'maximum_new_generation':11 if old else 16})
    monkeypatch.setattr(scope,'dispatch_view',lambda:SimpleNamespace(physical_capacity=lambda:{
        'memory_available_bytes':2*1024**4,'disk_free_bytes':2*1024**4,'passed':True}))
    monkeypatch.setattr(scope.os,'getloadavg',lambda:(0,0,0))
def claims(actors,graders):
    return [{'spec':{'role':'actor'},'reserved_cpu':6,'reserved_memory_bytes':48*scope.GIB} for _ in range(actors)]+[
        {'spec':{'role':'score'},'reserved_cpu':4,'reserved_memory_bytes':16*scope.GIB} for _ in range(graders)]

def test_overlap_never_exceeds108_cpu776gib_and11_new_pairs(monkeypatch):
    setup_budget(monkeypatch,True)
    value=scope._budget(claims(11,1),4,16*scope.GIB)
    assert value['reserved_cpu_after']==108 and value['reserved_memory_bytes_after']==776*scope.GIB
    with pytest.raises(scope.ResourceBusy):scope._budget(claims(11,0),6,48*scope.GIB)

def test_quiescent_predecessor_allows_original16_with112_cpu840gib(monkeypatch):
    setup_budget(monkeypatch,False)
    value=scope._budget(claims(15,2),6,48*scope.GIB)
    assert value['reserved_cpu_after']==112 and value['reserved_memory_bytes_after']==840*scope.GIB

def test_called_and_uncalled_identity_sets_cannot_overlap():
    plan=scope.load(reference(scope.PLAN_FILE));assert scope.validate_plan(plan)
    broken=copy.deepcopy(plan);broken['used_original_slots'].append(broken['admitted_original_slots'][0])
    with pytest.raises(PermissionError):scope.validate_plan(broken)
