"""Freeze the scoped continuation; reuse the one approved50-CNY amendment."""
import importlib.util,json,sqlite3
from proworksim.software_context_budget_runtime_v188 import scope,STATE,REMAINING,VERSION,OLD
from proworksim.software_context_cash_v187 import AUTHORITY,effective_cap
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_alignment_contract_v181 import VERSION as ALIGNMENT


def main():
 if scope.AUTH_FILE.exists():raise ValueError('Never reseal an entered owner')
 remaining=scope.load(reference(REMAINING))
 assert len(remaining['rows'])==10 and all(not r['primary_panel'] for r in remaining['rows'])
 with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:assert effective_cap(db)==300_000_000_000
 budget_log=scope.ROOT/'artifacts/software-benchmark-v187/cpu-controls-r1/pytest-r2.log'
 handoff_log=scope.ROOT/'artifacts/software-benchmark-v188/cpu-controls-r1/pytest.log'
 if '3 passed' not in budget_log.read_text() or '1 passed' not in handoff_log.read_text():
  raise ValueError('Budget and predecessor-ownership controls required')
 proposal=scope.retain(scope.ROOT/'artifacts/software-benchmark-v188/runtime-authorization-r1/proposal.json',{
  'version':VERSION,'user_grant':reference(AUTHORITY),'remaining':reference(REMAINING),
  'original_plan':reference(scope.PLAN_FILE),'same_cumulative_account':str(scope.LEDGER_FILE),
  'original_cash_field_is_historical':250,'effective_cash_cap_CNY':300,'additional_amendment_CNY':0,
  'predecessor':str(OLD),'predecessor_pair_finishes_without_interruption':True,
  'original_unentered_repeats':10,'extra_model_attempts':0,'new_user_unit':scope.API_UNIT,
  'maximum_generation_pairs':4,'maximum_graders':2,
  'temporary_coexistence_cpu_upper':48,'temporary_coexistence_memory_GiB_upper':296,
  'shared_host_changes':0,'original_solver_runtime_unchanged':True,
  'CPU_controls':[reference(budget_log),reference(handoff_log)]})
 spec=importlib.util.spec_from_file_location('seal188',scope.ROOT/'tools/seal_role_pilot_v143.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 files=module.source_closure(roots=[p for folder in ('src/proworksim','tools','tests') for p in (scope.ROOT/folder).glob('*v188.py')])
 files += [reference(scope.PLAN_FILE),reference(REMAINING),reference(AUTHORITY),proposal,
  reference(budget_log),reference(handoff_log),
  reference(scope.API_ROOT/'coordinator-unit.json'),
  reference(scope.ROOT/'docs/experiments/software-benchmark-v188-budget-continuation.md')]
 source=scope.retain(scope.SOURCE_FILE,{'version':VERSION,'files':files,'solver_runtime_changed':False})
 auth=scope.retain(scope.AUTH_FILE,{'version':VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),
  'source_index':source,'execution_alignment_version':ALIGNMENT,'constraints':scope.CONSTRAINTS,
  'cash_cap_CNY':'300.00','cash_amendment':reference(AUTHORITY),'proposal':proposal,
  'historical_plan_cash_field_overridden_by_explicit_user_amendment':True,
  'standing_nondisruptive_Docker_API_authority':True,'shared_host_configuration_changes':0})
 scope.require_allowed()
 print(json.dumps({'sealed':True,'authority':auth,'cash_cap_CNY':300,'remaining':10}))


if __name__=='__main__':main()
