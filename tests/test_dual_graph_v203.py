import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from org_scenarios_v203 import cases
from proworksim.software_org_policy_v203 import propose,TransferEvidence
from proworksim.software_dual_graph_v203 import CrossGraph,completeness

@pytest.mark.parametrize('case',cases(),ids=lambda c:c['id'])
def test_authored_structural_control(case):
    before=copy.deepcopy(case);result=propose(case['state'],'O4')
    actual={(c['operation'],tuple(c['tasks'])) for c in result['candidates'] if c['validation']['valid']}
    expected={(c['operation'],tuple(c['tasks'])) for c in case['expected_valid_interventions']}
    assert actual==expected and case==before and result['world_actions']==0

def test_completeness_axes_do_not_promote_scope():
    q=completeness({'node_syntax_complete':True,'syntax_node_type':'Assign','file_source_complete':False,'qualified_scope_known':False})
    assert q['statement_complete'] and q['span_complete'] and not q['scope_complete'] and not q['file_complete']

def test_receipt_projection_rollback_and_ownership_not_file_ownership():
    g=CrossGraph('test',['a','b']);e={'id':'e1','actor':'a','action':'claim_task','arguments':{},'step':1,'ok':True,'source':{'pointer':'test'},'result':{'task_id':'T','owner':'a','revision':1}}
    g.observe(e);g.observe(e);assert len(g.events)==1
    assert g.edges[0]['not_file_ownership'] is True
    old=copy.deepcopy(g.__dict__);bad=copy.deepcopy(e);bad['id']='e2';bad['result']['owner']='foreign'
    with pytest.raises(ValueError):g.observe(bad)
    assert g.__dict__==old

def test_migration_cannot_skip_or_copy_private_memory():
    package={'task_id':'T','task_revision':1,'old_owner':'a','new_owner':'b','project_region':['sample.py'],'code_version':{'object_id':'o','version_id':'v1'},
        'artifacts':['p1'],'test_evidence':[],'required_facts':[{'value':'value = 2','access':'published_artifact'}],'unresolved_issues':[],
        'provenance':['source'],'permissions':['published:p1']}
    observer=TransferEvidence(package)
    with pytest.raises(ValueError):observer.advance('VERIFIED',{'ok':True})
    assert observer.state=='PROPOSED'
    package['required_facts'][0]['access']='peer_private_history'
    with pytest.raises(ValueError):TransferEvidence(package)

def test_complete_package_readback_required_before_context_transferred():
    from proworksim.software_responsibility_transfer_v203 import TransferEvidence as StrictTransfer
    import json
    package={'task_id':'T','task_revision':1,'old_owner':'a','new_owner':'b','project_region':['sample.py'],'code_version':{'object_id':'o','version_id':'v1'},
        'artifacts':['p1'],'test_evidence':[],'required_facts':[{'value':'value = 2','access':'published_artifact'}],'unresolved_issues':[],'provenance':['source'],'permissions':['published:p1']}
    t=StrictTransfer(package)
    offer={'ok':True,'source':{'receipt':1},'actor':'a','tool':'offer_transfer','arguments':{},'result':{'offer_id':'off1','task_id':'T','task_revision':1,'recipient':'b','from_member':'a'}}
    t.advance('AUTHORIZED',offer)
    accepted={'ok':True,'source':{'receipt':2},'actor':'b','tool':'accept_transfer','arguments':{'offer_id':'off1'},'result':{'task_id':'T','owner':'b','revision':1}}
    wrong=copy.deepcopy(accepted);wrong['result']['task_id']='another'
    with pytest.raises(ValueError):t.advance('ACCEPTED',wrong)
    assert t.state=='AUTHORIZED';t.advance('ACCEPTED',accepted)
    source={'ok':True,'source':{'receipt':3},'actor':'b','tool':'read_file','arguments':{},'result':{'source_reference':package['code_version'],'text':'value = 2\n'}}
    with pytest.raises(ValueError):t.advance('CONTEXT_TRANSFERRED',source)
    readback={'ok':True,'source':{'receipt':4},'actor':'b','tool':'read_work_event','arguments':{},'result':{'actor_id':'a','recipient':'b','task_id':'T','body':json.dumps(package)}}
    bad=copy.deepcopy(readback);bad['result']['body']=json.dumps({'preview':'truncated'})
    with pytest.raises(ValueError):t.acknowledge_package(bad)
    t.acknowledge_package(readback);t.advance('CONTEXT_TRANSFERRED',source);assert t.state=='CONTEXT_TRANSFERRED'

def test_mapping_confidence_revision_and_explicit_cross_region():
    g=CrossGraph('test',['a','b'])
    def observe(i,actor,action,result,args=None):g.observe({'id':str(i),'actor':actor,'action':action,'arguments':args or {},'step':i,'ok':True,'source':{'control':i},'result':result})
    observe(1,'a','claim_task',{'task_id':'A','owner':'a','revision':1})
    observe(2,'b','claim_task',{'task_id':'B','owner':'b','revision':1,'depends_on':['A'],'dependency_revisions':{'A':1}})
    assert any(e['kind']=='crosses_region' for e in g.snapshots[-1]['edges'])
    observe(3,'a','org_matrix_scope',{'task_id':'B','task_revision':1,'assignee':'b'})
    observe(4,'b','revise_task',{'task_id':'B','owner':'b','revision':2,'depends_on':[]})
    assert not any(e['kind'] in {'assigned_to','crosses_region'} for e in g.snapshots[-1]['edges'])
    observe(5,'b','run_tests',{'report_id':'r','executed':True,'passed':True,'source_reference':{'object_id':'b','version_id':'v1'}},{'selection':['public']})
    e=next(e for e in g.snapshots[-1]['edges'] if e['kind']=='validates')
    assert e['status']=='Confirmed Dynamic' and 'not_program_call_coverage' in e['confirmation_scope']
