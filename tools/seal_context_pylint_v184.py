"""Seal only the original four uncalled task identities and repaired scorer."""
import importlib.util,json
from proworksim.software_context_pylint_v184 import scope,TASK,VERSION
from proworksim import software_benchmark_scope_v183 as controls
from proworksim.software_benchmark_alignment_contract_v181 import VERSION as alignment
from proworksim.software_benchmark_candidates_v054 import reference

def main():
 if scope.AUTH_FILE.exists():raise ValueError('Already sealed')
 plan=scope.load(reference(scope.PLAN_FILE));rows=[r for r in plan['rows'] if r['instance_id']==TASK]
 assert len(rows)==4 and scope.load(reference(controls.STATE_ROOT/'summary.json'))['passed']
 proposal=reference(scope.ROOT/'artifacts/software-benchmark-v184/pylint-completion-r1/proposal.json')
 spec=importlib.util.spec_from_file_location('seal184',scope.ROOT/'tools/seal_role_pilot_v143.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 files=m.source_closure(roots=[p for folder in ('src/proworksim','tools') for p in (scope.ROOT/folder).glob('*v184.py')])
 files += [reference(scope.PLAN_FILE),proposal,reference(controls.STATE_ROOT/'summary.json'),reference(scope.ROOT/'docs/experiments/software-benchmark-v184-pylint-completion.md')]
 source=scope.retain(scope.SOURCE_FILE,{'version':VERSION,'files':files,'controller_model_runtime_unchanged':True})
 scope.retain(scope.AUTH_FILE,{'version':VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),'source_index':source,
  'execution_alignment_version':alignment,'constraints':scope.CONSTRAINTS,'cash_cap_CNY':'250.00','companion_proposal':proposal,
  'standing_user_request':'按照审计继续实验；非干扰实验Docker/API无需另行请求','additional_model_attempts':0,'shared_host_configuration_changes':0})
 scope.require_allowed();print(json.dumps({'sealed':True,'same_original_tasks':4,'extra_model_attempts':0}))
if __name__=='__main__':main()
