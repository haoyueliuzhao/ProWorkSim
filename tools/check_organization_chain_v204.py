"""Zero API: actual SDK checkpoint + isolated actor RPC + tests + exact review/delivery.

Synthetic two-file fixture inside a disposable original Python image; not a
benchmark repair, no gold and no fixture context reused by real model trials.
"""
import argparse,importlib.util,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path);a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
os.environ['OH_PERSISTENCE_DIR']=str(a.output/'sdk-settings')
from proworksim.software_organization_runtime_v204 import Actor,after_opportunity
from proworksim import software_sdk_resume_v203_3_4 as resume
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim import software_role_baseline_world_v141 as world
from proworksim.repository_sources_v054 import capture_repository
from proworksim.storage import json_bytes
spec=importlib.util.spec_from_file_location('chain_fixture',ROOT/'tools/run_sdk_resume_controls_v203_3_2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.resume=resume
row=json.load(open(ROOT/'artifacts/software-benchmark-v203-3-3/preparation-r1/candidates.json'))['rows'][0]
state=resume.read(a.checkpoint)[0] if a.checkpoint else None
actor=Actor(row,a.output/'actor',resume_test_calls=state['public_test_calls'] if state else 0)
def fixture(folder):
 folder.mkdir(parents=True);source=folder/'source';source.mkdir();(source/'sample.py').write_text('value = 1\n');(source/'test_sample.py').write_text('def test_value():\n    from sample import value\n    assert value == 2\n')
 task=actor.config['public_task']
 manifest=capture_repository(source,folder/'snapshot',task_id=row['instance_id'],problem_statement='SYNTHETIC TRANSPORT CONTROL: change sample value to 2; not an original issue repair.',
  source_identity={**{k:task[k] for k in ('instance_id','repo','base_commit')},'dataset_revision':'78f471bf655a3137b2e8a75af1501690ec009ec3'})
 d=DispatchDeadline(soft_seconds=21600,hard_seconds=23400)
 prepared=world.prepare_case(manifest,folder/'prepared',organization_id='REVIEW2',public_test_callback=actor.test,deadline=d,public_test_entry=actor.entry)
 return prepared,d,[]
m.fixture=fixture;rt=None
try:
 actor.start();prepared,rt,script,_=m.build(a.output,'restored' if a.checkpoint else 'prefix',a.checkpoint)
 actor.bind_deadline(rt.deadline)
 if a.checkpoint:
  # Existing deterministic script executes failed test, repair, successful author
  # test, immutable patch, reviewer adoption/test/accept and author submission.
  original=m.runtime.run_fragment
  def checked_run(prepared,rt):return original(prepared,rt,on_opportunity=lambda o:after_opportunity(actor,a.output/'batch-pause.json'))
  m.runtime.run_fragment=checked_run
  m.suffix(a.output,prepared,rt,script,arm='KEEP',checkpoint=a.checkpoint);rt=None
  events=prepared.world.state['software_events'];tests=[x for x in events if x['kind']=='test']
  assert len(tests)>=4 and tests[-1]['passed'] is True
  proof={'passed':True,'SDK_restored':True,'actual_container_RPC':True,'same_deadline':actor.rpc.hard_at==prepared.source_provider.runner.hard_at,
   'test_results':[{'actor':x['actor_id'],'passed':x['passed'],'executed':x.get('executed')} for x in tests],
   'legal_deliveries':len(prepared.world._software()['deliveries']),'API_calls':0,'gold_used':False,'synthetic_control_not_benchmark_result':True}
  m.save(a.output/'chain-summary.json',proof);print(json.dumps(proof))
 else:
  for w in rt.policies.values():w.agent.condenser.max_size=12
  for _ in range(20):
   rt.sync_members();result=rt.step();after_opportunity(actor,a.output/'batch-pause.json')
   if result['status'] in ('environment_error','execution_integrity_error'):raise RuntimeError(str(result))
   if rt.opportunities>=12 and script.summaries:break
  assert script.summaries and prepared.source_provider.runner.calls==1
  m.save(a.output/'checkpoint-proof.json',resume.save(prepared,rt,a.output/'checkpoint',control_state=script.snapshot()))
  print(json.dumps({'saved':True,'API_calls':0,'actual_public_test_calls':1}))
finally:
 if rt:m.runtime.close_runtime(rt)
 actor.close()
