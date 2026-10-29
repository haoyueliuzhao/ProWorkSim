from contextlib import contextmanager
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tarfile

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dead_owner_recovery_test', ROOT/'tools/recover_api_owner_v080.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def test_live_or_unproved_owner_rejected_before_client(monkeypatch):
    def denied():
        raise PermissionError('owner not proven dead')
    monkeypatch.setattr(recovery, 'dead_owner', denied)
    monkeypatch.setattr(recovery, 'client_for', lambda *_: pytest.fail('No Docker call allowed'))
    with pytest.raises(PermissionError, match='not proven dead'):
        recovery.recover_pair(123)


def test_non_allowlisted_pair_cannot_operate(monkeypatch):
    monkeypatch.setattr(recovery, 'dead_owner', lambda: {})
    monkeypatch.setattr(recovery, 'proposal', lambda: {'rows': []})
    monkeypatch.setattr(recovery, 'client_for', lambda *_: pytest.fail('No Docker call allowed'))
    with pytest.raises(PermissionError, match='outside'):
        recovery.recover_pair(123)


def test_archive_summary_reads_small_metadata_without_extracting_paths(monkeypatch, tmp_path):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tar:
        raw=json.dumps({'status':'closed','attempts':7,'known_actual_tokens':1234}).encode()
        member=tarfile.TarInfo('output/controller-result.json')
        member.size=len(raw)
        tar.addfile(member,io.BytesIO(raw))
        link=tarfile.TarInfo('../../outside')
        link.type=tarfile.SYMTYPE
        link.linkname='/etc/passwd'
        tar.addfile(link)
    called=[]
    @contextmanager
    def verified(_):
        called.append('open')
        yield io.BytesIO(stream.getvalue())
        called.append('verified')
    monkeypatch.setattr(recovery,'open_verified_archive',verified)
    result=recovery.archive_summary({},controller=True)
    assert result['round_trip_verified'] and result['members']==2
    assert result['selected_metadata']['output/controller-result.json']['attempts']==7
    assert called==['open','verified'] and not (tmp_path/'outside').exists()


def stopped_pair(running=False):
    obj=SimpleNamespace(id='a'*64,attrs={'State':{'Running':running,'Pid':42 if running else 0}})
    volume=SimpleNamespace()
    claims={r:{'test_claim':r} for r in ('actor','controller','volume')}
    return SimpleNamespace(objects={'actor':obj,'controller':obj,'volume':volume},claims=claims,
        claim_bodies={r:{'docker_name':r} for r in claims})


def test_live_retained_object_never_releases_lease(monkeypatch):
    monkeypatch.setattr(recovery.owned,'validate_container_identity',lambda obj,*a:obj.attrs)
    monkeypatch.setattr(recovery.original,'release_resource',lambda *a,**k:pytest.fail('Live source cannot release capacity'))
    with pytest.raises(RuntimeError,match='live retained'):
        recovery.retain_quiet_sources(stopped_pair(True),[])


def test_retention_preserves_all_objects_but_releases_quiet_execution_capacity(monkeypatch):
    monkeypatch.setattr(recovery.owned,'validate_container_identity',lambda obj,*a:obj.attrs)
    monkeypatch.setattr(recovery.owned,'validate_volume',lambda *a:None)
    released=[]
    monkeypatch.setattr(recovery.original,'release_resource',lambda ref,**kw:released.append((ref,kw)))
    result=recovery.retain_quiet_sources(stopped_pair(),[])
    assert result['quiescent'] and not result['all_owned_objects_removed']
    assert {x['role'] for x in result['retained_objects']}=={'actor','controller','volume'}
    assert len(released)==3 and all(x[1]=={'quiescent':True} for x in released)


def test_only_two_recovery_workers_enter(tmp_path,monkeypatch):
    monkeypatch.setattr(recovery,'OUT',tmp_path)
    with recovery.bounded_worker(),recovery.bounded_worker():
        with pytest.raises(RuntimeError,match='two scoped'):
            with recovery.bounded_worker():
                pytest.fail('A third worker entered')
    with recovery.bounded_worker():
        pass


def test_export_failure_keeps_unique_stopped_source_and_records_unknown(tmp_path,monkeypatch):
    row={'slot_index':1,'slot_id':'original-API-slot','configuration':{},'model_key':'DEEPSEEK'}
    entry={'slot_index':1,'row':row,'claims':{}}
    monkeypatch.setattr(recovery,'OUT',tmp_path/'recovery')
    monkeypatch.setattr(recovery.original,'BATCH_ROOT',tmp_path/'original')
    monkeypatch.setattr(recovery,'dead_owner',lambda:{'dead':True})
    monkeypatch.setattr(recovery,'proposal',lambda:{'rows':[entry]})
    closed=[]
    monkeypatch.setattr(recovery,'client_for',lambda _:SimpleNamespace(close=lambda:closed.append(True)))
    pair=SimpleNamespace(objects={'actor':object()},stop_writers=lambda:{'all_quiet':True},
        cleanup=lambda:pytest.fail('Failed export must not delete original objects'))
    monkeypatch.setattr(recovery,'restore_pair',lambda *a:(pair,[]))
    def failure(*a,**k):
        raise OSError('bounded export failed')
    monkeypatch.setattr(recovery,'preserve_archive',failure)
    monkeypatch.setattr(recovery,'usage_observation',lambda _:{'known_actual_tokens_lower_bound':1200})
    monkeypatch.setattr(recovery,'retain_quiet_sources',lambda *a:{'quiescent':True,'cleanup_errors':[],
        'retained_objects':[{'role':'actor'}],'all_owned_objects_removed':False})
    ref=recovery.recover_pair(1)
    value=recovery.load(ref)
    assert value['generation_status']=='technical_unknown' and value['export_pending']
    assert value['retained_objects']==[{'role':'actor'}] and value['new_model_calls']==0
    assert closed==[True]
    evidence=recovery.load(value['evidence'])
    assert evidence['export_error']['message']=='bounded export failed'


def test_completed_recovery_does_not_reoperate_objects(tmp_path,monkeypatch):
    monkeypatch.setattr(recovery,'OUT',tmp_path)
    monkeypatch.setattr(recovery,'dead_owner',lambda:{})
    monkeypatch.setattr(recovery,'proposal',lambda:{'rows':[{'slot_index':1}]})
    folder=tmp_path/'episodes/1'
    folder.mkdir(parents=True)
    expected=write_new(folder/'completed.json',{'quiescent':True})
    monkeypatch.setattr(recovery,'client_for',lambda *_:pytest.fail('Completed identity must not repeat'))
    assert recovery.recover_pair(1)==expected
