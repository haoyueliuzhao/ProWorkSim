"""Direct API, independent cash ledger, paired admission and physical retries."""
import copy
import json
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from . import software_benchmark_scope_v192 as scope
from .software_context_api_v175 import ReplayLedger,ReplayAPI,AdmissionBusy,CashClosed,canonical,digest,load_api_key
from .software_benchmark_candidates_v054 import reference,checked,write_new
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_deepseek_contract_v105 import validate_payload,slot_user_id,PreDispatchBudgetStopped,APIUncertainFailure
from .software_benchmark_deepseek_prefix_v055_r2 import count_incomplete_prefix,pending_tail_tool_ids
from .storage import digest as byte_digest,json_bytes

VERSION='v192-context-task-direct-physical-ledger-r1'
START_HOLD=5_000_000_000
REPEAT_EARMARK=10_000_000_000
JOB_CAP=40_000_000_000
ENDPOINT='http://127.0.0.1:18219'


class TaskLedger(ReplayLedger):
    def __init__(self,*,path=None,plan=None,counter=None):
        super().__init__(path or scope.LEDGER_FILE,plan_ref=reference(scope.PLAN_FILE),cap=300_000_000_000)
        self.rows={r['slot_id']:r for r in (plan or scope.load(reference(scope.PLAN_FILE)))['rows']}
        self.counter=counter
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS context_requests_v192(request_id TEXT PRIMARY KEY,logical_id TEXT,prompt_upper INTEGER,token_hold INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS context_phase_v192(name TEXT PRIMARY KEY,body TEXT)')
            value=canonical({'plan':reference(scope.PLAN_FILE),'cap_CNY':300,'cash_gate':'new_paired_block_only',
                'unentered_repeat_earmark_CNY_per_episode':10,'old_ledger_balance_transferred':False,
                'initial_estimated_hold_CNY_per_episode':5,'started_episodes_finish':True,
                'episode_input_output_tokens':5000000,'per_episode_worst_tariff_CNY':40})
            old=db.execute("SELECT body FROM context_phase_v192 WHERE name='policy'").fetchone()
            if old and old[0]!=value:raise ValueError('Context phase policy changed')
            db.execute("INSERT OR IGNORE INTO context_phase_v192 VALUES('policy',?)",(value,))

    def _account(self,db):
        spent=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost ELSE reserved END),0) FROM requests").fetchone()[0]
        holds=0
        for job in db.execute("SELECT * FROM jobs WHERE status='running'").fetchall():
            used=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN cost ELSE reserved END),0) FROM requests WHERE job_id=?",(job['job_id'],)).fetchone()[0]
            holds+=max(0,(START_HOLD if job['kind']=='v192-full-task' else job['cap'])-used)
        return spent,holds

    def _repeat_earmark(self,db,excluding=()):
        return sum(REPEAT_EARMARK for r in self.rows.values() if not r['primary_panel'] and r['slot_id'] not in excluding
            and not db.execute('SELECT 1 FROM jobs WHERE job_id=?',(r['slot_id'],)).fetchone())

    def admit_block(self,rows):
        if not rows or any(self.rows.get(r['slot_id'])!=r for r in rows):raise ValueError('Foreign paired admission')
        with self.transaction() as db:
            if any(db.execute('SELECT 1 FROM jobs WHERE job_id=?',(r['slot_id'],)).fetchone() for r in rows):
                raise ValueError('A whole task attempt cannot be silently restarted')
            spent,holds=self._account(db)
            earmark=self._repeat_earmark(db,{r['slot_id'] for r in rows})
            if spent+holds+earmark+len(rows)*START_HOLD>self.policy['cap_nanoyuan']:
                raise CashClosed('New block cannot enter the independent300 CNY account while protecting pending repeats')
            for r in rows:db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',
                (r['slot_id'],'v192-full-task',JOB_CAP,'running',time.time()))

    def snapshot(self):
        value=super().snapshot()
        with self.transaction() as db:earmark=self._repeat_earmark(db)
        return {**value,'unentered_repeat_earmark_CNY':earmark/1e9,
            'committed_plus_repeat_earmark_CNY':value['committed_upper_CNY']+earmark/1e9,
            'repeat_earmark_is_estimate_not_worst_case_guarantee':True,'old_balance_transferred':False}

    def reserve(self,job_id,request_id,purpose,step,attempt,payload):
        if job_id not in self.rows or purpose not in {'agent','condenser'} or attempt not in (1,2,3):
            raise ValueError('Physical request outside the frozen context panel')
        prompt=self.counter.measure(payload)['prompt_tokens'];cap=payload['max_tokens'];hold=prompt+cap
        if prompt>98304 or not 1<=cap<=32768:raise ValueError('Original context/output bound exceeded')
        with self.transaction() as db:
            job=db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
            if not job or job['status']!='running':raise ValueError('No paired task start grant')
            rows=db.execute('SELECT r.*,d.token_hold FROM requests r JOIN context_requests_v192 d USING(request_id) WHERE job_id=?',(job_id,)).fetchall()
            used=sum(json.loads(r['usage'])['total_tokens'] if r['status']=='settled' else r['token_hold'] for r in rows)
            if used+hold>5000000 or len(rows)>=512:raise PreDispatchBudgetStopped('shared_team_limit_before_dispatch')
            if db.execute('SELECT 1 FROM requests WHERE request_id=?',(request_id,)).fetchone():raise ValueError('Physical identity reused')
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (request_id,job_id,purpose,step,attempt,'reserved',digest(payload),prompt*2000+cap*8000,None,None,None,None,time.time(),None))
            db.execute('INSERT INTO context_requests_v192 VALUES(?,?,?,?)',(request_id,step,prompt,hold))

    def physical(self,slot):
        if slot not in self.rows:raise ValueError('Foreign usage query')
        with self.transaction() as db:
            rows=[dict(r) for r in db.execute('SELECT r.*,d.logical_id,d.prompt_upper,d.token_hold FROM requests r JOIN context_requests_v192 d USING(request_id) WHERE job_id=? ORDER BY started',(slot,))]
        known=[];unknown=[]
        for r in rows:
            if r['status']=='settled':
                u=json.loads(r['usage']);known.append({'call_id':r['request_id'],'logical_id':r['logical_id'],
                    'purpose':r['purpose'],'prompt_tokens':u['input_tokens'],'completion_tokens':u['output_tokens'],
                    'response':json.loads(r['response_ref']),'cost_upper_CNY':r['cost']/1e9})
            else:unknown.append({'call_id':r['request_id'],'logical_id':r['logical_id'],'purpose':r['purpose'],
                'status':r['status'],'reserved_tokens':r['token_hold'],'cost_upper_CNY':r['reserved']/1e9})
        return {'calls':known,'unresolved_calls':unknown,'usage_capture_complete':not unknown,
            'known_actual_tokens':sum(r['prompt_tokens']+r['completion_tokens'] for r in known),
            'uncertain_reserved_tokens':sum(r['reserved_tokens'] for r in unknown),
            'actual_cost_upper_CNY':sum(r['cost_upper_CNY'] for r in known),
            'reserved_cost_upper_CNY':sum(r['cost_upper_CNY'] for r in unknown)}


