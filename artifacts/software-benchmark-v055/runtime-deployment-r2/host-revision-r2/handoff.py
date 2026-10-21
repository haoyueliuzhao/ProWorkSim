import json,os,signal,subprocess,time,re
from pathlib import Path
from datetime import datetime
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_benchmark_supervision_v054 import process_identity
R=Path('/data0/zhuxinrui/projects/ProWorkSim');K=R/'runs/software-benchmark-v055';E=K/'host-revision-r2/handoff';OLD='proworksim-v055-deepseek-six-conditions-r1.service';NEW='proworksim-v055-deepseek-six-conditions-host-r2.service'
def unit(name):
 p=subprocess.run(['systemctl','--user','show',name,'--property=MainPID,ActiveState,SubState,InvocationID,ControlGroup,KillMode'],capture_output=True,text=True,check=True);return dict(x.split('=',1) for x in p.stdout.splitlines())
u=unit(OLD);pid=int(u['MainPID']);assert pid>0 and u['ActiveState']=='active' and u['KillMode']=='process';identity=process_identity(pid);args=Path(f'/proc/{pid}/cmdline').read_bytes().decode().split('\0');assert 'proworksim.software_benchmark_queue_v055' in args
state=K/'queue-r1/state.json';deadline=time.monotonic()+55
while time.monotonic()<deadline:
 before=reference(state);s=json.loads(state.read_bytes());age=time.time()-datetime.fromisoformat(s['updated_utc']).timestamp();wchan=Path(f'/proc/{pid}/wchan').read_text().strip()
 if wchan=='hrtimer_nanosleep' and .3<=age<=4.3:break
 time.sleep(.05)
else:raise RuntimeError('No safe coordinator sleep boundary; no signals sent')
assert process_identity(pid)==identity and unit(OLD)==u
os.kill(pid,signal.SIGSTOP)
try:
 for _ in range(100):
  if re.search(r'^State:\s+T',Path(f'/proc/{pid}/status').read_text(),re.M):break
  time.sleep(.01)
 else:raise RuntimeError('No stopped coordinator state')
 assert reference(state)==before and process_identity(pid)==identity
 E.mkdir(exist_ok=False);intent=write_new(E/'intent.json',{'old_unit':u,'old_identity':identity,'state_before':before,'only_coordinator_signalled':True,'worker_model_grader_signals':[],'script':reference(__file__),'new_unit':NEW})
except BaseException:
 os.kill(pid,signal.SIGCONT);raise
subprocess.run(['systemctl','--user','stop',OLD],check=True,timeout=30);assert unit(OLD)['MainPID']=='0'
a=['systemd-run','--user','--unit='+NEW,'--property=Restart=no','--property=KillMode=process','--working-directory='+str(R),'--setenv=PYTHONPATH='+str(R/'src')+':'+str(R),str(R/'.venv/bin/python'),str(R/'tools/run_deepseek_queue_host_v055_r2.py'),'run','--revision',str(K/'host-revision-r2/revision.json'),'--sha256','f997401e3ea08988fa2347e7dfd5f00e41cd3dcf001728cb5af7fa4cd4210424']
p=subprocess.run(a,capture_output=True,text=True,check=True);print(write_new(E/'launched.json',{'intent':intent,'argv':a,'stdout':p.stdout,'stderr':p.stderr,'old_or_new_episode_replayed':False,'model_reloads':0}))
