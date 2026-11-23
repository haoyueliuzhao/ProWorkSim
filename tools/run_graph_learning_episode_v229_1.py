"""Supplemental first-window episode, using the frozen v229 worker setup and proposal service."""
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_graph_learning_episode_v229 import (
    ROOT, AUTH, LIMIT, read, save, Snapshot, draft_graph, WindowLedger, checked, reference,
    ControlledWorld, ACCOUNTABLE, activate, graph, menu, support,
)
from proworksim.software_graph_recruitment_v229_1 import inspect_opportunity

PLAN=ROOT/'artifacts/software-benchmark-v229/dev1-extension-r1'


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

    from proworksim.software_natural_checkpoint_v224_2 import INITIAL_WORK_INSTRUCTION
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(out/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',HF_HUB_OFFLINE='1',
                      HF_DATASETS_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHON_DOTENV_DISABLED='1',OPENHANDS_SUPPRESS_BANNER='1')
    plan=read(PLAN/'panel.json')
    if args.index not in plan['supplement_indices']:raise ValueError('Outside frozen supplemental cohort')
    row=plan['rows'][args.index]
    mode=args.condition;observer=None;slot=f'v229:{out.parent.name}:{mode}'
    meter=WindowLedger(read(AUTH));actor=runtime=None;admitted=False
    result={'status':'preparing','instance_id':row['instance_id'],'condition':mode,'slot':slot,'started':time.time()}
    save(out/'result.json',result)
    singletons={}
    try:
        for item in read(PLAN/'freeze.json')['files']:checked(item)
        state=None
        if mode!='PREFIX':
            prefix=args.prefix;cp=prefix/'checkpoint';state,proof=resume.read(cp)
            node=state['control_state']['node'];ordinal=state['control_state']['ordinal']
            observer=state['control_state']['observer']
            bank=read(prefix/'candidate-bank.json')
            if bank['checkpoint']!=proof['identity'] or mode not in bank['decision']['q']:
                raise ValueError('Branch outside frozen support')
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
        owner=native.build_team_owner(post,organization_id='FREE2',slot_id=slot,condition_id='v229-'+mode,
                folder=out/'model-ledger',deadline=deadline,identity={'policy_version':native.VERSION,'model':'deepseek-flash','thinking':False},
                observation_token_counter=content,observation_tokenizer_id=meta['tokenizer_id'],require_content_counter=True)
        initial=native.CONTRACT+'\n'+actor.config['public_task']['problem_statement']+'\n'+public_context(actor.config,actor.public)
        runtime,_,_=native.build_runtime(owner,prepared,out/'runtime',deadline=deadline,public_initial_message=initial)
        resume.register_persistence_types()
        graphs={m:AnomalyGraph(m) for m in ('member_001','member_002')}
        histories={m:[] for m in graphs};monitor=graphs.get(observer);metrics={'eligible':0,'valid':0,'rejections':{},'by_tool':{},'public_test_attempts':0,'handoff_attempts':0}
        cost=0;controller_seconds=0.0
        def notify(text,members=None):
            for member,w in runtime.policies.items():
                if not members or member in members:w.conversation.send_message(text)
        if state:
            save(out/'restore.json',resume.restore_runtime(prepared,runtime,cp))
            events=read(prefix/'observations.json')
            node=explain(node,events,observer)
            for prev in events:monitor.observe(prev['ordinal'],prev['outcome'])

            monitor.regression_targets=frozenset(sorted({s for passed in monitor.test_passes.values() for s in passed if s!=node.get('subject')})[:2])
            save(out/'common-state.json',{'checkpoint':proof['identity'],'node':node,'graph':graph(world),
                 'remaining':LIMIT-prefix_tokens,'regression_targets':sorted(monitor.regression_targets)})
            notify('Work observation: '+json.dumps({'kind':node['anomaly_type'],'subject':node.get('subject'),'scopes':node['affected_work'],'evidence':menu(world,node,observer)['evidence']}),[observer])
            native.enter_continuation(runtime)
        cost=bank['osa_tokens'] if state else 0
        controller_seconds=bank['osa_seconds'] if state else 0.0
        native.set_native_limit(runtime,LIMIT-cost)
        actor.bind_deadline(runtime.deadline);meter.admit(slot,LIMIT-prefix_tokens-cost);admitted=True
        result['status']='running';save(out/'result.json',result)
        if state:
            target=bank['choice'] if mode=='CHANGE' else {'option':'K','evidence':bank['choice']['evidence'],'reason':'Controlled baseline: retain current organization'}
            record=activate(world,node,observer,bank['menu'],target,origin='osa')
            if record['changed']!=(mode=='CHANGE'):raise ValueError('Incorrect graph manipulation')
            save(out/'assigned-graph.json',record)
            notify('This active graph governs both workers. Read dynamic_status. Follow the assigned work; a pending diagnosis must be handed off via DIAG <own event number> <finding>. You may report a concrete obstacle using BLOCK messages. Continue through review and submission. Active graph: '+json.dumps(record['after']))
        else:notify(INITIAL_WORK_INSTRUCTION+' Public scope annotations: '+json.dumps(row['requirements']))
        def step(outcome):
            nonlocal node,observer,monitor
            after_opportunity(actor,out/'transport-fault.json');i=runtime.opportunities
            member=outcome.get('worker_id')
            if not state and member in graphs:
                graphs[member].observe(i,outcome)
                histories[member].append({'ordinal':i,'outcome':outcome})
            elif state:monitor.observe(i,outcome)
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
                                      'osa_tokens':cost,'anomalies':[(n['anomaly_type'],n['status']) for g in ([monitor] if state else graphs.values()) for n in g.nodes.values()]})
            if world.protocol()['terminal']:return
            if mode=='PREFIX':
                if member not in graphs or owner.adapter.ledger.actual>=4_960_000:return
                candidate=inspect_opportunity(world,member,graphs[member],i,singletons)
                if candidate is not None:
                    node=candidate;observer=member;monitor=graphs[member];raise Snapshot
        try:
            boundary=native.run_fragment(prepared,runtime,on_opportunity=step);save(out/'boundary.json',boundary)
            if boundary['execution_integrity_failure']:raise ValueError(str(boundary['execution_integrity_failure']))
            result.update(status='closed',termination=boundary['termination_class'],logical_tokens=owner.adapter.ledger.actual+cost)
            if state:
                result.update(mechanism=mechanism_endpoint(monitor.view(),node['anomaly_id'],ordinal),
                              metrics=metrics,osa_tokens=cost,shared_osa_calls=bank['osa_calls'],shared_osa_seconds=controller_seconds)
                save(out/'final-organization.json',{'graph':graph(world),'control':world.protocol().get('graph_control')})
            native.close_runtime(runtime);runtime=None
            save(out/'candidate-lock.json',native.lock_fixed_candidates(prepared,out/'closure',sdk_closed=True))
        except Snapshot:
            save(out/'observations.json',histories[observer])
            proof=resume.save(prepared,runtime,out/'checkpoint',control_state={'node':node,'ordinal':runtime.opportunities,'observer':observer})
            save(out/'checkpoint-proof.json',proof)
            prefix_tokens=owner.adapter.ledger.actual
            node=explain(node,histories[observer],observer)
            frozen=menu(world,node,observer)
            start=time.monotonic()
            if len(frozen['options'])>1:
                cost,choice=draft_graph(world,node,observer,counter,wire,meter,slot,out/'draft',LIMIT-prefix_tokens)
            else:cost,choice=0,None
            controller_seconds=time.monotonic()-start
            valid=choice is not None
            if not valid:choice={'option':'K','evidence':[next(iter(frozen['evidence']))],'reason':'No valid alternative; continue under original graph'}
            bank=support(frozen,choice,proof['identity'],LIMIT-prefix_tokens-cost,read(args.policy))
            bank.update(osa_tokens=cost,valid_nomination=valid,osa_seconds=controller_seconds,
                        osa_calls=len(list((out/'draft/api').glob('*/usage.json'))),
                        primary_arm=max(bank['decision']['q'],key=bank['decision']['q'].get))
            save(out/'candidate-bank.json',bank)
            result.update(status='point_ready',prefix_tokens=prefix_tokens,osa_tokens=cost,observer=observer,kind=node['anomaly_type'])
    except Exception as exc:
        result.update(status='technical_unknown',error=str(exc),traceback=traceback.format_exc())
    finally:
        for cleanup in ([lambda:native.close_runtime(runtime)] if runtime else [])+([lambda:meter.close(slot)] if admitted else [])+([actor.close] if actor else []):
            try:cleanup()
            except Exception as exc:result.setdefault('cleanup_errors',[]).append(str(exc))
        if 'test_cost' in locals():result['public_test_cost']=test_cost
        if mode=='PREFIX':save(out/'single-support-observations.json',list(singletons.values()))
        result['finished']=time.time();save(out/'result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--index',type=int,required=True);parser.add_argument('--condition',choices=['PREFIX','KEEP','CHANGE'],required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--prefix',type=Path)
    parser.add_argument('--policy',type=Path,required=True)
    main(parser.parse_args())
