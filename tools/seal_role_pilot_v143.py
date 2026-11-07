"""Prepare and seal a reviewable pilot proposal; never grant or start runtime work."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path

from proworksim import software_benchmark_scope_v143 as scope
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.storage import digest

VERSION = 'v143-zero-model-deployment-recovery-seal-r1'
BUDGET_GRANT = scope.ROOT/'artifacts/software-benchmark-v142/budget-grant-r1/authorization.json'
PYTEST_PLAN = scope.BATCH_ROOT/'pytest10081-offline-build-plan.json'
PYTEST_PROVENANCE = scope.BATCH_ROOT/'pytest-build-preparation/provenance.json'
MEMBER_INVENTORY = scope.ROOT/'artifacts/software-benchmark-v141/member-schema-r1/inventory.json'
CONTROL_PATHS = {
    'P0_integration': 'artifacts/software-benchmark-v141/p0-integration-r1/summary.json',
    'host': 'artifacts/software-benchmark-v142/host-controls-r1/summary.json',
    'host_routes': 'artifacts/software-benchmark-v142/host-route-controls-r1/summary.json',
    'queue': 'artifacts/software-benchmark-v142/coordinator-cpu-r1/summary.json',
    'grading': 'artifacts/software-benchmark-v141/grading-environment-repair-r1/summary.json',
    'seal': 'artifacts/software-benchmark-v142/seal-controls-r1/summary.json',
    'native_startup_repair':'artifacts/software-benchmark-v143/native-startup-controls-r1/summary.json',
    'recovery_scope':'artifacts/software-benchmark-v143/recovery-binding-controls-r1/summary.json',
    'diagnostic_error_handling':'artifacts/software-benchmark-v143/diagnostic-runner-controls-r1/summary.json',
    'host_deployment':'artifacts/software-benchmark-v143/host-deployment-controls-r1/summary.json',
}
REQUIRED_SOURCE_NAMES = (
    'src/proworksim/software_benchmark_scope_v142.py',
    'src/proworksim/software_benchmark_episode_v142.py',
    'src/proworksim/software_benchmark_host_api_v142.py',
    'src/proworksim/software_benchmark_deepseek_api_v142.py',
    'src/proworksim/software_benchmark_grading_v142.py',
    'src/proworksim/software_benchmark_environment_v141.py',
    'src/proworksim/software_benchmark_grading_repairs_v141.py',
    'src/proworksim/software_benchmark_sdk_bundle_v141.py',
    'src/proworksim/software_role_baseline_runtime_v141.py',
    'tools/run_role_pilot_v142.py', 'tools/launch_role_pilot_v142.py',
    'tools/activate_role_pilot_v142.py',
    'tools/check_httpbin_direct_v142.py', 'tools/run_offline_scorer_v096.py',
)


def source_closure(root=None, *, roots=None):
    """Read local Python import/literal dependencies; never import their runtime."""
    root = Path(root or scope.ROOT).resolve()
    if roots is None:
        roots = [root/name for name in REQUIRED_SOURCE_NAMES]
        roots += [path for folder in ('src/proworksim', 'tools', 'tests')
                  for version in (141, 142, 143) for path in (root/folder).glob(f'*v{version}.py')]
    pending, found = list(roots), {}
    while pending:
        path = Path(pending.pop()).resolve()
        if path in found:
            continue
        if not path.is_relative_to(root) or path.suffix != '.py' or not path.is_file():
            raise ValueError('Source closure requires an existing local Python file: '+str(path))
        found[path] = reference(path)
        try:
            package = '.'.join(path.relative_to(root/'src').with_suffix('').parts).rsplit('.', 1)[0]
        except ValueError:
            package = None
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literal = node.value
                if literal.endswith('.py') and '\n' not in literal:
                    targets = ([root/folder/literal for folder in ('tools', 'src/proworksim', 'tests')]
                               if Path(literal).name == literal else
                               [root/literal] if literal.startswith(('tools/', 'src/', 'tests/')) else [])
                    pending.extend(p for p in targets if p.is_file())
                elif literal.startswith('proworksim.') and all(part.isidentifier() for part in literal.split('.')):
                    names.append(literal)
            if isinstance(node, ast.Import):
                names += [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if package is None:
                        continue
                    base = '.'.join(package.split('.')[:len(package.split('.'))-node.level+1])
                    full = base+('.'+node.module if node.module else '')
                else:
                    full = node.module or ''
                names += [full, *[full+'.'+item.name for item in node.names]]
            for name in names:
                if name == 'proworksim' or name.startswith('proworksim.'):
                    target = root/'src'/Path(*name.split('.'))
                    for candidate in (target.with_suffix('.py'), target/'__init__.py'):
                        if candidate.is_file():
                            pending.append(candidate)
                            break
    return [found[path] for path in sorted(found)]


def validate_budget_grant(value):
    if (value.get('version') != 'v142-api-budget-user-grant-r1'
            or value.get('API_cash_cap_CNY') != '400.00'
            or value.get('cash_scope') != 'new independent pilot ledger, all3groups combined'
            or value.get('planned_tasks') != 40 or value.get('planned_episodes') != 120
            or value.get('planned_groups') != list(scope.GROUP_IDS)
            or value.get('team_input_output_token_cap') != 5_000_000
            or value.get('batch_input_output_token_cap') != 600_000_000
            or value.get('authorizes_root_equivalent_runtime_resources') is not False
            or value.get('changes_old_ledgers') is not False
            or value.get('budget_guarantees_completion') is not False):
        raise ValueError('The actual user cash grant is not the common400-CNY pilot budget')
    return value


def validate_review_shapes(plan, bundle, schemas, unit, budget):
    validate_budget_grant(budget)
    if (len(plan.get('rows', [])) != 120 or len(plan.get('environments', {})) != 40
            or plan.get('constraints') != scope.CONSTRAINTS
            or set(schemas.get('schemas', {})) != set(scope.GROUP_IDS)
            or schemas.get('neutral_calls') != 0 or schemas.get('provider_search_or_fetch') is not False
            or set(bundle.get('probe', {}).get('organization_ids', [])) != set(scope.GROUP_IDS)
            or bundle['probe'].get('model_calls') != 0
            or bundle['probe'].get('all_controller_and_worker_entrypoints_imported') is not True
            or bundle['probe'].get('exact_local_content_counter_executed') is not True
            or any(bundle['probe'].get('forbidden_operation_counts', {}).values())
            or bundle.get('content_tokenizer', {}).get('require_content_counter') is not True):
        raise ValueError('Three actual role schemas, exact local counter and offline bundle must match the120 panel')
    if (scope.CONTAINER_PARENT is not None or len(set(map(str, scope.LEDGER_FILES.values()))) != 1
            or unit.get('unit') != scope.API_UNIT or unit.get('system_parent_slice') is not None
            or unit.get('memory_max_bytes') != 32*scope.GIB or unit.get('memory_high_bytes') != 30*scope.GIB
            or unit.get('memory_swap_max_bytes') != 0 or unit.get('cpu_quota_percent') != 800
            or unit.get('restart') != 'no' or unit.get('root_operations') != 0):
        raise ValueError('Only one new ordinary-user manager and one shared400 ledger are planned')
    for group in scope.GROUP_IDS:
        rows = [row for row in plan['rows'] if row['organization_id'] == group]
        if (len(rows) != 40 or set(schemas['schemas'][group]) != set(rows[0]['fixed_members'])
                or len({row['instance_id'] for row in rows}) != 40):
            raise ValueError('The paired task panel or actual group member schemas changed')
    return {'passed': True, 'runtime_authorized': False, 'live_environment_admission_complete': False,
            'one_common_cash_ledger': True, 'new_system_parent_slice': False}


def ensure_unentered():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Sealing is only an ordinary-user local file operation')
    blocked = [scope.AUTH_FILE, scope.USER_GRANT_FILE, scope.SOURCE_FILE, scope.PROPOSAL_FILE,
               scope.LEDGER_FILE, scope.CLAIM_FILE, scope.LEASE_FILE,
               scope.API_ROOT/'launch-intent.json', scope.API_ROOT/'execution-started.json']
    if any(path.exists() for path in blocked):
        raise PermissionError('An approved, entered, claimed, accounted or sealed pilot cannot be resealed')


def read_control(path):
    path = Path(path)
    value = json.loads(path.read_bytes())
    if value.get('passed') is not True:
        raise ValueError('A necessary pure CPU control lacks a passed gate: '+str(path))
    for item in value.get('sources', []):
        source = Path(item['path'])
        source = source if source.is_absolute() else scope.ROOT/source
        if digest(source.read_bytes()) != item['sha256']:
            raise ValueError('CPU control predates its recorded source: '+str(source))
    return reference(path)


def postgrant_sequence():
    return ['reuse_completed_endpoint_probe', 'cold_grading_preparation', 'launch_unique_user_coordinator']


def build_proposal(*, plan_ref, source_ref, bundle_ref, schemas_ref, unit_ref, controls, review,
                   payloads, cold_preparation):
    from proworksim.software_benchmark_alignment_contract_v141 import VERSION as ALIGNMENT
    return {'version': scope.VERSION, 'status': 'prepared', 'runtime_authorized': False,
        'execution_started': False, 'execution_alignment_version': ALIGNMENT,
        'plan': plan_ref, 'source_index': source_ref, 'constraints': scope.CONSTRAINTS,
        'different_tasks': 40, 'new_generation_attempts': 120, 'same_original_unconsumed120':True,
        'retired_original_diagnostic':1, 'replacement_diagnostic':5,
        'standing_Docker_policy':reference(scope.STANDING_POLICY_FILE),
        'prior_zero_model_stop':reference(scope.PRIOR_COMPLETION_FILE), 'organizations': list(scope.GROUP_IDS),
        'API_budget_user_grant': reference(BUDGET_GRANT), 'API_cash_cap_CNY': '400.00',
        'cash_budget_scope': scope.CASH_MODE, 'ledger_paths': {g: str(p) for g, p in scope.LEDGER_FILES.items()},
        'one_shared_ledger_not_three400_caps': True, 'old_ledgers_opened_or_changed': False,
        'budget_guarantees_all_tasks_complete': False, 'new_model_tokens_upper_bound': 600_000_000,
        'team_input_output_token_cap': 5_000_000, 'tokens_are_shared_per_team_not_per_member': True,
        'new_neutral_API_calls': 0, 'maximum_containers': 570, 'maximum_named_volumes': 125,
        'maximum_generation_pairs': 16, 'maximum_concurrent_startups': 4, 'maximum_graders': 2,
        'new_diagnostic_pairs': 4, 'diagnostic_model_calls': 0,
        'maximum_official_control_containers': 80, 'maximum_code_score_containers': 120,
        'maximum_delivery_score_containers': 120,
        'same_tree_delivery_reuse': 'Only this exact task/group/attempt locked code candidate',
        'new_system_manager_objects': 0, 'system_parent_slice': None,
        'ordinary_user_unit': scope.API_UNIT, 'coordinator_unit': unit_ref,
        'coordinator_CPU_quota_cores': 8, 'coordinator_memory_GiB': 32,
        'combined_CPU_quota_cores': 112, 'combined_memory_GiB': 840,
        'combined_memory_limit_kind': 'sum of bounded owned objects, including two4GiB host scorers',
        'maximum_TLS_scoring_sessions': 16, 'maximum_external_scoring_connections': 8192,
        'maximum_external_scoring_payload_bytes': 1024*1024**2,
        'additional_health_probe_connections': 0, 'additional_health_probe_application_bytes': 0,
        'original_probe_reused_connections': 4, 'original_probe_maximum_application_bytes':64*1024,
        'container_network': 'none', 'container_cap_drop': ['ALL'],
        'cap_add_except_declared_Requests_graders': [],
        'Requests_grader_cap_add': ['NET_ADMIN', 'NET_BIND_SERVICE'],
        'scoring_egress': 'Only frozen httpbin.org public addresses80/443 after bounded direct probe',
        'API_egress': 'Direct DeepSeek HTTPS, no reverse proxy, no provider web/search tools',
        'CA_profile': reference(scope.CA_PROFILE_FILE), 'host_binds': 0, 'host_listeners': 0, 'GPUs': 0,
        'shared_host_configuration_changes': 0, 'existing_units_or_other_tasks_modified': False,
        'mount_network_driver_cgroup_global_configuration_changes': False,
        'cleanup': 'Only this batch exact-owned IDs with retained identity and quiescence proof',
        'provider_search_or_fetch': False, 'automatic_retry_or_resampling': False,
        'task_local_anomalies': 'Quarantine original evidence and continue unrelated queue items',
        'source_bundle': bundle_ref, 'actual_member_schemas': schemas_ref,
        'payloads_verified_at_seal': payloads, 'controls': controls,
        'cold_preparation': cold_preparation, 'postgrant_sequence': postgrant_sequence(),
        'coordinator_gates_after_launch': [
            'four_zero_model_diagnostics_including_measured_large_repository_peak',
            'source_bound_gold_empty_admission_or_qualified_history_equivalence',
            'initialize_one_fresh400_CNY_ledger', 'asynchronous_generation_and_official_scoring',
            'quiescent_exact_owned_object_cleanup_and_manager_release'],
        'postgrant_admission_required': {'network_resolution': str(scope.NETWORK_RESOLUTION_FILE),
            'four_zero_model_diagnostics': str(scope.PREPARATION_QUALIFICATION_FILE),
            'fresh_gold_empty_or_exact_equivalence': str(scope.COORDINATOR_ROOT),
            'fresh_API_ledger': str(scope.LEDGER_FILE)},
        'live_environment_admission_complete': False, 'pure_review_shape': review,
        'no_approved_authorization_or_service_written_by_sealer': True}


def inspect_inputs():
    paths = {**{name: scope.ROOT/path for name, path in CONTROL_PATHS.items()},
             'plan': scope.PLAN_FILE, 'budget_grant': BUDGET_GRANT,
             'pytest_plan': PYTEST_PLAN, 'pytest_provenance': PYTEST_PROVENANCE,
             'member_inventory': MEMBER_INVENTORY}
    return {'version': VERSION, 'missing': [name for name, path in paths.items() if not path.is_file()],
            'paths': {name: str(path) for name, path in paths.items()},
            'source_seal_created': False, 'runtime_authorized': False, 'operations': 0}


def seal():
    """Freeze review artifacts only, after all cooperating authors have finished."""
    ensure_unentered()
    from proworksim import software_benchmark_host_api_v143 as host
    from proworksim import software_benchmark_sdk_bundle_v143 as bundle
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    budget = validate_budget_grant(scope.load(reference(BUDGET_GRANT)))
    controls = {name: read_control(scope.ROOT/path) for name, path in CONTROL_PATHS.items()}
    bundle_ref = reference(bundle.OUTPUT/'manifest.json')
    manifest = scope.load(bundle_ref)
    if manifest.get('version') != bundle.VERSION or manifest.get('adapter') != reference(bundle.__file__):
        raise ValueError('Prepared offline bundle differs from its final source')
    for item in (*manifest['source_tools'].values(), *manifest['project_modules'].values(),
                 manifest['archive'], manifest['member_inventory'], manifest['probe_source']):
        checked(item)
    for key in ('benchmark_scorer_or_gold_modules_included', 'host_key_files_included',
                'host_DeepSeek_API_or_cash_ledger_code_included', 'models_or_weights_included'):
        if manifest.get(key) is not False:
            raise ValueError('The actor bundle contains out-of-scope material')
    schemas_ref = host.prepare_schemas(MEMBER_INVENTORY)
    schemas = scope.load(schemas_ref)
    if schemas.get('runtime_bundle') != bundle_ref:
        raise ValueError('Actual member schemas bind another final bundle')
    checked(schemas['actual_member_inventory'])
    spec = importlib.util.spec_from_file_location('v142_review_launcher', scope.ROOT/'tools/launch_role_pilot_v143.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    unit_ref = launcher.prepare()['specification']
    unit = scope.load(unit_ref)
    review = validate_review_shapes(plan, manifest, schemas, unit, budget)
    pytest = scope.load(reference(PYTEST_PLAN))
    if (pytest.get('instance_id') != 'pytest-dev__pytest-10081' or len(pytest.get('wheels', [])) != 6
            or pytest.get('network_mode') != 'none' or pytest.get('automatic_download') is not False
            or pytest.get('host_installation') is not False or pytest.get('runtime_qualified') is not False):
        raise ValueError('The exact unqualified offline build dependency plan changed')
    payloads = {'bundle_archive': manifest['archive'], 'baseline_pyproject': pytest['baseline_pyproject'],
                'pytest_wheels': [row['wheel'] for row in pytest['wheels']]}
    for item in [payloads['baseline_pyproject'], *payloads['pytest_wheels']]:
        checked(item)
    cold = {}
    for name in ('scorer-manifest.json', 'qualification-preparation.json',
                 'provider-bindings/environments/offline.json',
                 'provider-bindings/environments/tls.json',
                 'provider-bindings/environments/bindings.json'):
        path = scope.COORDINATOR_ROOT/name
        if path.is_file():
            cold[name] = reference(path)
    files = source_closure()+[reference(path) for path in (
        scope.PLAN_FILE, scope.PANEL_FILE, scope.CPU_POOL_FILE, scope.SOURCE_PANEL_FILE,
        scope.SOURCE_PLAN_FILE, scope.CA_PROFILE_FILE, host.TOKENIZER, BUDGET_GRANT,
        scope.STANDING_POLICY_FILE, scope.PRIOR_COMPLETION_FILE,
        PYTEST_PLAN, PYTEST_PROVENANCE, PYTEST_PROVENANCE.with_name('baseline-source.json'))]
    for row in plan['rows']:
        files += [row['configuration'], scope.load(row['configuration'])['configuration']]
    files += [bundle_ref, schemas_ref, schemas['actual_member_inventory'], unit_ref,
              manifest['public_test_dependencies']['manifest'], *controls.values()]
    # Immutable cold evidence remains distinct from future live provider/network results.
    files += list(cold.values())
    files += [reference(path) for path in (scope.COORDINATOR_ROOT/'qualifications').glob('*.json')]
    files += [reference(path) for path in scope.GRADING_ROOT.glob('control-v142-*/request.json')]
    files = list({item['path']: item for item in files}.values())
    files.extend(scope.validate_original_probe_reuse()['references'])
    ensure_unentered()
    source_value = {'version': scope.VERSION, 'files': files, 'controls': controls,
        'runtime_authorized': False, 'live_environment_admission_complete': False,
        'runtime_data_excluded_from_static_source_index': True,
        'payloads_verified_at_seal': payloads,
        'payload_bytes_rechecked_before_own_upload_not_every_API_call': True,
        'cash_ledger_and_network_and_execution_receipts_are_not_static_source_inputs': True}
    scope.SOURCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    source_ref = write_new(scope.SOURCE_FILE, source_value)
    proposal = build_proposal(plan_ref=reference(scope.PLAN_FILE), source_ref=source_ref,
        bundle_ref=bundle_ref, schemas_ref=schemas_ref, unit_ref=unit_ref,
        controls=controls, review=review, payloads=payloads, cold_preparation=cold)
    scope.PROPOSAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    return {'proposal': write_new(scope.PROPOSAL_FILE, proposal), 'source_index': source_ref,
            'runtime_authorized': False, 'live_environment_admission_complete': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--inspect', action='store_true', help='Read-only readiness list; no hashes or seal written')
    modes.add_argument('--seal', action='store_true', help='Write source seal and unapproved review proposal only')
    args = parser.parse_args()
    print(json.dumps(inspect_inputs() if args.inspect else seal(), ensure_ascii=False))
