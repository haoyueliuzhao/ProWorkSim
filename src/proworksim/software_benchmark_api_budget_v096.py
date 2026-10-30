"""Same CNY1700 ledger, exact unused original IDs, and all prior recovery costs."""
from __future__ import annotations

from pathlib import Path

from . import software_benchmark_deepseek_budget_v089 as amended
from . import software_benchmark_api_scope_v096 as scope
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_deepseek_runtime_v069 import private_function

VERSION = 'v096-original-79-API-ledger-registry-r1'
LEDGER, API_VIEW, RuntimeView = amended.LEDGER, amended.API_VIEW, amended.RuntimeView
wire = amended.wire


def financial_recovery_rows():
    rows = scope.load(reference(scope.FINANCIAL_RECOVERY_INVENTORY))['rows']
    amended.validate_retry_registry(rows)
    return rows


def budget_status():
    # Original 6000 rows are always included by v089. Keep its 44 recovery IDs
    # too: a new original-ID phase may not erase their uncertain reservations.
    return amended.budget_status(retry_rows=financial_recovery_rows())


def build_runtime(*, scope_guard, identity_file, rows=None):
    rows = scope.canonical_rows() if rows is None else rows
    registry = scope.validate_registry(rows)
    identity_file = Path(identity_file)

    class Runtime(wire.DeepSeekRuntime):
        def _require_allowed(self, *, slot_id=None, instance_id=None):
            return scope_guard('v096.api.request', slot_id=slot_id, instance_id=instance_id)

        def read_only_preflight(self):
            amended.require_amendment()
            status = self.budget_status()
            if status['state'] != 'ready':
                raise wire.APIUnavailable(status)
            inventory = scope.load(reference(scope.CANONICAL_INVENTORY_FILE))
            if scope.validate_registry(inventory['rows']) != registry:
                raise ValueError('Runtime original-ID registry differs from sealed inventory')
            self.qualified = wire.policy.load(reference(wire.QUALIFICATION))
            if (self.qualified.get('passed') is not True or self.qualified.get('model_calls') != 2
                    or self.qualified.get('unknown_usage_calls') != 0):
                raise wire.APIQualificationPending('Original neutral qualification is not intact')
            preparation = wire.policy.load(self.qualified['plan'])
            if (Path(self.qualified['plan']['path']).resolve() != wire.QUALIFICATION.parent/'plan.json'
                    or preparation.get('ledger') != str(LEDGER)
                    or self.qualified.get('cash_snapshot',{}).get('ledger_path') != str(LEDGER)):
                raise ValueError('Original neutral calls and current runtime must share one ledger')
            for source in preparation['sources']:
                checked(source)
            self.preparation_usage_validation = wire.validate_existing_preparation_usage(
                amended.preparation_usage(),self.qualified)
            self.schemas = wire.policy.load(wire.prepare_schema_inventory())
            self.zero_API_admission = scope.zero_request_snapshot(list(registry.values()))
            self.rows, self.inventory = dict(registry), inventory
            return {'preparation':preparation,
                'allowed_tool_names':set(self.schemas['tool_names']['REF'])|set(self.schemas['tool_names']['PROJECT']),
                'eligible_API_slots':79,'neutral_usage':self.preparation_usage_validation}

        initialize_for_run = private_function(wire.DeepSeekRuntime.initialize_for_run,api=API_VIEW)

        def logical_resident(self):
            if self.client is None or self.counter is None or self.qualified is None:
                raise wire.APIQualificationPending('Initialize the original-ID API client explicitly')
            identity = {'version':VERSION,'model_key':'DEEPSEEK','model':API_VIEW.MODEL,
                'model_revision':API_VIEW.DOCUMENTED_MODEL_VERSION,
                'documented_model_version':API_VIEW.DOCUMENTED_MODEL_VERSION,
                'provider_weight_revision_pinnable':False,'project_training_adapter_loaded':False,
                'context_limit':API_VIEW.CONTEXT_TOKENS,'max_output_tokens':API_VIEW.MAX_OUTPUT_TOKENS,
                'thinking':True,'service_admission_complete':True,'port':18219,
                'endpoint':wire.ENDPOINT,'host_listener':False,'deployment_version':VERSION,
                'qualification':reference(wire.QUALIFICATION),'tool_schema_inventory':reference(wire.SCHEMA_FILE),
                'continuation_inventory':reference(scope.CANONICAL_INVENTORY_FILE),
                'ledger_path':str(LEDGER),'cash_cap_CNY':'1700.00','new_neutral_calls':0,
                'explicit_budget_amendment':reference(amended.AMENDMENT_COMPLETED),
                'original_first_model_attempt':True,'model_resampling':False,
                'prior_44_recovery_ids_and_costs_retained':True}
            identity_ref = wire.policy.retain(identity_file,identity)
            return {'model_key':'DEEPSEEK','endpoint':wire.ENDPOINT,'api_key_file':None,
                'identity':identity_ref,'identity_value':identity,'directory':str(identity_file.parent),
                'logical_only_no_listener':True}

        def transport_factory(self,row,output):
            if registry.get(row.get('slot_id')) != row:
                raise PermissionError('Only the exact unused original model row may obtain a broker')
            # Existing full row/config/index equality and single-request-ID
            # anti-replay remain inside the original transport implementation.
            return private_function(wire.DeepSeekRuntime.transport_factory,
                _ledger_read=amended.ledger_read,budget_status=self.budget_status,api=API_VIEW)(self,row,output)

        def budget_status(self):
            return budget_status()

        def usage_for_slot(self,row):
            if registry.get(row.get('slot_id')) != row:
                raise PermissionError('Usage is limited to a sealed original-ID row')
            return amended.usage_for_slot(row,retry_rows=financial_recovery_rows())

        def preparation_usage(self):
            return amended.preparation_usage()

    return Runtime(scope_guard=scope_guard)
