"""Four frozen S1 context conditions, paired cash starts, asynchronous official scores."""
import fcntl
import json
import os
from pathlib import Path
import signal
import threading
import time
from collections import deque,Counter
from concurrent.futures import ThreadPoolExecutor
from proworksim.software_context_budget_runtime_v187 import scope,original_scope,REMAINING,Grading,bind_capacity,capacity_status,never_entered,predecessor_closed,OLD
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate
from proworksim.software_context_task_api_v181 import CashClosed
from proworksim.software_context_budget_runtime_v187 import Runtime
from proworksim.storage import atomic_write,json_bytes


def detail(error):return {'type':type(error).__name__,'message':str(error)}


class Coordinator:
    def __init__(self):
        scope.require_allowed();scope.verify_host_limits()
        self.plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
        self.stop=threading.Event();self.entered_stop=threading.Event()
        signal.signal(signal.SIGTERM,lambda *_:self.stop.set())
        signal.signal(signal.SIGINT,lambda *_:self.stop.set())
        self.memory=HostMemoryGate(maximum=2);self.startups=threading.BoundedSemaphore(2)
        self.start_lock=threading.Lock();self.start_holds=set()
        from proworksim.software_benchmark_episode_v181 import build_episode
        self.episode=build_episode(scope=scope,guard=scope.require_allowed,host_memory=self.memory,admission_check=self.started)
        self.capacity_gate={}
        bind_capacity(self.episode,scope.dispatch_view(),self.stop,lambda v:setattr(self,'capacity_gate',v))
        self.grading=Grading();self.records={};self.exceptions={};self.qualified={};self.scores={};self.score_pending=deque()
        self.runtime=None;self.stage='zero_model_diagnostics';self.last=0

    def started(self,row):
        with self.start_lock:
            if row['slot_id'] in self.start_holds:
                self.start_holds.remove(row['slot_id']);self.startups.release()

    def progress(self,**extra):
        value={'version':scope.VERSION,'updated_unix':time.time(),'stage':self.stage,
            'planned_primary':48,'planned_repeats':12,'qualified_environments':len(self.qualified),
            'generation_finished':len(self.records),'generation_statuses':dict(Counter(r['status'] for r in self.records.values())),
            'code_scored':sum(v['endpoint']=='code' and isinstance(v.get('resolved'),bool) for v in self.scores.values()),
            'scores':self.scores,'exceptions':self.exceptions,'records':self.records,
            'cash':self.runtime.ledger.snapshot() if self.runtime else None,
            'capacity_gate':self.capacity_gate,**extra}
        workers=value.get('generation_active',0)
        value['generation_inflight_or_waiting']=workers
        value['generation_active']=len(list((scope.BATCH_ROOT/'resource-claims').glob('active-actor-*.json')))
        value['generation_waiting']=max(0,workers-value['generation_active'])
        if not value['generation_active'] and self.capacity_gate and not self.capacity_gate['admit']:
            value['pipeline_status']='waiting_resources'
        else:value['pipeline_status']=self.stage
        atomic_write(scope.API_ROOT/'progress.json',json_bytes(value));return value

    def diagnostic(self,index):
        from proworksim.software_benchmark_diagnostic_receipts_v143 import inspect_diagnostic
        from proworksim.software_benchmark_alignment_contract_v181 import condition,shared_strategy
        ref=self.episode.run_diagnostic(index,stop_event=self.entered_stop)
        spec=next(s for s in self.plan['diagnostics'] if s['index']==index)
        inspect_diagnostic(ref,spec,load=scope.load,condition=lambda _:condition(spec['group_id']),
            shared_strategy=lambda _:shared_strategy(spec['group_id']),controller_memory_bytes=32*scope.GIB)
        return ref

    def controls(self):
        prepared=self.grading.prepare_environment_qualifications()
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending={pool.submit(self.grading.run_request,r,self.entered_stop):r for r in prepared['controls']}
            while pending:
                for future,ref in list(pending.items()):
                    if not future.done():continue
                    request=scope.load(ref);key=request['resource_key']
                    try:
                        result=future.result()
                        if result.get('returncode')!=0 or not self.grading.trustworthy_cleanup(ref):
                            raise RuntimeError('Environment control lacks successful completion/cleanup')
                    except Exception as error:self.exceptions[key]=detail(error)
                    del pending[future]
                self.progress(control_jobs_active=len(pending));time.sleep(1)
        for task in self.plan['environments']:
            try:self.qualified[task]=self.grading.qualify(task)
            except Exception as error:self.exceptions['qualification:'+task]=detail(error)
        scope.retain(scope.COORDINATOR_ROOT/'qualification-outcomes.json',
            {'qualified':self.qualified,'exceptions':self.exceptions,'model_calls':0})

    def generation(self,row):
        while not self.startups.acquire(timeout=.5):
            if self.stop.is_set():raise InterruptedError('Drained before startup admission')
        if self.stop.is_set():
            self.startups.release();raise InterruptedError('Drained before startup admission')
        with self.start_lock:self.start_holds.add(row['slot_id'])
        try:
            ref=self.episode.run_episode(row,self.runtime.resident(row),stop_event=self.entered_stop,
                api_transport_factory=self.runtime.transport_factory)
            value=scope.load(ref)
            return {'row':row,'result':ref,'status':value['status']}
        finally:self.started(row)

    def prepare_scores(self,record):
        row=record['row'];value=scope.load(record['result'])
        quiet=scope.load(value['quiescence']) if value.get('quiescence') else {}
        if quiet.get('all_owned_objects_removed') is not True or quiet.get('cleanup_errors'):
            self.stop.set();raise RuntimeError('Owned generation cleanup requires recovery before new starts')
        physical=self.runtime.ledger.physical(row['slot_id'])
        record['physical_usage']=physical
        if record['status']!='closed':
            self.exceptions[row['slot_id']]=value.get('error',{'reason':value.get('failure_classification')});return
        request=self.memory.run_heavy(row['slot_id'],'prepare_official_code',lambda:self.grading.prepare_score(record['result']))
        self.score_pending.append((record,'code',request))

    def collect_score(self,record,endpoint,request_ref,future):
        request=scope.load(request_ref);key=request['resource_key']
        result=future.result();quiet=self.grading.trustworthy_cleanup(request_ref)
        receipt=scope.load(reference(Path(request['directory'])/'receipt.json'))
        identity=scope.load(receipt['identity'])
        if not quiet or result.get('returncode')!=0 or identity.get('request')!=request_ref:
            raise RuntimeError('Official score completion/identity/cleanup did not close')
        resolved=receipt.get('resolved') if receipt.get('status')=='official_report' else None
        self.scores[key]={'slot_id':record['row']['slot_id'],'endpoint':endpoint,'resolved':resolved,
            'status':receipt.get('status'),'receipt':reference(Path(request['directory'])/'receipt.json')}
        if endpoint=='code':
            delivery=self.memory.run_heavy(record['row']['slot_id'],'delivery_disposition',
                lambda:self.grading.delivery_disposition(record['result'],request_ref))
            if delivery.get('scoring_request'):
                self.score_pending.append((record,'delivery',delivery['scoring_request']))
            else:self.scores['delivery-'+str(record['row']['slot_index'])]={
                'slot_id':record['row']['slot_id'],'endpoint':'delivery',**delivery}

    def run(self):
        scope.retain(scope.API_ROOT/'execution-started.json',{'pid':os.getpid(),'plan':reference(scope.PLAN_FILE),
            'started_unix':time.time(),'source_index':reference(scope.SOURCE_FILE)})
        self.stage='waiting_predecessor'
        while not predecessor_closed():
            self.progress(reason='current episodes finish naturally before budget-owner handoff')
            if self.stop.wait(10):return
        remaining=scope.load(reference(REMAINING))
        old=scope.load(reference(OLD/'final.json'))
        for row in remaining['rows']:
            if not never_entered(row):raise ValueError('The predecessor entered a supposedly pending repeat')
        scope.retain(scope.API_ROOT/'predecessor-handoff.json',{'old_final':reference(OLD/'final.json'),
            'old_resources_removed':True,'existing_episodes_interrupted':0,'remaining':reference(REMAINING)})
        self.records=old['records'];self.scores=old['scores']
        self.exceptions={k:v for k,v in old.get('exceptions',{}).items() if not k.startswith('unentered:')}
        self.qualified=scope.load(reference(original_scope.COORDINATOR_ROOT/'qualification-outcomes.json'))['qualified']
        pylint=scope.ROOT/'runs/software-benchmark-v184/pylint-completion-r1/grading-coordinator/qualifications/pylint-dev__pylint-8898.json'
        self.qualified['pylint-dev__pylint-8898']=reference(pylint)
        self.runtime=Runtime(self.plan);self.runtime.resident(remaining['rows'][0])
        self.stage='generation_and_async_scoring'
        blocks=[]
        for row in remaining['rows']:
            key=(row['instance_id'],row['repeat_index'])
            if not blocks or blocks[-1][0]!=key:blocks.append((key,[]))
            blocks[-1][1].append(row)
        pending=deque(blocks);generation={};grading={};cash_closed=False
        with ThreadPoolExecutor(max_workers=4) as gp,ThreadPoolExecutor(max_workers=2) as sp:
            while pending or generation or grading or self.score_pending:
                self.capacity_gate=capacity_status(scope.dispatch_view())
                if pending and not generation and not self.stop.is_set() and not cash_closed and self.capacity_gate['admit']:
                    key,rows=pending.popleft()
                    if key[0] not in self.qualified:
                        self.exceptions['unentered:'+str(key)]={'reason':'environment_not_qualified'}
                    else:
                        try:self.runtime.ledger.admit_block(rows)
                        except CashClosed:pending.appendleft((key,rows));cash_closed=True
                        else:
                            for row in rows:generation[gp.submit(self.generation,row)]=row
                for future,row in list(generation.items()):
                    if not future.done():continue
                    try:
                        record=future.result();self.records[row['slot_id']]=record
                        self.runtime.ledger.finish(row['slot_id'],'closed' if record['status']=='closed' else 'technical_unknown')
                        self.prepare_scores(record)
                    except Exception as error:
                        self.exceptions[row['slot_id']]=detail(error)
                        self.runtime.ledger.finish(row['slot_id'],'technical_unknown')
                        self.records.setdefault(row['slot_id'],{'row':row,'status':'technical_unknown','error':detail(error)})
                        # Raw failure after entry without any returned cleanup proof
                        # stops new admission, but lets all entered work finish.
                        if 'result' not in self.records[row['slot_id']] and not never_entered(row):self.stop.set()
                    del generation[future]
                for future,item in list(grading.items()):
                    if not future.done():continue
                    try:self.collect_score(*item,future)
                    except Exception as error:self.exceptions[scope.load(item[2])['resource_key']]=detail(error)
                    del grading[future]
                while self.score_pending and len(grading)<2:
                    item=self.score_pending.popleft();grading[sp.submit(self.grading.run_request,item[2],self.entered_stop)]=item
                if time.monotonic()-self.last>=10:
                    self.progress(generation_active=len(generation),grading_active=len(grading),
                        pending_blocks=len(pending),new_admission_cash_closed=cash_closed);self.last=time.monotonic()
                if (cash_closed or self.stop.is_set()) and not generation and not grading and not self.score_pending:break
                time.sleep(.5)
        self.stage='closed';self.memory.close()
        result=self.progress(generation_active=0,grading_active=0,pending_blocks=len(pending),
            unentered_rows=[r for _,rows in pending for r in rows],new_admission_cash_closed=cash_closed)
        scope.retain(scope.API_ROOT/'final.json',result)


if __name__=='__main__':
    scope.API_ROOT.mkdir(parents=True,exist_ok=True)
    lock=(scope.API_ROOT/'coordinator.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    runner=None
    try:runner=Coordinator();runner.run()
    except BaseException as error:
        atomic_write(scope.API_ROOT/'coordinator-error.json',json_bytes({'error':detail(error),'unix':time.time()}))
        raise
