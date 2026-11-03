"""Seal completed preparation for review; this never grants runtime authority."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v112 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

PROPOSAL = scope.ROOT / 'artifacts/software-benchmark-v112/concurrency-amendment-r1/proposal.json'
ENTRIES = ('tools/run_aligned_interface_v112.py', 'tools/launch_aligned_interface_v112.py', 'tools/summarize_aligned_interface_v112.py', 'tools/prepare_concurrency_v112.py', 'tools/seal_concurrency_v112.py', 'tools/run_ref_controller_v110.py', 'tools/run_project_controller_v110.py', 'tools/run_native_worker_docker_v110.py', 'tools/run_managed_worker_docker_v110.py', 'tools/run_public_tests_v110.py', 'tools/public_test_library_v110.py', 'tools/run_offline_scorer_v096.py', 'src/proworksim/software_benchmark_grading_v112.py', 'src/proworksim/software_benchmark_sdk_bundle_v110.py', 'src/proworksim/software_benchmark_host_api_v112.py')


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
    from datetime import datetime,timezone
    from proworksim import software_benchmark_scope_v111 as prior
    from proworksim import software_benchmark_host_api_v112 as host
    from proworksim import software_benchmark_sdk_bundle_v110 as bundle
    from proworksim.software_benchmark_alignment_contract_v110 import VERSION as ALIGNMENT_VERSION
    if (scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists()
            or any((root/'execution-started.json').exists() for root in (prior.API_ROOT,scope.API_ROOT))):
        raise PermissionError('Never re-seal an approved or entered concurrency revision')
    parent=prior.require_allowed()
    old=prior.load(parent['plan'])
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    if plan['rows']!=old['rows'] or plan['resources']!=old['resources']:
        raise ValueError('Concurrency cannot add model attempts or object identities')
    controls={}
    for name,path in (('scope','concurrency-controls-r1/scope.json'),
                      ('runtime','runtime-binding-controls-r1/summary.json'),
                      ('grading','grading-binding-controls-r1/summary.json')):
        ref=reference(scope.ROOT/'artifacts/software-benchmark-v112'/path)
        if scope.load(ref).get('passed') is not True:
            raise ValueError('New deployment binding failed: '+name)
        controls[name]=ref
    manifest=reference(bundle.OUTPUT/'manifest.json')
    schemas=reference(host.SCHEMAS)
    if scope.load(schemas)['native_bundle']!=manifest:
        raise ValueError('Concurrency changed the admitted model-visible interface')
    sources=write_new(scope.SOURCE_FILE,{'version':scope.VERSION,'files':source_closure(),
        'controls':controls,'same_model_visible_runtime_bundle':manifest,'actual_tool_schemas':schemas,
        'original_source_index':parent['source_index'],'model_calls':0,'Docker_operations':0})
    proposal={**parent,'version':scope.VERSION,'status':'prepared',
        'execution_alignment_version':ALIGNMENT_VERSION,
        'original_authorization':reference(prior.AUTH_FILE),
        'original_plan':parent['plan'],'plan':reference(scope.PLAN_FILE),
        'source_index':sources,'constraints':scope.CONSTRAINTS,
        'actual_tool_schemas':schemas,'new_binding_controls':controls,
        'explicit_concurrency_instruction':'提高并发','first_start_only':True,
        'generation_pairs':16,'grading_jobs':2,'combined_CPU':112,'combined_memory_GiB':576,
        'same_per_object_limits':True,'additional_attempts':0,'additional_object_allowance':0,
        'additional_cash':0,'new_service_count':1,'same_user_service':scope.API_UNIT,
        'execution_started':False,'authorization_created':False,
        'recorded_utc':datetime.now(timezone.utc).isoformat()}
    proposal.pop('proposal',None)
    proposal.pop('superseding_concurrency_change_requested_before_launch',None)
    proposal['resource_scope']={**parent['resource_scope'],'maximum_simultaneous_generation_pairs':16}
    PROPOSAL.parent.mkdir(parents=True,exist_ok=True)
    proposal_ref=write_new(PROPOSAL,proposal)
    authority={**proposal,'status':'approved','proposal':proposal_ref,
        'explicit_user_reply':'授权上述限定范围并启动；提高并发',
        'authorization_basis':'Original exact object grant plus subsequent explicit concurrency increase; no new privilege, host configuration, object count or money allowance.',
        'authorization_created':True}
    return {'proposal':proposal_ref,'authorization':write_new(scope.AUTH_FILE,authority),
            'source_index':sources,'resource_operations':0,'model_calls':0}


if __name__=='__main__':
    print(json.dumps(seal(),ensure_ascii=False))

