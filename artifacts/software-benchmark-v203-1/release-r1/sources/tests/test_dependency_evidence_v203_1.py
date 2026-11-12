import copy,json
import pytest
from proworksim.software_dependency_evidence_v203_1 import DependencyEvidence,EvidenceError,no_change,synchronization_event
from proworksim.software_static_topology_v203_1 import partition

def source(tmp_path,ledger,payload,origin='harness_receipt',producer='checker'):
    path=tmp_path/f'{len(ledger.sources)}.json';path.write_text(json.dumps(payload));return ledger.source(path,'',origin,producer)
def relation(tmp_path):
    g=DependencyEvidence();v={'task:A':1,'task:B':1};s=source(tmp_path,g,{'claim':'A needs B'},'actor_proposal','actorA');r=g.propose('task:A','task:B','task_depends_on',v,s,'actorA');return g,r,v
def confirm(tmp_path,g,r,v):
    witness=source(tmp_path,g,{'source_version':v,'execution':'controlled evidence; not a SWE semantic truth claim'})
    payload={'relation_id':r,'source_entity':'task:A','target_entity':'task:B','source_version':v,'verdict':'supported','verifier':'checker',
        'checks':[{'passed':True,'original_witness':witness}],'verification_scope':'authored CPU contract only'}
    sid=source(tmp_path,g,payload,'independent_check','checker');g.confirm(r,sid,'checker');return sid

@pytest.mark.parametrize('origin,producer',[('actor_proposal','actorA'),('policy_feedback','policy'),('harness_receipt','adopter')])
def test_no_self_confirmation_or_feedback_upgrade(tmp_path,origin,producer):
    g,r,v=relation(tmp_path);s=source(tmp_path,g,{'relation_id':r},origin,producer)
    with pytest.raises(EvidenceError):g.confirm(r,s,producer)
    assert g.relations[r]['status']=='candidate'

def test_versioned_confirmation_invalidation_preserves_history(tmp_path):
    g,r,v=relation(tmp_path);sid=confirm(tmp_path,g,r,v);old=g.snapshot()
    change=source(tmp_path,g,{'new_versions':{'task:A':2,'task:B':1}});g.invalidate(r,{'task:A':2,'task:B':1},change,'Task revision changed')
    assert old['relations'][r]['status']=='confirmed' and g.relations[r]['status']=='invalidated'
    with pytest.raises(EvidenceError):g.confirm(r,sid,'checker')

def test_unregistered_or_wrong_version_witness_cannot_confirm(tmp_path):
    g,r,v=relation(tmp_path);p={'relation_id':r,'source_entity':'task:A','target_entity':'task:B','source_version':v,'verdict':'supported','verifier':'checker',
        'checks':[{'passed':True,'original_witness':'invented'}],'verification_scope':'example'}
    sid=source(tmp_path,g,p,'independent_check','checker')
    with pytest.raises(EvidenceError):g.confirm(r,sid,'checker')

def test_code_relation_not_task_dependency(tmp_path):
    g=DependencyEvidence();s=source(tmp_path,g,{'import':'b'},'actor_proposal','a')
    with pytest.raises(EvidenceError):g.propose('code:a','code:b','task_depends_on',{'a':'v1'},s,'a')

@pytest.mark.parametrize('cause',['environment','waiting','budget','unknown'])
def test_blocked_does_not_imply_org_failure(tmp_path,cause):
    g,r,v=relation(tmp_path);sid=source(tmp_path,g,{'task_id':'task:A','executed':True,'blocked':True,'cause':cause})
    e=g.block('task:A',None,cause,sid);assert not e['organization_failure_proven'] and not e['supports_dependency_diagnosis']

def test_block_unblock_requires_new_actual_evidence(tmp_path):
    g,r,v=relation(tmp_path);confirm(tmp_path,g,r,v)
    sid=source(tmp_path,g,{'task_id':'task:A','executed':True,'blocked':True,'cause':'missing_required_artifact','source_version':v})
    assert g.block('task:A','task:B','missing_required_artifact',sid,r)['kind']=='TASK_BLOCKED'
    wrong=source(tmp_path,g,{'task_id':'task:A','unblocked':True},'actor_proposal','actorA')
    with pytest.raises(EvidenceError):g.unblock('task:A',wrong)
    ready=source(tmp_path,g,{'task_id':'task:A','unblocked':True,'executed':True});g.unblock('task:A',ready);assert not g.blocked

def test_no_change_is_distinct_from_abstention():
    a=no_change('Existing handoff is sufficient',evidence_sufficient=True);b=no_change('Missing causality evidence',evidence_sufficient=False)
    assert a['action']==b['action']=='No-Change' and not a['abstained_for_insufficient_evidence'] and b['abstained_for_insufficient_evidence']

@pytest.mark.parametrize('kind,origin',[('HANDOFF_PRESENTED','harness_receipt'),('HANDOFF_READ','actor_proposal'),('HANDOFF_ADOPTED','policy_feedback')])
def test_lifecycle_does_not_conflate_sent_read_adopted(kind,origin):
    with pytest.raises(EvidenceError):synchronization_event(kind,{'origin':origin,'payload':{'recipient':'b','source_version':'v1'},'payload_sha256':'test'},'b','v1')

def test_topology_partition_handoffs_permissions_and_memory():
    tasks={'task:A':{'locked_owner':'a','required_tools':['edit']},'task:B':{'required_tools':['edit']},'task:R':{'review_of':'task:A','required_tools':['test']}}
    members={m:{'live':True,'tools':['edit','test']} for m in ['a','b']}
    deps=[{'relation_id':'d','relation_type':'task_depends_on','source_entity':'task:B','target_entity':'task:A','source_version':{'A':1,'B':1},'status':'confirmed','evidence_source':['check']}]
    facts=[{'id':'private','owner':'a'},{'id':'published','owner':'a','granted_to':['b'],'publication_receipt':'grant'}]
    result=partition(tasks,members,deps,facts)
    assert result['status']=='prepared' and result['owners']['task:A']=='a' and result['owners']['task:R']=='b'
    assert 'private' not in result['memory_visibility']['b'] and 'published' in result['memory_visibility']['b']
    assert result['world_actions']==0 and max(result['workload_units'].values())==2

def test_topology_rejects_infeasible_tools_and_bounded_search():
    tasks={'task:A':{'required_tools':['missing']}};members={m:{'live':True,'tools':[]} for m in ['a','b']}
    assert partition(tasks,members,[],[])['status']=='infeasible'
    with pytest.raises(ValueError):partition({str(i):{} for i in range(9)},members,[],[])
