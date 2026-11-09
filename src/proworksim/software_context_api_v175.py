"""Independent250-CNY replay ledger and direct, finite-retry provider calls.

Budget admission reserves a whole bounded job; already admitted work is never
stopped by the cash gate. Exceptions remain local to one logical request/job.
Old experiment ledgers are never opened by this runtime.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time

from .software_benchmark_candidates_v054 import checked,reference,write_new
from .software_benchmark_deepseek_api_v157 import DirectHTTPS,TransportFailure
from .software_benchmark_deepseek_api_v105 import load_api_key
from .software_input_provenance_v156 import normalized_usage
from .storage import atomic_write,json_bytes

VERSION='v175-independent-context-replay-cash-r1'
CAP=250_000_000_000
FULL_CALL_RESERVATION=98304*2000+32768*8000
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'runs/software-benchmark-v175/context-replay-r1'


def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()


class AdmissionBusy(RuntimeError):pass
class CashClosed(RuntimeError):pass
class RequestFailed(RuntimeError):pass


class ReplayLedger:
    def __init__(self,path,*,plan_ref,cap=CAP):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.policy={'version':VERSION,'plan':plan_ref,'cap_nanoyuan':cap,
            'cash_gate':'reserve_bounded_job_at_start_only','max_physical_attempts_per_logical':3,
            'max_job_tokens':5000000,'rates_nanoyuan_per_token':{'miss':2000,'hit':40,'output':8000},
            'cost_is_peak_tariff_upper_not_invoice':True,'old_ledgers_modified':False}
        with self.transaction() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS metadata(name TEXT PRIMARY KEY,value TEXT);'
                'CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY,kind TEXT,cap INTEGER,status TEXT,started REAL,finished REAL);'
                'CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY,job_id TEXT,purpose TEXT,step INTEGER,attempt INTEGER,'
                'status TEXT,payload_sha TEXT,reserved INTEGER,cost INTEGER,usage TEXT,response_ref TEXT,error TEXT,started REAL,finished REAL);')
            old=db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
            if old and old[0]!=canonical(self.policy):raise ValueError('Never reopen a different or historical cash policy')
            db.execute("INSERT OR IGNORE INTO metadata VALUES('policy',?)",(canonical(self.policy),))

    @contextmanager
    def transaction(self):
        db=sqlite3.connect(self.path,timeout=60)
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        try:yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    def _account(self,db):
        spent=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost ELSE reserved END),0) FROM requests").fetchone()[0]
        holds=0
        for job in db.execute("SELECT job_id,cap FROM jobs WHERE status='running'").fetchall():
            used=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost ELSE reserved END),0) FROM requests WHERE job_id=?",(job['job_id'],)).fetchone()[0]
            holds+=max(0,job['cap']-used)
        return spent,holds

    def admit(self,job_id,kind,*,job_cap=5_000_000_000):
        with self.transaction() as db:
            old=db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
            if old:
                if old['kind']!=kind or old['cap']!=job_cap:raise ValueError('Replay job identity changed')
                return old['status']
            spent,holds=self._account(db)
            if spent+holds+job_cap>self.policy['cap_nanoyuan']:
                if holds:raise AdmissionBusy('Waiting for already-running jobs to release unused reservations')
                raise CashClosed('New-job cash admission closed')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',(job_id,kind,job_cap,'running',time.time()))
            return 'running'

    def request(self,request_id):
        with self.transaction() as db:
            row=db.execute('SELECT * FROM requests WHERE request_id=?',(request_id,)).fetchone()
            return dict(row) if row else None

    def reserve(self,job_id,request_id,purpose,step,attempt,payload):
        if attempt not in (1,2,3) or not 1<=payload.get('max_tokens',0)<=32768:
            raise ValueError('Finite attempt and output bounds required')
        reservation=98304*2000+payload['max_tokens']*8000
        with self.transaction() as db:
            job=db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
            if not job or job['status']!='running':raise ValueError('No actual whole-job admission')
            prior=db.execute('SELECT * FROM requests WHERE request_id=?',(request_id,)).fetchone()
            if prior:raise ValueError('An actual physical identity is never sent twice')
            used=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost ELSE reserved END),0) FROM requests WHERE job_id=?",(job_id,)).fetchone()[0]
            if used+reservation>job['cap']:raise ValueError('Bounded job request allocation was exceeded')
            known=sum(json.loads(r[0])['total_tokens'] for r in db.execute("SELECT usage FROM requests WHERE job_id=? AND status='settled'",(job_id,)))
            unknown=db.execute("SELECT count(*) FROM requests WHERE job_id=? AND status!='settled'",(job_id,)).fetchone()[0]*131072
            if known+unknown+131072>5000000:raise ValueError('Original shared5M token ceiling exceeded')
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (request_id,job_id,purpose,step,attempt,'reserved',digest(payload),reservation,None,None,None,None,time.time(),None))

    def settle(self,request_id,body,response_ref):
        usage=normalized_usage(body.get('usage'))
        if usage is None:raise ValueError('No actual provider usage')
        cost=usage['cache_miss_input_tokens']*2000+usage['cached_input_tokens']*40+usage['output_tokens']*8000
        with self.transaction() as db:
            row=db.execute('SELECT * FROM requests WHERE request_id=?',(request_id,)).fetchone()
            if not row:raise ValueError('Settlement without reservation')
            if row['status']=='settled':
                if row['usage']!=canonical(usage) or row['response_ref']!=canonical(response_ref):
                    raise ValueError('Conflicting duplicate settlement')
                return usage
            if cost>row['reserved']:raise ValueError('Provider charge exceeded full declared context/output reservation')
            db.execute("UPDATE requests SET status='settled',cost=?,usage=?,response_ref=?,finished=? WHERE request_id=?",
                (cost,canonical(usage),canonical(response_ref),time.time(),request_id))
        return usage

    def uncertain(self,request_id,error):
        with self.transaction() as db:
            db.execute("UPDATE requests SET status='unknown',error=?,finished=? WHERE request_id=? AND status!='settled'",
                (canonical(error),time.time(),request_id))

    def finish(self,job_id,status):
        if status not in {'closed','technical_unknown'}:raise ValueError('Only final job states allowed')
        with self.transaction() as db:
            db.execute('UPDATE jobs SET status=?,finished=? WHERE job_id=?',(status,time.time(),job_id))

    def snapshot(self):
        with self.transaction() as db:
            spent,holds=self._account(db)
            calls=[dict(r) for r in db.execute('SELECT * FROM requests')]
            jobs={r[0]:r[1] for r in db.execute('SELECT status,count(*) FROM jobs GROUP BY status')}
        settled=[r for r in calls if r['status']=='settled']
        return {'cap_CNY':self.policy['cap_nanoyuan']/1e9,
            'settled_upper_CNY':sum(r['cost'] for r in settled)/1e9,
            'unknown_or_inflight_upper_CNY':sum(r['reserved'] for r in calls if r['status']!='settled')/1e9,
            'unused_active_job_holds_CNY':holds/1e9,'committed_upper_CNY':(spent+holds)/1e9,
            'physical_requests':len(calls),'settled_requests':len(settled),'jobs':jobs,
            'known_actual_tokens':sum(json.loads(r['usage'])['total_tokens'] for r in settled),
            'cash_checked_only_on_new_job_admission':True}


class ReplayAPI:
    def __init__(self,ledger,*,counter,api_key,concurrency=32,transport_factory=None,sleep=time.sleep):
        self.ledger,self.counter,self.key=ledger,counter,api_key
        self.slots=threading.BoundedSemaphore(concurrency)
        self.transport_factory=transport_factory or (lambda:DirectHTTPS(self.key,timeout_seconds=1800))
        self.sleep=sleep

    def call(self,job_id,payload,*,purpose,step,folder):
        if (payload.get('model')!='deepseek-flash' or payload.get('thinking')!={'type':'disabled'}
            or payload.get('stream') is not False):raise ValueError('Freeze the non-thinking direct completion model')
        if self.counter.measure(payload)['prompt_tokens']>98304:
            raise ValueError('No silent truncation beyond the common input cap')
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        for attempt in (1,2,3):
            rid=f'{job_id}:{purpose}:{step}:attempt{attempt}'
            sub=folder/(purpose+'-'+str(step)+'-'+str(attempt));sub.mkdir(exist_ok=True)
            request_path=sub/'request.json';response_path=sub/'response.json'
            if request_path.exists():
                if json.loads(request_path.read_bytes())!=payload:raise ValueError('Resume changed an actual request')
            else:write_new(request_path,payload)
            prior=self.ledger.request(rid)
            if prior and prior['status']=='settled':
                return json.loads(checked(json.loads(prior['response_ref'])).read_bytes()),rid
            if prior and response_path.exists():
                body=json.loads(response_path.read_bytes());self.ledger.settle(rid,body,reference(response_path));return body,rid
            if prior:
                if prior['status']=='reserved':
                    self.ledger.uncertain(rid,{'type':'interrupted_without_trustworthy_response','retained_reservation':True})
                continue
            self.ledger.reserve(job_id,rid,purpose,step,attempt,payload)
            try:
                with self.slots:
                    transport=self.transport_factory();body=transport.request('POST','/chat/completions',payload)
                ref=write_new(response_path,body)
                self.ledger.settle(rid,body,ref)
                return body,rid
            except BaseException as error:
                detail=error.evidence if isinstance(error,TransportFailure) else {'type':type(error).__name__}
                self.ledger.uncertain(rid,detail)
                write_new(sub/'error.json',{'request_id':rid,'error':detail,'retry_uses_new_physical_identity':True})
                if not isinstance(error,TransportFailure):raise
                if error.http_status in (400,401,403,404):break
                delay=error.evidence.get('retry_after_seconds')
                self.sleep(delay if delay is not None else min(2**attempt,8))
        raise RequestFailed('Finite physical recovery attempts exhausted for this request; other jobs continue')
