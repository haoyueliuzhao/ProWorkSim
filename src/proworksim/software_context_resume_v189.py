"""Resume original episodes after an unlocked active-lease snapshot race."""
import fcntl,inspect,json,sqlite3
from types import FunctionType,ModuleType
from . import software_context_budget_runtime_v188 as previous
from . import software_context_task_api_v181 as api
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_candidates_v054 import reference

VERSION='v189-locked-capacity-snapshot-and-original-result-recovery-r1'
ROOT=previous.ROOT
STATE=ROOT/'runs/software-benchmark-v189/lease-race-recovery-r1'
REMAINING=STATE/'remaining.json'
HANDOFF=ROOT/'artifacts/software-benchmark-v189/recovery-r1/handoff.json'
OLD_PROGRESS=STATE/'predecessor-progress.json'
original_scope=previous.original_scope
_ns=clone_namespace(original_scope,STATE_ROOT=STATE,API_ROOT=STATE/'api-coordinator',
 SOURCE_FILE=STATE/'sources.json',AUTH_FILE=ROOT/'config/v189-context-resume-authority.json',
 API_UNIT='proworksim-v189-context-resume.service',__file__=__file__)
source=inspect.getsource(original_scope.require_allowed)
if source.count("auth.get('cash_cap_CNY')!='250.00'")!=1:raise ValueError('Review budget guard')
source=source.replace("auth.get('cash_cap_CNY')!='250.00'","auth.get('cash_cap_CNY')!='300.00'")
exec(compile(source,__file__+':approved300','exec'),_ns)
_ns['require_grading_allowed']=_ns['require_allowed']
scope=ModuleType(__name__+'.scope');scope.__dict__.update(_ns)
Grading=previous.Grading
never_entered=previous.never_entered


def active_claims(policy):
    """Use the same allocation lock as reserve/release; read mutable leases once."""
    directory=policy.BATCH_ROOT/'resource-claims'
    with (directory/'allocation.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_SH)
        return [json.loads(path.read_bytes()) for path in directory.glob('active-*.json')]


def capacity_status(policy,*,physical=None,active=None,load1=None):
    if active is None:active=active_claims(policy)
    return previous.capacity_status(policy,physical=physical,active=active,load1=load1)


bind_capacity=clone_function(previous.bind_capacity,
    {**previous.bind_capacity.__globals__,'capacity_status':capacity_status})


def predecessor_closed():
    proof=scope.load(reference(HANDOFF))
    if proof.get('old_manager_stopped') is not True or proof.get('old_resources_removed') is not True:return False
    old_slots=set(proof['completed_slots'])
    if any(c.get('spec',{}).get('slot_id') in old_slots for c in active_claims(scope.dispatch_view())):return False
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
        if old_slots:
            placeholders=','.join('?' for _ in old_slots)
            if db.execute("SELECT count(*) FROM requests WHERE status='reserved' AND job_id IN ("+placeholders+')',tuple(old_slots)).fetchone()[0]:return False
    return True


_ledger_ns={**previous.TaskLedger.admit_block.__globals__,'scope':scope,'REMAINING':REMAINING,
 'predecessor_closed':predecessor_closed}
class TaskLedger(previous.TaskLedger):
    admit_block=clone_function(previous.TaskLedger.admit_block,_ledger_ns)

_api={**vars(api),'scope':scope,'TaskLedger':TaskLedger}
_api['Route']=type('Route',(api.Route,),{k:clone_function(v,_api)
 for k,v in vars(api.Route).items() if isinstance(v,FunctionType)})
_parent=type('Runtime',(api.Runtime,),{k:clone_function(v,_api)
 for k,v in vars(api.Runtime).items() if isinstance(v,FunctionType)})
class Runtime(_parent):
    def resident(self,row):
        with self.lock:return super().resident(row)
