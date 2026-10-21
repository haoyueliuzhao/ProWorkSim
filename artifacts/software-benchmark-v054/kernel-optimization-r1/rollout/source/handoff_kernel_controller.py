"""Adopt live original workers, then suppress only the old GPU6's new slots."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from datetime import datetime

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from tools.drain_formal_queue_v054 import identity, properties

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
RUN = ROOT/'runs/software-benchmark-v054'
KERNEL = RUN/'kernel-optimization-r1'
QUEUE = RUN/'formal-queue-r1'
OLD = 'proworksim-v054-formal-queue-deferred-r1.service'
NEW = 'proworksim-v054-formal-queue-kernel-r1.service'
policy = reference(KERNEL/'kernel-router-policy-r1.json')
unit = properties(OLD)
pid = int(unit['MainPID'])
assert pid > 0 and unit['ActiveState'] == 'active'
owner = identity(pid)
args = Path(f'/proc/{pid}/cmdline').read_bytes().decode().split('\0')
assert str(ROOT/'tools/run_deferred_fault_queue_v054.py') in args and 'run' in args
assert str(RUN/'deferred-fault-policy-r1.json') in args
until = time.monotonic()+40
while time.monotonic() < until:
    before = reference(QUEUE/'state.json')
    state = json.loads((QUEUE/'state.json').read_text())
    age = time.time()-datetime.fromisoformat(state['updated_utc']).timestamp()
    channel = Path(f'/proc/{pid}/wchan').read_text().strip()
    intents = any(row['generation']['status']=='intent' or any(x['status']=='intent' for x in row['scores'].values()) for row in state['rows'])
    if not intents and channel=='hrtimer_nanosleep' and .5 <= age <= 3:
        break
    time.sleep(.05)
else:
    raise RuntimeError('No safe coordinator sleep boundary; no service touched')
assert identity(pid)==owner and properties(OLD)==unit
os.kill(pid,signal.SIGSTOP)
try:
    until=time.monotonic()+2
    while time.monotonic()<until:
        if re.search(r'^State:\s+T',Path(f'/proc/{pid}/status').read_text(),re.M):
            break
        time.sleep(.02)
    else:
        raise RuntimeError('Coordinator did not stop')
    assert identity(pid)==owner and reference(QUEUE/'state.json')==before
except BaseException:
    if identity(pid)==owner:
        os.kill(pid,signal.SIGCONT)
    raise
out=KERNEL/'controller-handoff-r1'
out.mkdir(exist_ok=False)
intent=write_new(out/'intent.json',{'policy':policy,'state_before':before,'old_unit':OLD,'old_identity':owner,'new_unit':NEW,'sleeping_tick_age_seconds':age,'script':reference(__file__),'only_controller_signalled':True,'task_or_model_units_signalled':[],'workers_not_drained':True,'actual_active_generation':state['active_generation']})
subprocess.run(['systemctl','--user','stop',OLD],check=True,timeout=25)
assert properties(OLD)['MainPID']=='0'
cli=[str(ROOT/'.venv/bin/python'),str(ROOT/'tools/run_kernel_queue_v054.py')]
result=subprocess.run([*cli,'adopt','--policy',policy['path'],'--policy-sha256',policy['sha256']],capture_output=True,text=True,check=True)
write_new(out/'adopt.json',{'intent':intent,'stdout':result.stdout,'stderr':result.stderr,'returncode':result.returncode})
argv=['systemd-run','--user','--unit='+NEW,'--property=Restart=no','--working-directory='+str(ROOT),'--setenv=PYTHONPATH='+str(ROOT/'src')+':'+str(ROOT),*cli,'run','--policy',policy['path'],'--policy-sha256',policy['sha256']]
write_new(out/'launch-intent.json',{'argv':argv,'adoption':reference(out/'adopt.json')})
launch=subprocess.run(argv,capture_output=True,text=True,check=True)
print(json.dumps(write_new(out/'launched.json',{'intent':intent,'returncode':launch.returncode,'stdout':launch.stdout,'stderr':launch.stderr,'model_reloads':0,'formal_replays':0})))
