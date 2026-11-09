import pytest
from proworksim.software_context_lifecycle_v180 import SummaryLifecycle

EPOCH={'workspace_tree_sha256':'a'*64,'public_test_evidence_id':None,'delivery_version_id':None}
USAGE={'input_tokens':100,'output_tokens':20,'total_tokens':120}


def make(tmp_path):return SummaryLifecycle(tmp_path/'state.json',episode_id='episode',member_id='member_001')
def install(owner,epoch):
    return owner.install(text='Historical state',covered_through_turn=21,source_epoch=epoch,
        source_sha256='b'*64,archive_reference='ctx:original',request_id='summary-call',usage=USAGE,created_at='CPU fixture')


def test_n_plus_m_trigger_and_no_repeated_summary_without_new_history(tmp_path):
    owner=make(tmp_path);owner.observe(21,EPOCH)
    assert owner.plan(actual_input_tokens=30000)['action']=='keep_original'
    epoch=owner.observe(31,EPOCH)['epoch'];plan=owner.plan(actual_input_tokens=50000)
    assert plan['action']=='summarize' and plan['new_source_turn_range']==[1,21]
    install(owner,epoch)
    assert owner.plan(actual_input_tokens=30000)['action']=='reuse'


def test_critical_change_stales_summary_then_updates_before_leaving_tail(tmp_path):
    owner=make(tmp_path);epoch=owner.observe(31,EPOCH)['epoch'];install(owner,epoch)
    changed={**EPOCH,'workspace_tree_sha256':'c'*64};owner.observe(32,changed)
    plan=owner.plan(actual_input_tokens=30000)
    assert plan['action']=='reuse' and not plan['working_state_validity_proxy']
    owner.observe(42,changed)
    assert owner.plan(actual_input_tokens=30000)['reason']=='critical_change_leaving_recent_tail'


def test_restart_idempotency_and_no_false_valid_reuse(tmp_path):
    owner=make(tmp_path);epoch=owner.observe(31,EPOCH)['epoch'];s=install(owner,epoch)
    args={'request_id':'a','logical_decision_id':'d1','summary_id':s['summary_id'],'usage':USAGE}
    owner.note_settled_request(**args);owner.note_settled_request(**args)
    restarted=make(tmp_path);assert restarted.metrics()['physical_presentations']==1
    restarted.observe(32,{**EPOCH,'public_test_evidence_id':'new-test'})
    restarted.note_settled_request(request_id='b',logical_decision_id='d2',summary_id=s['summary_id'],usage=USAGE)
    result=restarted.metrics()
    assert result['epoch_valid_distinct_decision_reuses']==1 and result['historical_only_presentations']==1
    with pytest.raises(ValueError):SummaryLifecycle(tmp_path/'state.json',episode_id='other',member_id='member_001')
