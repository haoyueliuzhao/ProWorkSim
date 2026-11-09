"""Host binding for13 unfinished teams and the explicit cash start policy."""
from __future__ import annotations

from decimal import Decimal
import sqlite3
import time

from . import software_benchmark_host_api_v157 as original
from . import software_benchmark_completion_api_v170 as amendment
from .software_benchmark_host_api_v159 import HostTeamTransport
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter

VERSION = amendment.VERSION
GROUP_IDS = original.GROUP_IDS
ENDPOINT = original.ENDPOINT
usage_for_slot = original.usage_for_slot


def _scope():
    from . import software_benchmark_scope_v170
    return software_benchmark_scope_v170


def budget_status(group):
    with original.ledger_read(group) as db:
        try:
            paid, held, starts, inflight = amendment.totals(db)
        except sqlite3.OperationalError:
            return {'state':'qualification_pending','can_start_generation':False,
                'temporary_wait':True,'reason':'cash_amendment_not_registered','cap_CNY':'550.00'}
        halt=db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()
        points=[r[0] for r in db.execute('SELECT observed FROM breaker_events WHERE observed>? ORDER BY observed',(time.time()-60,))]
        count=db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
    remaining=amendment.THRESHOLD-paid-held-starts
    pause=max(0,points[-1]+30-time.time()) if len(points)>=3 else 0
    state=('shared_halted' if halt else 'cash_exhausted' if remaining<amendment.START_HOLD else
           'waiting_concurrency' if inflight>=16 else 'waiting_cooldown' if pause else 'ready')
    yuan=lambda n:str(Decimal(n)/10**9)
    return {'version':VERSION,'group_id':group,'state':state,'can_start_generation':state=='ready',
        'temporary_wait':state.startswith('waiting_'),'reason':halt[0] if halt else None,
        'cap_CNY':'550.00','cash_cap_mode':'new_team_start_only','started_teams_continue':True,
        'remaining_CNY':yuan(remaining),'settled_upper_CNY':yuan(paid),
        'reserved_or_unknown_CNY':yuan(held),'initial_team_start_holds_CNY':yuan(starts),
        'committed_upper_CNY':yuan(paid+held),'over_start_threshold_CNY':yuan(max(0,paid+held-amendment.THRESHOLD)),
        'inflight_count':inflight,'attempts':count,'admission_wait_seconds':pause,
        'ledger_path':str(_scope().LEDGER_FILE),'provider_invoice_claimed':False}


class DeepSeekRuntime(original.DeepSeekRuntime):
    @staticmethod
    def authorize(operation, **identity):
        if operation != 'v157.api.request':
            raise PermissionError('Unexpected physical provider operation')
        return _scope().require_allowed('v170.api.request', **identity)

    def initialize_for_run(self):
        scope=_scope(); scope.require_allowed('v170.api.request')
        if not scope.predecessor_quiescence_status()['passed']:
            raise PermissionError('Prior generation and grading resources must be cleaned')
        plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
        self.rows={r['slot_id']:r for r in plan['rows']}
        self.authority_ref=reference(scope.RECOVERY_AUTHORITY_FILE)
        apis={g:original.api_for(g) for g in GROUP_IDS}
        authority,entries=amendment.validate_authority(apis['C0'],self.authority_ref)
        if {r['recovery_slot_id'] for r in entries}!=set(self.rows):
            raise ValueError('The host plan differs from the13 authorized completion identities')
        registration=amendment.register(apis['C0'],self.authority_ref)
        self.apis={g:amendment.completion_api(g,a,self.authority_ref) for g,a in apis.items()}
        _,schema_path,_=original._paths()
        self.schema_ref=reference(schema_path); self.schemas=scope.load(self.schema_ref)['schemas']
        token_ref=reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')
        self.counter=OfficialDeepSeekCounter(token_ref['path'],manifest_sha256=token_ref['sha256'],reservation_margin_tokens=128)
        self.max_physical_concurrency=self.apis['C0'].POLICY['max_concurrency']
        runtime=original.runtime_for(apis=self.apis,schemas=self.schemas,counter=self.counter,
            authorize=self.authorize,api_key=self.apis['C0'].load_api_key(scope.ROOT/'.env'),
            max_concurrency=self.max_physical_concurrency)
        self.clients,self.http_slots=runtime.clients,runtime.http_slots; self._route_claimed=set()
        scope.retain(scope.API_ROOT/'cash-and-recovery-registration.json',registration)
        return self

    def for_group(self,group):
        if group not in GROUP_IDS: raise ValueError('Unknown condition')
        return GroupView(self,group)

    def admit_team(self,row):
        if self.rows.get(row['slot_id'])!=row: raise ValueError('Foreign team admission')
        try:
            return self.clients[row['group_id']].ledger.admit_team(row['slot_id'])
        except amendment.base.PreDispatchBudgetStopped as error:
            from .software_benchmark_group_admission_v157 import AdmissionDeferred
            raise AdmissionDeferred(str(error)) from error

    def release_unentered(self,row):
        return self.clients[row['group_id']].ledger.release_unentered(row['slot_id'])

    def transport_factory(self,row,output):
        slot=row['slot_id']
        if self.rows.get(slot)!=row: raise ValueError('Foreign completion team')
        with self.lock:
            if slot in self._route_claimed: raise ValueError('A team cannot acquire two model transports')
            with original.ledger_read(row['group_id']) as db:
                if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1',(slot,)).fetchone():
                    raise ValueError('An already called completion identity cannot replay')
                grant=db.execute('SELECT state FROM team_start_grants_v170 WHERE slot_id=?',(slot,)).fetchone()
                if grant is None or grant['state']!='started': raise ValueError('No real scheduler start grant')
            route=HostTeamTransport(self,row,output)
            self._route_claimed.add(slot);self.transports.append(route)
            return route


class GroupView(original.GroupView):
    def budget_status(self):
        return budget_status(self.group)

    def logical_resident(self):
        scope=_scope();api=self.runtime.apis[self.group]
        identity={'version':VERSION,'model_key':'DEEPSEEK','model':api.MODEL,
            'model_revision':api.DOCUMENTED_MODEL_VERSION,'documented_model_version':api.DOCUMENTED_MODEL_VERSION,
            'provider_weight_revision_pinnable':False,'project_training_adapter_loaded':False,
            'context_limit':131072,'max_output_tokens':32768,'thinking':False,'service_admission_complete':True,
            'port':18219,'endpoint':ENDPOINT,'host_listener':False,'deployment_version':VERSION,
            'organization_id':'REVIEW2','group_id':self.group,'tool_schema_inventory':self.runtime.schema_ref,
            'ledger_path':str(scope.LEDGER_FILE),'cash_authority':self.runtime.authority_ref,
            'cash_cap_CNY':'550.00','cash_cap_scope':'new_team_start_only','started_teams_finish_above_threshold':True,
            'additional_nominal_CNY':'50.00','new_neutral_calls':0,
            'source_attribution':'estimated_fragments_provider_actual_usage_authoritative',
            'provider_health_qualification':'first_formally_scheduled_valid_response',
            'independent_completion_attempt':True,'maximum_recoveries_per_original':1}
        path=scope.API_ROOT/'api-runtime'/self.group/'identity.json';ref=scope.retain(path,identity)
        return {'model_key':'DEEPSEEK','endpoint':ENDPOINT,'api_key_file':None,'identity':ref,
            'identity_value':identity,'directory':str(path.parent),'logical_only_no_listener':True}
