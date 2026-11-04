"""Actual team actor method checks identity before any public test operation."""
import copy
import time

import pytest

from proworksim import software_benchmark_managed_actor_v131 as actor
from proworksim.storage import digest, json_bytes


def test_member_and_group_are_bound_through_actual_execute(monkeypatch, tmp_path):
    session=object.__new__(actor.ManagedOperationSession)
    session.config={'instance_id':'fixture__team-131','organization_id':'REVIEW',
        'fixed_members':['member_001','member_002'],'lifecycle_deadline':time.monotonic()+60}
    session.preflight_passed=True
    session.terminal_locked=False
    session.test_calls=0
    session.baseline={}
    session.gitlinks=[]
    session.root=tmp_path
    session.entry={'argv':['fixture','-m','pytest']}
    session.public_test_environment_v130={'fixture':'only'}
    session.public_dependency_profile_v130=None
    calls=[]
    candidate={'tree_sha256':'a'*64,'files':{},'entry_metadata':{}}
    monkeypatch.setattr(actor,'reconstruct_delta',lambda *_a,**_kw:candidate)
    monkeypatch.setattr(actor,'selected_entry',lambda entry,selection,**_kw:(entry,selection))
    monkeypatch.setattr(actor,'synchronize_tree',lambda *_a,**_kw:None)
    def run(entry,**kw):
        calls.append(copy.deepcopy(kw['request']))
        return {'passed':False,'execution':{'executed':True,'validation_status':'no_tests'},
                'groups':{'public_repository_tests':{'tests':[{'test_id':'fixture','passed':False}]}}}
    monkeypatch.setattr(actor,'run_public_entry',run)
    request={'version':'v131-fixed-organization-managed-world-r1','instance_id':session.config['instance_id'],
        'actor_id':'member_002','organization_id':'REVIEW','call_index':1,
        'source_reference':{'object_id':'member2-private','version_id':'v1'},'tree_sha256':'a'*64,
        'hard_deadline_monotonic':session.config['lifecycle_deadline'],
        'hidden_evaluation':False,'arbitrary_command':False,
        'public_test_selection_revision':'v110-public-test-selection-r1',
        'public_test_selection':{'kind':'full'}}
    for wrong in ({'actor_id':'member_004'},{'organization_id':'CHIEF'},
                  {'version':'v110-public-test-selection-r1'}):
        with pytest.raises(ValueError):
            session.execute('managed_public_test',{'request':{**request,**wrong}})
    assert calls==[] and session.test_calls==0
    result,receipt=session.execute('managed_public_test',{'request':request})
    assert calls==[request]
    assert result['execution']['actor_id']=='member_002'
    assert result['execution']['organization_id']=='REVIEW'
    assert result['execution']['managed_request_sha256']==digest(json_bytes(request))
    assert result['execution']['validation_status']=='no_tests' and not result['passed']
    assert receipt=={'operation_executed':True} and session.test_calls==1
