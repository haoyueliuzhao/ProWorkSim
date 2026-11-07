"""Scripted local score-retry and exact same-tree delivery checks; no Docker."""
import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_grading_v146 as grading
from proworksim import software_benchmark_scope_v146 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def host_fixture(tmp_path, monkeypatch, *, rows=None):
    for name, path in {'PLAN_FILE':tmp_path/'plan.json','API_ROOT':tmp_path/'api',
                       'GRADING_ROOT':tmp_path/'grading','COORDINATOR_ROOT':tmp_path/'coordinator',
                       'BATCH_ROOT':tmp_path}.items():
        monkeypatch.setattr(scope,name,path)
    write_new(scope.PLAN_FILE,{'rows':rows or [],'resources':{'score-retry-10200':{
        'role':'score','slot_id':'slot','score_retry':True,
        'retry_of_resource_key':'score-10200','same_locked_candidate_required':True}}})
    checks=[]
    scorer=SimpleNamespace(VERSION='fixture-scorer',environment=SimpleNamespace(),write_new=write_new,
        _generation_result=lambda *args:checks.append('generation'),
        validate_project_delivery=lambda *args:{'submitted':True,'same_tree':True})
    policy=SimpleNamespace(PLAN_FILE=scope.PLAN_FILE,load=scope.load,
                           physical_capacity=lambda:{'passed':True})
    return grading.host(policy,scorer),scorer,checks


def test_only_technical_score_failure_prepares_same_lock_retry_with_admission(tmp_path,monkeypatch):
    host,_,_=host_fixture(tmp_path,monkeypatch)
    folder=scope.GRADING_ROOT/'score-10200'
    folder.mkdir(parents=True)
    candidate=write_new(tmp_path/'candidate-lock.json',{'tree_sha256':'fixed-tree'})
    request_ref=write_new(folder/'request.json',{'resource_key':'score-10200','slot_id':'slot',
        'directory':str(folder),'candidate_lock':candidate,'generation_result':{'original':'result'}})
    write_new(folder/'quiescence.json',{'quiescent':True,'cleanup_errors':[]})
    write_new(folder/'receipt.json',{'status':'technical_unknown','resolved':None})
    new_ref=host.prepare_score_retry(request_ref)
    revised=scope.load(new_ref)
    assert revised['resource_key']=='score-retry-10200'
    assert revised['candidate_lock']==candidate
    assert revised['generation_result']=={'original':'result'}
    assert revised['retry_of_request']==request_ref
    gate=scope.validate_score_retry_admission('score-retry-10200')
    assert gate['same_candidate'] is True
    assert gate['prior_request']==request_ref
    assert gate['prior_completion']==reference(folder/'receipt.json')
    with pytest.raises(ValueError,match='Only one'):
        host.prepare_score_retry(new_ref)
    (folder/'receipt.json').write_text('{"status":"official_report","resolved":false}')
    with pytest.raises(ValueError,match='Normal test failure'):
        host.prepare_score_retry(request_ref)


def test_same_tree_delivery_accepts_retry_key_but_rejects_different_lock_and_slot(tmp_path,monkeypatch):
    config=write_new(tmp_path/'config.json',{'instance_id':'fixture__repo-1'})
    row={'slot_id':'slot','slot_index':10200,'arm':'PROJECT','instance_id':'fixture__repo-1',
         'configuration':config}
    host,scorer,checks=host_fixture(tmp_path,monkeypatch,rows=[row])
    code=write_new(tmp_path/'code-lock.json',{'tree_sha256':'same-tree',
        'patch_receipt':{'base_tree_sha256':'same-base'}})
    delivery=write_new(tmp_path/'delivery-lock.json',{'tree_sha256':'same-tree',
        'patch_receipt':{'base_tree_sha256':'same-base'}})
    result_ref=write_new(tmp_path/'result.json',{'slot_id':'slot','candidate_lock':code,
        'delivery_candidate_lock':delivery,'delivery_evidence':{'fixture':True}})
    manifest=write_new(tmp_path/'manifest.json',{'fixture':True})
    host.delivery_disposition.__globals__['prepare_manifest']=lambda:manifest
    folder=scope.GRADING_ROOT/'score-retry-10200'
    folder.mkdir(parents=True)
    request_ref=write_new(folder/'request.json',{'resource_key':'score-retry-10200','slot_id':'slot',
        'candidate_lock':code,'generation_result':result_ref,'directory':str(folder)})
    identity={'request':request_ref,'candidate_lock':code,'configuration':config,'endpoint':'code',
        'plan':reference(scope.PLAN_FILE),'scorer_manifest':manifest}
    identity_ref=write_new(folder/'identity.json',identity)
    receipt={'version':scorer.VERSION,'resource_key':'score-retry-10200','slot_id':'slot',
        'identity':identity_ref,'status':'official_report','resolved':True,
        'official_result':[None,{'fixture__repo-1':{'resolved':True,'patch_successfully_applied':True}}]}
    write_new(folder/'receipt.json',receipt)
    write_new(folder/'completion.json',{'returncode':0})
    write_new(folder/'quiescence.json',{'resource_key':'score-retry-10200','quiescent':True,
        'cleanup_errors':[],'create_result_unknown':False})
    actual=host.delivery_disposition(result_ref,request_ref)
    assert actual['status']=='same_tree_official_result_reused'
    assert actual['resolved'] is True
    assert actual['scoring_request'] is None
    assert checks==['generation']
    for key,value in [('candidate_lock',delivery),('slot_id','foreign-slot')]:
        # Only scripted temporary records change; exercise the executed private
        # host function and preserve all other valid candidate/cleanup evidence.
        bad={**scope.load(request_ref),key:value}
        bad_ref=write_new(tmp_path/(key+'-bad-request.json'),bad)
        bad_identity=write_new(tmp_path/(key+'-bad-identity.json'),{**identity,'request':bad_ref})
        (folder/'receipt.json').write_text(json.dumps({**receipt,'identity':bad_identity}))
        with pytest.raises(ValueError,match='exact same-tree'):
            host.delivery_disposition(result_ref,bad_ref)
