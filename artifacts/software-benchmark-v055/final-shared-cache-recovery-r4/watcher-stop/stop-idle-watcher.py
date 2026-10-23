"""Stop only the completed cache watcher's exact idle service identity."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,subprocess,time
ROOT=Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT=ROOT/'runs/software-benchmark-v055/final-shared-cache-recovery-r4/watcher-stop'
UNIT='proworksim-v055-cache-reclamation-r2.service'
PID=1357003
INVOCATION='cc30d29caed348a7b2376f0f570ec2e7'
GROUP='/user.slice/user-1021.slice/user@1021.service/app.slice/'+UNIT

def now():return datetime.now(timezone.utc).isoformat()
def write(name,value):
 with (OUT/name).open('x') as f:
  json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
def show():
 p=subprocess.run(['systemctl','--user','show',UNIT,'--property=Id,MainPID,ActiveState,SubState,ControlGroup,InvocationID,KillMode,Result,ExecMainStatus'],capture_output=True,text=True,check=True,timeout=15)
 return dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
def identity(pid):
 try:raw=Path(f'/proc/{pid}/stat').read_text()
 except FileNotFoundError:return None
 return {'pid':pid,'start_ticks':int(raw[raw.rfind(')')+2:].split()[19])}
def members():
 root=Path('/sys/fs/cgroup'+GROUP)
 if not root.exists():return {}
 return {str(p):[int(x) for x in p.read_text().split()] for p in root.rglob('cgroup.procs')}

pre=show()
if (pre['Id']!=UNIT or pre['MainPID']!=str(PID) or pre['InvocationID']!=INVOCATION
    or pre['ControlGroup']!=GROUP or pre['KillMode']!='control-group' or pre['ActiveState']!='active'):
 raise RuntimeError('Exact cache watcher identity changed; no stop sent')
process=identity(PID)
if not process:raise RuntimeError('Original watcher no longer exists; no stop sent')
for _ in range(30):
 children=Path(f'/proc/{PID}/task/{PID}/children').read_text().split()
 groups=members();pids={x for value in groups.values() for x in value}
 status=json.loads((ROOT/'runs/software-benchmark-v055/cache-reclamation-r1/status.json').read_bytes())
 age=(datetime.now(timezone.utc)-datetime.fromisoformat(status['observed_utc'])).total_seconds()
 if not children and pids=={PID} and 0<=age<8 and status['reclaimed_this_cycle']==0:
  break
 time.sleep(1)
else:raise RuntimeError('No proven idle watcher-only window; no stop sent')
intent={'created_utc':now(),'unit_before':pre,'watcher_process':process,'exact_cgroup_members':groups,
 'children':children,'last_cycle_status':status,'cycle_age_seconds':age,'action':['systemctl','--user','stop',UNIT],
 'only_original_cache_watcher_targeted':True,'snapshot_archive_service_untouched':True,'model_calls':0}
write('stop-intent.json',intent)
if identity(PID)!=process or Path(f'/proc/{PID}/task/{PID}/children').read_text().split():
 raise RuntimeError('Watcher identity/children changed immediately before stop; no stop sent')
result=subprocess.run(['systemctl','--user','stop',UNIT],capture_output=True,text=True,timeout=30)
post=show();post_members=members();gone=identity(PID)!=process
receipt={'finished_utc':now(),'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
 'unit_after':post,'old_process_absent':gone,'remaining_exact_cgroup_members':post_members,
 'stopped_cleanly':result.returncode==0 and post['ActiveState']=='inactive' and post['MainPID']=='0'
     and gone and not any(post_members.values()),'no_other_units_stopped':True,'model_calls':0}
write('stop-receipt.json',receipt)
print(json.dumps(receipt))
if not receipt['stopped_cleanly']:raise SystemExit(1)
