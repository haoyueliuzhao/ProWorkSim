"""Seal the same12 unentered repeats under the explicit300-CNY cash amendment."""
import importlib.util,json,sqlite3
from proworksim.software_context_budget_runtime_v187 import scope,STATE,REMAINING,VERSION
from proworksim.software_context_cash_v187 import AUTHORITY,effective_cap
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_benchmark_alignment_contract_v181 import VERSION as ALIGNMENT

def main():
 if scope.AUTH_FILE.exists():raise ValueError('Never reseal an active budget owner')
 remaining=scope.load(reference(REMAINING))
 assert len(remaining['rows'])==12 and all(not r['primary_panel'] for r in remaining['rows'])
 with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:assert effective_cap(db)==300_000_000_000
 log=scope.ROOT/'artifacts/software-benchmark-v187/cpu-controls-r1/pytest-r2.log'
 if '3 passed' not in log.read_text():raise ValueError('Actual budget-boundary controls missing')
 proposal=scope.retain(scope.ROOT/'artifacts/software-benchmark-v187/runtime-authorization-r1/proposal.json',{
  'version':VERSION,'user_grant':reference(AUTHORITY),'remaining':reference(REMAINING),
  'original_plan':reference(scope.PLAN_FILE),'same_cumulative_account':str(scope.LEDGER_FILE),
  'original_cash_field_is_historical':250,'effective_cash_cap_CNY':300,'added_CNY':50,
  'old_episodes_finish_without_interruption':True,'original_unentered_repeats':12,
  'extra_model_attempts':0,'new_user_unit':scope.API_UNIT,'maximum_generation_pairs':4,'maximum_graders':2,
  'temporary_coexistence_cpu_upper':48,'temporary_coexistence_memory_GiB_upper':296,
  'shared_host_changes':0,'original_solver_runtime_unchanged':True,'CPU_controls':reference(log)})
 spec=importlib.util.spec_from_file_location('seal187',scope.ROOT/'tools/seal_role_pilot_v143.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 files=m.source_closure(roots=[p for folder in ('src/proworksim','tools','tests') for p in (scope.ROOT/folder).glob('*v187.py')])
 files += [reference(scope.PLAN_FILE),reference(REMAINING),reference(AUTHORITY),proposal,reference(log),
  reference(scope.ROOT/'docs/experiments/software-benchmark-v187-budget-amendment.md')]
 source=scope.retain(scope.SOURCE_FILE,{'version':VERSION,'files':files,'solver_runtime_changed':False})
 auth=scope.retain(scope.AUTH_FILE,{'version':VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),
  'source_index':source,'execution_alignment_version':ALIGNMENT,'constraints':scope.CONSTRAINTS,
  'cash_cap_CNY':'300.00','cash_amendment':reference(AUTHORITY),'proposal':proposal,
  'historical_plan_cash_field_overridden_by_explicit_user_amendment':True,
  'standing_nondisruptive_Docker_API_authority':True,'shared_host_configuration_changes':0})
 scope.require_allowed();print(json.dumps({'sealed':True,'authority':auth,'new_cap_CNY':300,'remaining':12}))
if __name__=='__main__':main()
