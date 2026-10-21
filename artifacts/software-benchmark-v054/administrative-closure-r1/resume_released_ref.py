import json,subprocess
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,write_new,checked
from proworksim.software_benchmark_supervision_v054 import process_identity
from proworksim.software_benchmark_ref_resident_v054 import RefResidentClient
root=Path('/data0/zhuxinrui/projects/ProWorkSim');ep=root/'runs/software-benchmark-v054/formal-queue-r1/slots/39/preclaim-1';output=root/'runs/software-benchmark-v054/administrative-closure-r1'
poison=json.loads((ep/'service/poison.json').read_bytes());assert poison['suspended']['signal']=='SIGSTOP'
session=json.loads((ep/'service/session.json').read_bytes());ready=session['resident_ready'];decl=session['resident_declaration'];unit=decl['unit'];assert unit=='proworksim-v054-resident-ref-r2.service'
release=json.loads((ep/'service/release.json').read_bytes());assert release['session']==reference(ep/'service/session.json');assert release['result']['claim_id']==session['claim_id']
assert release['result']['quiescent'] is True and release['result']['engine_unfinished']==0 and release['result']['cache_reset'] is True
statepath=root/'runs/software-benchmark-v054/residents-r2/ref/session-state.json';state=json.loads(statepath.read_bytes());assert state['phase']=='idle' and state['active_claim'] is None and state['inflight_http']==0
assert process_identity(ready['host_process']['pid'])==ready['host_process']
props=dict(line.split('=',1) for line in subprocess.check_output(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,ControlGroup,InvocationID'],text=True).splitlines())
assert int(props['MainPID'])==ready['host_process']['pid'] and props['ActiveState']=='active' and props['ControlGroup'].endswith('/'+unit)
intent=write_new(output/'resume-idle-resident-intent.json',{'unit':unit,'host_process':ready['host_process'],'unit_properties':props,'release':reference(ep/'service/release.json'),'saved_idle_state':reference(statepath),'original_fault':reference(ep/'service/poison.json'),'reason':'Explicit review: only an administrative closure race followed a completely released idle session; no model reentry','new_generation_requests':0})
subprocess.run(['systemctl','--user','kill','--kill-who=all','--signal=CONT',unit],check=True)
status=RefResidentClient(decl['admin']['endpoint'],decl['admin']['api_key_file']).call('status')
assert status['state']=='idle' and status['poisoned'] is False and status['active_claim'] is None and status['inflight']==0
assert process_identity(ready['host_process']['pid'])==ready['host_process']
print(json.dumps(write_new(output/'resume-idle-resident.json',{'intent':intent,'status':status,'same_process':True,'model_reloaded':False,'new_generation_requests':0})))
