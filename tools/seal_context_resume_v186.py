"""Seal a host-only restart of20 never-called original task identities."""
import importlib.util,json
from pathlib import Path
from proworksim.software_context_resume_v186 import scope,STATE,REMAINING,HANDOFF,VERSION
from proworksim.software_benchmark_candidates_v054 import reference,checked
from proworksim.software_benchmark_alignment_contract_v181 import VERSION as ALIGNMENT

def main():
 if scope.AUTH_FILE.exists():raise ValueError('Do not reseal an activated owner')
 rows=scope.load(reference(REMAINING));assert len(rows['rows'])==20
 assert scope.load(reference(HANDOFF))['old_manager_stopped']
 log=scope.ROOT/'artifacts/software-benchmark-v186/cpu-controls-r1/pytest.log'
 if '4 passed' not in log.read_text():raise ValueError('Necessary resource and ledger CPU controls did not pass')
 manifest=scope.ROOT/'runs/software-benchmark-v181/sdk-bundle-r3/manifest.json'
 package=scope.load(reference(manifest))
 for ref in [*package['source_tools'].values(),*package['project_modules'].values()]:checked(ref)
 out=scope.ROOT/'artifacts/software-benchmark-v186/resume-authorization-r1'
 proposal=scope.retain(out/'proposal.json',{'version':VERSION,'user_request':'恢复任务',
  'original_plan':reference(scope.PLAN_FILE),'remaining':reference(REMAINING),'idle_handoff':reference(HANDOFF),
  'same_model_runtime':reference(manifest),'same_model_and_context_and_seeds':True,
  'new_model_attempts_outside_original_plan':0,'remaining_original_attempts':20,
  'total_cash_start_limit_CNY':250,'already_admitted_starts_continue':True,'initial_hold_CNY_per_task':5,
  'API_unit':scope.API_UNIT,'maximum_generation_pairs':4,'maximum_graders':2,
  'CPU_upper':40,'memory_GiB_upper':264,'disk_floor_GiB':128,'spool_per_pair_GiB':4,
  'no_new_environment_controls':True,'no_GPU_or_shared_host_changes':True,'CPU_controls':reference(log)})
 spec=importlib.util.spec_from_file_location('source186',scope.ROOT/'tools/seal_role_pilot_v143.py')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 roots=[p for folder in ('src/proworksim','tools','tests') for p in (scope.ROOT/folder).glob('*v186.py')]
 files=mod.source_closure(roots=roots)
 files += [reference(scope.PLAN_FILE),reference(REMAINING),reference(HANDOFF),reference(manifest),proposal,reference(log),
  reference(scope.ROOT/'docs/experiments/software-benchmark-v186-resume.md')]
 sources=scope.retain(scope.SOURCE_FILE,{'version':VERSION,'files':files,'solver_runtime_changed':False})
 auth=scope.retain(scope.AUTH_FILE,{'version':VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),
  'source_index':sources,'constraints':scope.CONSTRAINTS,'execution_alignment_version':ALIGNMENT,
  'cash_cap_CNY':'250.00','proposal':proposal,'user_request':'恢复任务',
  'standing_nondisruptive_Docker_API_authority':True,'new_user_unit':scope.API_UNIT,
  'shared_host_configuration_changes':0})
 scope.require_allowed();print(json.dumps({'sealed':True,'authorization':auth,'remaining':20,'extra_attempts':0}))
if __name__=='__main__':main()
