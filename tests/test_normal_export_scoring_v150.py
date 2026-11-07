"""Managed-lock dispatch and exact technical retry gates; CPU/files only."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_rescore_v150 as scoring
from proworksim import software_benchmark_closed_export_recovery_v149 as exports
from proworksim.software_benchmark_candidates_v054 import write_new


def test_only_1766_uses_qualified_long_idle_and_all_other_providers_remain_standard():
    scorer=scoring.build_scorer(manifest_provider=lambda:{})
    assert scorer.environment.provider('psf__requests-1766').transport.Limits().idle_seconds==180
    assert scorer.environment.provider('psf__requests-1921').transport.Limits().idle_seconds==60
    assert scorer.environment.provider('psf__requests-2931') is scorer.environment.standard.offline
    assert scorer.environment.provider('sympy__sympy-1') is None
    assert scoring.CONSTRAINTS['maximum_containers']==168
    assert scoring.CONSTRAINTS['maximum_active_containers']==2


def test_executing_official_scorer_dereferences_managed_patch_without_changing_bytes(tmp_path,monkeypatch):
    scorer=scoring.build_scorer(manifest_provider=lambda:{})
    namespace=scorer.validate_request.__globals__
    task='cpu__task-1'
    raw=b'diff --git a/example.py b/example.py\n'
    patch=write_new(tmp_path/'candidate.patch',raw)
    patch_receipt=write_new(tmp_path/'patch-receipt.json',{'patch':patch})
    lock=write_new(tmp_path/'lock.json',{'patch_receipt':patch_receipt})
    mapping=write_new(tmp_path/'mapping.json',{})
    monkeypatch.setitem(namespace,'base',SimpleNamespace(
        read_local_dataset=lambda _: {task:{}},sha256=lambda data:hashlib.sha256(data).hexdigest(),
        canonical=lambda value:json.dumps(value,sort_keys=True).encode()))
    monkeypatch.setitem(namespace,'validate_mapping',lambda *a,**k:{})
    class StopBeforeDocker(RuntimeError):
        pass
    seen=[]
    def observe(path,value):
        assert path.name=='identity.json'
        seen.append(value)
        raise StopBeforeDocker
    monkeypatch.setitem(namespace,'write_new',observe)
    config={'instance_id':task,'condition_id':'CPU','scorer_request_base':{
        'dataset':{},'baseline_mapping':mapping,'image':{'image_id':'CPU'}}}
    request={'candidate_lock':lock,'prepared_request':{},'capacity_claim':{},
        'resource_key':'score-1','configuration':{},'plan':{},'scorer_manifest':{},
        'limits':scorer.LIMITS,'cpuset_cpus':'0,1,2,3','directory':str(tmp_path)}
    with pytest.raises(StopBeforeDocker):
        scorer._score(request,{'role':'score','endpoint':'code'},config,{})
    assert seen[0]['patch_sha256']==hashlib.sha256(raw).hexdigest()
    assert seen[0]['patch_bytes']==len(raw)


def test_retry_cannot_override_a_known_failed_official_score(tmp_path,monkeypatch):
    row={'slot_id':'v146:CPU','slot_index':10209}
    plan=write_new(tmp_path/'plan.json',{'rows':[row]})
    monkeypatch.setattr(scoring,'PLAN',tmp_path/'plan.json')
    monkeypatch.setattr(scoring,'GRADING',tmp_path/'grading')
    lock={'unique_lock':True}
    export=write_new(tmp_path/'export.json',{})
    monkeypatch.setattr(exports,'validate_export_result_bounded',lambda ref,original:{
        'candidate_lock':lock,'completed_work_proven_before_export':True})
    folder=scoring.GRADING/'score-10209'
    folder.mkdir(parents=True)
    request=write_new(folder/'request.json',{'directory':str(folder),'resource_key':'score-10209',
        'candidate_lock':lock,'generation_result':export})
    write_new(folder/'quiescence.json',{'quiescent':True,'cleanup_errors':[],'create_result_unknown':False})
    write_new(folder/'receipt.json',{'status':'official_report','resolved':False})
    completion=write_new(folder/'completion.json',{'state':'technical_unknown','cleanup_proven':True})
    admission={'slot_id':row['slot_id'],'endpoint':'code','scoring_attempt':2,
        'export_result':export,'candidate_lock':lock,'prior_request':request,'prior_completion':completion}
    with pytest.raises(PermissionError,match='Normal scored'):
        scoring.validate_admission(admission)
    assert scoring.load(plan)['rows']==[row]
    assert json.loads((folder/'receipt.json').read_text())['resolved'] is False