class Route:
    port=18219
    timeout_seconds=1800
    def __init__(self,owner,row,output):
        self.owner,self.row,self.slot_id=owner,row,row['slot_id'];self.cancelled=threading.Event()
        self.folder=Path(output)/'physical-api-v192';self.folder.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()

    def validate_identity(self,slot):
        if slot!=self.slot_id:raise ValueError('API route identity changed')

    def abort(self):self.cancelled.set()

    def post(self,path,payload):
        if path not in {'/tokenize','/tokenize-prefix','/chat/completions'}:raise ValueError('No search or remote execution route')
        if payload.get('team_slot_id')!=self.slot_id or payload.get('member_id')!='member_001':raise ValueError('Foreign private session')
        wire=payload['wire'];purpose=payload.get('usage_id','agent')
        if wire.get('user_id')!=slot_user_id(self.slot_id+':member_001',self.row['condition_id']):raise ValueError('Cache/session identity changed')
        expected=self.owner.schemas[self.row['group_id']]['member_001']
        names={r['function']['name'] for r in expected}
        if path!='/tokenize-prefix':validate_payload(wire,names)
        if wire.get('tools') and wire['tools']!=expected:raise ValueError('Frozen S1 tools changed')
        with self.lock:
            if self.cancelled.is_set():raise PreDispatchBudgetStopped('owned_episode_stopped_before_dispatch')
            if path=='/tokenize':return self.owner.counter(wire)
            if path=='/tokenize-prefix':
                pending=tuple(payload['pending_ids'])
                if pending!=pending_tail_tool_ids(wire['messages']):raise ValueError('Incomplete SDK tail identity changed')
                amount=count_incomplete_prefix(SimpleNamespace(counter=self.owner.counter,folder=self.folder),wire,pending)
                return {'prompt_tokens':amount,'request_sha256':byte_digest(json_bytes(wire)),
                    'method':'official_recipe_incomplete_prefix','count_only_not_dispatchable':True}
            scope.require_allowed('v192.api.request',slot_id=self.slot_id)
            if payload.get('condition')!=self.row['condition_id'] or payload.get('slot_id')!=self.slot_id:
                raise ValueError('Generation condition changed')
            if (purpose=='agent' and wire.get('tools')!=expected) or (purpose=='condenser' and wire.get('tools')):
                raise ValueError('Agent/summary tool permission changed')
            logical=payload['request_id']
            if not logical.startswith(self.slot_id+':member_001:'):raise ValueError('Foreign logical request')
            try:body,rid=self.owner.api.call(self.slot_id,wire,purpose=purpose,step=logical,folder=self.folder)
            except PreDispatchBudgetStopped:raise
            except Exception as error:
                # Return a finite IPC error so a failed request cannot strand
                # its controller waiting on a broker that already exited.
                raise APIUncertainFailure(type(error).__name__+': '+str(error)) from error
            return body


