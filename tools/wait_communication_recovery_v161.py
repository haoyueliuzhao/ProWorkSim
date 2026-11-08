"""Bounded ordinary-user wait for v159 cleanup, then launch sealed v161 once."""
from __future__ import annotations
import argparse,importlib.util,json,os,secrets,subprocess,time
from proworksim import software_benchmark_scope_v161 as scope
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment
from proworksim.storage import atomic_write,json_bytes
VERSION='v161-48h-zero-model-predecessor-waiter-r1'
UNIT='proworksim-v161-technical-recovery-waiter.service'
FOLDER=scope.BATCH_ROOT/'waiter'
SPEC=FOLDER/'specification-r2.json'
MAX_WAIT_SECONDS=48*3600
POLL_SECONDS=60

def specification():
    return {'version':VERSION,'unit':UNIT,'uid':os.getuid(),'entrypoint':reference(__file__),
        'maximum_wait_seconds':MAX_WAIT_SECONDS,'poll_seconds':POLL_SECONDS,
        'memory_max_bytes':512*1024**2,'memory_swap_max_bytes':0,'cpu_quota_percent':5,
        'maximum_tasks':64,'restart':'no','ordinary_user_only':True,
        'predecessor_root':str(scope.PREDECESSOR_ROOT),'new_scope':reference(scope.__file__),
        'model_calls_in_waiter':0,'containers_created_in_waiter':0,'shared_host_changes':0}

def prepare():
    value=scope.load(reference(SPEC)) if SPEC.exists() else {**specification(),'ownership_token':secrets.token_hex(16)}
    scope.retain(SPEC,value)
    return {'specification':reference(SPEC),'launch_performed':False,'API_calls':0}

def command(value):
    expected=specification()
    if os.getuid()==0 or set(value)!=set(expected)|{'ownership_token'} or any(value[k]!=v for k,v in expected.items()):
        raise PermissionError('Only the exact bounded ordinary-user waiter may start')
    return ['systemd-run','--user','--collect','--no-block','--unit='+UNIT,
        '--description=ProWorkSim v161 cleanup waiter '+value['ownership_token'],
        '--property=Restart=no','--property=CPUQuota=5%','--property=MemoryMax=512M',
        '--property=MemorySwapMax=0','--property=TasksMax=64','--property=RuntimeMaxSec='+str(MAX_WAIT_SECONDS+120),
        '--property=WorkingDirectory='+str(scope.ROOT),'--setenv=PYTHONPATH='+str(scope.ROOT/'src'),
        '--property=StandardOutput=append:'+str(FOLDER/'stdout.log'),
        '--property=StandardError=append:'+str(FOLDER/'stderr.log'),
        str(scope.ROOT/'.venv/bin/python'),'-B',str(scope.ROOT/'tools/wait_communication_recovery_v161.py'),'--execute']

def start():
    scope.require_allowed('v161.wait')
    value=scope.load(reference(SPEC));argv=command(value)
    if any((FOLDER/name).exists() for name in ('launch-intent.json','started.json')):
        raise PermissionError('Waiter identity already consumed; never automatically start a second waiter')
    observed=subprocess.run(['systemctl','--user','show',UNIT,'--no-pager','--property=ActiveState,MainPID'],
        env=user_manager_environment(),capture_output=True,text=True,timeout=20)
    values=dict(line.split('=',1) for line in observed.stdout.splitlines() if '=' in line)
    if observed.returncode or values.get('ActiveState')!='inactive' or values.get('MainPID')!='0':
        raise PermissionError('Exact new waiter unit must be inactive')
    write_new(FOLDER/'launch-intent.json',{'version':VERSION,'authorization':reference(scope.AUTH_FILE),
        'specification':reference(SPEC),'command':argv,'unix':time.time()})
    result=subprocess.run(argv,env=user_manager_environment(),capture_output=True,text=True,timeout=30)
    receipt={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'API_calls':0}
    scope.retain(FOLDER/'launch-result.json',receipt)
    if result.returncode:raise RuntimeError('Waiter launch failed; preserve its identity for inspection')
    return receipt

def ready(status):
    return (status.get('passed') is True and status.get('v159_all_owned_objects_removed') is True
        and status.get('lease_empty') is True and status.get('predecessor_service_inactive') is True)

def execute():
    scope.require_allowed('v161.wait')
    if not SPEC.exists():raise PermissionError('Waiter specification has not been frozen')
    command(scope.load(reference(SPEC)))
    write_new(FOLDER/'started.json',{'version':VERSION,'pid':os.getpid(),'unix':time.time(),
        'maximum_wait_seconds':MAX_WAIT_SECONDS,'authorization':reference(scope.AUTH_FILE)})
    deadline=time.monotonic()+MAX_WAIT_SECONDS
    while time.monotonic()<deadline:
        try:status=scope.predecessor_quiescence_status()
        except Exception as error:status={'passed':False,'error':{'type':type(error).__name__,'message':str(error)}}
        atomic_write(FOLDER/'progress.json',json_bytes({'version':VERSION,'unix':time.time(),
            'remaining_wait_seconds':max(0,deadline-time.monotonic()),'predecessor':status,'API_calls':0}))
        if ready(status):
            scope.retain(FOLDER/'predecessor-cleanup-admission.json',status)
            path=scope.ROOT/'tools/launch_communication_pilot_v161.py'
            spec=importlib.util.spec_from_file_location('v161_after_cleanup_launcher',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            result=module.launch()
            return scope.retain(FOLDER/'completion.json',{'version':VERSION,'status':'launched_once',
                'launch_receipt':result,'waiter_API_calls':0})
        time.sleep(min(POLL_SECONDS,max(0,deadline-time.monotonic())))
    return scope.retain(FOLDER/'completion.json',{'version':VERSION,'status':'bounded_wait_expired',
        'launched':False,'API_calls':0})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    for name in ('prepare','start','execute'):g.add_argument('--'+name,action='store_true')
    a=p.parse_args();print(json.dumps(prepare() if a.prepare else start() if a.start else execute(),ensure_ascii=False))
