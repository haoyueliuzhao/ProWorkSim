"""Same original remaining episodes, with the explicitly amended300-CNY start gate."""
import inspect
import json
import sqlite3
import time
from pathlib import Path
from types import ModuleType,FunctionType
from . import software_context_resume_v186 as previous
from . import software_context_task_api_v181 as api
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_candidates_v054 import reference
from .software_context_cash_v187 import effective_cap,CAP,AUTHORITY,VERSION

ROOT=previous.ROOT
STATE=ROOT/'runs/software-benchmark-v187/budget-continuation-r1'
REMAINING=STATE/'remaining.json'
OLD=previous.scope.API_ROOT
_ns=clone_namespace(previous.original_scope,STATE_ROOT=STATE,API_ROOT=STATE/'api-coordinator',
 SOURCE_FILE=STATE/'sources.json',AUTH_FILE=ROOT/'config/v187-context-budget-authority.json',
 API_UNIT='proworksim-v187-context-budget.service',__file__=__file__)
_guard=inspect.getsource(previous.original_scope.require_allowed)
if _guard.count("auth.get('cash_cap_CNY')!='250.00'")!=1:raise ValueError('Review the concrete budget authorization check')
_guard=_guard.replace("auth.get('cash_cap_CNY')!='250.00'","auth.get('cash_cap_CNY')!='300.00'")
exec(compile(_guard,__file__+':amended-cash-authority','exec'),_ns)
_ns['require_grading_allowed']=_ns['require_allowed']
_limits=inspect.getsource(previous.original_scope.verify_host_limits).replace('host_cpu_pool()[:8]','host_cpu_pool()[40:48]')
exec(compile(_limits,__file__+':companion-coordinator-limits','exec'),_ns)
scope=ModuleType(__name__+'.scope');scope.__dict__.update(_ns)
original_scope=previous.original_scope
Grading=previous.Grading
capacity_status=previous.capacity_status
bind_capacity=previous.bind_capacity
never_entered=previous.never_entered


def predecessor_closed():
    path=OLD/'final.json'
    if not path.exists():return False
    value=json.loads(path.read_bytes())
    if value.get('stage')!='closed' or value.get('generation_active') or value.get('grading_active'):return False
    if list((scope.BATCH_ROOT/'resource-claims').glob('active-*.json')):return False
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
        if db.execute("SELECT count(*) FROM requests WHERE status='reserved'").fetchone()[0]:return False
    for row in value.get('records',{}).values():
        if not row.get('result'):continue
        result=scope.load(row['result']);ref=result.get('quiescence')
        if not ref:return False
        quiet=scope.load(ref)
        if quiet.get('all_owned_objects_removed') is not True or quiet.get('cleanup_errors'):return False
    return True


class TaskLedger(previous.TaskLedger):
    def admit_block(self,rows):
        if not predecessor_closed():raise ValueError('The previous owner is still finishing entered work')
        allowed={r['slot_id'] for r in scope.load(reference(REMAINING))['rows']}
        with self.transaction() as db:
            for row in rows:
                key=row['slot_id']
                if key not in allowed or self.rows.get(key)!=row or not never_entered(row,db):raise ValueError('Only the original unentered repeats may enter')
                if db.execute('SELECT 1 FROM jobs WHERE job_id=?',(key,)).fetchone():raise ValueError('An admitted or called episode cannot replay')
            spent,holds=self._account(db)
            if spent+holds+len(rows)*api.START_HOLD>effective_cap(db):
                raise api.CashClosed('New paired block exceeds authorized300-CNY start admission')
            for row in rows:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',
                (row['slot_id'],'v181-full-task',api.JOB_CAP,'running',time.time()))
            return {'new_grants':len(rows),'effective_cap_CNY':300}

    def snapshot(self):
        value=super().snapshot()
        with self.transaction() as db:cap=effective_cap(db)
        return {**value,'cap_CNY':cap/1e9,'original_policy_cap_CNY':250,'approved_added_CNY':50,
            'cash_amendment':reference(AUTHORITY),'old_policy_unchanged':True}


_api={**vars(api),'scope':scope,'TaskLedger':TaskLedger}
_api['Route']=type('Route',(api.Route,),{k:clone_function(v,_api)
    for k,v in vars(api.Route).items() if isinstance(v,FunctionType)})
_parent=type('Runtime',(api.Runtime,),{k:clone_function(v,_api)
    for k,v in vars(api.Runtime).items() if isinstance(v,FunctionType)})

class Runtime(_parent):
    def resident(self,row):
        with self.lock:return super().resident(row)
