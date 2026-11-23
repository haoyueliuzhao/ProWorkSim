"""One fresh prefix or one paired continuation on the same original OpenHands state."""
import argparse
import json
import os
import time
import traceback
from copy import deepcopy
from pathlib import Path

from proworksim.software_anomaly_budget_v226 import AnomalyLedger
from proworksim.software_benchmark_candidates_v054 import checked,reference
from proworksim.software_graph_controller_v228 import ACCOUNTABLE,ControlledWorld,activate,graph,menu
from proworksim.storage import atomic_write,json_bytes

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'artifacts/software-benchmark-v228/control-r1'
LEDGER=ROOT/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite'
LIMIT=5_000_000


def read(path):
    return json.loads(path.read_bytes())


def save(path,value):
    atomic_write(path,json_bytes(value))


class Snapshot(Exception):
    pass


def request_graph(world,node,observer,counter,transport,meter,slot,out,remaining,blocker):
    from proworksim.software_organization_api_v204 import Backend
    from proworksim.software_organization_proposal_budget_v223_2 import prepare_dispatch
    out.mkdir()
    frozen=menu(world,node,observer)
    save(out/'options.json',frozen)
    fn={'name':'activate_organization','description':'Choose a legal local target by ID and cite its evidence.',
        'parameters':{'type':'object','properties':{'option':{'type':'string','enum':list(frozen['options'])},
          'evidence':{'type':'array','items':{'type':'string','enum':list(frozen['evidence'])},'minItems':1},
          'reason':{'type':'string','maxLength':1200}},'required':['option','evidence','reason'],'additionalProperties':False}}
    payload={**frozen,'remaining_team_tokens':remaining,'reported_execution_blocker':blocker}
    prompt=('You control the active organization graph of two workers. Choose KEEP (K) when appropriate. '
            'A diagnosis option assigns the other worker a scoped evidence-gathering and handoff duty. '
            'A transfer option changes only unstarted work. Evaluate the observed problem, switching costs, '
            'stage and remaining budget. You cannot write code, run tests or submit. '
            'Use activate_organization exactly once. Use short IDs such as E1 to cite the actual evidence.')
    wire={'model':'deepseek-flash','thinking':{'type':'disabled'},'temperature':1.0,'top_p':1.0,
          'stream':False,'max_tokens':2048,'tools':[{'type':'function','function':fn}],'tool_choice':'auto',
          'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]}
    backend=Backend(out/'api',meter,slot,counter,transport,{'activate_organization'})
    charged=0
    for attempt in range(2):
        wire,allocation=prepare_dispatch(wire,counter,min(remaining,60_000)-charged)
        if not allocation['dispatch']:break
        response=backend.post('/chat/completions',{'wire':wire,'team_slot_id':slot,'member_id':observer,'usage_id':'agent'})
        charged+=response['usage']['total_tokens']
        msg=response['choices'][0]['message']
        calls=msg.get('tool_calls') or []
        try:
            if len(calls)!=1 or calls[0]['function']['name']!=fn['name']:raise ValueError('Choose exactly one listed target')
            record=activate(world,node,observer,frozen,json.loads(calls[0]['function']['arguments']),origin='osa')
            save(out/'activation.json',record)
            return charged,record
        except (ValueError,TypeError,KeyError) as error:
            save(out/f'rejected-{attempt}.json',{'reason':str(error)})
            wire['messages'] += [msg]+[{'role':'tool','tool_call_id':c['id'],'content':str(error)} for c in calls]+[
                {'role':'user','content':'Correct the decision once using only the supplied option and evidence IDs.'}]
    return charged,None


def main(args):
    from proworksim import software_natural_organization_runtime_v224_2 as native, software_natural_organization_world_v224_2 as natural
    from proworksim import software_role_baseline_world_v141 as base,software_sdk_resume_v203_3_4 as resume
    from proworksim.software_organization_actor_v223_1 import Actor
    from proworksim.software_organization_runtime_v204 import after_opportunity,public_context
    from proworksim.software_organization_api_v204 import Backend,DirectHTTPS
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    from proworksim.software_benchmark_deepseek_api_v105 import load_api_key
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_anomaly_graph_v226 import AnomalyGraph,mechanism_endpoint
    from proworksim.software_anomaly_pilot_v226 import stable_control_node
    from proworksim.software_natural_checkpoint_v224_2 import INITIAL_WORK_INSTRUCTION
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(out/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',HF_HUB_OFFLINE='1',
                      HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHON_DOTENV_DISABLED='1',OPENHANDS_SUPPRESS_BANNER='1')
    row=read(PLAN/'panel.json')['rows'][args.index]
    mode=args.condition;observer=row['observer'];slot=f'v228:{out.parent.name}:{mode}'
    meter=AnomalyLedger(LEDGER,stage='v228',stage_cny=135);actor=runtime=None;admitted=False
    result={'status':'preparing','instance_id':row['instance_id'],'condition':mode,'slot':slot,'started':time.time()}
    save(out/'result.json',result)
    try:
        for item in read(PLAN/'freeze.json')['files']:checked(item)
        state=None
        if mode!='PREFIX':
            prefix=args.prefix;cp=prefix/'checkpoint';state,proof=resume.read(cp)
            node=state['control_state']['node'];ordinal=state['control_state']['ordinal']
            prefix_tokens=proof['prefix_tokens']
        else:prefix_tokens=0;node=None
        actor=Actor(row,out/'actor',resume_test_calls=state['public_test_calls'] if state else 0);actor.start()
        deadline=DispatchDeadline(soft_seconds=21600,hard_seconds=23400)
        test_cost={'calls':0,'callback_wall_seconds':0.0,'reported_command_seconds':0.0}
        def public_test(**kwargs):
            start=time.monotonic();test_cost['calls']+=1
            try:
                result=actor.test(**kwargs)
                test_cost['reported_command_seconds']+=result.get('execution',{}).get('wall_seconds',0)
                return result
            finally:test_cost['callback_wall_seconds']+=time.monotonic()-start
        prepared=base.prepare_case(out/'actor/source-manifest.json',out/'prepared',organization_id='FREE2',
                                   public_test_callback=public_test,deadline=deadline,public_test_entry=actor.entry)
        natural.attach(prepared,[x['id'] for x in row['requirements']],condition='G')
        if state:resume.restore_world(prepared,cp)
        world=prepared.world;world.__class__=ControlledWorld
        tok=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json';h=reference(tok)['sha256']
        counter=OfficialDeepSeekCounter(tok,manifest_sha256=h);content,meta=load_official_content_counter(tok,manifest_sha256=h)
        names={t['function']['name'] for m in ('member_001','member_002') for t in native.member_wire_tools('FREE2',m)}
        wire=DirectHTTPS(load_api_key(ROOT/'.env'),timeout_seconds=1800)
        worker=Backend(out/'api',meter,slot,counter,wire,names)
        def post(route,payload):
            if route=='/chat/completions' and world.protocol()['terminal']:raise ValueError('Episode already terminal')
            return worker.post(route,payload)
        owner=native.build_team_owner(post,organization_id='FREE2',slot_id=slot,condition_id='v228-'+mode,
                folder=out/'model-ledger',deadline=deadline,identity={'policy_version':native.VERSION,'model':'deepseek-flash','thinking':False},
                observation_token_counter=content,observation_tokenizer_id=meta['tokenizer_id'],require_content_counter=True)
        initial=native.CONTRACT+'\n'+actor.config['public_task']['problem_statement']+'\n'+public_context(actor.config,actor.public)
        runtime,_,_=native.build_runtime(owner,prepared,out/'runtime',deadline=deadline,public_initial_message=initial)
        resume.register_persistence_types()
        monitor=AnomalyGraph(observer);history=[];metrics={'eligible':0,'valid':0,'rejections':{},'by_tool':{},'public_test_attempts':0,'handoff_attempts':0}
        cost=0;calls=0;seen_blockers=0;controller_seconds=0.0
        def notify(text,members=None):
            for member,w in runtime.policies.items():
                if not members or member in members:w.conversation.send_message(text)
        def decide(blocker=None):
            nonlocal cost,calls,controller_seconds
            if runtime.team_budget.snapshot()['held_tokens']:raise ValueError('In-flight worker call')
            start=time.monotonic();calls+=1
            charge,record=request_graph(world,node,observer,counter,wire,meter,slot,out/f'control-{calls}',
                               LIMIT-owner.adapter.ledger.actual-cost,blocker)
            controller_seconds+=time.monotonic()-start;cost+=charge
            runtime.team_budget.native_allocation=LIMIT-cost
            if not record:
                if calls==1:raise ValueError('Invalid controller decision; no W1 graph activated')
                notify('Blocker reviewed; no valid replacement graph. Existing organization remains active.')
                return
            notify('Active organization version '+str(record['version'])+'. Use dynamic_status to read current work. '
                   'This active graph supersedes old consent or voting instructions. Carry out your own assigned work. '
                   'For pending diagnosis send_message to its recipient on its task with DIAG <your new read/test event sequence> <finding>. '
                   'For an actual obstacle use send_message with BLOCK <permission|dependency|in_flight|budget|state_conflict> <specific obstacle>. '
                   'Review and delivery still require actual work and exact evidence. Current graph: '+json.dumps(record['after']))
        if state:
            save(out/'restore.json',resume.restore_runtime(prepared,runtime,cp))
            for prev in read(prefix/'observations.json'):monitor.observe(prev['ordinal'],prev['outcome'])
            if node['anomaly_type']=='STABLE':monitor.nodes[node['anomaly_id']]=deepcopy(node)
            monitor.regression_targets=frozenset(sorted({s for passed in monitor.test_passes.values() for s in passed if s!=node.get('subject')})[:2])
            save(out/'common-state.json',{'checkpoint':proof['identity'],'node':node,'graph':graph(world),
                 'remaining':LIMIT-prefix_tokens,'regression_targets':sorted(monitor.regression_targets)})
            notify('Work observation: '+json.dumps({'kind':node['anomaly_type'],'subject':node.get('subject'),'scopes':node['affected_work']}),[observer])
            native.enter_continuation(runtime)
        native.set_native_limit(runtime,LIMIT)
        actor.bind_deadline(runtime.deadline);meter.admit(slot,LIMIT-prefix_tokens);admitted=True
        result['status']='running';save(out/'result.json',result)
        if mode=='W1':decide()
        elif mode=='W0':notify('Autonomous organization. Decide and coordinate yourselves with the existing managed tools, retain or change duties as useful. Continue the original issue.')
        else:notify(INITIAL_WORK_INSTRUCTION+' Public scope annotations: '+json.dumps(row['requirements']))
        def step(outcome):
            nonlocal node,seen_blockers
            after_opportunity(actor,out/'transport-fault.json');i=runtime.opportunities
            monitor.observe(i,outcome)
            action=(outcome.get('decision') or {}).get('action');resp=outcome.get('response') or {}
            if state and action in ACCOUNTABLE:
                valid=int(resp.get('ok') is True);metrics['eligible']+=1;metrics['valid']+=valid
                if not valid:
                    code=((resp.get('error') or {}).get('rejection') or {}).get('code','unclassified')
                    metrics['rejections'][code]=metrics['rejections'].get(code,0)+1
                counts=metrics['by_tool'].setdefault(action,[0,0]);counts[0]+=valid;counts[1]+=1
                metrics['public_test_attempts']+=action in ('run_tests','run_patch_review_tests')
                metrics['handoff_attempts']+=action in ('handoff_patch','send_message')
            save(out/'progress.json',{'opportunity':i,'logical_tokens':owner.adapter.ledger.actual+cost,
                                      'osa_tokens':cost,'anomalies':[(n['anomaly_type'],n['status']) for n in monitor.nodes.values()]})
            if world.protocol()['terminal']:return
            if mode=='PREFIX':
                if outcome.get('worker_id')==observer:history.append({'ordinal':i,'outcome':outcome})
                if owner.adapter.ledger.actual>=4_960_000:return
                for n in monitor.nodes.values():
                    if n['anomaly_type']==row['target_scene'] and n['status'] in ('OPEN','ACTIVE','REOPENED') and n['affected_work']:
                        node=n;raise Snapshot
                if row['target_scene']=='STABLE' and monitor.current_work:
                    try:node=stable_control_node(monitor,[(o['ordinal'],o['outcome']) for o in history],affected_work=[monitor.current_work])
                    except ValueError:return
                    raise Snapshot
            elif mode=='W1':
                reports=world.protocol()['graph_control']['blockers']
                if calls<2 and len(reports)>seen_blockers and LIMIT-owner.adapter.ledger.actual-cost>10_000:
                    seen_blockers=len(reports);decide(reports[-1])
        try:
            boundary=native.run_fragment(prepared,runtime,on_opportunity=step);save(out/'boundary.json',boundary)
            if boundary['execution_integrity_failure']:raise ValueError(str(boundary['execution_integrity_failure']))
            result.update(status='closed',termination=boundary['termination_class'],logical_tokens=owner.adapter.ledger.actual+cost)
            if state:
                result.update(mechanism=mechanism_endpoint(monitor.view(),node['anomaly_id'],ordinal),
                              metrics=metrics,osa_tokens=cost,control_attempts=calls,controller_wall_seconds=controller_seconds)
                save(out/'final-organization.json',{'graph':graph(world),'control':world.protocol().get('graph_control')})
            native.close_runtime(runtime);runtime=None
            save(out/'candidate-lock.json',native.lock_fixed_candidates(prepared,out/'closure',sdk_closed=True))
        except Snapshot:
            save(out/'observations.json',history)
            save(out/'checkpoint-proof.json',resume.save(prepared,runtime,out/'checkpoint',control_state={'node':node,'ordinal':runtime.opportunities}))
            result.update(status='point_ready',prefix_tokens=owner.adapter.ledger.actual)
    except Exception as exc:
        result.update(status='technical_unknown',error=str(exc),traceback=traceback.format_exc())
    finally:
        for cleanup in ([lambda:native.close_runtime(runtime)] if runtime else [])+([lambda:meter.close(slot)] if admitted else [])+([actor.close] if actor else []):
            try:cleanup()
            except Exception as exc:result.setdefault('cleanup_errors',[]).append(str(exc))
        if 'test_cost' in locals():result['public_test_cost']=test_cost
        result['finished']=time.time();save(out/'result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--index',type=int,required=True);parser.add_argument('--condition',choices=['PREFIX','W0','W1'],required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--prefix',type=Path)
    main(parser.parse_args())
