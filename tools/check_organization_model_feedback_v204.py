"""Read actual test feedback and later same-member requests; scores are not a gate."""
import argparse,json
from pathlib import Path
from proworksim.storage import json_bytes
p=argparse.ArgumentParser();p.add_argument('--block',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
progress=json.loads((a.block/'progress.json').read_text());checks=[]
for run in progress['results']:
 folder=a.block/run['branch']['name'];result=run['result'];events=json.loads((folder/'final-world.json').read_text())['software_events']
 tests=[e for e in events if e.get('kind')=='test' and e.get('executed')is True and e.get('public_execution',{}).get('execution',{}).get('counts',{}).get('tests_run',0)>0]
 requests=[json.loads(f.read_text()) for f in (folder/'physical-api').glob('*/request.json')];witness=[]
 for test in tests:
  ref=test['source_reference']
  for req in requests:
   if req['payload']['member_id']!=test['actor_id']:continue
   # A real tool observation must describe this exact tested source. Merely
   # occurring later in wall time, or a model's own claim of passing, is insufficient.
   for message in req['payload']['wire']['messages']:
    if message['role'] not in ('tool','user'):continue
    text=message.get('content') or ''
    try:value=json.loads(text)
    except (ValueError,TypeError):continue
    raw=json.dumps(value,sort_keys=True)
    if ref['object_id'] in raw and ref['version_id'] in raw and '"executed": true' in raw and ('test' in raw or 'validation_status' in raw):
     witness.append({'actor':test['actor_id'],'test_sequence':test['sequence'],'source_reference':ref,'request_id':req['physical_id']});break
   if witness:break
 checks.append({'name':run['branch']['name'],'generation_status':result['status'],'actual_test_executions':len(tests),'feedback_consumption_witness':witness,
  'passed':result['status']=='closed' and bool(tests) and bool(witness)})
passed=len(checks)==2 and all(x['passed'] for x in checks)
a.output.write_bytes(json_bytes({'passed':passed,'checks':checks,'solved_required':False,'host_submitted_for_model':False,'new_model_calls':0}))
print(json.dumps({'passed':passed,'checks':checks}))
