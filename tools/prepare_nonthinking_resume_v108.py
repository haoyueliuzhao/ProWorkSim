"""Prepare and seal a continuation within the user's existing bounded authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json

from proworksim import software_benchmark_scope_v108 as scope
from proworksim import software_benchmark_scope_v107 as previous
from proworksim import software_benchmark_resume_inventory_v108 as inventory
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ARTIFACT = scope.ROOT/'artifacts/software-benchmark-v108/deployment-amendment-r1'


def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():
        raise ValueError('Entered runtime preparation is immutable')
    inventory_ref = inventory.prepare()
    from proworksim import software_benchmark_host_api_v108 as host
    from proworksim import software_benchmark_sdk_bundle_v108 as bundle
    from proworksim.software_benchmark_episode_v108 import build_episode
    schemas = host.prepare_schemas()
    episode = build_episode(guard=lambda *_a, **_kw: {'plan': reference(scope.PLAN_FILE)})
    if (episode.runtime is not bundle or episode._run.__globals__['runtime'] is not bundle
            or episode.OwnedActorPair.__init__.__globals__['policy'].AUTHORIZATION_FILE != scope.AUTH_FILE
            or host.DeepSeekRuntime.transport_factory.__globals__['scope'] is not scope):
        raise ValueError('The actual controller bundle, provider or model broker is bound to an old deployment')
    spec = importlib.util.spec_from_file_location('v108_prepare_launcher',
        scope.ROOT/'tools/launch_nonthinking_interface_v108.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    launched = launcher.prepare()
    proof = {'version': 'v108-original-57-runtime-preparation-r1', 'passed': True,
        'inventory': inventory_ref, 'bundle': reference(bundle.OUTPUT/'manifest.json'),
        'actual_tool_schemas': schemas, 'launch_specification': launched['specification'],
        'actual_episode_controller_and_broker_binding': True,
        'original_model_samples_replayed': 0, 'API_calls': 0, 'Docker_operations': 0,
        'service_operations': 0, 'GPU_operations': 0}
    return scope.retain(ARTIFACT/'preparation.json', proof)


def seal(*, budget_controls):
    if scope.AUTH_FILE.exists() or scope.SOURCE_FILE.exists() or (scope.API_ROOT/'execution-started.json').exists():
        raise ValueError('An approved or entered source set may not be resealed')
    prepared = scope.load(reference(ARTIFACT/'preparation.json'))
    controls = {
        'runtime': reference(scope.ROOT/'artifacts/software-benchmark-v108/runtime-control-r1/summary.json'),
        'scoring': reference(scope.ROOT/'artifacts/software-benchmark-v108/scoring-control-r1/summary.json'),
        'budget_closure': reference(budget_controls),
        'HTTP_validity': reference(scope.ROOT/'artifacts/software-benchmark-v108/http-validity-control-r1/summary.json'),
    }
    for name, ref in controls.items():
        value = scope.load(ref)
        if value.get('passed') is not True or value.get('API_calls', value.get('model_calls')) != 0:
            raise ValueError('Bounded CPU control did not pass: '+name)
    reconciled = scope.load(reference(scope.COORDINATOR_RECONCILIATION))
    if reconciled.get('released') is not True:
        raise ValueError('The exact stopped owner has not released its local capacity')
    if any((scope.BATCH_ROOT/'resource-claims').glob('active-*.json')):
        raise ValueError('The predecessor still has an active local capacity identity')
    qualification_ref = reference(scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json')
    qualifications = scope.load(qualification_ref)
    if (len(qualifications.get('qualifications', {})) != 50
            or qualifications.get('controls') != [] or qualifications.get('reuse_failures') != {}
            or any(value.get('status') != 'qualified' for value in qualifications['qualifications'].values())):
        raise ValueError('The continuation requires all 50 prior qualifications without new controls')
    old_auth = scope.load(reference(previous.AUTH_FILE))
    paths = sorted({p.resolve() for directory in ('src/proworksim', 'tools', 'tests')
                    for p in (scope.ROOT/directory).glob('*_v108.py')})
    paths.extend(scope.ROOT/'src/proworksim'/name for name in (
        'software_benchmark_requests_tls_v068.py', 'software_benchmark_grading_recovery_v068.py'))
    source_ref = write_new(scope.SOURCE_FILE, {'version': scope.VERSION,
        'files': [reference(path) for path in paths],
        'original_source_chain': reference(previous.SOURCE_FILE),
        'runtime_bundle': prepared['bundle'], 'actual_tool_schemas': prepared['actual_tool_schemas'],
        'controls': controls, 'preparation': reference(ARTIFACT/'preparation.json'),
        'API_calls': 0, 'Docker_operations': 0, 'service_operations': 0})
    authorization = {'version': scope.VERSION, 'status': 'approved',
        'original_authorization': reference(scope.previous.AUTH_FILE),
        'prior_deployment_authorization': reference(previous.AUTH_FILE),
        'source_index': source_ref, 'plan': reference(scope.PLAN_FILE),
        'constraints': scope.CONSTRAINTS, 'API_cash_cap_CNY': scope.CASH_CAP_CNY,
        'new_generation_attempts': 100, 'remaining_original_attempts': 57,
        'preserved_original_attempts': 43, 'additional_generation_attempts': 0,
        'resume_inventory': prepared['inventory'],
        'coordinator_reconciliation': reference(scope.COORDINATOR_RECONCILIATION),
        'same_owned_user_unit': scope.API_UNIT, 'additional_containers': 0, 'additional_volumes': 0,
        'diagnostics_repeated': 0, 'old_grading_jobs_replayed': 0,
        'same_independent_ledger': str(scope.LEDGER_FILE),
        'new_lifecycle_metadata_root': str(scope.API_ROOT), 'new_coordinator_lease': str(scope.LEASE_FILE),
        'shared_host_configuration_changes': 0, 'GPU_operations': 0, 'system_services_changed': 0,
        'preparation_recovery': old_auth['preparation_recovery'],
        'reused_API_qualification': old_auth['reused_API_qualification'],
        'qualification_reuse': qualification_ref, 'runtime_controls': controls,
        'new_preparation_API_requests': 0, 'existing_preparation_calls_retained': 2,
        'original_results_and_cash_unchanged': True,
        'scope_inherited_from_original_authorization': True,
        'user_resume_request': '恢复实验，同时技术未知具体是什么？是否有系统性缺陷',
        'approval_basis': 'Resume only the 57 unused original task identities within the already approved 350 CNY and unchanged resource pool.',
        'changes': ['bind TLS finish to the actual scoring function globals',
                    'separate proven physical cleanup from unresolved CA/scoring evidence',
                    'recognize the exact no-dispatch REF budget exception for terminal candidate export',
                    'import 43 immutable original attempts and usage; dispatch only the original 57 unused rows'],
        'recorded_utc': datetime.now(timezone.utc).isoformat()}
    proposal = write_new(ARTIFACT/'proposal.json', {**authorization,
        'status': 'original_authorized_scope_continuation_ready', 'authorization_created': False})
    authorization['proposal'] = proposal
    auth_ref = write_new(scope.AUTH_FILE, authorization)
    scope.require_allowed()
    return {'authorization': auth_ref, 'source_index': source_ref, 'proposal': proposal,
            'API_calls': 0, 'Docker_operations': 0, 'service_operations': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--seal', action='store_true')
    parser.add_argument('--budget-controls', type=scope.Path)
    args = parser.parse_args()
    if args.seal and args.budget_controls is None:
        parser.error('--seal requires the existing --budget-controls receipt')
    print(json.dumps(prepare() if args.prepare else seal(budget_controls=args.budget_controls), ensure_ascii=False))
