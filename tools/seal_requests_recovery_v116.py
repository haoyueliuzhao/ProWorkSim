"""Seal completed preparation for review; this never grants runtime authority."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from proworksim import software_benchmark_scope_v116 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

PROPOSAL = scope.ROOT / 'artifacts/software-benchmark-v116/runtime-amendment-r1/proposal.json'
ENTRIES = ('tools/run_requests_recovery_v116.py', 'tools/launch_requests_recovery_v116.py', 'tools/summarize_requests_recovery_v116.py', 'tools/seal_requests_recovery_v116.py', 'src/proworksim/software_benchmark_grading_requests_v116.py', 'src/proworksim/software_benchmark_environment_v116.py', 'src/proworksim/software_benchmark_grading_ca_v116.py', 'src/proworksim/software_benchmark_episode_recovery_v116.py', 'src/proworksim/software_benchmark_host_api_v116.py', 'tools/run_offline_scorer_v096.py', 'tools/run_ref_controller_v110.py', 'tools/run_project_controller_v110.py', 'tools/run_native_worker_docker_v110.py', 'tools/run_managed_worker_docker_v110.py', 'tools/run_public_tests_v110.py', 'tools/public_test_library_v110.py')


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
    from proworksim import software_benchmark_scope_v115 as prior
    from proworksim import software_benchmark_host_api_v116 as host
    from proworksim.software_benchmark_candidates_v054 import checked
    from proworksim.software_benchmark_alignment_contract_v110 import VERSION as ALIGNMENT_VERSION
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists() or PROPOSAL.exists() or prior.LEASE_FILE.exists():
        raise PermissionError('An authorized, sealed or active revision cannot be resealed')
    parent = prior.require_allowed()
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    spec = importlib.util.spec_from_file_location('v116_recovery_check', scope.ROOT/'tools/run_requests_recovery_v116.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_recovery_rows(plan)
    recovery = scope.load(reference(scope.REQUESTS_RECOVERY_FILE))
    # Pure predicate input only: this dictionary is never written as authority.
    simulated = {'status': 'approved', 'additional_object_allowance': 4,
                 'total_authorized_containers': 30, 'total_authorized_TLS_sessions': 14}
    module.validate_requests_recovery(recovery, plan, simulated)
    controls = {}
    for name in ('concrete-evaluator-control-r1', 'grading-ca-controls-r1', 'requests-runtime-controls-r1'):
        ref = reference(scope.ROOT/'artifacts/software-benchmark-v116'/name/'summary.json')
        value = scope.load(ref)
        if value.get('passed') is not True and value.get('status') != 'passed':
            raise ValueError('A required evaluator, CA or runtime CPU control did not pass')
        for item in value.get('sources', []):
            checked(item)
        for key in ('adapter', 'profile', 'scorer_source', 'control_source', 'official_source'):
            item = value.get(key)
            if isinstance(item, dict) and {'path','sha256','bytes'} <= item.keys():
                checked(item)
        controls[name] = ref
    schema_ref = reference(host.SCHEMAS)
    schemas = scope.load(schema_ref)
    prior_qualification = scope.load(parent['API_qualification'])
    previous_schemas = scope.load(prior_qualification['schema_inventory'])
    if (prior_qualification.get('passed') is not True
            or previous_schemas.get('schemas') != schemas.get('schemas')
            or previous_schemas.get('tool_names') != schemas.get('tool_names')):
        raise ValueError('Only exactly unchanged tools may reuse the passed API qualification')
    unit_ref = reference(scope.API_ROOT/'coordinator-unit.json')
    sources = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': source_closure(),
        'controls': controls, 'prior_source_index': parent['source_index'],
        'installed_CA_recovery': reference(scope.REQUESTS_RECOVERY_FILE),
        'model_calls': 0, 'Docker_operations': 0})
    value = {**parent, 'version': scope.VERSION, 'status': 'prepared',
        'original_batch_authorization': reference(scope.PARENT_AUTH_FILE),
        'original_authorization': reference(scope.ORIGINAL_AUTH_FILE),
        'concurrency_authorization': reference(scope.CONCURRENCY_AUTH_FILE),
        'preparation_recovery': reference(scope.PREPARATION_RECOVERY_FILE),
        'precreation_recovery': reference(scope.TLS_PRECREATION_RECOVERY_FILE),
        'installed_CA_recovery': reference(scope.INSTALLED_CA_RECOVERY_FILE),
        'network_resolution': reference(scope.NETWORK_RESOLUTION_FILE),
        'CA_profile': reference(scope.CA_PROFILE_FILE),
        'execution_alignment_version': ALIGNMENT_VERSION,
        'explicit_concurrency_instruction': '提高并发',
        'plan': reference(scope.PLAN_FILE), 'source_index': sources, 'constraints': scope.CONSTRAINTS,
        'API_cash_cap_CNY': scope.CASH_CAP_CNY, 'cash_budget_scope': scope.CASH_MODE,
        'ledger_path': str(scope.LEDGER_FILE), 'cash_before_run': reference(scope.BUDGET_BASELINE_FILE),
        'original_authorized_total_containers': 26, 'already_created_containers': 12,
        'additional_object_allowance': 4, 'total_authorized_containers': 30,
        'maximum_new_containers': 18, 'maximum_new_named_volumes': 4,
        'total_authorized_named_volumes': 4,
        'original_TLS_session_allowance': 10, 'additional_TLS_sessions': 4,
        'total_authorized_TLS_sessions': 14,
        'maximum_TLS_sessions': 10, 'maximum_connections': 5120,
        'maximum_TLS_payload_bytes': 640*1024**2,
        'total_authorized_connections': 7168, 'total_authorized_TLS_payload_bytes': 896*1024**2,
        'combined_CPU': 40, 'combined_memory_GiB': 192,
        'generation_pair_concurrency': 4, 'scoring_concurrency': 2, 'TLS_scoring_concurrency': 1,
        'new_generation_attempts': 4, 'new_controls': 4, 'diagnostics_repeated': 0,
        'new_neutral_API_calls': 0, 'already_called_models_resampled': 0, 'additional_cash': 0,
        'original_locked_candidate_rescores': 0, 'stopped_tree_supplemental_scores': 0,
        'original_completed_scores_preserved': 4,
        'new_binding_controls': controls, 'actual_tool_schemas': schema_ref,
        'ordinary_user_service_specification': unit_ref,
        'same_owned_user_service': scope.API_UNIT, 'shared_host_configuration_changes': 0,
        'execution_started': False, 'runtime_authorized': False,
        'authorization_basis': 'Prepared request only: four additional TLS control containers/sessions require specific authorization. No new model identity, seed, neutral probe, cash allowance or completed-candidate rescore.'}
    for key in ('proposal', 'approved_client_date', 'explicit_user_reply'):
        value.pop(key, None)
    PROPOSAL.parent.mkdir(parents=True, exist_ok=True)
    proposal = write_new(PROPOSAL, value)
    if scope.AUTH_FILE.exists():
        raise RuntimeError('An authorization appeared during preparation; stop for review')
    return {'proposal': proposal, 'source_index': sources,
            'authorization_written': False, 'runtime_authorized': False,
            'additional_control_containers_requested': 4, 'maximum_new_containers': 18,
            'total_authorized_containers_requested': 30,
            'total_authorized_TLS_sessions_requested': 14,
            'model_calls': 0, 'Docker_operations': 0}


if __name__ == '__main__':
    print(json.dumps(seal(), ensure_ascii=False))
