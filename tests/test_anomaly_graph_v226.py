from copy import deepcopy
import pytest
from proworksim.software_anomaly_graph_v226 import AnomalyGraph
from proworksim.software_anomaly_selector_v226 import evaluate,feedback,FEATURES

def act(g,i,tool,result,*,actor='member_001',args=None):
    o={'worker_id':actor,'decision':{'action':tool,'arguments':args or {}},'response':{'command_id':str(i),'ok':True,'result':result}}
    g.observe(i,o)
    return o

def modify(g,i,v):
    act(g,i,'replace_file',{'source_reference':{'object_id':'source','version_id':v},'files_sha256':v})

def run(g,i,v,fail=True,target='a.py::test_x',nested=False):
    act(g,i,'run_tests',{'executed':True,'passed':not fail,'source_reference':{'object_id':'source','version_id':v},
        'counts':{'failed':int(fail),'passed':int(not fail),'tests_run':1,'errors':0},
        'evidence_overview':{'nested_report_count':int(nested)},
        'diagnostic_summary':{'failed_tests':[{'nodeid':target,'phase':'call','outcome':'failed'}]},
        'selection_normalization':{'executed':{'targets':[target]}}})

def test_version_dedup_resolution_reopening_and_cap():
    g=AnomalyGraph('member_001',regression_targets=['a.py::test_reg']);act(g,1,'begin_work',{'task_id':'t'})
    modify(g,2,'v1');run(g,3,'v1');run(g,4,'v1');assert not g.nodes
    modify(g,5,'v2');run(g,6,'v2');n=next(iter(g.nodes.values()));assert n['status']=='OPEN'
    modify(g,7,'v3');run(g,8,'v3',False);act(g,9,'work_readiness',{'ready':True,'task_id':'t'})
    assert n['status']!='RESOLVED'
    run(g,10,'v3',False,'a.py::test_reg');act(g,11,'work_readiness',{'ready':True,'task_id':'t'})
    assert n['status']=='RESOLVED'
    modify(g,12,'v4');run(g,13,'v4');modify(g,14,'v5');run(g,15,'v5')
    assert n['status']=='REOPENED' and n['recurrence']==1 and len(g.wakes)==2

def test_no_nested_or_foreign_evidence_and_exact_replay():
    g=AnomalyGraph('member_001')
    for i in (1,3):
        modify(g,i,str(i));run(g,i+1,str(i),nested=True)
    assert not g.nodes
    o=act(g,5,'integrate_patch',{'conflict_count':1,'source_reference':{'object_id':'x','version_id':'v2'}})
    before=deepcopy(g.view());g.observe(5,o);assert before==g.view()
    act(g,6,'submit_integration',{'episode_state':'DELIVERED'},actor='member_002');assert before==g.view()
    o['response']['result']['conflict_count']=0
    with pytest.raises(ValueError):g.observe(5,o)

def test_blockage_and_delivery_stall_require_evidence():
    g=AnomalyGraph('member_001');act(g,1,'work_readiness',{'task_id':'t','ready':False,'gaps':[{'kind':'upstream_patch_not_adopted','task_id':'p'}]})
    act(g,2,'work_readiness',{'task_id':'t','ready':True,'gaps':[]});assert next(iter(g.nodes.values()))['status']=='RESOLVED'
    ready={'ready_to_submit':True,'final_identity':{'files_sha256':'abc'}}
    act(g,3,'delivery_readiness',ready)
    act(g,4,'read_task',{});act(g,5,'read_task',{});act(g,6,'delivery_readiness',ready)
    assert any(n['anomaly_type']=='A5' for n in g.nodes.values())
    act(g,7,'submit_integration',{'episode_state':'DELIVERED'})
    assert all(n['status']=='RESOLVED' for n in g.nodes.values())

def test_class_mass_and_five_response_interactions():
    ctx={k:.6 for k in FEATURES}
    plans={'KEEP':{'diagnosis':'current','actions':[]},'a':{'diagnosis':'peer','actions':[{'tool':'run_tests'},{'tool':'assign_work'}]}}
    plans['b']={**plans['a'],'actions':plans['a']['actions'][::-1]}
    d=evaluate({'anomaly_type':'A1'},ctx,plans,[0.]*5)
    assert d['q']=={'KEEP':.5,'a':.25,'b':.25}
    outcomes={k:{'legal_correct':k=='KEEP','logical_tokens':100} for k in plans}
    f=feedback(d,outcomes);assert max(f['N'].values())==0 and f['C']['KEEP']>0
    q=evaluate({'anomaly_type':'A1'},ctx,plans,[.7]*5)
    assert feedback(q,outcomes)['target']!=feedback(q,outcomes,novelty=False)['target']

