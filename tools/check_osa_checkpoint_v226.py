"""Run a real two-worker SDK on a local fixture and save an A2 decision point."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from proworksim import software_natural_organization_runtime_v224_2 as runtime
from proworksim import software_natural_organization_world_v224_2 as world
from proworksim import software_sdk_resume_v203_3_4 as resume
from proworksim.harness_port import HarnessPort
from proworksim.software_anomaly_pilot_v226 import AnomalyPilot
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import digest,json_bytes

R=Path(__file__).resolve().parents[1]
class PointReady(Exception):pass

def main(out):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    os.environ.update(OH_PERSISTENCE_DIR=str(out/'sdk-settings'),LITELLM_LOCAL_MODEL_COST_MAP='True',
        OPENHANDS_SUPPRESS_BANNER='1',HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',PYTHON_DOTENV_DISABLED='1')
    sys.path.insert(0,str(R/'tests'))
    import test_role_baseline_world_v141 as fixture
    def clean_run(argv,**kwargs):
        kwargs['env']={k:v for k,v in kwargs.get('env',os.environ).items() if k not in ('PYTHONHOME','PYTHONPATH','LD_LIBRARY_PATH','LD_PRELOAD')}
        return subprocess.run(argv,**kwargs)
    setup=clone_function(fixture.prepare,{**fixture.prepare.__globals__,'sys':SimpleNamespace(executable=str(R/'.venv/bin/python')),'subprocess':SimpleNamespace(run=clean_run)})
    prepared,_,_,_=setup(out/'fixture')
    deadline=DispatchDeadline(soft_seconds=180,hard_seconds=240)
    prepared.source_provider.runner.hard_at=deadline.hard_at
    world.attach(prepared,['behavior','regression'],condition='G')
    plan=[('split_work',{'task_id':'work_root','children':[{'task_id':'implementation','description':'Fix','scope':['behavior']},
            {'task_id':'check','description':'Check result','scope':['regression']}],'reason':'Independent obligations'}),
          ('change_dependency',{'task_id':'check','operation':'add','depends_on':'implementation','reason':'Needs upstream'}),
          ('work_readiness',{'task_id':'check'})]
    requests=[]; actor_steps=0
    def scripted(route,payload):
        nonlocal actor_steps
        if route.startswith('/tokenize'):
            return {'prompt_tokens':1000,'request_sha256':digest(json_bytes(payload['wire'])),'method':'CPU fixture','count_only_not_dispatchable':route.endswith('prefix')}
        assert route=='/chat/completions' and len(requests)<20
        requests.append(payload)
        if payload['member_id']=='member_001':
            tool,args=plan[actor_steps];actor_steps+=1
        else:tool,args='dynamic_status',{}
        msg={'role':'assistant','content':None,'tool_calls':[{'id':'cpu-'+str(len(requests)),'type':'function','function':{'name':tool,'arguments':json.dumps(args)}}]}
        return {'id':'cpu-'+str(len(requests)),'model':'deepseek-flash','object':'chat.completion','created':0,'choices':[{'index':0,'finish_reason':'tool_calls','message':msg}],'usage':{'prompt_tokens':256,'completion_tokens':25,'total_tokens':281,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':256}}
    owner=runtime.build_team_owner(scripted,organization_id='FREE2',slot_id='v226:cpu:A2',condition_id='scripted',
        folder=out/'model-ledger',deadline=deadline,identity={'policy_version':runtime.VERSION,'model':'scripted-no-provider','thinking':False})
    rt,_,_=runtime.build_runtime(owner,prepared,out/'runtime',deadline=deadline,public_initial_message=runtime.CONTRACT)
    pilot=AnomalyPilot((0.,)*5)
    ordinal=0
    try:
        resume.register_persistence_types()
        def step(o):
            nonlocal ordinal
            ordinal+=1
            if o.get('response',{}).get('ok') is False:raise ValueError(str(o['response']['error']))
            worker=next(v for v in reversed(requests) if v['member_id']=='member_001') if any(v['member_id']=='member_001' for v in requests) else None
            point=pilot.observe(ordinal,o,prepared.world,5_000_000-owner.adapter.ledger.actual,worker_request=worker)
            if point:raise PointReady
        try:runtime.run_fragment(prepared,rt,on_opportunity=step)
        except PointReady:pass
        point,=pilot.points
        assert point.node['anomaly_type']=='A2'
        proof=resume.save(prepared,rt,out/'checkpoint',control_state={'v226':pilot.graph.view(),'policy_sha':pilot.policy_sha})
        stored=resume.read(out/'checkpoint')[0]
        assert stored['control_state']['v226']==pilot.graph.view() and stored['prefix_ledger']['known_actual_tokens']==owner.adapter.ledger.actual
        result={'passed':True,'actual_SDK':True,'provider_calls':0,'scripted_worker_calls':len(requests),
                'anomaly':point.node,'remaining_token_budget_recorded':point.remaining,
                'worker_request_includes_own_context':len(point.worker_request['messages'])==3,
                'osa_request_message_count':len(point.osa_request['messages']),
                'checkpoint_proof':proof,'policy_updated':False}
        (out/'summary.json').write_bytes(json_bytes(result))
        print('Real SDK saved A2 checkpoint, no provider calls')
    finally:runtime.close_runtime(rt)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);main(p.parse_args().output)
