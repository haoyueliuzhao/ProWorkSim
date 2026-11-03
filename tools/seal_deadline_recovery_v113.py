"""Seal completed preparation for review; this never grants runtime authority."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v113 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

PROPOSAL = scope.ROOT / 'artifacts/software-benchmark-v113/deadline-recovery-r1/proposal.json'
ENTRIES = ('tools/run_aligned_interface_v113.py', 'tools/launch_aligned_interface_v113.py', 'tools/summarize_aligned_interface_v113.py', 'tools/seal_deadline_recovery_v113.py', 'tools/run_ref_controller_v110.py', 'tools/run_project_controller_v110.py', 'tools/run_native_worker_docker_v110.py', 'tools/run_managed_worker_docker_v110.py', 'tools/run_public_tests_v110.py', 'tools/public_test_library_v110.py', 'tools/run_offline_scorer_v096.py', 'src/proworksim/software_benchmark_grading_v113.py', 'src/proworksim/software_benchmark_sdk_bundle_v110.py', 'src/proworksim/software_benchmark_episode_v113.py', 'src/proworksim/software_benchmark_host_api_v113.py')


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
    from datetime import datetime,timezone
    from proworksim import software_benchmark_scope_v112 as previous
    from proworksim import software_benchmark_host_api_v113 as host
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists():
        raise ValueError('Never re-seal an approved recovery')
    if previous.LEASE_FILE.exists():
        raise PermissionError('The stopped owner must release its own capacity first')
    parent=previous.require_allowed()
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    old=previous.load(parent['plan'])
    if plan['rows']!=old['rows'] or plan['resources']!=old['resources'] or plan['constraints']!=old['constraints']:
        raise ValueError('No new attempts, resources or limits may enter this recovery')
    recovery=scope.load(reference(scope.PREPARATION_RECOVERY_FILE))
    module_spec=importlib.util.spec_from_file_location('v113_recovery_validation',scope.ROOT/'tools/run_aligned_interface_v113.py')
    manager=importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(manager)
    manager.validate_preparation_recovery(recovery,plan)
    controls={}
    for name,path in (('deadline','deadline-controls-r1/summary.json'),
                      ('runtime','runtime-recovery-controls-r1/summary.json'),
                      ('grading','grading-binding-control-r1/summary.json')):
        ref=reference(scope.ROOT/'artifacts/software-benchmark-v113'/path)
        if scope.load(ref).get('passed') is not True:
            raise ValueError('Recovery control failed: '+name)
        controls[name]=ref
    sources=write_new(scope.SOURCE_FILE,{'version':scope.VERSION,'files':source_closure(),
        'controls':controls,'original_sources':parent['source_index'],
        'preparation_recovery':reference(scope.PREPARATION_RECOVERY_FILE),
        'actual_tool_schemas':reference(host.SCHEMAS),'API_calls':0,'Docker_operations':0})
    proposal={**parent,'version':scope.VERSION,'status':'prepared',
        'concurrency_authorization':reference(previous.AUTH_FILE),
        'plan':reference(scope.PLAN_FILE),'source_index':sources,
        'preparation_recovery':reference(scope.PREPARATION_RECOVERY_FILE),
        'diagnostics_repeated':0,'diagnostic_PROJECT_original_passed':False,
        'additional_attempts':0,'additional_object_allowance':0,'additional_cash':0,
        'formal_attempts_previously_entered':0,'old_failure_overwritten':False,
        'remaining_original_formal_attempts':100,'new_binding_controls':controls,
        'actual_tool_schemas':reference(host.SCHEMAS),'recorded_utc':datetime.now(timezone.utc).isoformat(),
        'execution_started':False,'authorization_created':False}
    proposal.pop('proposal',None)
    PROPOSAL.parent.mkdir(parents=True,exist_ok=True)
    proposal_ref=write_new(PROPOSAL,proposal)
    auth={**proposal,'status':'approved','proposal':proposal_ref,'authorization_created':True,
        'authorization_basis':'Repair the original authorized first launch; reuse verified diagnostic segments and CPU boundary proof, not consumed resource identities. All 100 formal attempts remain unused; no quota expansion.'}
    return {'proposal':proposal_ref,'authority':write_new(scope.AUTH_FILE,auth),
            'model_calls':0,'Docker_operations':0,'diagnostics_repeated':0}


if __name__=='__main__':
    print(json.dumps(seal(),ensure_ascii=False))

