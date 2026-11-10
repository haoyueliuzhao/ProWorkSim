import fcntl,json,threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from proworksim import software_context_resume_v189 as r


def test_capacity_snapshot_excludes_concurrent_lease_deletion(tmp_path,monkeypatch):
    directory=tmp_path/'resource-claims';directory.mkdir()
    lockpath=directory/'allocation.lock';lockpath.touch()
    lease=directory/'active-grader-0.json'
    lease.write_text(json.dumps({'spec':{'role':'score'},'reserved_spool_bytes':2*1024**3}))
    original=Path.read_bytes;observed=[]
    def read(path):
        if path==lease:
            with lockpath.open('rb') as writer:
                with pytest.raises(BlockingIOError):fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
                observed.append('release blocked until snapshot read completes')
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',read)
    policy=SimpleNamespace(BATCH_ROOT=tmp_path,CONSTRAINTS=r.scope.CONSTRAINTS,host_cpu_pool=lambda:list(range(176)))
    physical={'memory_available_bytes':900*1024**3,'disk_free_bytes':200*1024**3,'passed':True}
    value=r.capacity_status(policy,physical=physical,load1=30)
    assert observed and value['admit'] and value['disk_floor_bytes']==134*1024**3
    with lockpath.open('rb') as writer:
        fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB);lease.unlink()
    assert r.capacity_status(policy,physical=physical,load1=30)['disk_floor_bytes']==132*1024**3


def test_real_episode_waiter_uses_locked_capacity_snapshot(monkeypatch):
    from proworksim.software_benchmark_episode_v181 import build_episode
    from proworksim.software_benchmark_alignment_contract_v181 import VERSION
    from proworksim.software_benchmark_candidates_v054 import reference
    def guard(*args,**kwargs):return {'status':'approved','execution_alignment_version':VERSION,
        'source_index':reference(r.scope.PLAN_FILE),'plan':reference(r.scope.PLAN_FILE),'constraints':r.scope.CONSTRAINTS}
    episode=build_episode(scope=r.scope,guard=guard)
    seen=[]
    original=r.bind_capacity.__globals__['capacity_status']
    def snapshot(policy):seen.append(policy);return {'admit':True,'waiting_reasons':[]}
    monkeypatch.setitem(r.bind_capacity.__globals__,'capacity_status',snapshot)
    r.bind_capacity(episode,r.scope.dispatch_view(guard),threading.Event(),lambda _:None)
    assert episode._run.__globals__['wait_capacity'] is episode.wait_capacity
    assert episode.wait_capacity()['admit'] and len(seen)==1
    assert original is r.capacity_status
