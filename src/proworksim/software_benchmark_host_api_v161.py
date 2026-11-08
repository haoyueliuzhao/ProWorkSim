"""One explicitly authorized technical retry per failed team, same500 account.

The cash policy and original physical requests remain immutable. New identities
are registered only after the predecessor is fully stopped and cleaned, and
each independent identity can obtain a model transport only once.
"""
from __future__ import annotations
from pathlib import Path

from . import software_benchmark_host_api_v157 as original
from . import software_benchmark_recovery_api_v161 as amendment
from .software_benchmark_host_api_v159 import HostTeamTransport
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter

VERSION='v161-independent-technical-attempt-host-same500-r1'
GROUP_IDS=original.GROUP_IDS
ENDPOINT=original.ENDPOINT
usage_for_slot=original.usage_for_slot
budget_status=original.budget_status


def _scope():
    from . import software_benchmark_scope_v161
    return software_benchmark_scope_v161


def checked_authority(plan,authority_ref,apis):
    """Read-only exact plan/identity check; this never registers or calls a model."""
    authority,entries=amendment._validate_authority(apis['C0'],authority_ref)
    expected={entry['recovery_slot_id']:entry for entry in entries}
    rows={row['slot_id']:row for row in plan['rows']}
    if len(rows)!=len(plan['rows']) or set(rows)!=set(expected):
        raise ValueError('The run plan must contain exactly the approved independent attempts')
    declared=plan.get('independent_recovery_original_slots')
    if declared is not None and (len(declared)!=len(expected)
            or set(declared)!={entry['original_slot_id'] for entry in entries}):
        raise ValueError('The run plan lost the original-to-recovery lineage')
    for slot,row in rows.items():
        entry=expected[slot]
        for key in ('instance_id','condition_id','group_id','seed','fixed_members','slot_index','configuration'):
            if row.get(key)!=entry[key]:
                raise ValueError('Recovery plan differs from the authorized unchanged condition: '+key)
        lineage=row.get('original_slot_id',entry['original_slot_id'] if declared is not None else None)
        if lineage!=entry['original_slot_id'] or row.get('organization_id')!='REVIEW2':
            raise ValueError('Recovery lineage/organization must remain explicit')
    if any(api.POLICY!=apis['C0'].POLICY for api in apis.values()):
        raise ValueError('Every communication condition must share the unchanged cash policy')
    return authority,expected


class DeepSeekRuntime(original.DeepSeekRuntime):
    @staticmethod
    def authorize(operation,**identity):
        if operation!='v157.api.request':
            raise PermissionError('Unexpected underlying physical transport operation')
        return _scope().require_allowed('v161.api.request',**identity)

    def initialize_for_run(self):
        scope=_scope();scope.require_allowed('v161.api.request')
        predecessor=scope.predecessor_quiescence_status()
        if any(predecessor.get(key) is not True for key in
                ('passed','v159_all_owned_objects_removed','lease_empty')):
            raise PermissionError('The predecessor must finish and remove all owned resources first')
        plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
        original_scope,schema_path,_=original._paths()
        if Path(scope.LEDGER_FILE).resolve()!=Path(original_scope.LEDGER_FILE).resolve():
            raise ValueError('Technical recovery cannot create another500-CNY account')
        base_apis={group:original.api_for(group) for group in GROUP_IDS}
        self.authority_ref=reference(scope.RECOVERY_AUTHORITY_FILE)
        authority,entries=checked_authority(plan,self.authority_ref,base_apis)
        self.rows={row['slot_id']:row for row in plan['rows']}
        with original.ledger_read('C0') as db:
            if db.execute("SELECT 1 FROM requests WHERE status='reserved' LIMIT 1").fetchone():
                raise PermissionError('The shared provider account still has an inflight request')
            for slot in self.rows:
                if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1',(slot,)).fetchone():
                    raise ValueError('An independent recovery attempt cannot be replayed')
        def authorize_registration(operation,**identity):
            if operation!='v161.register_attempts' or identity!={'authority':self.authority_ref}:
                raise PermissionError('Unexpected technical identity registration scope')
            return scope.require_allowed(operation)
        registration=amendment.register_authorized_attempts(base_apis['C0'],self.authority_ref,authorize_registration)
        self.apis={group:amendment.recovery_api(group,api,self.authority_ref) for group,api in base_apis.items()}
        self.schema_ref=reference(schema_path)
        self.schemas=scope.load(self.schema_ref)['schemas']
        token_ref=reference(scope.ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json')
        self.counter=OfficialDeepSeekCounter(token_ref['path'],manifest_sha256=token_ref['sha256'],reservation_margin_tokens=128)
        self.max_physical_concurrency=self.apis['C0'].POLICY['max_concurrency']
        runtime=original.runtime_for(apis=self.apis,schemas=self.schemas,counter=self.counter,
            authorize=self.authorize,api_key=self.apis['C0'].load_api_key(scope.ROOT/'.env'),
            max_concurrency=self.max_physical_concurrency)
        self.clients,self.http_slots=runtime.clients,runtime.http_slots
        self._route_claimed=set()
        scope.retain(scope.API_ROOT/'independent-attempt-admission.json',{
            'version':VERSION,'predecessor':predecessor,'registration':registration,
            'authority':self.authority_ref,'cash_status':budget_status('C0'),
            'new_attempts':len(entries),'additional_cash_allowance_CNY':'0.00',
            'original500_cash_policy':self.apis['C0'].POLICY})
        return self

    def for_group(self,group):
        if group not in GROUP_IDS:raise ValueError('Unknown communication condition')
        return GroupView(self,group)

    def transport_factory(self,row,output):
        slot=row['slot_id']
        if self.rows.get(slot)!=row:
            raise ValueError('Only the sealed independent recovery row may dispatch')
        with self.lock:
            if slot in self._route_claimed:
                raise ValueError('A technical attempt cannot acquire a second model transport')
            with original.ledger_read(row['group_id']) as db:
                if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1',(slot,)).fetchone():
                    raise ValueError('This technical attempt already dispatched; no replay permitted')
            route=HostTeamTransport(self,row,output)
            self._route_claimed.add(slot);self.transports.append(route)
        return route


class GroupView(original.GroupView):
    def logical_resident(self):
        scope=_scope();api=self.runtime.apis[self.group]
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
            'independent_technical_attempt':True,'maximum_recoveries_per_original':1,
            'recovery_authority':self.runtime.authority_ref,'old_attempts_and_costs_preserved':True}
        path=scope.API_ROOT/'api-runtime'/self.group/'identity.json';ref=scope.retain(path,identity)
        return {'model_key':'DEEPSEEK','endpoint':ENDPOINT,'api_key_file':None,'identity':ref,
            'identity_value':identity,'directory':str(path.parent),'logical_only_no_listener':True}