class Runtime:
    def __init__(self,plan):
        from .software_role_baseline_runtime_v192 import prepare_schema_inventory
        token=reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')
        self.counter=OfficialDeepSeekCounter(token['path'],manifest_sha256=token['sha256'],reservation_margin_tokens=128)
        self.plan=plan;self.schemas=prepare_schema_inventory()['schemas']
        self.ledger=TaskLedger(plan=plan,counter=self.counter)
        self.api=ReplayAPI(self.ledger,counter=self.counter,api_key=load_api_key(scope.ROOT/'.env'),concurrency=4)
        self.claimed=set();self.lock=threading.Lock()

    def transport_factory(self,row,output):
        with self.lock:
            if row['slot_id'] in self.claimed or self.ledger.physical(row['slot_id'])['calls']:raise ValueError('Model episode cannot be resampled')
            self.claimed.add(row['slot_id'])
        return Route(self,row,output)

    def resident(self,row):
        value={'model_key':'DEEPSEEK','model':'deepseek-flash','thinking':False,'trained_adapter_loaded':False,
            'context_limit':131072,'max_output_tokens':32768,'service_admission_complete':True,
            'host_listener':False,'model_revision':'provider_alias_not_weight_pinnable','version':VERSION}
        with self.lock:ref=scope.retain(scope.API_ROOT/'identity.json',value)
        return {'model_key':'DEEPSEEK','endpoint':ENDPOINT,'api_key_file':None,'identity':ref,
            'identity_value':value,'directory':str(scope.API_ROOT),'logical_only_no_listener':True}
