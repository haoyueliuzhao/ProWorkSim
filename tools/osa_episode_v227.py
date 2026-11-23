"""Fresh two-worker development attempt; match the preselected scene using live receipts."""
import argparse
import json
import os
import time
import traceback
from pathlib import Path
from copy import deepcopy
from proworksim.storage import json_bytes, atomic_write
from proworksim.software_anomaly_budget_v226 import AnomalyLedger
from proworksim.software_benchmark_candidates_v054 import checked,reference

R=Path(__file__).resolve().parents[1]
P=R/'artifacts/software-benchmark-v227/window-r1'
L=R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
def read(p):return json.loads(p.read_bytes())
def save(p,v):atomic_write(p,json_bytes(v))
class PointFound(Exception):pass

class PreparationLedger(AnomalyLedger):
    def __init__(self):
        super().__init__(L,stage='v227',stage_cny=15)
        self.stage='v227prep'

def proposals(point, organization, node, remaining, worker_request, theta, counter, key, out, task_id):
    from proworksim.software_osa_session_v226 import OSASession,fingerprint
    from proworksim.software_anomaly_selector_v226 import panel_by_effect,context_from,evaluate
    from proworksim.software_organization_api_v204 import Backend,DirectHTTPS
    from proworksim.software_organization_proposal_budget_v223_2 import prepare_dispatch
    from proworksim.software_osa_session_v226 import project_evidence
    meter=PreparationLedger()
    limit=min(150_000,max(0,(remaining-40_000)//2))
    if limit<1:raise ValueError('Insufficient remaining logical tokens to request paired proposals')
    slots={w:f'v227prep:{task_id}:{w}' for w in ('worker','osa')}
    meter.reserve_panel(task_id,{slot:limit for slot in slots.values()})
    keep={'keep':True,'candidate_id':'KEEP-'+node['anomaly_id'],'diagnosis':'current','actions':[],
          'response_categories':['KEEP'],'reason':'Retain current arrangement','anomaly_id':node['anomaly_id'],
          'evidence_ids':[project_evidence(node['evidence_refs'][0])['id']]}
    plans=[('baseline',keep)]
    for who,slot in slots.items():
        folder=out/who;folder.mkdir()
        meter.admit(slot,limit)
        try:
            session=OSASession(fingerprint(theta))
            original=session.request(node,organization,remaining_tokens=remaining)
            wire={**original,'model':'deepseek-flash','thinking':{'type':'disabled'},'temperature':1.0,'top_p':1.0,'stream':False,'max_tokens':4096,'tool_choice':'auto'}
            if who=='worker':
                assert worker_request['member_id']==point and worker_request['usage_id']=='agent'
                wire['messages'][0]['content']='You are the actual worker. Propose a local response using your own observed task context and the allowed options, or retain current responsibilities. Cite evidence IDs.'
                wire['messages'].insert(1,{'role':'user','content':json.dumps(worker_request['wire']['messages'],ensure_ascii=False)})
            backend=Backend(folder/'api',meter,slot,counter,DirectHTTPS(key,timeout_seconds=1800),{'propose_response'})
            for attempt in range(2):
                with meter.db() as db:n=db.execute('select coalesce(sum(tokens),0) from requests where slot=?',(slot,)).fetchone()[0]
                wire,allocation=prepare_dispatch(wire,counter,limit-n)
                if not allocation['dispatch']:raise ValueError('Proposal token boundary')
                response=backend.post('/chat/completions',{'wire':wire,'team_slot_id':slot,'member_id':point,'usage_id':'agent'})
                msg=response['choices'][0]['message'];calls=msg.get('tool_calls') or []
                try:
                    if len(calls)!=1:raise ValueError('One proposal required')
                    fn=calls[0]['function'];plan=session.receive(fn['name'],json.loads(fn['arguments']))
                    plans.append((who,plan));save(folder/'plan.json',plan);break
                except (ValueError,KeyError,TypeError,PermissionError) as exc:
                    save(folder/f'invalid-{attempt}.json',{'reason':str(exc)})
                    if attempt==1:break
                    wire['messages'] += [msg]+[{'role':'tool','tool_call_id':c['id'],'content':str(exc)} for c in calls]+[{'role':'user','content':'Correct the proposal once, using only current evidence and option IDs.'}]
        except Exception as exc:
            save(folder/'error.json',{'type':type(exc).__name__,'message':str(exc)})
        finally:meter.close(slot)
    with meter.db() as db:
        if any(db.execute('SELECT status FROM slots WHERE id=?',(s,)).fetchone()!=('closed',) for s in slots.values()):raise ValueError('Unsettled proposal usage')
        charge=sum(db.execute('SELECT coalesce(sum(tokens),0) FROM requests WHERE slot=?',(s,)).fetchone()[0] for s in slots.values())
    candidates=panel_by_effect(plans)
    decision=evaluate(node,context_from(node,organization,remaining-charge),candidates,theta)
    return {'candidates':candidates,'decision':decision,'proposal_tokens':charge,'limit':remaining-charge,'node':node,'policy_before':theta}

def main(a):
    from proworksim import software_natural_organization_runtime_v224_2 as rtlib,software_natural_organization_world_v224_2 as world,software_role_baseline_world_v141 as base,software_sdk_resume_v203_3_4 as resume
    from proworksim.software_organization_actor_v223_1 import Actor
    from proworksim.software_organization_runtime_v204 import after_opportunity,public_context
    from proworksim.software_organization_api_v204 import Backend,DirectHTTPS
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_anomaly_graph_v226 import AnomalyGraph,mechanism_endpoint
    from proworksim.software_natural_checkpoint_v224_2 import INITIAL_WORK_INSTRUCTION
    from proworksim.software_anomaly_pilot_v226 import register_response,record_execution,stable_control_node
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(out/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHON_DOTENV_DISABLED='1',OPENHANDS_SUPPRESS_BANNER='1')
    row=read(P/'candidate-tasks.json')['rows'][a.index]
    actor=rt=None;admitted=False;meter=AnomalyLedger(L,stage='v227',stage_cny=100)
    slot='v227:'+out.parent.name+':'+out.name;prefix=out.parent/'PREFIX'
    branch=a.condition!='PREFIX'
    result={'status':'preparing','condition':a.condition,'instance_id':row['instance_id'],'slot':slot,'started':time.time()}
    save(out/'result.json',result)
    try:
        for ref in read(P/'freeze.json')['files']:checked(ref)
        bank=read(prefix/'bank.json') if branch else None
        cp=prefix/'checkpoint'
        state=resume.read(cp)[0] if branch else None
        limit=bank['limit'] if branch else 5_000_000;fee=bank['proposal_tokens'] if branch else 0
        actor=Actor(row,out/'actor',resume_test_calls=state['public_test_calls'] if state else 0);actor.start()
        deadline=DispatchDeadline(soft_seconds=21600,hard_seconds=23400)
        prepared=base.prepare_case(out/'actor/source-manifest.json',out/'prepared',organization_id='FREE2',public_test_callback=actor.test,deadline=deadline,public_test_entry=actor.entry)
        world.attach(prepared,[x['id'] for x in row['requirements']],condition='G')
        if branch:resume.restore_world(prepared,cp)
        tok=R/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';h=reference(tok)['sha256']
        counter=OfficialDeepSeekCounter(tok,manifest_sha256=h);content,meta=load_official_content_counter(tok,manifest_sha256=h)
        names={t['function']['name'] for m in ('member_001','member_002') for t in rtlib.member_wire_tools('FREE2',m)}
        key=load_api_key(R/'.env')
        backend=Backend(out/'api',meter,slot,counter,DirectHTTPS(key,timeout_seconds=1800),names)
        latest={};observer=row['observer'];graph=AnomalyGraph(observer)
        def post(route,payload):
            if route=='/chat/completions':
                if prepared.world.protocol()['terminal']:raise ValueError('Terminal episode')
                if payload['usage_id']=='agent':latest[payload['member_id']]=deepcopy(payload)
            return backend.post(route,payload)
        owner=rtlib.build_team_owner(post,organization_id='FREE2',slot_id=slot,condition_id='v227-'+a.condition,folder=out/'model-ledger',deadline=deadline,identity={'policy_version':rtlib.VERSION,'model':'deepseek-flash','thinking':False},observation_token_counter=content,observation_tokenizer_id=meta['tokenizer_id'],require_content_counter=True)
        initial=rtlib.CONTRACT+'\n'+actor.config['public_task']['problem_statement']+'\n'+public_context(actor.config,actor.public)
        rt,_,_=rtlib.build_runtime(owner,prepared,out/'runtime',deadline=deadline,public_initial_message=initial)
        resume.register_persistence_types();offers=set();history=[];node=None
        if branch:
            save(out/'restore.json',resume.restore_runtime(prepared,rt,cp));rtlib.set_native_limit(rt,5_000_000-fee)
            node=bank['node'];candidate=bank['candidates'][a.condition]
            graph.regression_targets=frozenset(bank['regression_targets'])
            for previous in read(prefix/'observations.json'):
                graph.observe(previous['ordinal'],previous['outcome'])
            if node['anomaly_type']=='STABLE':graph.nodes[node['anomaly_id']]=deepcopy(node)
            register_response(prepared.world,candidate,{'bank':reference(prefix/'bank.json')},node,evidence_ids=candidate['evidence_ids'])
            for w in rt.policies.values():w.conversation.send_message('Recorded proposal. The integrator chooses keep, defer or attempt. Members can decline. Continue the original task and submit when ready. Proposal: '+json.dumps(candidate,ensure_ascii=False))
            rtlib.enter_continuation(rt)
        else:
            rtlib.set_native_limit(rt,5_000_000)
            for w in rt.policies.values():w.conversation.send_message(INITIAL_WORK_INSTRUCTION+' Public scope annotations: '+json.dumps(row['requirements'],ensure_ascii=False))
        actor.bind_deadline(rt.deadline);meter.admit(slot,limit);admitted=True
        result['status']='running';save(out/'result.json',result)
        def step(outcome):
            nonlocal node
            after_opportunity(actor,out/'transport-fault.json');ordinal=rt.opportunities
            graph.observe(ordinal,outcome)
            if outcome.get('worker_id')==observer:history.append({'ordinal':ordinal,'outcome':outcome})
            if branch:record_execution(graph,node,bank['candidates'][a.condition],outcome,ordinal,offers)
            usage=owner.adapter.ledger.snapshot()
            save(out/'progress.json',{'opportunity':ordinal,'tokens':usage['known_actual_tokens']+fee,'anomalies':[(n['anomaly_type'],n['status']) for n in graph.nodes.values()],'terminal':prepared.world.protocol()['terminal']})
            if branch or prepared.world.protocol()['terminal'] or observer not in latest or usage['known_actual_tokens']>=4_960_000:return
            for n in graph.nodes.values():
                if n['anomaly_type']==row['target_scene'] and n['status'] in ('OPEN','ACTIVE','REOPENED') and n['affected_work']:
                    node=n;raise PointFound
            if row['target_scene']=='STABLE':
                try:node=stable_control_node(graph,[(s['ordinal'],s['outcome']) for s in history],affected_work=[graph.current_work] if graph.current_work else [])
                except ValueError:return
                raise PointFound
        try:
            boundary=rtlib.run_fragment(prepared,rt,on_opportunity=step)
            save(out/'boundary.json',boundary)
            if boundary['execution_integrity_failure']:raise ValueError('Execution integrity failure')
            result.update(status='closed',matched=branch,logical_tokens=owner.adapter.ledger.actual+fee,termination=boundary['termination_class'])
            if branch:result['worker_choice']=prepared.world.protocol().get('choice')
            if branch:result['anomaly_endpoint']=mechanism_endpoint(graph.view(),node['anomaly_id'],bank['ordinal'])
            rtlib.close_runtime(rt);rt=None;save(out/'candidate-lock.json',rtlib.lock_fixed_candidates(prepared,out/'closure',sdk_closed=True))
        except PointFound:
            remaining=5_000_000-owner.adapter.ledger.actual
            save(out/'observations.json',history)
            save(out/'checkpoint-proof.json',resume.save(prepared,rt,out/'checkpoint',control_state={'node':node,'ordinal':rt.opportunities}))
            org=prepared.world._action_dynamic_status(observer,'SOFTWARE27')
            bank=proposals(observer,org,node,remaining,latest[observer],read(a.policy),counter,key,out,out.parent.name)
            bank['regression_targets']=sorted({test for tests in graph.test_passes.values() for test in tests if test!=node.get('subject')})[:2]
            bank['ordinal']=rt.opportunities;save(out/'bank.json',bank)
            result.update(status='point_ready',matched=True,prefix_tokens=owner.adapter.ledger.actual)
        save(out/'graph.json',graph.view())
    except Exception as error:
        result.update(status='technical_unknown',error=str(error),traceback=traceback.format_exc())
    finally:
        try:
            if rt:rtlib.close_runtime(rt)
        finally:
            if admitted:meter.close(slot)
            if actor:actor.close()
            save(out/'result.json',{**result,'finished':time.time()})

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--index',type=int,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',required=True);p.add_argument('--policy',type=Path,required=True);main(p.parse_args())
