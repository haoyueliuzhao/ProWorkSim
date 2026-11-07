"""Key-free runtime binding for explicitly authorized independent v146 recovery.

These functions only return configuration bytes. No Docker client, API client,
experiment inventory, credential file or authority is created here.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .software_benchmark_alignment_contract_v146 import (
    shared_strategy, validate_condition, validate_controller_identity, validate_plan_identity,
)
from . import software_role_baseline_contract_v141 as roles
from .software_benchmark_candidates_v054 import checked
from .software_benchmark_public_tests_v110 import (
    VERSION as TEST_VERSION, capabilities, contract_for_actor,
)
from .storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_FILES = {'public_test_library_sha256': ROOT/'tools/public_test_library_v141.py',
                'public_test_launcher_sha256': ROOT/'tools/run_public_tests_v141.py',
                'public_test_dependency_helper_sha256': ROOT/'tools/public_test_dependencies_v130.py',
                'public_test_execution_sha256': ROOT/'tools/public_test_execution_v141.py',
                'public_test_evidence_sha256': ROOT/'tools/public_test_evidence_v141.py'}
RESULT_REVISION = 'v141-session-bound-public-test-execution-r1'



def public_dependency_descriptor(instance_id):
    # This is an explicitly prepared public baseline profile, not a model-selected
    # package installation. Other tasks retain their original environment.
    path = ROOT/'artifacts/software-benchmark-v130/public-dependencies-r1/manifest.json'
    manifest = json.loads(path.read_bytes())
    if instance_id != manifest['instance_id']:
        return None
    from .software_benchmark_candidates_v054 import reference
    return {'version': manifest['version'], 'instance_id': instance_id,
            'actor_root': manifest['actor_root'], 'manifest': reference(path)}


def actor_inputs(base_config, *, public_test_entry, row):
    """Extend an already admitted actor layout, preserving its outer limits."""
    validate_plan_identity(row)
    spec = roles.organization(row['organization_id'])
    config = copy.deepcopy(base_config)
    if config.get('instance_id') != row['instance_id']:
        raise ValueError('The actor and role-baseline row belong to different tasks')
    config.update(organization_id=spec['id'], fixed_members=list(spec['fixed_members']),
                  member_count=spec['member_count'], role_contract_version=roles.VERSION,
                  role_catalog_sha256=roles.catalog_sha256())
    if any(key in config for key in (*PUBLIC_FILES, 'public_test_contract_sha256')):
        raise ValueError('The public actor test contract must be bound once')
    config['public_test_entry'] = copy.deepcopy(public_test_entry)
    config['public_test_dependencies'] = public_dependency_descriptor(config['instance_id'])
    if config.get('public_fixture_diagnostic') is not None:
        raise ValueError('Old fixture qualifications cannot be reused with v141')
    config['public_test_result_revision'] = RESULT_REVISION
    contract = contract_for_actor(config)
    raw = json_bytes(contract)
    config.update(public_test_contract_sha256=digest(raw),
                  **{key: digest(path.read_bytes()) for key, path in PUBLIC_FILES.items()})
    return {'config': config, 'public_test_contract': contract,
            'files': {'public-test-contract.json': raw,
                      'public-test-dependencies.json': json_bytes(config['public_test_dependencies'])},
            'initial_file_mode': 0o444, 'initial_file_uid': 0,
            'PROJECT_authority': 'admitted config retained by isolated PID1',
            'REF_file_is_immutable_authority': False, 'Docker_operations': 0}


def validate_actor_selection(ready, expected):
    if (ready.get('public_test_result_revision') != RESULT_REVISION
            or expected.get('public_test_result_revision') != RESULT_REVISION
            or ready.get('public_test_selection_revision') != TEST_VERSION
            or ready.get('public_test_contract_sha256') != expected['public_test_contract_sha256']):
        raise ValueError('The actor did not initialize the exact selected-test protocol')
    spec = roles.organization(expected.get('organization_id'))
    for key, value in {'organization_id': spec['id'], 'fixed_members': spec['fixed_members'],
                       'member_count': spec['member_count'], 'role_contract_version': roles.VERSION,
                       'role_catalog_sha256': roles.catalog_sha256()}.items():
        if ready.get(key) != value or expected.get(key) != value:
            raise ValueError('The actor role roster or role contract is stale')
    if ready.get('public_test_files_sha256') != {key: expected[key] for key in PUBLIC_FILES}:
        raise ValueError('The actor did not load the exact public-test implementation files')
    descriptor = expected.get('public_test_dependencies')
    profile = ready.get('public_dependency_profile')
    if (ready.get('public_dependency_admission_checked') is not True
            or (descriptor is None and profile is not None)
            or (descriptor is not None and (not isinstance(profile, dict)
                or profile.get('manifest_sha256') != descriptor['manifest']['sha256']
                or profile.get('instance_id') != expected['instance_id']))):
        raise ValueError('The actor did not admit the same public dependency overlay')
    return {'public_test_result_revision': RESULT_REVISION,
            'public_test_selection_revision': TEST_VERSION,
            'public_test_contract_sha256': ready['public_test_contract_sha256'],
            'public_test_files_sha256': ready['public_test_files_sha256'],
            'role_contract_version': roles.VERSION, 'role_catalog_sha256': roles.catalog_sha256()}


def public_test_guidance(arm, entry):
    exposed = capabilities(entry)
    capability = json.dumps(exposed, ensure_ascii=False, sort_keys=True)
    shapes = {
        'pytest': ({'kind': 'pytest', 'targets': ['tests/test_example.py::test_case'],
                    'keyword': 'case and not slow', 'markers': 'not slow'},
                   'kind, targets, optional keyword (-k), optional markers (-m)'),
        'django': ({'kind': 'django', 'targets': ['example.tests.ExampleTests.test_case']},
                   'kind, targets (public dotted test labels)'),
        'sympy': ({'kind': 'sympy', 'targets': ['sympy/core/tests/test_example.py'],
                   'keywords': ['case']}, 'kind, targets, optional keywords (native -k list)'),
    }
    common = ('Public testing uses the declared task interpreter and /testbed. '
              'Choose targets from the public repository and issue; no hidden acceptance tests are provided. '
              'Omitting selection runs the original public entry. Supported selections: ' + capability)
    if exposed['frontend'] in shapes:
        example, fields = shapes[exposed['frontend']]
        common += ('\nAllowed fields: ' + fields + '. Shape example only: '
                   + json.dumps(example, sort_keys=True)
                   + '. Replace all example targets and filters with those found in this public repository.')
    if arm == 'REF':
        return common + ('\nThe shared convenience entry is '
            '/opt/pws-runtime/bin/python /opt/pws-runtime/public-test.py '
            "--selection '<selection JSON>'. It is available through the native terminal; "
            'other native terminal capabilities remain available. It produces no PROJECT submission evidence.')
    if arm == 'PROJECT':
        return common + ('\nUse run_tests(selection=<selection object>), then copy next_cursor exactly '
            'when reading its public output. A selected test is evidence only for its recorded source '
            'version and selected scope, not a claim that every public or hidden test passed. '
            'A zero-test, all-skipped or unverified run is not reported as passed; inspect validation_status and counts.')
    raise ValueError('Only the two single-agent conditions are defined')


def controller_inputs(host_config, row, ready, model_identity, endpoint, *, diagnostic=False,
                      public_context=None, public_environment=None, public_test_entry=None,
                      file_policy=None, gitlinks=None, actor_config=None, content_tokenizer=None):
    """Project public fields only; a future host must separately authorize its plan."""
    from .software_benchmark_content_tokenizer_v141 import descriptor, validate_descriptor
    tokenizer = validate_descriptor(descriptor() if content_tokenizer is None else content_tokenizer)
    validate_plan_identity(row)
    condition_raw = checked(host_config['configuration']).read_bytes()
    condition = json.loads(condition_raw)
    validate_condition(condition)
    arm = row['arm']
    if (arm != 'PROJECT' or condition['arm'] != arm
            or row.get('model_key') != 'DEEPSEEK'
            or any(host_config.get(key) != row[key] for key in ('slot_id', 'seed', 'source_slot_id', 'condition_id'))
            or condition['condition_id'] != row['condition_id']):
        raise ValueError('Bind the new aligned public task, condition and attempt identity')
    if diagnostic:
        if model_identity:
            raise ValueError('A zero-model diagnostic cannot acquire model identity')
    elif model_identity.get('thinking') is not False:
        raise ValueError('This preparation retains the explicit nonthinking model route')
    if actor_config is None:
        raise ValueError('The independently admitted actor config is required to bind the public contract')
    validate_actor_selection(ready, actor_config)
    from .software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION, terminal_initialization_action
    if (not isinstance(public_context, dict) or public_context.get('version') != CONTEXT_VERSION
            or public_context.get('instance_id') != row['instance_id']):
        raise ValueError('Use the same admitted public execution context for both conditions')
    terminal_initialization_action(public_environment)
    entry = copy.deepcopy(public_test_entry or host_config['public_test_entry'])
    if entry != actor_config['public_test_entry']:
        raise ValueError('Both controller and actor must use the same fixed public entry')
    safe_identity = {key: model_identity[key] for key in (
        'model', 'model_key', 'model_revision', 'documented_model_version', 'vllm_version', 'raw_release',
        'adapter_sha256', 'model_manifest_sha256', 'context_limit', 'max_output_tokens',
        'service_admission_complete', 'port', 'deployment_version', 'thinking',
        'provider_model_alias', 'provider_weight_revision_pinnable') if key in model_identity}
    public = host_config['public_task']
    config = {'version': 'v146-role-baseline-controller-r1',
        'slot_id': row['slot_id'], 'source_slot_id': row['source_slot_id'], 'seed': row['seed'],
        'condition_id': row['condition_id'], 'execution_arm': arm, 'model_key': 'DEEPSEEK',
        'configuration': {'path': '/pws/control/condition.json', 'sha256': digest(condition_raw), 'bytes': len(condition_raw)},
        'public_task': {key: public[key] for key in ('instance_id', 'repo', 'base_commit', 'problem_statement')},
        'ref_endpoint': endpoint, 'model_identity_value': safe_identity, 'output': '/pws/output',
        'start': '/pws/control/start.json', 'ready': '/pws/control/actor-ready.json',
        'diagnostic': bool(diagnostic),
        'measurement_kind': 'zero_model_diagnostic' if diagnostic else 'full_verified_comparison',
        'execution_alignment': shared_strategy(row['organization_id']),
        'organization_id':row['organization_id'], 'group_id':row['group_id'],
        'fixed_members':list(row['fixed_members']), 'member_count':row['member_count'],
        'public_test_contract_sha256': actor_config['public_test_contract_sha256'],
        'public_test_result_revision': RESULT_REVISION,
        'public_test_files_sha256': ready['public_test_files_sha256'],
        'role_contract_version': roles.VERSION, 'role_catalog_sha256': roles.catalog_sha256(),
        'public_test_entry': entry, 'content_tokenizer': tokenizer,
        'public_context': {key: public_context[key] for key in ('version', 'visible_text', 'visible_facts')},
        'public_environment': {key: public_environment[key] for key in
                               ('kind', 'image_id', 'source_config_sha256', 'public_python')}}
    config['public_context']['visible_text'] += '\n\n' + public_test_guidance(arm, entry)
    if actor_config.get('public_test_dependencies') is not None:
        config['public_context']['visible_text'] += ('\nThe documented public-test entry adds the frozen public pytest-httpbin/httpbin dependencies. '
            'It preserves task files, the interpreter and pytest version, with explicit legacy-raises and httpbin compatibility fixes. Raw terminal commands may not include '
            'this convenience environment. Fixture availability is not a claim that tests or TLS passed.')
    config['public_environment']['environment'] = {
        key: public_environment['environment'][key] for key in ('PATH', 'CONDA_PREFIX', 'CONDA_DEFAULT_ENV')
        if key in public_environment['environment']}
    if arm == 'PROJECT':
        from .repository_sources_v054 import normalize_policy
        config['file_policy'] = normalize_policy(file_policy if file_policy is not None else host_config.get('file_policy'))
        config['dataset_revision'] = host_config['dataset_revision']
        config['gitlinks'] = gitlinks if gitlinks is not None else host_config.get('gitlinks', [])
    validate_controller_identity(config, arm)
    return {'condition.json': condition_raw, 'actor-ready.json': json_bytes(ready),
            'controller-config.json': json_bytes(config)}
