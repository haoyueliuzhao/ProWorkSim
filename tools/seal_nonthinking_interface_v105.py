"""Seal completed preparation for review; this never grants runtime authority."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v105 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

PROPOSAL = scope.ROOT / 'artifacts/software-benchmark-v105/runtime-authorization-r1/proposal.json'
ENTRIES = (
    'tools/run_nonthinking_interface_v105.py',
    'tools/launch_nonthinking_interface_v105.py',
    'tools/run_ref_controller_v105.py',
    'tools/run_project_controller_v105.py',
    'tools/run_managed_worker_docker_v103.py',
    'tools/run_offline_scorer_v096.py',
    'tools/summarize_interface_panel_v105.py',
    'tools/seal_nonthinking_interface_v105.py',
    'src/proworksim/software_benchmark_grading_v105.py',
    'src/proworksim/software_benchmark_sdk_bundle_v105.py',
)


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
    if scope.AUTH_FILE.exists() or (scope.API_ROOT / 'execution-started.json').exists():
        raise PermissionError('Do not alter an approved or entered runtime')
    if scope.SOURCE_FILE.exists():
        raise ValueError('Source sealing is single-use; inspect the existing record')
    evidence = {}
    for name, filename in (
        ('adapter', 'nonthinking-sdk-control-r1/summary.json'),
        ('runtime', 'runtime-cpu-control-r1/result.json'),
        ('scorer', 'scoring-control-r1/manager-isolation.json'),
    ):
        ref = reference(scope.ROOT / 'artifacts/software-benchmark-v105' / filename)
        value = scope.load(ref)
        if value.get('passed') is not True:
            raise ValueError('Preparation control did not pass: '+name)
        evidence[name] = ref
    scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    from proworksim import software_benchmark_host_api_v105 as host
    from proworksim import software_benchmark_sdk_bundle_v105 as bundle
    bundle_ref = reference(bundle.OUTPUT / 'manifest.json')
    schemas_ref = reference(host.SCHEMAS)
    manifest = scope.load(bundle_ref)
    if scope.load(schemas_ref)['native_bundle'] != bundle_ref:
        raise ValueError('Actual tool schemas refer to another runtime bundle')
    if not manifest.get('probe'):
        raise ValueError('The actual runtime archive has no preload probe')
    sources = write_new(scope.SOURCE_FILE, {
        'version': scope.VERSION, 'files': source_closure(),
        'runtime_bundle': bundle_ref, 'actual_tool_schemas': schemas_ref,
        'controls': evidence, 'model_calls': 0, 'Docker_operations': 0,
    })
    proposal = scope.load(reference(PROPOSAL))
    proposal.update(status='source_sealed_ready_for_scope_confirmation', source_index=sources,
        plan=reference(scope.PLAN_FILE), panel=reference(scope.PANEL_FILE),
        inventory=reference(scope.INVENTORY_FILE), constraints=scope.CONSTRAINTS,
        preparation_evidence=evidence, runtime_bundle=bundle_ref,
        actual_tool_schemas=schemas_ref,
        authorization_created=False, execution_started=False)
    # The existing draft was explicitly not an approval; retain it before replacing it.
    write_new(PROPOSAL.parent / 'pre-seal-proposal.json', scope.load(reference(PROPOSAL)))
    PROPOSAL.write_text(json.dumps(proposal, ensure_ascii=False, indent=2)+'\n')
    return {'source_index': sources, 'proposal': reference(PROPOSAL),
            'authorization_created': False, 'model_calls': 0, 'Docker_operations': 0}


if __name__ == '__main__':
    print(json.dumps(seal(), ensure_ascii=False))
