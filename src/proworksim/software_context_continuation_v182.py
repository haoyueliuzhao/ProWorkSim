"""Host-only continuation: serialize identity creation and recover unentered starts.

The frozen v181 controller, tools, histories, task IDs and model settings remain
byte-identical. Only a proven zero-object, zero-HTTP startup can enter again.
"""
import copy
import inspect
import json
import time
from pathlib import Path
from types import ModuleType,FunctionType
from . import software_benchmark_scope_v181 as original_scope
from . import software_context_task_api_v181 as original_api
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_candidates_v054 import reference

ROOT=original_scope.ROOT
STATE=ROOT/'runs/software-benchmark-v182/context-continuation-r1'
VERSION='v182-zero-call-start-recovery-and-independent-host-queue-r1'

_scope_ns=clone_namespace(original_scope,API_ROOT=STATE/'api-coordinator',STATE_ROOT=STATE,
 SOURCE_FILE=STATE/'runtime-sources.json',AUTH_FILE=ROOT/'config/v182-context-continuation-authority.json',
 API_UNIT='proworksim-v182-context-continuation.service',__file__=__file__)
_verify=inspect.getsource(original_scope.verify_host_limits).replace('host_cpu_pool()[:8]','host_cpu_pool()[40:48]')
exec(compile(_verify,__file__+':own-coordinator-limits','exec'),_scope_ns)
scope=ModuleType(__name__+'.scope');scope.__dict__.update(_scope_ns)


def unentered(row):
    if not original_scope.never_consumed(row):return False
    import sqlite3
    with sqlite3.connect(original_scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
        return db.execute('SELECT count(*) FROM requests WHERE job_id=?',(row['slot_id'],)).fetchone()[0]==0


def startup_recovery_proof(row):
    if not unentered(row):raise ValueError('Called or resource-consumed attempts cannot be restarted')
    path=original_scope.API_ROOT/'progress.json'
    data=json.loads(path.read_bytes());record=data.get('records',{}).get(row['slot_id'])
    if (not record or record.get('status')!='technical_unknown' or record.get('result')
        or record.get('error',{}).get('type')!='FileExistsError'):
        raise ValueError('Only the proved before-entry identity-file race may resume')
    return {'prior_progress_sha256':reference(path)['sha256'],'record':record,
        'zero_physical_HTTP':True,'zero_owned_object_claims':True,'first_model_attempt':True}


class TaskLedger(original_api.TaskLedger):
    def admit_block(self,rows):
        proofs={}
        with self.transaction() as db:
            existing={r['slot_id']:dict(old) for r in rows
                if (old:=db.execute('SELECT * FROM jobs WHERE job_id=?',(r['slot_id'],)).fetchone())}
        for row in rows:
            if row['slot_id'] in existing:proofs[row['slot_id']]=startup_recovery_proof(row)
        with self.transaction() as db:
            spent,holds=self._account(db)
            if spent+holds+len(rows)*original_api.START_HOLD>self.policy['cap_nanoyuan']:
                raise original_api.CashClosed('New paired block cannot enter cumulative250 account')
            db.execute('CREATE TABLE IF NOT EXISTS zero_call_recoveries_v182(job_id TEXT PRIMARY KEY,prior_job TEXT,proof TEXT,recovered REAL)')
            for row in rows:
                key=row['slot_id']
                if self.rows.get(key)!=row or not unentered(row):raise ValueError('Foreign or consumed planned task')
                current=db.execute('SELECT * FROM jobs WHERE job_id=?',(key,)).fetchone()
                if key in existing:
                    if dict(current)!=existing[key] or current['status']!='technical_unknown':raise ValueError('Startup state changed')
                    db.execute('INSERT INTO zero_call_recoveries_v182 VALUES(?,?,?,?)',
                        (key,original_api.canonical(dict(current)),original_api.canonical(proofs[key]),time.time()))
                    db.execute("UPDATE jobs SET status='running',finished=NULL WHERE job_id=?",(key,))
                elif current is not None:raise ValueError('Task concurrently admitted')
                else:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',
                    (key,'v181-full-task',original_api.JOB_CAP,'running',time.time()))


_api_ns={**vars(original_api),'scope':scope,'TaskLedger':TaskLedger}
_api_ns['Route']=type('Route',(original_api.Route,),{k:clone_function(v,_api_ns)
    for k,v in vars(original_api.Route).items() if isinstance(v,FunctionType)})
_api_ns['Runtime']=type('Runtime',(original_api.Runtime,),{k:clone_function(v,_api_ns)
    for k,v in vars(original_api.Runtime).items() if isinstance(v,FunctionType)})


class Runtime(_api_ns['Runtime']):
    def resident(self,row):
        with self.lock:return super().resident(row)


def predecessor_closed():
    path=original_scope.API_ROOT/'final.json'
    if not path.exists():return False
    data=json.loads(path.read_bytes())
    for record in data.get('records',{}).values():
        if not record.get('result'):continue
        result=original_scope.load(record['result']);ref=result.get('quiescence')
        if not ref:return False
        quiet=original_scope.load(ref)
        if quiet.get('all_owned_objects_removed') is not True or quiet.get('cleanup_errors'):return False
    return True
