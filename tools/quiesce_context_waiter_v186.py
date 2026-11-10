"""Stop only the owned v182 manager after proving its jobs never entered."""
import json,os,signal,sqlite3,subprocess,time
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v181/full-context-pilot-r1'
OLD=ROOT/'runs/software-benchmark-v182/context-continuation-r1/api-coordinator'
OUT=ROOT/'artifacts/software-benchmark-v186/idle-handoff-r1'
UNIT='proworksim-v182-context-continuation.service'
LEDGER=ROOT/'runs/software-benchmark-v175/context-replay-r1/api-ledger.sqlite'


def state():
    proc=subprocess.run(['systemctl','--user','show',UNIT,'--property=ActiveState,MainPID,ControlGroup'],
        env=user_manager_environment(),capture_output=True,text=True,check=True,timeout=10)
    return dict(line.split('=',1) for line in proc.stdout.splitlines() if '=' in line)


def idle_proof(pid):
    entry=json.loads((OLD/'execution-started.json').read_bytes())
    if entry['pid']!=pid or pid<=1:raise ValueError('Not the recorded coordinator process')
    process=Path('/proc')/str(pid)
    if process.stat().st_uid!=os.getuid():raise PermissionError('Foreign process owner')
    command=(process/'cmdline').read_bytes().replace(b'\0',b' ').decode()
    if str(ROOT/'tools/run_context_tasks_v182.py') not in command:raise ValueError('PID was reused')
    info=state()
    if info['MainPID']!=str(pid):raise ValueError('Unit PID changed')
    members=(Path('/sys/fs/cgroup')/info['ControlGroup'].lstrip('/')/'cgroup.procs').read_text().split()
    if members!=[str(pid)]:raise ValueError('The manager still owns child processes')
    active=list((RUN/'resource-claims').glob('active-*.json'))
    if active:raise ValueError('A live container/resource lease prevents idle handoff')
    with sqlite3.connect(LEDGER.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        if db.execute("SELECT count(*) FROM requests WHERE status!='settled'").fetchone()[0]:raise ValueError('An HTTP attempt is live or uncertain')
        jobs=[dict(r) for r in db.execute("SELECT * FROM jobs WHERE status='running'")]
        if len(jobs)!=4:raise ValueError('Unexpected pending start count')
        rows=json.loads((RUN/'execution-plan.json').read_bytes())['rows']
        for job in jobs:
            row=next(r for r in rows if r['slot_id']==job['job_id'])
            if db.execute('SELECT count(*) FROM requests WHERE job_id=?',(job['job_id'],)).fetchone()[0]:raise ValueError('An admitted job already called the model')
            if any((RUN/'resource-claims'/f'{role}-{row["slot_index"]}.json').exists() for role in ('actor','controller','volume')):
                raise ValueError('An admitted job consumed an object identity')
            if (RUN/'episodes'/str(row['slot_index'])).exists():raise ValueError('An episode already entered')
    return {'pid':pid,'unit':info,'jobs':jobs,'cgroup_processes':members,'live_HTTP':0,'active_resources':0,
        'all_waiting_tasks_zero_API_zero_objects':True,'command':command}


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=False)
    info=state();pid=int(info['MainPID']);proof=idle_proof(pid)
    write_new(OUT/'before.json',proof)
    write_new(OUT/'old-progress.json',json.loads((OLD/'progress.json').read_bytes()))
    with sqlite3.connect(LEDGER.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(OUT/'ledger-before.sqlite') as target:source.backup(target)
    os.kill(pid,signal.SIGTERM);deadline=time.monotonic()+5
    while time.monotonic()<deadline and Path('/proc',str(pid)).exists():time.sleep(.25)
    forced=False
    if Path('/proc',str(pid)).exists():
        write_new(OUT/'still-idle-after-TERM.json',idle_proof(pid))
        # Old SIGTERM only cancels new admissions; it cannot wake the four
        # already queued capacity waiters. There are no subprocesses or model
        # calls to interrupt, as proven again immediately above.
        os.kill(pid,signal.SIGKILL);forced=True
    for _ in range(40):
        if state()['MainPID']=='0':break
        time.sleep(.25)
    final=state()
    if final['MainPID']!='0':raise RuntimeError('Old owned manager still active')
    result={'old_manager_stopped':True,'SIGTERM_sent':True,'idle_manager_SIGKILL_required':forced,
        'model_calls_interrupted':0,'containers_interrupted':0,'state':final,'shared_host_changes':0}
    write_new(OUT/'completion.json',result);print(json.dumps(result))
