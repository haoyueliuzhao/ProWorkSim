"""Necessary new scope/parent controls; no Docker, privileged action or API."""
import copy
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v131 as scope
from proworksim import software_benchmark_api_parent_v131 as parent
from proworksim import software_benchmark_alignment_contract_v131 as contract
from proworksim.software_benchmark_actor_parent_v131 import ParentContainers
from proworksim.software_benchmark_candidates_v054 import reference


def test_exact_five_by_fifty_and_shared_limits():
    plan = scope.load(reference(scope.PLAN_FILE))
    assert scope.validate_plan(plan) is plan
    assert len(plan['rows']) == 250
    assert len({r['instance_id'] for r in plan['rows']}) == 50
    assert sum(r['generation_token_upper_bound'] for r in plan['rows']) == 1_250_000_000
    assert scope.MAX_GENERATIONS == 48 and scope.MAX_STARTUPS == 8 and scope.MAX_GRADERS == 2
    assert len(set(scope.LEDGER_FILES.values())) == 5
    for group in contract.GROUP_IDS:
        c = contract.condition(group)
        assert c['episode_limits']['input_plus_output_tokens'] == 5_000_000
        assert c['execution_strategy']['final_review']['maximum'] == c['member_count']
        assert c['execution_strategy']['final_review']['scope'] == 'once_per_member_per_episode'
    bad = copy.deepcopy(plan)
    bad['rows'][0]['organization_id'] = 'REVIEW'
    with pytest.raises((ValueError, PermissionError)):
        scope.validate_plan(bad)


def test_new_parent_requires_grant_and_preserves_cpu_memory_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(parent, 'AUTHORIZATION', tmp_path/'no-grant.json')
    with pytest.raises(PermissionError, match='specific user approval'):
        parent.approved()
    command = parent.creation_command('owned fixture')
    assert command[:4] == ['sudo','-n','busctl','--system']
    assert 'StartTransientUnit' in command and parent.SLICE == 'proworksimv131api.slice'
    assert command[command.index('StartTransientUnit')+3] == 'fail'
    assert command[command.index('CPUQuotaPerSecUSec')+1:command.index('CPUQuotaPerSecUSec')+3] == ['t',str(144_000_000)]
    folder = tmp_path/parent.SLICE
    folder.mkdir()
    for name, value in {'memory.max':str(832*1024**3),'memory.high':str(768*1024**3),
        'memory.swap.max':'0','pids.max':'32768','cgroup.procs':'','cpu.max':'14400000 100000'}.items():
        (folder/name).write_text(value)
    assert parent.kernel_boundary(cgroup_root=tmp_path)['cpu_quota_cores'] == 144
    (folder/'cpu.max').write_text('max 100000')
    with pytest.raises(PermissionError, match='CPU quota'):
        parent.kernel_boundary(cgroup_root=tmp_path)


def test_actual_create_proxy_injects_only_owned_parent(monkeypatch):
    seen=[]
    monkeypatch.setattr(parent, 'require_qualified', lambda: {'qualified':True})
    proxy = ParentContainers(SimpleNamespace(create=lambda **kw: seen.append(kw) or kw))
    original = {'image':'sha256:'+'a'*64,'network_mode':'none','mem_limit':16*1024**3}
    result=proxy.create(**original)
    assert result == {**original,'cgroup_parent':'proworksimv131api.slice'}
    assert len(seen)==1
    with pytest.raises(ValueError, match='scoped provider'):
        proxy.create(**original,cgroup_parent='foreign.slice')
    assert len(seen)==1


def test_nominal_container_maxima_do_not_cap_concurrency(monkeypatch):
    monkeypatch.setattr(parent,'pressure_probe',lambda:{'current_bytes':100*scope.GIB,
        'high_bytes':768*scope.GIB,'max_bytes':832*scope.GIB,'qualified':True})
    monkeypatch.setattr(scope,'dispatch_view',lambda:SimpleNamespace(physical_capacity=lambda:{
        'memory_available_bytes':800*scope.GIB,'disk_free_bytes':900*scope.GIB,'passed':True}))
    monkeypatch.setattr(scope,'host_cpu_pool',lambda:list(range(176)))
    monkeypatch.setattr(scope.os,'getloadavg',lambda:(20,20,20))
    active=[{'spec':{'role':'actor'},'reserved_cpu':6,'reserved_memory_bytes':32*scope.GIB,
             'reserved_spool_bytes':4*scope.GIB} for _ in range(47)]
    result=scope._budget(active,6,32*scope.GIB,4*scope.GIB)
    assert result['individual_memory_caps_sum_after']==1536*scope.GIB
    assert result['aggregate_memory_hard_cap_bytes']==832*scope.GIB
    monkeypatch.setattr(parent,'pressure_probe',lambda:{'current_bytes':750*scope.GIB,
        'high_bytes':768*scope.GIB,'max_bytes':832*scope.GIB,'qualified':True})
    with pytest.raises(scope.ResourceBusy):
        scope._budget(active,6,32*scope.GIB,4*scope.GIB)
