"""Freeze a concrete PROJECT rerun proposal; grant is recorded separately."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from proworksim import software_benchmark_scope_v119 as scope
from proworksim.software_benchmark_candidates_v054 import reference,write_new,checked

PROPOSAL=scope.ROOT/'artifacts/software-benchmark-v119/runtime-authorization-r1/proposal.json'
ENTRIES=('tools/run_project_rerun_v119.py','tools/launch_project_rerun_v119.py',
 'tools/summarize_project_rerun_v119.py','tools/prepare_project_panel_v118.py',
 'tools/prepare_project_runtime_v118.py','tools/seal_project_rerun_v119.py',
 'tools/run_project_controller_v118.py','tools/run_managed_worker_docker_v119.py',
 'tools/run_native_worker_docker_v118.py','tools/run_public_tests_v118.py',
 'tools/public_test_library_v118.py','tools/public_test_dependencies_v118.py',
 'tools/public_fixture_diagnostic_v119.py','tools/run_offline_scorer_v096.py',
 'src/proworksim/software_benchmark_grading_v119.py',
 'src/proworksim/software_benchmark_host_api_v119.py',
 'src/proworksim/software_benchmark_sdk_bundle_v119.py',
 'src/proworksim/software_benchmark_episode_v119.py')

def source_closure():
    pending = [scope.ROOT / name for name in ENTRIES]
    found = {}
    while pending:
        path = pending.pop().resolve()
        if str(path) in found:
            continue
        if not path.is_file():
            raise FileNotFoundError(path)
        found[str(path)] = reference(path)
        try:
            module = '.'.join(path.relative_to(scope.ROOT / 'src').with_suffix('').parts)
            package = module.rsplit('.', 1)[0]
        except ValueError:
            package = None
        for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith('.py'):
                literal = node.value
                target = (scope.ROOT / 'tools' / literal if Path(literal).name == literal
                          else scope.ROOT / literal if literal.startswith('tools/') else None)
                if target is not None and target.is_file():
                    pending.append(target)
            candidates = []
            if isinstance(node, ast.Import):
                candidates = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if package is None:
                        continue
                    base = '.'.join(package.split('.')[:len(package.split('.'))-node.level+1])
                    full = base + ('.'+node.module if node.module else '')
                else:
                    full = node.module or ''
                candidates = [full, *[full+'.'+item.name for item in node.names]]
            for name in candidates:
                if not name.startswith('proworksim'):
                    continue
                target = scope.ROOT / 'src' / Path(*name.split('.'))
                for candidate in (target.with_suffix('.py'), target / '__init__.py'):
                    if candidate.is_file():
                        pending.append(candidate)
                        break
    return [found[key] for key in sorted(found)]


def seal():
    import subprocess
    from proworksim import software_benchmark_sdk_bundle_v119 as bundle
    from proworksim import software_benchmark_host_api_v119 as host
    from proworksim import software_benchmark_grading_v119 as grading
    from proworksim.software_benchmark_alignment_contract_v117 import VERSION as ALIGNMENT
    from proworksim.software_benchmark_generation_admission_v119 import diagnostic_descriptor
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists() or PROPOSAL.exists():
        raise PermissionError('Never reseal an approved or entered recovery')
    scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    parent=scope.load(reference(scope.PARENT_AUTH_FILE))
    recovery=scope.load(reference(scope.RECOVERY_FILE))
    if (recovery['formal_model_calls'] != 0 or recovery['neutral_model_calls'] != 0
            or recovery['prior_created_containers']!=2 or recovery['prior_created_volumes']!=1
            or scope.load(recovery['prior_owner_release']).get('released') is not True):
        raise ValueError('The prior failed owner or original attempts are not unused/quiescent')
    completed=subprocess.run(grading.command(['--verify-preparation']),capture_output=True,text=True,timeout=60,check=False)
    if completed.returncode:
        raise ValueError('Current source/prepared scoring identities differ: '+completed.stderr[-2000:])
    verified=json.loads(completed.stdout)
    bundle_ref=reference(bundle.OUTPUT/'manifest.json'); b=scope.load(bundle_ref)
    for ref in (*b['source_tools'].values(),*b['project_modules'].values()):
        checked(ref)
    schemas_ref=reference(host.SCHEMAS); schemas=scope.load(schemas_ref)
    if schemas['runtime_bundle']!=bundle_ref or set(schemas['schemas'])!={'PROJECT'}:
        raise ValueError('The actual PROJECT schema/bundle identity changed')
    controls={}
    for name in ('runtime-controls-r1/summary.json','grading-transport-control-r1/preparation.json',
                 'public-fixture-contract-controls-r1/summary.json','prior-call-audit-r1/summary.json'):
        ref=reference(scope.ROOT/'artifacts/software-benchmark-v119'/name)
        value=scope.load(ref)
        if 'passed' in value and value['passed'] is not True:
            raise ValueError('Required recovery control failed')
        controls[name]=ref
    files=source_closure()+[reference(path) for path in (scope.PLAN_FILE,scope.PANEL_FILE,scope.CPU_POOL_FILE,
        scope.BUDGET_BASELINE_FILE,scope.NETWORK_RESOLUTION_FILE,scope.CA_PROFILE_FILE,scope.RECOVERY_FILE,
        host.SCHEMAS,bundle.OUTPUT/'manifest.json',scope.API_ROOT/'coordinator-unit.json')]
    sources=write_new(scope.SOURCE_FILE,{'version':scope.VERSION,'files':files,'controls':controls,
        'prepared_grading_identity_verified':verified,'runtime_authorized':False})
    value={**parent,'version':scope.VERSION,'status':'prepared','runtime_authorized':False,
        'parent_authorization':reference(scope.PARENT_AUTH_FILE),'startup_recovery':reference(scope.RECOVERY_FILE),
        'plan':reference(scope.PLAN_FILE),'source_index':sources,'constraints':scope.CONSTRAINTS,
        'execution_alignment_version':ALIGNMENT,'new_generation_attempts':50,
        'additional_formal_generation_attempts':0,'prior_created_containers':2,'prior_created_volumes':1,
        'cumulative_maximum_containers':304,'cumulative_maximum_named_volumes':52,
        'maximum_containers':302,'maximum_named_volumes':51,
        'additional_diagnostic_pairs':1,'public_fixture_diagnostic':diagnostic_descriptor(),
        'neutral_API_calls':1,'neutral_identity_reused':host.NEUTRAL_SLOT,
        'prior_neutral_API_calls':0,'controls':controls,'source_bundle':bundle_ref,
        'actual_PROJECT_schemas':schemas_ref,'prepared_grading_identity_verified':verified,
        'old_root_failure_retained':True,'old_public_fixture_false_retained':True,
        'additional_cash':0,'execution_started':False}
    value.pop('proposal',None)
    PROPOSAL.parent.mkdir(parents=True,exist_ok=True)
    return {'proposal':write_new(PROPOSAL,value),'source_index':sources,'runtime_authorized':False}

if __name__=='__main__':
    print(json.dumps(seal(),ensure_ascii=False))