def test_development_confirmation_separation_and_count():
    from proworksim.software_anomaly_selector_v226 import context_from,development_update,confirmation_value,panel_by_effect
    g=AnomalyGraph('member_001');act(g,1,'work_readiness',{'task_id':'t','ready':False,'gaps':[{'kind':'upstream_patch_not_adopted','task_id':'p'}]})
    node=g.view()['anomalies'][0];org={'work':{'t':{'owner':'a','depends_on':['p']},'p':{'owner':'b'}}}
    plans=[('baseline',{'keep':True,'diagnosis':'current','actions':[]}),('worker',{'diagnosis':'peer','actions':[{'actor':'a','tool':'integrate_patch','arguments':{'patch_id':'p'}}]})]
    cs=panel_by_effect(plans+[( 'osa',plans[1][1])]);assert len(cs)==2 and sorted(len(p['sources']) for p in cs.values())==[1,2]
    theta=[0.]*5
    d=evaluate(node,context_from(node,org,3_000_000),cs,theta)
    outcomes={k:{'legal_correct':k=='KEEP','logical_tokens':4_000_000} for k in cs}
    panels=[{'instance_id':i,'decision':d,'outcomes':outcomes,'policy_before':theta,'complete':True,'split':'development'} for i in ['a','b']]
    first=development_update(theta,panels,window=1);assert first['updated']
    assert confirmation_value(d['q'],outcomes)==pytest.approx(.42)
    with pytest.raises(ValueError):development_update(theta,[panels[0],panels[0]],window=1)
    with pytest.raises(ValueError):development_update(theta,[panels[0],{**panels[1],'split':'confirmation'}],window=2)
    assert development_update(theta,[panels[0],{**panels[1],'complete':False}],window=1)['updated'] is False

def test_actual_two_proposals_preserve_choice_and_worker_consent(tmp_path):
    from test_natural_coordination_v224_2 import prepare
    from test_organization_world_v211 import split,ok
    from test_role_baseline_world_v141 import M1,M2
    from proworksim.software_anomaly_pilot_v226 import AnomalyPilot,register_response
    import json
    p,c,_=prepare(tmp_path);split(c);pilot=AnomalyPilot((0.,)*5)
    # Use actual permission-bounded receipts for the two decision points.
    def observe(n,tool,args):
        response=c(M1,tool,**args)
        return pilot.observe(n,{'worker_id':M1,'decision':{'action':tool,'arguments':args},
            'response':response},p.world,4_000_000,worker_request={'member_id':M1,'usage_id':'agent','wire':{'messages':[{'role':'user','content':'WORKER_PRIVATE'}]}})
    def freeze(point,action):
        assert 'WORKER_PRIVATE' not in str(point.osa_request)
        choices=[]
        for session,wire,who in [(pilot.worker,point.worker_request,'worker'),(pilot.osa,point.osa_request,'osa')]:
            msg=json.loads(wire['messages'][-1]['content']);e=msg['anomaly']['evidence_refs'][0]['id']
            options=[i for i,v in msg['available_options'].items() if v['operation']==action] if who=='osa' else []
            choices.append(session.receive('propose_response',{'option_ids':options[:1],'evidence_ids':[e],'reason':'Based on actual work readiness.'}))
        bank,d=pilot.bank(point,*choices)
        assert 'KEEP' in bank and len(d['features']['KEEP'])==5
        candidate=choices[-1];register_response(p.world,candidate,{'synthetic_control':True},point.node,evidence_ids=candidate['evidence_ids'])
        return candidate
    # Define a genuine unmet upstream obligation under the actual world.
    ok(c,M1,'change_dependency',task_id='regression',depends_on='behavior',operation='add',reason='Real upstream')
    pt=observe(1,'work_readiness',{'task_id':'regression'});assert pt.node['anomaly_type']=='A2'
    first=freeze(pt,'KEEP');ok(c,M1,'select_arrangement',candidate_id=first['candidate_id'],decision='keep',reason='Retain owners')
    assert observe(2,'work_readiness',{'task_id':'regression'}) is None
    # A second, distinct signed work_test_missing rejection: cannot invent one.
    ok(c,M1,'assign_verification',task_id='behavior',reviewer=M2,reason='Independent')
    ok(c,M1,'add_collaboration',task_id='behavior',peer=M2,reason='Review')
    ok(c,M1,'begin_work',task_id='behavior');ok(c,M1,'write_file',path='sample.py',text='value = 2\n')
    patch=ok(c,M1,'fix_patch',task_ids=['behavior'],message='Actual version')['patch_id']
    pt=observe(8,'complete_work',{'task_id':'behavior','patch_id':patch});assert pt.node['anomaly_type']=='A4'
    second=freeze(pt,'peer_diagnosis')
    assert p.world.protocol()['choice'] is None and p.world.protocol()['v226_decisions'][0]['choice']['decision']=='keep'
    ok(c,M1,'select_arrangement',candidate_id=second['candidate_id'],decision='attempt',reason='Allow peer diagnosis')
    for step in second['actions']:ok(c,step['actor'],step['tool'],**step['arguments'])
    assert p.world._task('behavior')['owner']==M1 and p.world.dynamic()['work']['behavior']['authors']==[M1]

