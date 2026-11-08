"""New runtime routing over the unchanged v157500-CNY physical account.

Only original teams which never dispatched HTTP can acquire a new transport.
Already called teams remain read-only; saved responses/candidates are handled
by independent recovery, never by silently sampling them again.
"""
from __future__ import annotations
from pathlib import Path
import sqlite3
import threading

from . import software_benchmark_host_api_v157 as original
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from .software_benchmark_wave2_account_v168 import audit,validate_recovery_plan

VERSION='v168-original-second-wave-same500-host-r1'
GROUP_IDS=original.GROUP_IDS
ENDPOINT=original.ENDPOINT
api_for=original.api_for
usage_for_slot=original.usage_for_slot
budget_status=original.budget_status


def _scope():
    from . import software_benchmark_scope_v168
    return software_benchmark_scope_v168


class HostTeamTransport(original.HostTeamTransport):
    def post(self,path,payload):
        value=super().post(path,payload)
        if path!='/team-budget':return value
        from .software_communication_finish_v159 import retry_evidence
        if value['uncertain_reserved_tokens']:
            with original.ledger_read(self.group) as db:
                rows=[dict(row) for row in db.execute('SELECT * FROM requests WHERE slot_id=?',(self.slot_id,))]
        else:rows=[]
        return retry_evidence(value,rows)


class DeepSeekRuntime(original.DeepSeekRuntime):
    @staticmethod
    def authorize(operation,**identity):
        if operation!='v157.api.request':
            raise PermissionError('Unexpected physical transport dispatch operation')
        return _scope().require_allowed('v168.api.request',**identity)

    def initialize_for_run(self):
        scope=_scope();scope.require_allowed('v168.api.request')
        plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
        original_scope,schemas_path,_=original._paths()
        source_plan=scope.load(reference(original_scope.PLAN_FILE))
        if plan.get('original_plan')!=reference(original_scope.PLAN_FILE):
            raise ValueError('The continuation must name the original immutable72-team plan')
        snapshot=audit(original_scope.LEDGER_FILE,source_plan)
        coexistence=scope.coexistence_status()
        if coexistence.get('passed') is not True:
            raise PermissionError('The bounded old/new resource coexistence is not proven')
        validate_recovery_plan(plan,source_plan,snapshot,coexistence=coexistence)
        snapshot['controlled_coexistence']=coexistence
        if Path(scope.LEDGER_FILE).resolve()!=Path(original_scope.LEDGER_FILE).resolve():
            raise ValueError('No replacement500-CNY ledger may be created')
        self.rows={row['slot_id']:row for row in plan['rows']}
        self.admitted_original_slots=frozenset(plan['admitted_original_slots'])
        self.used_original_slots=frozenset(plan['used_original_slots'])
        self.schema_ref=reference(schemas_path)
        self.schemas=scope.load(self.schema_ref)['schemas']
        token_ref=reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')
        self.counter=OfficialDeepSeekCounter(token_ref['path'],manifest_sha256=token_ref['sha256'],reservation_margin_tokens=128)
        self.apis={group:original.api_for(group) for group in GROUP_IDS}
        self.max_physical_concurrency=self.apis['C0'].POLICY['max_concurrency']
        runtime=original.runtime_for(apis=self.apis,schemas=self.schemas,counter=self.counter,
            authorize=self.authorize,api_key=self.apis['C0'].load_api_key(scope.ROOT/'.env'),
            max_concurrency=self.max_physical_concurrency)
        self.clients,self.http_slots=runtime.clients,runtime.http_slots
        self._route_claimed=set()
        scope.retain(scope.API_ROOT/'original-ledger-admission.json',snapshot)
        return self

    def for_group(self,group):
        if group not in GROUP_IDS:raise ValueError('Unknown communication condition')
        return GroupView(self,group)

    def transport_factory(self,row,output):
        slot=row['slot_id']
        if (self.rows.get(slot)!=row or slot not in self.admitted_original_slots
                or slot in self.used_original_slots):
            raise ValueError('An already called original team cannot obtain a recovery transport')
        with self.lock:
            if slot in self._route_claimed:
                raise ValueError('A recovery team cannot acquire a second model transport')
            with original.ledger_read(row['group_id']) as db:
                count=db.execute('SELECT COUNT(*) FROM requests WHERE slot_id=?',(slot,)).fetchone()[0]
            if count:
                raise ValueError('This original team has already dispatched; no model replay permitted')
            route=HostTeamTransport(self,row,output)
            self._route_claimed.add(slot);self.transports.append(route)
        return route


class GroupView(original.GroupView):
    def logical_resident(self):
        scope=_scope();api=original.api_for(self.group)
        identity={'version':VERSION,'model_key':'DEEPSEEK','model':api.MODEL,
            'model_revision':api.DOCUMENTED_MODEL_VERSION,'documented_model_version':api.DOCUMENTED_MODEL_VERSION,
            'provider_weight_revision_pinnable':False,'project_training_adapter_loaded':False,
            'context_limit':131072,'max_output_tokens':32768,'thinking':False,'service_admission_complete':True,
            'port':18219,'endpoint':ENDPOINT,'host_listener':False,'deployment_version':VERSION,
            'organization_id':'REVIEW2','group_id':self.group,'tool_schema_inventory':self.runtime.schema_ref,
            'ledger_path':api.POLICY['child_ledger_path'],'cash_authority':api.POLICY['cash_authority'],
            'cash_cap_CNY':'500.00','cash_cap_scope':'unchanged_original_v157_total',
            'additional_cash_allowance_CNY':'0.00','new_neutral_calls':0,
            'source_attribution':'estimated_fragments_provider_actual_usage_authoritative',
            'provider_health_qualification':'first_formally_scheduled_valid_response',
            'used_original_team_resampling':False}
        path=scope.API_ROOT/'api-runtime'/self.group/'identity.json';ref=scope.retain(path,identity)
        return {'model_key':'DEEPSEEK','endpoint':ENDPOINT,'api_key_file':None,'identity':ref,
            'identity_value':identity,'directory':str(path.parent),'logical_only_no_listener':True}
