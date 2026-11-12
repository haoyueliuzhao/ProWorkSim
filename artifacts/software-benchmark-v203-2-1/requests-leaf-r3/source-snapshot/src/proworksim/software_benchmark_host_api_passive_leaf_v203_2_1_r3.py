"""Direct passive-pilot host: REVIEW2 teams share one150-CNY actual ledger.

Only explicit initialization loads a key. Token counting and construction are
CPU operations. Per-team forks capture every physical HTTP attempt, including
bounded transient retries; observation failures never replay a paid response.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from decimal import Decimal
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace

from . import software_benchmark_deepseek_api_v203_2_1 as implementation
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_deepseek_prefix_v055_r2 import pending_tail_tool_ids, count_incomplete_prefix
from .software_benchmark_host_api_v156 import instrument_client
from .software_benchmark_usage_metrics_v064 import normalize_usage_call
from .storage import digest, json_bytes

VERSION = 'v203.2.1-original-Requests-first-model-host-r3'
GROUP_IDS = implementation.GROUP_IDS
ENDPOINT = 'http://127.0.0.1:18219'
MAX_PROFILE_RESERVATION_NANOYUAN = 98304*2000+32768*8000


def _scope():
    from . import software_benchmark_scope_passive_leaf_v203_2_1_r3
    return software_benchmark_scope_passive_leaf_v203_2_1_r3


def _paths():
    scope = _scope()
    return scope, scope.API_ROOT/'api-runtime/member-tool-schemas-r1.json', scope.BUDGET_BASELINE_FILE


# Reuse the exact original cash policy and logical12-team identities. Other logical teams may already have paid requests; only this original
# Requests task must remain uncalled and unadmitted before leaf dispatch.
from . import software_benchmark_host_api_v203_2_1 as initial_host
api_for = initial_host.api_for
initialize_authority = initial_host.initialize_authority
initialize_ledger = initial_host.initialize_ledger


def prepare_schemas(inventory_path=None):
    scope, path, _ = _paths()
    if inventory_path is None:
        from .software_role_baseline_runtime_v203_2_1 import prepare_schema_inventory
        inventory = prepare_schema_inventory()
        inventory_ref = scope.retain(scope.API_ROOT/'api-runtime/actual-member-schema-inventory.json', inventory)
    else:
        inventory_ref = reference(inventory_path)
        inventory = scope.load(inventory_ref)
    schemas = {'REVIEW2':inventory['schemas']['REVIEW2']}
    if set(schemas) != set(GROUP_IDS):
        raise ValueError('Actual schemas must retain all three communication conditions')
    for members in schemas.values():
        if set(members) != {'member_001', 'member_002'}:
            raise ValueError('The compressor does not create a third member')
        for tools in members.values():
            names = [t.get('function', {}).get('name') for t in tools]
            if not names or None in names or len(names) != len(set(names)) or set(names)&{'terminal','web_search','browser','fetch'}:
                raise ValueError('Only the real managed member tools are allowed')
    if any(schemas[group] != schemas['REVIEW2'] for group in GROUP_IDS):
        raise ValueError('All communication conditions require identical member tool capabilities')
    return scope.retain(path, {'version': VERSION, 'actual_member_inventory': inventory_ref,
        'schemas': schemas, 'neutral_calls': 0, 'provider_search_or_fetch': False,
        'host_listener': False, 'organization_id': 'REVIEW2'})


prepare_runtime_schemas = prepare_schemas


@contextmanager
def ledger_read(group):
    api = api_for(group)
    path = Path(api.POLICY['child_ledger_path'])
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        row = db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()
        if row is None or row[0] != implementation.canonical(api.POLICY):
            raise ValueError('The independent communication ledger policy changed')
        yield db
    finally:
        db.close()


def budget_status(group):
    scope = _scope()
    api = api_for(group)
    if not Path(scope.LEDGER_FILE).exists():
        return {'group_id': group, 'state': 'qualification_pending', 'can_start_generation': False,
                'temporary_wait': True, 'cap_CNY': '150.00'}
    with ledger_read(group) as db:
        rows = list(db.execute('SELECT status,reserved_nanoyuan,settled_nanoyuan FROM requests'))
        halt = db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
        points = [r[0] for r in db.execute('SELECT observed FROM breaker_events WHERE observed>? ORDER BY observed', (time.time()-60,))]
    settled = sum(r['settled_nanoyuan'] for r in rows if r['status']=='settled')
    reserved = sum(r['reserved_nanoyuan'] for r in rows if r['status']=='reserved')
    unknown = sum(r['reserved_nanoyuan'] for r in rows if r['status'] not in {'reserved','settled'})
    inflight = sum(r['status']=='reserved' for r in rows)
    admission=api.BudgetLedger().cash_admission()
    remaining=admission['available_for_new_teams_nanoyuan']
    pause=max(0,points[-1]+30-time.time()) if len(points)>=3 else 0
    state=('shared_halted' if halt else 'waiting_team_cash' if not admission['can_start'] and admission['active_team_count'] else
           'cash_exhausted' if not admission['can_start'] else 'waiting_concurrency' if inflight>=scope.MAX_HTTP_CONCURRENCY else
           'waiting_cooldown' if pause else 'ready')
    yuan = lambda n: str(Decimal(n)/10**9)
    return {'version': VERSION, 'group_id': group, 'state': state, 'can_start_generation': state=='ready',
        'temporary_wait': state.startswith('waiting_'), 'reason': halt[0] if halt else None,
        'cash_scope': 'one_new150_passive_account', 'cap_CNY': '150.00',
        'remaining_CNY': yuan(remaining), 'settled_upper_CNY': yuan(settled),
        'uncertain_reserved_CNY': yuan(unknown), 'committed_upper_CNY': yuan(settled+reserved+unknown),
        'inflight_count': inflight, 'attempts': len(rows), 'admission_wait_seconds': pause,
        'new_team_admission_reservation_CNY': '40.00', 'remaining_team_holds_CNY':yuan(admission['remaining_team_holds_nanoyuan']),
        'existing_team_requests_use_actual_request_reservation': True, 'started_teams_not_cash_interrupted':True, 'ledger_path': str(scope.LEDGER_FILE)}


def usage_for_slot(row):
    group = row.get('group_id', row.get('condition'))
    with ledger_read(group) as db:
        records = [dict(r) for r in db.execute('SELECT * FROM requests WHERE slot_id=? ORDER BY reserved_utc,request_id', (row['slot_id'],))]
    calls, unknown = [], []
    for record in records:
        if record['condition'] != row.get('condition_id',row.get('condition')) or record['member_id'] not in row['fixed_members']:
            raise ValueError('Physical usage lost the original condition/member identity')
        if record['status']=='settled':
            value = normalize_usage_call(record['request_id'], record['usage_id'], json.loads(record['usage_json']),
                accounted_cost_cny=str(Decimal(record['settled_nanoyuan'])/10**9))
            calls.append({**value, 'member_id': record['member_id'], 'organization_id':'REVIEW2', 'group_id':group})
        else:
            unknown.append({'call_id':record['request_id'], 'member_id':record['member_id'], 'purpose':record['usage_id'],
                'reserved_tokens':record['reserved_tokens'], 'reserved_cost_cny':str(Decimal(record['reserved_nanoyuan'])/10**9),
                'reservation_is_actual_usage':False, 'status':record['status']})
    return {'calls':calls, 'unresolved_calls':unknown, 'usage_capture_complete':not unknown,
        'usage_source':'v157_shared_physical_sqlite', 'team_pool_not_per_member':True}


class HostTeamTransport:
    port, timeout_seconds = 18219, 1800

    def __init__(self, runtime, row, output):
        self.runtime, self.row = runtime, copy.deepcopy(row)
        self.slot_id = row['slot_id']
        self.condition_id = row.get('condition_id', row.get('condition'))
        self.group = row.get('group_id', row.get('condition'))
        self.client = runtime.clients[self.group].fork_for_episode()
        self.folder = Path(output)/'host-api-counts'
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock, self.cancelled = threading.RLock(), threading.Event()
        from .software_observer_journal_v203_2_1 import ObserverJournal
        import base64, hashlib
        self.physical_journal_path=Path(output)/'physical-observer/events.sqlite'
        def capture(kind,raw,context,metadata):
            stamp=time.time()
            # The FIFO model thread differs from the generation owner thread.
            # Open and close on the actual capture thread; never share sqlite
            # connections across them or retain an unbounded in-memory queue.
            with ObserverJournal(self.physical_journal_path) as journal:
                journal.append(kind,kind+':'+str(context['physical_id']),
                    {'raw_base64':base64.b64encode(raw).decode(),'raw_sha256':hashlib.sha256(raw).hexdigest(),
                     'raw_bytes':len(raw),'context':context,'metadata':metadata,'observed_at':stamp},
                    {'capture_boundary':'actual_HTTP_body_bytes','episode_id':self.slot_id})
        self.client.transport.physical_capture=capture
        if self.client.http_slots is not runtime.http_slots:
            raise ValueError('All teams must share actual HTTP permits')

    def validate_identity(self, slot_id):
        if slot_id != self.slot_id:
            raise ValueError('A broker cannot leave its fixed team')

    def abort(self):
        self.cancelled.set()
        self.client.transport.abort()

    def post(self, path, payload):
        api = self.runtime.apis[self.group]
        if path == '/team-budget':
            if payload != {'team_slot_id':self.slot_id}:
                raise ValueError('Budget reads are bound to the same original team')
            return self.client.ledger.team_snapshot(self.slot_id)
        if path not in {'/tokenize','/tokenize-prefix','/chat/completions'}:
            raise ValueError('No search, fetch, URL, or provider tool route')
        member = payload.get('member_id')
        if payload.get('team_slot_id') != self.slot_id or member not in self.row['fixed_members']:
            raise ValueError('Every request needs its original member and team identity')
        wire = payload['wire']
        purpose = payload.get('usage_id','compressor' if path=='/compressor-tokenize' else 'agent')
        if wire.get('user_id') != api.slot_user_id(self.slot_id+':'+member,self.condition_id):
            raise ValueError('Member/condition cache identity changed')
        api.validate_payload(wire,self.client.allowed_tool_names,purpose)
        expected = {t['function']['name']:t for t in self.runtime.schemas[self.group][member]}
        supplied = {t['function']['name']:t for t in wire.get('tools',[])}
        if supplied and supplied != expected:
            raise ValueError('The actual frozen member tools changed')
        common={'wire','member_id','team_slot_id'}
        with self._lock:
            if self.cancelled.is_set():
                raise api.PreDispatchBudgetStopped('owned_team_stopped_before_dispatch')
            if path in {'/tokenize','/compressor-tokenize'}:
                if set(payload)!=common:
                    raise ValueError('Unexpected count request extension')
                return self.runtime.counter(wire)
            if path=='/tokenize-prefix':
                if set(payload)!=common|{'pending_ids'}:
                    raise ValueError('Unexpected member prefix extension')
                pending=tuple(payload['pending_ids'])
                if not pending or pending_tail_tool_ids(wire['messages'])!=pending:
                    raise ValueError('Only the actual pending SDK tail is countable')
                (self.folder/member).mkdir(parents=True,exist_ok=True)
                value=count_incomplete_prefix(SimpleNamespace(counter=self.runtime.counter,folder=self.folder/member),wire,pending)
                return {'prompt_tokens':value,'request_sha256':digest(json_bytes(wire)),
                    'method':'official_original_member_incomplete_prefix','count_only_not_dispatchable':True,
                    'exact_provider_token_ids_available':False}
            wanted=common|{'request_id','slot_id','condition','usage_id','prompt_upper_bound'}
            if (set(payload)!=wanted or payload['slot_id']!=self.slot_id or payload['condition']!=self.condition_id
                    or purpose not in implementation.PURPOSES or purpose=='agent' and supplied!=expected
                    or purpose!='agent' and supplied):
                raise ValueError('Frozen team/member/request purpose or tools changed')
            if self.group=='C0' and purpose=='compressor':
                raise ValueError('C0 has no compression service calls')
            self.runtime.authorize('v203.2.1.api.request',slot_id=self.slot_id,instance_id=self.row['instance_id'])
            measured=self.runtime.counter(wire)
            if measured['request_sha256']!=digest(json_bytes(wire)) or measured['prompt_tokens']!=payload['prompt_upper_bound']:
                raise ValueError('Host/controller exact-wire reservation measurements differ')
            result=self.client.complete(wire,**{k:v for k,v in payload.items() if k not in common},
                member_id=member,cancel_event=self.cancelled)
            # In-memory route qualification cannot introduce a post-paid disk failure/replay.
            with self.runtime.lock:
                self.runtime.successful_routes.setdefault(self.group,set()).add(self.slot_id)
            return result


def runtime_for(*,apis,schemas,counter,authorize,api_key,max_concurrency,capture_root=None):
    if set(apis)!=set(GROUP_IDS) or set(schemas)!=set(GROUP_IDS):
        raise ValueError('The complete REVIEW2 API and schema views are required')
    policies=[api.POLICY for api in apis.values()]
    if any(p!=policies[0] for p in policies[1:]) or any(api.group_id!=g for g,api in apis.items()):
        raise ValueError('One exact authority/ledger/policy must fund distinct condition views')
    runtime=SimpleNamespace(apis=apis,schemas=schemas,counter=counter,authorize=authorize,
        http_slots=threading.BoundedSemaphore(max_concurrency),clients={},
        lock=threading.RLock(),successful_routes={g:set() for g in GROUP_IDS})
    for group,api in apis.items():
        if api.POLICY['max_concurrency']!=max_concurrency:
            raise ValueError('Physical permit and cash concurrency limits differ')
        names={t['function']['name'] for member in schemas[group].values() for t in member}
        runtime.clients[group]=api.DeepSeekClient(api_key=api_key,allowed_tool_names=names,http_slots=runtime.http_slots)
    return runtime


class DeepSeekRuntime:
    def __init__(self):
        self.clients,self.rows,self.schemas,self.apis={},{},{},{}
        self.transports=[]
        self.lock=threading.RLock()
        self.successful_routes={g:set() for g in GROUP_IDS}

    @staticmethod
    def authorize(operation,**identity):
        if operation!='v203.2.1.api.request':
            raise PermissionError('Unexpected underlying API scope operation')
        return _scope().require_allowed(operation,**identity)

    def initialize_for_run(self):
        scope,path,_=_paths()
        scope.require_allowed('v203.2.1.api.request')
        plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
        self.rows={r['slot_id']:r for r in plan['rows']}
        self.schemas=scope.load(reference(path))['schemas']
        token_ref=reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')
        self.counter=OfficialDeepSeekCounter(token_ref['path'],manifest_sha256=token_ref['sha256'],reservation_margin_tokens=128)
        self.apis={g:api_for(g) for g in GROUP_IDS}
        scope.validate_first_model_admission()
        runtime=runtime_for(apis=self.apis,schemas=self.schemas,counter=self.counter,authorize=self.authorize,
            api_key=self.apis['REVIEW2'].load_api_key(scope.ROOT/'.env'),max_concurrency=scope.MAX_HTTP_CONCURRENCY)
        self.clients,self.http_slots=runtime.clients,runtime.http_slots
        return self

    def for_group(self,group):
        if group not in GROUP_IDS:
            raise ValueError('Unknown communication condition')
        return GroupView(self,group)

    def transport_factory(self,row,output):
        if self.rows.get(row['slot_id'])!=row:
            raise ValueError('Only the original sealed team may obtain a transport')
        route=HostTeamTransport(self,row,output)
        with self.lock:
            self.transports.append(route)
        return route

    def cancel_group(self,group):
        with self.lock:
            routes=[r for r in self.transports if r.group==group]
        for route in routes:
            route.abort()

    def cancel_all(self):
        for group in GROUP_IDS:
            self.cancel_group(group)

    usage_for_slot=staticmethod(usage_for_slot)


class GroupView:
    def __init__(self,runtime,group):
        self.runtime,self.group=runtime,group

    def budget_status(self):
        return budget_status(self.group)

    def logical_resident(self):
        scope,path,authority=_paths()
        identity={'version':VERSION,'model_key':'DEEPSEEK','model':implementation.old.MODEL,
            'model_revision':implementation.old.DOCUMENTED_MODEL_VERSION,
            'documented_model_version':implementation.old.DOCUMENTED_MODEL_VERSION,
            'provider_weight_revision_pinnable':False,'project_training_adapter_loaded':False,
            'context_limit':131072,'max_output_tokens':32768,'thinking':False,'service_admission_complete':True,
            'port':18219,'endpoint':ENDPOINT,'host_listener':False,'deployment_version':VERSION,
            'organization_id':'REVIEW2','group_id':self.group,'tool_schema_inventory':reference(path),
            'ledger_path':str(scope.LEDGER_FILE),'cash_cap_CNY':'150.00','cash_cap_scope':'whole_new_pilot',
            'cash_authority':reference(authority),'new_neutral_calls':0,
            'provider_health_qualification':'first_formally_scheduled_valid_response',
            'source_attribution':'estimated_fragments_provider_actual_usage_authoritative'}
        target=scope.API_ROOT/'api-runtime'/self.group/'identity.json'
        ref=scope.retain(target,identity)
        return {'model_key':'DEEPSEEK','endpoint':ENDPOINT,'api_key_file':None,'identity':ref,
            'identity_value':identity,'directory':str(target.parent),'logical_only_no_listener':True}

    def transport_factory(self,row,output):
        if row.get('group_id',row.get('condition'))!=self.group:
            raise ValueError('A condition view cannot dispatch another communication condition')
        return self.runtime.transport_factory(row,output)

    def cancel_all(self):
        return self.runtime.cancel_group(self.group)

    def settled_route_witnesses(self):
        with self.runtime.lock:
            slots=sorted(self.runtime.successful_routes[self.group])
        return {'PROJECT':slots[0]} if slots else {}

    usage_for_slot=staticmethod(usage_for_slot)
    preparation_usage=staticmethod(lambda:{'calls':[],'unresolved_calls':[],
        'usage_capture_complete':True,'new_preparation_API_calls':0})
