import copy
from types import SimpleNamespace
import pytest
from proworksim.software_organization_v042 import build_test_report,test_result_page as original_page
from proworksim.software_public_test_view_v192 import project_test_page,full_observer_result,VERSION
from proworksim.storage import digest,json_bytes

def fixture():
    evidence={'version':'test-evidence-fixture','framework':'pytest','report_count':3000,'partial':False,'error':None,
        'sessions':[{'run_id':'root','parent_run_id':None,'root':True,'exitstatus':1,'counts':{'passed':999,'failed':1},
            'test_reports':[{'nodeid':'test.py::case'+str(i),'outcome':'passed'} for i in range(3000)]}]}
    result={'groups':{'public':{'passed':False,'tests':[]}},'public_execution':{'execution':{'test_evidence':evidence}},
        'source_reference':{'object_id':'workspace','version_id':'v7'},'files_sha256':'f'*64,
        'executed':True,'passed':False,'untested':[],'scope':'public','independent_acceptance':'not_run',
        'fixed_submission_is_acceptance':False}
    event={'world_id':'world','instance_id':'task','branch_id':'branch','project_id':'project',
        'actor_id':'member_001','test_event_sequence':1,'operation_id':'op'}
    report=build_test_report(result,actor_id='member_001',event_identity=event)
    page=original_page(report);page.update(test_evidence=copy.deepcopy(evidence),counts={'passed':999,'failed':1},validation_status='failed')
    return page,report,evidence

def test_large_evidence_header_is_bounded_without_changing_test_or_pages():
    page,report,full=fixture();before=copy.deepcopy(report);out=project_test_page(page,report,'member_001')
    assert report==before
    assert len(json_bytes(out['test_evidence']))<=4096<len(json_bytes(full))
    for key in ('passed','executed','source_reference','counts','validation_status','body_sha256','page'):assert out[key]==page[key]
    cursor=out['test_evidence']['full_details']['cursor']
    assert any(p['cursor']==cursor for p in report['pages'])
    assert ''.join(p['text'] for p in report['pages'])==report['body']
    assert digest(report['body'].encode())==report['body_sha256']

def test_observer_gets_full_original_hierarchy_but_model_does_not():
    page,report,full=fixture();out=project_test_page(page,report,'member_001')
    world=SimpleNamespace(_software=lambda:{'test_reports':{report['report_id']:report}})
    observed=full_observer_result(world,'member_001',out)
    assert observed['test_evidence']==full and out['test_evidence']['version']==VERSION
    with pytest.raises(ValueError):full_observer_result(world,'member_002',out)

def test_wrong_member_or_version_cannot_read_projection():
    page,report,_=fixture()
    with pytest.raises(PermissionError):project_test_page(page,report,'member_002')
    page['source_reference']['version_id']='v8'
    with pytest.raises(ValueError):project_test_page(page,report,'member_001')
