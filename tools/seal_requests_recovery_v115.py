"""Seal completed preparation for review; this never grants runtime authority."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v115 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

PROPOSAL = scope.ROOT / 'artifacts/software-benchmark-v115/runtime-amendment-r1/proposal.json'
ENTRIES = ('tools/run_requests_recovery_v115.py', 'tools/launch_requests_recovery_v115.py', 'tools/summarize_requests_recovery_v115.py', 'tools/seal_requests_recovery_v115.py', 'src/proworksim/software_benchmark_grading_requests_v115.py', 'src/proworksim/software_benchmark_environment_v114.py', 'src/proworksim/software_benchmark_grading_ca_v114.py', 'src/proworksim/software_benchmark_episode_recovery_v115.py', 'src/proworksim/software_benchmark_host_api_v115.py', 'tools/run_offline_scorer_v096.py', 'tools/run_ref_controller_v110.py', 'tools/run_project_controller_v110.py', 'tools/run_native_worker_docker_v110.py', 'tools/run_managed_worker_docker_v110.py', 'tools/run_public_tests_v110.py', 'tools/public_test_library_v110.py')


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
    import importlib.util
    from proworksim import software_benchmark_scope_v114 as prior
    from proworksim import software_benchmark_host_api_v115 as host
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists() or prior.LEASE_FILE.exists():
        raise PermissionError('An entered revision or active owner cannot be resealed')
    parent=prior.require_allowed()
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    spec=importlib.util.spec_from_file_location('v115_recovery_check',scope.ROOT/'tools/run_requests_recovery_v115.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recovery=scope.load(reference(scope.TLS_PRECREATION_RECOVERY_FILE))
    module.validate_precreation_recovery(recovery,plan)
    controls={}
    for name in ('concrete-evaluator-control-r1','requests-runtime-controls-r1'):
        ref=reference(scope.ROOT/'artifacts/software-benchmark-v115'/name/'summary.json')
        value=scope.load(ref)
        if value.get('passed') is not True:
            raise ValueError('Necessary evaluator or recovery binding control failed')
        controls[name]=ref
    sources=write_new(scope.SOURCE_FILE,{'version':scope.VERSION,'files':source_closure(),
        'controls':controls,'prior_source_index':parent['source_index'],
        'precreation_recovery':reference(scope.TLS_PRECREATION_RECOVERY_FILE),
        'model_calls':0,'Docker_operations':0})
    value={**parent,'version':scope.VERSION,'status':'prepared',
        'original_batch_authorization':reference(prior.AUTH_FILE),
        'plan':reference(scope.PLAN_FILE),'source_index':sources,'constraints':scope.CONSTRAINTS,
        'precreation_recovery':reference(scope.TLS_PRECREATION_RECOVERY_FILE),
        'original_authorized_total_containers':26,'already_created_containers':8,
        'additional_object_allowance':0,'maximum_new_containers':18,
        'original_locked_candidate_rescores':0,'stopped_tree_supplemental_scores':0,
        'original_completed_scores_preserved':4,'new_controls':4,
        'new_binding_controls':controls,'actual_tool_schemas':reference(host.SCHEMAS),
        'execution_started':False,'runtime_authorized':False}
    value.pop('proposal',None)
    PROPOSAL.parent.mkdir(parents=True,exist_ok=True)
    proposal=write_new(PROPOSAL,value)
    auth={**value,'status':'approved','runtime_authorized':True,'proposal':proposal,
        'authorization_basis':'Continue the original 26-container grant after four proven pre-creation failures; exactly eight actual containers were used, eighteen remain. No re-scoring of completed work or additional money/model attempts.'}
    return {'proposal':proposal,'authorization':write_new(scope.AUTH_FILE,auth),
            'remaining_containers':18,'model_calls':0,'Docker_operations':0}


if __name__=='__main__':
    print(json.dumps(seal(),ensure_ascii=False))

