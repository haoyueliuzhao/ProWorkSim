import argparse, hashlib, json, os, signal, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT=ROOT/'runs/software-benchmark-v055/three-volume-host-deployment-r1'
def now(): return datetime.now(timezone.utc).isoformat()
def sha(data): return hashlib.sha256(data).hexdigest()
def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x') as stream: json.dump(value,stream,ensure_ascii=False,indent=2); stream.write('\n')
def show(unit):
 r=subprocess.run(['systemctl','--user','show',unit,'--property=ActiveState,SubState,MainPID,InvocationID,KillMode'],check=True,capture_output=True,text=True,timeout=10)
 return dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
p=argparse.ArgumentParser();p.add_argument('kind',choices=['qwen','deepseek']);p.add_argument('--revision',type=Path,required=True);p.add_argument('--sha256',required=True);args=p.parse_args()
if args.kind=='qwen':
 old='proworksim-v054-formal-queue-ref-handoff-r5.service'; new='proworksim-v054-formal-queue-three-volumes-r6.service'
 old_entry='tools/run_qwen_ref_handoff_v054_r5.py'; entry='tools/run_qwen_three_volumes_v054_r6.py'
 state=ROOT/'runs/software-benchmark-v054/formal-queue-r1/state.json'
else:
 old='proworksim-v055-deepseek-six-conditions-native-host-r8.service'; new='proworksim-v055-deepseek-six-conditions-native-host-r9.service'
 old_entry='tools/run_deepseek_queue_native_host_v055_r8.py'; entry='tools/run_deepseek_queue_native_host_v055_r9.py'
 state=ROOT/'runs/software-benchmark-v055/queue-r1/state.json'
 if show('proworksim-v054-formal-queue-three-volumes-r6.service').get('ActiveState')!='active': raise RuntimeError('Deploy three-volume Qwen accounting before tertiary DeepSeek dispatch')
seal=args.revision.resolve(); expected=args.sha256
assert seal.is_relative_to(ROOT/'runs') and sha(seal.read_bytes())==expected
assert show(new).get('MainPID','0')=='0'
before=show(old); pid=int(before['MainPID']); assert pid>0 and before['ActiveState']=='active' and before['KillMode']=='process'
cmdline=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0'); assert str(ROOT/old_entry).encode() in cmdline
deadline=time.monotonic()+45
while True:
 if time.monotonic()>deadline: raise TimeoutError('No safe controller sleep boundary; old unit untouched')
 if (Path('/proc')/str(pid)/'wchan').read_text().strip()!='hrtimer_nanosleep': time.sleep(.1); continue
 raw=state.read_bytes()
 if show(old)!=before: raise RuntimeError('Controller identity changed before handoff')
 os.kill(pid,signal.SIGSTOP)
 try:
  if state.read_bytes()!=raw: os.kill(pid,signal.SIGCONT); continue
  if 'T' not in (Path('/proc')/str(pid)/'status').read_text().split('State:',1)[1].splitlines()[0]: os.kill(pid,signal.SIGCONT); continue
  directory=OUT/args.kind; directory.mkdir(parents=True,exist_ok=False); (directory/'state-before.json').write_bytes(raw)
  launch=['systemd-run','--user','--unit='+new,'--property=Restart=no','--property=KillMode=process','--working-directory='+str(ROOT),'--setenv=PYTHONPATH='+str(ROOT/'src')+':'+str(ROOT/'tools')+':'+str(ROOT),str(ROOT/'.venv/bin/python'),'-B',str(ROOT/entry),'run','--revision',str(seal),'--sha256',expected]
  write(directory/'intent.json',{'utc':now(),'source_sha256':sha(Path(__file__).read_bytes()),'old_unit':old,'old_identity':before,'old_cmdline':[x.decode() for x in cmdline if x],'state_before_sha256':sha(raw),'seal':{'path':str(seal),'sha256':expected},'argv':launch,'only_old_manager_signalled':True,'GPU_services_signalled':0,'formal_tasks_replayed':0,'inflight_directories_moved':False})
  subprocess.run(['systemctl','--user','stop',old],check=True,timeout=15)
  if show(old)['MainPID']!='0': raise RuntimeError('Old controller remains')
  result=subprocess.run(launch,check=True,capture_output=True,text=True,timeout=15)
  write(directory/'launched.json',{'utc':now(),'new_unit':new,'argv':launch,'stdout':result.stdout,'stderr':result.stderr,'GPU_services_signalled':0,'formal_tasks_replayed':0})
  print(json.dumps({'kind':args.kind,'new_unit':new,'receipt':str(directory/'launched.json')})); break
 except BaseException:
  try: os.kill(pid,signal.SIGCONT)
  except ProcessLookupError: pass
  raise
