"""Freeze a concrete PROJECT rerun proposal; grant is recorded separately."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from proworksim import software_benchmark_scope_v121 as scope
from proworksim.software_benchmark_candidates_v054 import reference,write_new,checked

PROPOSAL=scope.ROOT/'artifacts/software-benchmark-v121/runtime-authorization-r1/proposal.json'
ENTRIES=('tools/start_authorized_recovery_v121.py', 'src/proworksim/software_benchmark_dispatch_control_v120.py','tools/set_dispatch_admission_v120.py','tools/run_project_recovery_v121.py','tools/launch_project_recovery_v121.py',
 'tools/summarize_project_recovery_v121.py','tools/prepare_project_recovery_v121.py',
 'tools/prepare_project_runtime_v118.py','tools/seal_project_recovery_v121.py',
 'tools/run_project_controller_v120.py','tools/run_managed_worker_docker_v119.py',
 'tools/run_native_worker_docker_v118.py','tools/run_public_tests_v118.py',
 'tools/public_test_library_v118.py','tools/public_test_dependencies_v118.py',
 'tools/public_fixture_diagnostic_v119.py','tools/run_offline_scorer_v096.py',
 'src/proworksim/software_benchmark_grading_v121.py',
 'src/proworksim/software_benchmark_host_api_v121.py',
 'src/proworksim/software_benchmark_sdk_bundle_v120.py',
 'src/proworksim/software_benchmark_episode_v121.py')

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
    from proworksim import software_benchmark_sdk_bundle_v120 as bundle
    from proworksim import software_benchmark_host_api_v121 as host
    from proworksim import software_benchmark_grading_v121 as grading
    from proworksim.software_benchmark_prior_completion_v121 import require_prior_completion
    from proworksim.software_benchmark_dispatch_control_v120 import DispatchAdmissionController
    from proworksim.software_benchmark_alignment_contract_v117 import VERSION as ALIGNMENT
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists() or PROPOSAL.exists():
        raise PermissionError('Never reseal an approved or entered recovery')
    completed_prior = require_prior_completion()
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    recovery = scope.load(reference(scope.RECOVERY_FILE))
    grant = scope.load(reference(scope.USER_GRANT_FILE))
    if (grant.get('status') != 'approved' or grant.get('explicit_user_reply') != '授权27题独立恢复'
            or grant.get('proposal') != reference(scope.USER_PROPOSAL_FILE)
            or recovery['new_generation_attempts'] != 27
            or recovery['old_episodes_resumed'] is not False
            or recovery['original_records_overwritten'] is not False):
        raise ValueError('Explicit independent recovery authority differs')
    stage_ids = {row['slot_id'] for row in plan['rows']}
    with host.ledger_read() as db:
        count = db.execute('SELECT count(*) FROM requests WHERE slot_id IN ('
            + ','.join('?' for _ in stage_ids) + ')', tuple(stage_ids)).fetchone()[0]
    if count:
        raise ValueError('Already-called recovery identities may not be replayed')
    completed = subprocess.run(grading.command(['--verify-preparation']),
        capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode:
        raise ValueError('Current grader/preparation identity mismatch: ' + completed.stderr[-2000:])
    verified = json.loads(completed.stdout)
    bundle_ref = reference(bundle.OUTPUT/'manifest.json')
    manifest = scope.load(bundle_ref)
    for ref in (*manifest['source_tools'].values(), *manifest['project_modules'].values()):
        checked(ref)
    schemas_ref = reference(host.SCHEMAS)
    schemas = scope.load(schemas_ref)
    prior = scope.load(recovery['prior_API_qualification'])
    if (schemas['runtime_bundle'] != bundle_ref or set(schemas['schemas']) != {'PROJECT'}
            or prior.get('passed') is not True
            or scope.load(prior['schema_inventory'])['schemas'] != schemas['schemas']):
        raise ValueError('Only the existing exact-schema neutral qualification may be reused')
    gate = DispatchAdmissionController(reference(scope.PLAN_FILE))
    if gate.limit(scope.MAX_GENERATIONS) != scope.MAX_GENERATIONS:
        raise ValueError('Explicit dispatch admission is not ready')
    controls = {}
    for name in ('runtime-controls-r1/summary.json', 'grading-transport-control-r1/preparation.json',
                 'authorized-start-controls-r1/summary.json'):
        ref = reference(scope.ROOT/'artifacts/software-benchmark-v121'/name)
        if scope.load(ref).get('passed') is not True:
            raise ValueError('Necessary new control not passed: ' + name)
        controls[name] = ref
    reusable = reference(scope.ROOT/'artifacts/software-benchmark-v121/identity-review-r1/reusable-evidence.json')
    controls['existing_execution_evidence_not_repeated'] = reusable
    files = source_closure() + [reference(p) for p in (
        scope.PLAN_FILE, scope.PANEL_FILE, scope.CPU_POOL_FILE, scope.RECOVERY_FILE,
        scope.USER_GRANT_FILE, scope.USER_PROPOSAL_FILE, scope.PRIOR_COMPLETION_FILE,
        scope.BUDGET_BASELINE_FILE, scope.NETWORK_RESOLUTION_FILE, scope.CA_PROFILE_FILE,
        host.SCHEMAS, bundle.OUTPUT/'manifest.json', scope.API_ROOT/'coordinator-unit.json')]
    sources = write_new(scope.SOURCE_FILE, {'version': scope.VERSION, 'files': files,
        'controls': controls, 'prepared_grading_identity_verified': verified,
        'runtime_authorized': False})
    value = {'version': scope.VERSION, 'status': 'prepared', 'runtime_authorized': False,
        'user_instruction': '授权27题独立恢复', 'user_grant': reference(scope.USER_GRANT_FILE),
        'authorized_recovery_proposal': reference(scope.USER_PROPOSAL_FILE),
        'parent_authorization': reference(scope.PARENT_AUTH_FILE),
        'independent_recovery': reference(scope.RECOVERY_FILE), 'prior_completion': completed_prior,
        'plan': reference(scope.PLAN_FILE), 'source_index': sources, 'constraints': scope.CONSTRAINTS,
        'controls': controls, 'execution_alignment_version': ALIGNMENT,
        'API_cash_cap_CNY': scope.CASH_CAP_CNY, 'cash_budget_scope': scope.CASH_MODE,
        'ledger_path': str(scope.LEDGER_FILE), 'cash_before_run': reference(scope.BUDGET_BASELINE_FILE),
        'additional_cash': 0, 'new_generation_attempts': 27,
        'cumulative_maximum_containers': 304, 'cumulative_maximum_named_volumes': 83,
        'maximum_containers': 108, 'maximum_named_volumes': 27,
        'new_model_tokens_upper_bound': 135000000, 'new_neutral_calls': 0,
        'new_diagnostics': 0, 'new_controls': 0,
        'API_qualification_reused': recovery['prior_API_qualification'],
        'source_bundle': bundle_ref, 'actual_PROJECT_schemas': schemas_ref,
        'maximum_generation_pairs': 16, 'maximum_graders': 2,
        'combined_CPU': 112, 'combined_memory_GiB': 576,
        'maximum_TLS_sessions': 2, 'maximum_external_grading_connections': 1024,
        'maximum_external_grading_payload_bytes': 128*1024**2,
        'network_resolution': reference(scope.NETWORK_RESOLUTION_FILE),
        'CA_profile': reference(scope.CA_PROFILE_FILE), 'container_network': 'none',
        'container_cap_drop': ['ALL'], 'host_binds': 0, 'host_listeners': 0, 'GPUs': 0,
        'shared_host_configuration_changes': 0, 'ordinary_user_unit': scope.API_UNIT,
        'old_unknown_results_and_costs_preserved': True,
        'dispatch_admission': plan['dispatch_admission'], 'execution_started': False}
    PROPOSAL.parent.mkdir(parents=True, exist_ok=True)
    return {'proposal': write_new(PROPOSAL, value), 'source_index': sources, 'runtime_authorized': False}


if __name__ == '__main__':
    print(json.dumps(seal(), ensure_ascii=False))
