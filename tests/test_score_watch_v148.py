"""Lightweight final-primary gating; no containers, API, sleeps or host writes."""
from __future__ import annotations

import json

import pytest

from proworksim import software_benchmark_rescore_v148 as watch
from proworksim.software_benchmark_candidates_v054 import write_new


def setup(tmp_path,*,generation='closed',delivery=True):
    row={'slot_index':10214,'slot_id':'v146:CPU:attempt1','instance_id':'psf__requests-1766'}
    generation_folder=tmp_path/'episodes/10214'
    generation_folder.mkdir(parents=True)
    quiet=write_new(generation_folder/'quiescence.json',{'quiescent':True,
        'all_owned_objects_removed':True,'cleanup_errors':[]})
    result=write_new(generation_folder/'result.json',{'status':generation,'slot_id':row['slot_id'],
        'quiescence':quiet,'candidate_lock':{'code_lock':True},
        'delivery_candidate_lock':{'delivery_lock':True} if delivery else None})
    (tmp_path/'api-coordinator/score-records').mkdir(parents=True)
    return row,result


def score(tmp_path,row,result,*,attempt=1,status='technical_unknown',resolved=None,clean=True,
          endpoint='code',delivery_disposition=None):
    prefix='score-' if endpoint=='code' else 'delivery-score-'
    key=prefix+('retry-' if attempt==2 else '')+'10214'
    folder=tmp_path/'grading'/key
    folder.mkdir(parents=True)
    request=write_new(folder/'request.json',{'slot_id':row['slot_id'],'generation_result':result})
    write_new(folder/'capacity-claim.json',{'CPU_fixture':True})
    write_new(folder/'quiescence.json',{'quiescent':clean,'cleanup_errors':[],
                                      'create_result_unknown':False})
    value={'request':request,'cleanup_proven':clean,
           'official_endpoint':{'status':status,'resolved':resolved}}
    if delivery_disposition is not None:
        value['delivery']=delivery_disposition
    return write_new(tmp_path/f'api-coordinator/score-records/10214-{endpoint}-attempt{attempt}.json',value)


@pytest.mark.parametrize('resolved',[False,True])
def test_normal_primary_result_is_never_rescored(tmp_path,resolved):
    row,result=setup(tmp_path)
    score(tmp_path,row,result,status='scored',resolved=resolved)
    assert watch.inspect_target(row,'code',original_root=tmp_path)['state']=='skip_primary_known'


def test_unknown_waits_for_primary_retry_then_requires_full_cleanup(tmp_path):
    row,result=setup(tmp_path)
    score(tmp_path,row,result)
    assert watch.inspect_target(row,'code',original_root=tmp_path)['state']=='waiting_primary_score'
    score(tmp_path,row,result,attempt=2)
    admitted=watch.inspect_target(row,'code',original_root=tmp_path)
    assert admitted['state']=='eligible' and admitted['candidate_lock']=={'code_lock':True}
    quiet=tmp_path/'grading/score-retry-10214/quiescence.json'
    quiet.write_text(json.dumps({'quiescent':False,'cleanup_errors':['writer live'],'create_result_unknown':False}))
    assert watch.inspect_target(row,'code',original_root=tmp_path)['state']=='waiting_primary_cleanup'


def test_same_tree_unknown_delivery_is_separately_bound_and_absent_delivery_skipped(tmp_path):
    row,result=setup(tmp_path)
    score(tmp_path,row,result,attempt=2,delivery_disposition={
        'status':'technical_unknown','resolved':None,'scoring_request':None})
    value=watch.inspect_target(row,'delivery',original_root=tmp_path)
    assert value['state']=='eligible' and value['candidate_lock']=={'delivery_lock':True}
    assert value['endpoint']=='delivery'


def test_generation_unknown_or_foreign_identity_never_enters_scorer(tmp_path):
    row,_=setup(tmp_path,generation='technical_unknown')
    assert watch.inspect_target(row,'code',original_root=tmp_path)['state']=='skip_generation_not_closed'
    with pytest.raises(ValueError):
        watch.inspect_target({**row,'slot_index':10103},'code',original_root=tmp_path)
    assert watch.CONSTRAINTS['maximum_containers']==8
    assert watch.CONSTRAINTS['maximum_active_containers']==1
    assert watch.CONSTRAINTS['maximum_real_tls_sessions']==8
