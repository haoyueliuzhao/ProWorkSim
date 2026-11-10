"""Resume unentered v181 identities with one capacity and cash admission rule."""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from types import FunctionType,ModuleType
from . import software_benchmark_scope_v181 as original_scope
from . import software_context_task_api_v181 as original_api
from .software_benchmark_expansion_episode_v069 import clone_namespace,clone_function
from .software_benchmark_candidates_v054 import reference

VERSION='v186-single-owner-capacity-and-global-start-hold-repair-r1'
ROOT=original_scope.ROOT
STATE=ROOT/'runs/software-benchmark-v186/resume20-r1'
REMAINING=STATE/'remaining.json'
HANDOFF=ROOT/'artifacts/software-benchmark-v186/idle-handoff-r1/completion.json'
_ns=clone_namespace(original_scope,STATE_ROOT=STATE,API_ROOT=STATE/'api-coordinator',
 SOURCE_FILE=STATE/'sources.json',AUTH_FILE=ROOT/'config/v186-context-resume-authority.json',
 API_UNIT='proworksim-v186-context-resume.service',__file__=__file__)
scope=ModuleType(__name__+'.scope');scope.__dict__.update(_ns)


def never_entered(row,db=None):
    if not original_scope.never_consumed(row) or (scope.BATCH_ROOT/'episodes'/str(row['slot_index'])).exists():return False
    if db is not None:return db.execute('SELECT count(*) FROM requests WHERE job_id=?',(row['slot_id'],)).fetchone()[0]==0
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as connection:return never_entered(row,connection)


def capacity_status(policy,*,physical=None,active=None,load1=None):
    """Same floors as atomic resource reservation; no inherited256GiB gate."""
    c=policy.CONSTRAINTS;physical=physical or policy.physical_capacity()
    if active is None:
        active=[scope.load(reference(p)) for p in (policy.BATCH_ROOT/'resource-claims').glob('active-*.json')]
    load1=os.getloadavg()[0] if load1 is None else load1
    disk_floor=c['disk_minimum_free_bytes']+c['generation_pair_payload_spool_bytes']+sum(r.get('reserved_spool_bytes',0) for r in active)
    memory_floor=c['memory_minimum_free_bytes']+c['generation_pair_reserved_memory_bytes']
    reasons=[]
    if physical['disk_free_bytes']<disk_floor:reasons.append('disk_reservation')
    if physical['memory_available_bytes']<memory_floor:reasons.append('memory_headroom')
    if load1>=len(policy.host_cpu_pool())-16:reasons.append('cpu_headroom')
    if sum(r['spec']['role']=='actor' for r in active)>=c['active_actor_limit']:reasons.append('generation_slots')
    return {'admit':not reasons,'waiting_reasons':reasons,'disk_floor_bytes':disk_floor,
        'memory_floor_bytes':memory_floor,'load_1m':load1,**physical,'observed_unix':time.time()}


def bind_capacity(episode,policy,stop_new,report):
    def capacity():
        value=capacity_status(policy);report(value);return value
    def wait_capacity(stop_event=None):
        while True:
            if stop_new.is_set() or stop_event is not None and stop_event.is_set():
                raise InterruptedError('Cancelled before resource or HTTP admission')
            policy.require_v066_allowed('v066.run')
            value=capacity()
            if value['admit']:return value
            stop_new.wait(2)
    actual=episode._run.__globals__
    actual.update(capacity=capacity,wait_capacity=wait_capacity)
    episode.capacity=capacity;episode.wait_capacity=wait_capacity
    if episode.run_episode.__globals__['_run'] is not episode._run:raise ValueError('Actual entrypoint lost its scoped capacity binding')
    return episode


class TaskLedger(original_api.TaskLedger):
    def _account(self,db):
        spent=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost ELSE reserved END),0) FROM requests").fetchone()[0]
        holds=0
        for job in db.execute("SELECT * FROM jobs WHERE status='running'").fetchall():
            used=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost ELSE reserved END),0) FROM requests WHERE job_id=?",(job['job_id'],)).fetchone()[0]
            # Job kind identifies this shared experimental account. A reader's
            # current task subset must never inflate other same-batch holds.
            initial=original_api.START_HOLD if job['kind']=='v181-full-task' else job['cap']
            holds+=max(0,initial-used)
        return spent,holds

    def admit_block(self,rows):
        allowed={r['slot_id'] for r in scope.load(reference(REMAINING))['rows']}
        handoff=scope.load(reference(HANDOFF))
        if handoff.get('old_manager_stopped') is not True:raise ValueError('Predecessor still owns the waiting starts')
        with self.transaction() as db:
            existing={}
            for row in rows:
                key=row['slot_id']
                if key not in allowed or self.rows.get(key)!=row or not never_entered(row,db):raise ValueError('Only the frozen unentered identities can resume')
                old=db.execute('SELECT * FROM jobs WHERE job_id=?',(key,)).fetchone()
                if old:
                    if old['status']!='running' or old['kind']!='v181-full-task':raise ValueError('Unreviewed previous job state')
                    existing[key]=dict(old)
            spent,holds=self._account(db)
            new=len(rows)-len(existing)
            if new and spent+holds+new*original_api.START_HOLD>self.policy['cap_nanoyuan']:
                raise original_api.CashClosed('New paired block exceeds cumulative250 start admission')
            db.execute('CREATE TABLE IF NOT EXISTS start_handoff_v186(job_id TEXT PRIMARY KEY,previous_job TEXT,proof TEXT,adopted REAL)')
            for row in rows:
                key=row['slot_id']
                if key in existing:
                    db.execute('INSERT INTO start_handoff_v186 VALUES(?,?,?,?)',
                        (key,original_api.canonical(existing[key]),original_api.canonical(reference(HANDOFF)),time.time()))
                else:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',
                    (key,'v181-full-task',original_api.JOB_CAP,'running',time.time()))
            return {'adopted_prior_grants':len(existing),'new_grants':new}


_api={**vars(original_api),'scope':scope,'TaskLedger':TaskLedger}
_api['Route']=type('Route',(original_api.Route,),{k:clone_function(v,_api)
    for k,v in vars(original_api.Route).items() if isinstance(v,FunctionType)})
_parent=type('Runtime',(original_api.Runtime,),{k:clone_function(v,_api)
    for k,v in vars(original_api.Runtime).items() if isinstance(v,FunctionType)})

class Runtime(_parent):
    def resident(self,row):
        with self.lock:return super().resident(row)


class Grading:
    """Reuse the already-qualified scorers, selecting only by task identity."""
    def __init__(self):
        from .software_benchmark_grading_v181 import factory as standard
        from .software_benchmark_grading_v184 import factory as pylint
        self.standard=standard();self.pylint=pylint()

    def for_ref(self,ref):
        value=scope.load(ref)
        return self.pylint if value['instance_id']=='pylint-dev__pylint-8898' else self.standard

    def prepare_score(self,ref,**kwargs):return self.for_ref(ref).prepare_score(ref,**kwargs)
    def run_request(self,ref,stop_event=None):return self.for_ref(ref).run_request(ref,stop_event=stop_event)
    def trustworthy_cleanup(self,ref):return self.for_ref(ref).trustworthy_cleanup(ref)
    def delivery_disposition(self,ref,request=None):return self.for_ref(ref).delivery_disposition(ref,request)