def test_regression_requires_matching_preintegration_version_and_evidence_to_close():
    g=AnomalyGraph('member_001',regression_targets=['a.py::test_reg'])
    act(g,1,'begin_work',{'task_id':'t'});modify(g,2,'old')
    run(g,3,'old',False);modify(g,4,'before')
    act(g,5,'integrate_patch',{'source_reference':{'object_id':'source','version_id':'merge0'},'conflicts':[]})
    run(g,6,'merge0');assert not any(n['anomaly_type']=='A3' for n in g.nodes.values())
    run(g,7,'merge0',False)
    act(g,8,'integrate_patch',{'source_reference':{'object_id':'source','version_id':'merge1'},'conflicts':[]});run(g,9,'merge1')
    n=next(n for n in g.nodes.values() if n['anomaly_type']=='A3');assert n['status']=='OPEN'
    modify(g,10,'repair');run(g,11,'repair',False);run(g,12,'repair',False,'a.py::test_reg')
    act(g,13,'delivery_readiness',{'ready_to_submit':True,'final_test':{'passed':True},'final_identity':{'source_reference':{'object_id':'source','version_id':'repair'}},'gaps':[],'current_fixed_patch_ids':['p']})
    assert n['status']=='RESOLVED'

def test_endpoint_silence_and_incomplete_repair_are_unknown():
    from proworksim.software_anomaly_graph_v226 import mechanism_endpoint
    g=AnomalyGraph('member_001');act(g,1,'begin_work',{'task_id':'t'})
    modify(g,2,'v1');run(g,3,'v1');modify(g,4,'v2');run(g,5,'v2')
    node=next(iter(g.nodes))
    assert mechanism_endpoint(g.view(),node,5)['resolved'] is None
    modify(g,6,'v3');run(g,7,'v3',False)
    assert mechanism_endpoint(g.view(),node,5)['resolved'] is None

def test_negative_control_needs_actual_progress_not_silence():
    from proworksim.software_anomaly_pilot_v226 import stable_control_node
    g=AnomalyGraph('member_001')
    with pytest.raises(ValueError):stable_control_node(g,[],affected_work=['t'])
    samples=[]
    for i in [1,2]:
        r={'executed':True,'passed':True,'counts':{'passed':1,'tests_run':1},'source_reference':{'object_id':'x','version_id':str(i)}}
        samples.append((i,act(g,i,'run_tests',r)))
    assert stable_control_node(g,samples,affected_work=['t'])['status']=='STABLE'
    act(g,3,'work_readiness',{'task_id':'t','ready':False,'gaps':[{'kind':'upstream_patch_not_adopted','task_id':'p'}]})
    with pytest.raises(ValueError):stable_control_node(g,samples,affected_work=['t'])

def test_complete_panel_cash_atomic_and_real_usage_reconciliation(tmp_path):
    from test_mapping_development_v224 import make_ledger
    from proworksim.software_anomaly_budget_v226 import AnomalyLedger,AdmissionStopped
    ledger=AnomalyLedger(make_ledger(tmp_path).path,stage='v227',stage_cny=100)
    with pytest.raises(AdmissionStopped):ledger.reserve_panel('large',{'v227:'+z:5_000_000 for z in ['KEEP','W','O']})
    with ledger.db() as db:assert db.execute("select count(*) from block_slots").fetchone()[0]==0
    slots={'v227:KEEP':3_000_000,'v227:W':3_000_000,'v227:O':3_000_000};ledger.reserve_panel('whole',slots)
    for slot,limit in slots.items():
        ledger.admit(slot,limit);ledger.reserve(slot,slot+':r',200)
        body={'id':slot,'model':'deepseek-flash','usage':{'prompt_tokens':100,'completion_tokens':5,'total_tokens':105,'prompt_cache_hit_tokens':80,'prompt_cache_miss_tokens':20}}
        actual=ledger.settle(slot+':r',body);assert actual['input_tokens']==100 and actual['output_tokens']==5
        ledger.close(slot)
    with pytest.raises(ValueError):ledger.reserve_panel('repeat',slots)

def test_worker_execution_is_bound_to_original_receipt_and_not_resolution():
    from proworksim.software_anomaly_pilot_v226 import record_execution
    g=AnomalyGraph('member_001')
    act(g,1,'work_readiness',{'task_id':'t','ready':False,'gaps':[{'kind':'upstream_patch_not_adopted','task_id':'p'}]})
    node=next(iter(g.nodes.values()));args={'patch_id':'p1'}
    response={'candidate_id':'z','actions':[{'actor':'member_001','tool':'integrate_patch','arguments':args}]}
    o=act(g,2,'integrate_patch',{'source_reference':{'object_id':'x','version_id':'v2'}},args=args)
    record_execution(g,node,response,o,2,set())
    assert node['response_history'][0]['disposition']=='executed' and node['status']=='ACTIVE'
    bad=deepcopy(o);bad['response']['result']['forged']=True
    with pytest.raises(ValueError):record_execution(g,node,response,bad,2,set())
