"""The300-CNY continuation with readiness restricted to the finished predecessor."""
import inspect,json,sqlite3
from types import ModuleType,FunctionType
from . import software_context_budget_runtime_v187 as previous
from . import software_context_task_api_v181 as api
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_candidates_v054 import reference

VERSION='v188-scoped-budget-handoff-r1'
ROOT=previous.ROOT
STATE=ROOT/'runs/software-benchmark-v188/budget-continuation-r1'
REMAINING=STATE/'remaining.json'
OLD=previous.scope.API_ROOT
original_scope=previous.original_scope
_ns=clone_namespace(original_scope,STATE_ROOT=STATE,API_ROOT=STATE/'api-coordinator',
 SOURCE_FILE=STATE/'sources.json',AUTH_FILE=ROOT/'config/v188-context-budget-authority.json',
 API_UNIT='proworksim-v188-context-budget.service',__file__=__file__)
source=inspect.getsource(original_scope.require_allowed).replace("auth.get('cash_cap_CNY')!='250.00'","auth.get('cash_cap_CNY')!='300.00'")
exec(compile(source,__file__+':authorized300','exec'),_ns)
_ns['require_grading_allowed']=_ns['require_allowed']
scope=ModuleType(__name__+'.scope');scope.__dict__.update(_ns)
Grading=previous.Grading
capacity_status=previous.capacity_status
bind_capacity=previous.bind_capacity
never_entered=previous.never_entered


def predecessor_closed():
    path=OLD/'final.json'
    if not path.exists():return False
    value=json.loads(path.read_bytes())
    if value.get('stage')!='closed' or value.get('generation_active') or value.get('grading_active'):return False
    records=value.get('records',{});slots=set(records)
    for path in (scope.BATCH_ROOT/'resource-claims').glob('active-*.json'):
        claim=json.loads(path.read_bytes())
        if claim.get('spec',{}).get('slot_id') in slots:return False
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
        if slots:
            placeholders=','.join('?' for _ in slots)
            if db.execute("SELECT count(*) FROM requests WHERE status='reserved' AND job_id IN ("+placeholders+')',tuple(slots)).fetchone()[0]:return False
    for record in records.values():
        if not record.get('result'):return False
        result=scope.load(record['result']);ref=result.get('quiescence')
        if not ref:return False
        quiet=scope.load(ref)
        if quiet.get('all_owned_objects_removed') is not True or quiet.get('cleanup_errors'):return False
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
