from types import SimpleNamespace
from proworksim.software_context_capacity_v192 import capacity_status
from proworksim import software_benchmark_scope_v192 as scope

def test_both_existing_filesystems_keep_their_headroom():
    g=1024**3
    policy=SimpleNamespace(CONSTRAINTS=scope.CONSTRAINTS,STORAGE_POLICY=scope.STORAGE_POLICY,host_cpu_pool=lambda:list(range(176)))
    physical={'disk_free_bytes':170*g,'docker_disk_free_bytes':133*g,'memory_available_bytes':800*g,'passed':True}
    active=[{'spec':{'role':'actor'},'reserved_spool_bytes':4*g}]*2
    result=capacity_status(policy,physical=physical,active=active,load1=50)
    assert result['admit'] and result['disk_floor_bytes']==140*g and result['Docker_disk_floor_bytes']==112*g
    assert not capacity_status(policy,physical={**physical,'docker_disk_free_bytes':111*g},active=active,load1=50)['admit']
    assert not capacity_status(policy,physical={**physical,'disk_free_bytes':139*g},active=active,load1=50)['admit']
