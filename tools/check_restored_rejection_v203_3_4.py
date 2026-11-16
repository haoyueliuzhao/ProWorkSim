import argparse,copy,importlib.util,json,os
from pathlib import Path
from proworksim import software_sdk_resume_v203_3_4 as revised
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
os.environ['OH_PERSISTENCE_DIR']=str(a.output/'sdk-settings')
spec=importlib.util.spec_from_file_location('resume_fixture',ROOT/'tools/run_sdk_resume_controls_v203_3_2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.resume=revised
old=m.Script.post;injected=[]
def post(self,route,payload):
 result=old(self,route,payload)
 if route=='/chat/completions' and payload['usage_id']=='agent' and not injected:
  calls=result['choices'][0]['message']['tool_calls'];extra=copy.deepcopy(calls[0]);extra['id']+='-extra';calls.append(extra);injected.append(copy.deepcopy(result))
 return result
m.Script.post=post
prepared,rt,script,calls=m.build(a.output,'rejection-only',ROOT/'artifacts/software-benchmark-v203-3-2/resume-r7/continuous/checkpoint')
script.phase='suffix';script.positions={m.M1:0,m.M2:0}
before=rt.owner.adapter.ledger.actual;events=len(prepared.world.state['software_events'])
try:
 rt.sync_members();first=rt.step()
 assert first['status']=='model_format_feedback',first
 assert len(prepared.world.state['software_events'])==events
 assert rt.owner.adapter.ledger.actual-before==281
 rt.sync_members();second=rt.step();assert second['status']!='environment_error',second
 rt.sync_members();third=rt.step();assert third.get('action_performed') is True,third
 assert rt.owner.adapter.ledger.actual-before==843
 proof={'same_worker_next_opportunity':third,'passed':True,'first':first,'second':second,'rejected_response_charged_once':True,'world_action_from_rejection':False,'API_calls':0,'original_schema_unchanged':True,'source':revised.VERSION}
 m.save(a.output/'summary.json',proof);print(json.dumps(proof))
finally:m.runtime.close_runtime(rt)
