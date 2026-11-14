"""Cold official grading and explicit reuse of the original fifty control pairs.

Fresh resource identities and a private transport policy never reopen an old
grant. Preparation performs only local source/evidence reads and metadata writes.
"""
from __future__ import annotations

import argparse
import ast
import copy
from functools import lru_cache
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
from types import FunctionType, ModuleType

from . import software_benchmark_scope_v105 as scope
from . import software_benchmark_scorer_v066 as original
from . import software_benchmark_scorer_v062 as old_scorer
from . import software_benchmark_grading_environment_v066 as original_environment
from . import software_benchmark_requests_offline_v066 as original_offline
from . import software_benchmark_requests_tls_v066 as original_tls
from . import software_benchmark_tcp_transport_v066 as original_tcp
from . import software_benchmark_io_v088 as io_adapter
from .software_benchmark_candidates_v054 import reference, write_new, checked
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function

VERSION = 'v105-cold-official-paired-interface-scoring-r1'
REUSE_VERSION = 'v105-reused-v062-control-qualification-r1'
EQUIVALENCE_VERSION = 'v105-explicit-v062-official-environment-equivalence-r1'
MODULE = 'proworksim.software_benchmark_grading_v105'
OLD_MANIFEST = scope.ROOT / 'runs/software-benchmark-v062/capability-probe-r1-20261026/coordinator-r2/scorer-manifest.json'


def clean_environment():
    value = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONEXECUTABLE', 'LD_LIBRARY_PATH', 'LD_PRELOAD'):
        value.pop(key, None)
    return value


def command(arguments):
    return [str(scope.ROOT / '.venv/bin/python'), '-B', str(scope.ROOT / 'tools/run_offline_scorer_v096.py'),
            '-m', MODULE, *arguments]


def module_from(namespace, name):
    value = ModuleType(name)
    value.__dict__.update(namespace)
    return value


def subclass_with_globals(cls, namespace):
    methods = {key: clone_function(value, namespace) for key, value in vars(cls).items()
               if isinstance(value, FunctionType)}
    return type(cls.__name__, (cls,), methods)


def private_environment(policy):
    tcp_ns = clone_namespace(original_tcp, select=io_adapter.POLL_SELECT)
    tcp_ns['_authorize'] = lambda task: policy.require_v066_allowed('v066.transport', instance_id=task)
    tcp = module_from(tcp_ns, __name__ + '.tcp')
    offline_ns = clone_namespace(original_offline, require_v066_allowed=policy.require_v066_allowed)
    old_offline_manifest = offline_ns['environment_manifest']

    def offline_manifest():
        return {**old_offline_manifest(), 'dispatch_guard': reference(scope.__file__),
                'authorization_bound_by': 'v105 plan and request; no grant hashed into its own source manifest'}

    offline_ns['environment_manifest'] = offline_manifest
    offline_ns['EnvironmentContainer'] = subclass_with_globals(original_offline.EnvironmentContainer, offline_ns)
    offline = module_from(offline_ns, __name__ + '.offline')
    tls_ns = clone_namespace(original_tls, prior=offline, transport=tcp, policy=policy)
    tls_ns['EnvironmentContainer'] = subclass_with_globals(original_tls.EnvironmentContainer, tls_ns)
    tls = module_from(tls_ns, __name__ + '.tls')
    return module_from(clone_namespace(original_environment, policy=policy, offline=offline, tls=tls),
                       __name__ + '.environment')


def scorer(policy, *, manifest_provider=None):
    environment = private_environment(policy)
    namespace = clone_namespace(original, policy=policy, environment=environment,
        BATCH_ROOT=scope.BATCH_ROOT, VERSION=VERSION)
    native_qualification = namespace['validate_qualification']

    def validate_qualification(ref, config, plan_ref):
        value = scope.load(ref)
        if value.get('version') == REUSE_VERSION:
            return validate_reused_qualification(ref, config, plan_ref)
        return native_qualification(ref, config, plan_ref)

    namespace['validate_qualification'] = validate_qualification
    native_manifest = namespace['installation_manifest']

    def installation_manifest():
        if manifest_provider is not None:
            return copy.deepcopy(manifest_provider())
        return {**native_manifest(), 'scoring_adapter': reference(__file__),
            'scorer_interpreter_profile': 'cold_v096_launcher_without_API_tokenizer_overlay',
            'host_launcher': reference(scope.ROOT / 'tools/run_offline_scorer_v096.py'),
            'host_library_threads': 1, 'scoring_policy_scope': reference(scope.__file__),
            'host_poll_adapter': reference(io_adapter.__file__),
            'old_qualification_validator': reference(old_scorer.__file__),
            'scoring_or_test_logic_changed': False, 'candidate_reselection': False,
            'old_resource_authority_reopened': False}

    namespace['installation_manifest'] = installation_manifest
    namespace['ObservedContainer'] = subclass_with_globals(original.ObservedContainer, namespace)
    namespace['Containers'] = subclass_with_globals(original.Containers, namespace)
    return module_from(namespace, __name__ + '.official_scorer')


@lru_cache(maxsize=1)
def cold_manifest():
    completed = subprocess.run(command(['--manifest']), cwd=scope.ROOT, env=clean_environment(),
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
    if completed.returncode:
        raise RuntimeError('Cold scorer manifest failed: ' + completed.stderr[-2500:])
    return json.loads(completed.stdout)


def _ast_identity(path, *, router=False):
    text = checked(reference(path)).read_text().replace('v066', 'v062').replace('v064', 'v062')
    if router:
        # Both helpers only serialize and exclusively retain local JSON; no
        # test, source tree, execution, or scoring behavior is implemented there.
        text = text.replace('software_benchmark_full_plan_v062 import retain',
                            'software_benchmark_ref_plan_v062 import retain')
    # Python 3.13+ changed the default representation of empty AST fields.
    # Retain the older explicit representation in both interpreters.
    options = {'show_empty': True} if 'show_empty' in inspect.signature(ast.dump).parameters else {}
    return hashlib.sha256(ast.dump(ast.parse(text), include_attributes=False, **options).encode()).hexdigest()


def environment_identity(config):
    base = config['scorer_request_base']
    image = base['image']
    if not isinstance(image.get('image_id'), str) or not image['image_id'].startswith('sha256:'):
        raise ValueError('Environment must pin an immutable image ID')
    return {'instance_id': config['instance_id'], 'image_id': image['image_id'],
        'dataset': base['dataset'], 'baseline_mapping': base['baseline_mapping'],
        'scorer_base_manifest': base['scorer_manifest'], 'docker_socket': base['docker_socket'],
        'docker_cli': base['docker_cli']}


def equivalence_value(manifest_ref, *, harness_source=None):
    old, new = scope.load(reference(OLD_MANIFEST)), scope.load(manifest_ref)
    immutable = ('parent', 'archive_adapter', 'limits', 'cap_add', 'cap_drop', 'no_new_privileges',
                 'official_tests_and_scoring_rules_changed', 'host_namespace_mount_or_daemon_operations',
                 'requests_capabilities_by_task')
    changed = [key for key in immutable if old.get(key) != new.get(key)]
    if changed or old_scorer.LIMITS != original.LIMITS:
        raise ValueError('Official scoring dependencies or resource rules changed: ' + ','.join(changed))
    components = []
    for stem in ('grading_environment', 'requests_offline', 'requests_tls', 'tcp_transport'):
        before = scope.ROOT / f'src/proworksim/software_benchmark_{stem}_v062.py'
        after = scope.ROOT / f'src/proworksim/software_benchmark_{stem}_v066.py'
        old_hash = _ast_identity(before, router=stem == 'grading_environment')
        if old_hash != _ast_identity(after, router=stem == 'grading_environment'):
            raise ValueError('Task environment differs beyond the declared namespace: ' + stem)
        components.append({'component': stem, 'original': reference(before), 'current_base': reference(after),
                           'normalized_AST_sha256': old_hash})
    if harness_source is None:
        # Only first preparation in the explicitly cold interpreter imports
        # the scorer package. Manager-side validation uses its sealed bytes.
        from swebench.harness import run_evaluation as harness
        harness_source = reference(harness.__file__)
    source_path = checked(harness_source)
    _, diagnostic = original.diagnostics.repair_function_ast(source_path.read_bytes())
    diagnostic = {key: value for key, value in diagnostic.items()
                  if key not in {'original_function_ast_sha256', 'repaired_function_ast_sha256'}}
    diagnostic['portable_identity'] = 'Exact upstream source SHA and two verified diagnostic-only assignments; interpreter-specific ast.dump digests omitted'
    return {'version': EQUIVALENCE_VERSION, 'old_manifest': reference(OLD_MANIFEST),
        'new_manifest': manifest_ref, 'new_plan': reference(scope.PLAN_FILE),
        'unchanged_manifest_fields': list(immutable), 'environment_components': components,
        'normalization': 'v066/v064 namespace to v062; router local retain helper import only',
        'official_harness_source': harness_source, 'diagnostic_only_repair': diagnostic,
        'old_and_new_limits': original.LIMITS, 'CPU_core_locations_may_change': True,
        'CPU_affinity_count_required': 4, 'private_scope_adapter': reference(__file__),
        'readiness_adapter': reference(io_adapter.__file__),
        'readiness_change': 'Host poll replaces select without framing, payload or destination changes',
        'new_model_calls': 0, 'new_controls': 0, 'Docker_operations': 0}


def qualification_value(task, proof_ref, plan):
    source = plan['environment_sources'][task]
    old_config = scope.load(source['qualification_configuration'])
    new_config = scope.load(plan['environments'][task]['configuration'])
    old_qualification = old_scorer.validate_qualification(
        source['qualification'], old_config, source['qualification_plan'])
    if environment_identity(old_config) != environment_identity(new_config):
        raise ValueError('Image, dataset, baseline, interpreter or scorer input identity changed')
    proof = scope.load(proof_ref)
    if proof != equivalence_value(proof['new_manifest'], harness_source=proof['official_harness_source']):
        raise ValueError('Scoring/environment equivalence is no longer exact')
    environment = private_environment(scope.dispatch_view(scope.require_grading_allowed))
    fields = environment.request_fields(task)
    details = []
    for record in old_qualification['controls']:
        receipt = scope.load(record['receipt'])
        identity = scope.load(receipt['identity'])
        old_cpu = original.cpus(identity['cpuset_cpus'])
        if len(old_cpu) != 4 or identity['limits'] != original.LIMITS:
            raise ValueError('Original actual scoring resources differ')
        old_environment = identity.get('environment_revision')
        if old_environment is not None:
            old_env, new_env = scope.load(old_environment), scope.load(fields['environment_revision'])
            administrative = {'adapter', 'policy', 'transport', 'legacy_fixture_adapter',
                              'dispatch_guard', 'authorization_bound_by', 'version'}
            if old_env.get('version', '').replace('v062', 'v064') != new_env.get('version'):
                raise ValueError('Unexpected fixture version lineage')
            if ({k: v for k, v in old_env.items() if k not in administrative}
                    != {k: v for k, v in new_env.items() if k not in administrative}):
                raise ValueError('Pinned fixture dependencies, CA policy or capabilities changed')
        if identity.get('network_resolution') != fields.get('network_resolution'):
            raise ValueError('The bounded original HTTP/TLS endpoint changed')
        details.append({'patch_kind': record['patch_kind'], 'original_identity': receipt['identity'],
                        'original_CPU_affinity': identity['cpuset_cpus'], 'CPU_count': 4})
    return {'version': REUSE_VERSION, 'instance_id': task, 'passed': True,
        'plan': reference(scope.PLAN_FILE), 'original_qualification': source['qualification'],
        'original_configuration': source['qualification_configuration'],
        'original_plan': source['qualification_plan'], 'new_environment_identity': environment_identity(new_config),
        'equivalence_proof': proof_ref, 'original_controls_validated': details,
        'model_calls': 0, 'new_controls': 0, 'original_results_or_qualifications_overwritten': False}


def validate_reused_qualification(ref, config, plan_ref):
    if plan_ref != reference(scope.PLAN_FILE):
        raise ValueError('Qualification belongs to another paired test')
    plan, value = scope.load(plan_ref), scope.load(ref)
    task = config['instance_id']
    expected_path = scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json')
    if Path(ref['path']).resolve() != expected_path or value.get('version') != REUSE_VERSION:
        raise ValueError('Unrecognized reused qualification identity')
    if (environment_identity(config) != environment_identity(scope.load(plan['environments'][task]['configuration']))
            or value != qualification_value(task, value['equivalence_proof'], plan)):
        raise ValueError('The original controls do not qualify this environment')
    return value


def prepare_environment_qualifications_local():
    policy = scope.dispatch_view(scope.require_grading_allowed)
    scoring = scorer(policy)
    environment = scoring.environment
    environment.prepare()
    manifest = scope.retain(scope.COORDINATOR_ROOT / 'scorer-manifest.json', scoring.installation_manifest())
    proof = scope.retain(scope.COORDINATOR_ROOT / 'qualification-equivalence.json', equivalence_value(manifest))
    plan = scope.load(reference(scope.PLAN_FILE))
    qualifications, controls, failures = {}, [], {}
    for task in plan['environments']:
        try:
            value = qualification_value(task, proof, plan)
            qualified = scope.retain(scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'), value)
            qualifications[task] = {'status': 'qualified', 'qualification': qualified, 'reused_controls': True}
        except (ValueError, KeyError, OSError) as error:
            failures[task] = {'status': 'requires_new_controls', 'error': type(error).__name__ + ': ' + str(error)}
            for kind in ('gold', 'empty'):
                key = 'control-' + task + '-' + kind
                request = {'version': VERSION, 'resource_key': key, 'instance_id': task, 'slot_id': None,
                    'plan': reference(scope.PLAN_FILE), 'configuration': plan['environments'][task]['configuration'],
                    'patch_kind': kind, 'limits': scoring.LIMITS, 'scorer_manifest': manifest,
                    'cpuset_cpus': None, 'directory': str(scope.GRADING_ROOT / key), 'candidate_lock': None,
                    **environment.request_fields(task)}
                controls.append(scope.retain(scope.GRADING_ROOT / key / 'request.json', request))
    result = {'version': VERSION, 'qualifications': qualifications, 'controls': controls,
        'reuse_failures': failures, 'equivalence': proof, 'model_calls': 0, 'Docker_operations': 0}
    scope.retain(scope.COORDINATOR_ROOT / 'qualification-reuse-decisions.json', result)
    return result


def prepare_environment_qualifications():
    """Keep the API manager's tokenizer overlay out of historical validation."""
    result = subprocess.run(command(['--prepare-qualifications']), cwd=scope.ROOT, env=clean_environment(),
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError('Cold environment qualification failed: ' + result.stderr[-3000:])
    return json.loads(result.stdout)


def host(policy, scoring):
    spec = importlib.util.spec_from_file_location('v105_grading_host', scope.ROOT / 'tools/run_capability_grading_v066.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    namespace = clone_namespace(module, policy=policy, scorer=scoring, environment=scoring.environment,
        ROOT=scope.ROOT, RUN_ROOT=scope.COORDINATOR_ROOT, BATCH_ROOT=scope.BATCH_ROOT, VERSION=VERSION,
        bootstrap_environment=clean_environment)
    namespace['bootstrap_environment'] = clean_environment
    namespace['capacity_available'] = lambda: policy.physical_capacity()['passed']

    def prepare_manifest():
        return scope.retain(scope.COORDINATOR_ROOT / 'scorer-manifest.json', cold_manifest())

    def prepare_score(result_ref, *, endpoint='code'):
        if endpoint not in {'code', 'delivery'}:
            raise ValueError('Only code and last legal delivery endpoints are allowed')
        result = scope.load(result_ref)
        plan = scope.load(reference(scope.PLAN_FILE))
        row = next((row for row in plan['rows'] if row['slot_id'] == result.get('slot_id')), None)
        if (row is None or result.get('status') != 'closed' or result.get('configuration') != row['configuration']
                or result.get('measurement_kind') != 'full_verified_comparison'
                or Path(result_ref['path']).resolve() != scope.BATCH_ROOT / 'episodes' / str(row['slot_index']) / 'result.json'):
            raise ValueError('Only this batch closed, original candidate can be graded')
        task = row['instance_id']
        qualification = reference(scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json'))
        config = scope.load(row['configuration'])
        scoring.validate_qualification(qualification, config, reference(scope.PLAN_FILE))
        if endpoint == 'delivery':
            if row['arm'] != 'PROJECT':
                raise ValueError('REF has no project delivery contract')
            proof = scoring.validate_project_delivery(result, config, Path(result_ref['path']).parent)
            if proof.get('submitted') is not True:
                raise ValueError('Absent legal delivery is recorded without scoring')
        key = ('score-' if endpoint == 'code' else 'delivery-score-') + str(row['slot_index'])
        request = {'version': VERSION, 'resource_key': key, 'instance_id': task,
            'plan': reference(scope.PLAN_FILE), 'configuration': row['configuration'],
            'candidate_lock': result['candidate_lock' if endpoint == 'code' else 'delivery_candidate_lock'],
            'generation_result': result_ref, 'measurement_kind': row['measurement_kind'],
            'source_slot_id': row['source_slot_id'], 'slot_id': row['slot_id'], 'qualification': qualification,
            'limits': scoring.LIMITS, 'scorer_manifest': prepare_manifest(), 'cpuset_cpus': None,
            'directory': str(scope.GRADING_ROOT / key), 'patch_kind': None,
            'delivery_evidence': result.get('delivery_evidence') if endpoint == 'delivery' else None,
            **scoring.environment.request_fields(task)}
        return scope.retain(scope.GRADING_ROOT / key / 'request.json', request)

    namespace.update(prepare_manifest=prepare_manifest, prepare_score=prepare_score)
    return module_from(namespace, __name__ + '.host')


class Grading:
    def __init__(self, policy):
        self.policy = policy
        self.scorer = scorer(policy, manifest_provider=cold_manifest)
        self.base = host(policy, self.scorer)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def prepare_environment_qualifications(self):
        return prepare_environment_qualifications()

    def run_request(self, request_ref, stop_event=None):
        request = scope.load(request_ref)
        scope.require_grading_allowed('v105.run', slot_id=request.get('slot_id'), instance_id=request['instance_id'])

        def fixed_python(arguments):
            if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
                raise ValueError('Only the official scoring child may be redirected')
            return command(arguments[2:])

        return clone_function(self.base.run_request, {**self.base.run_request.__globals__,
            'fixed_python': fixed_python, 'bootstrap_environment': clean_environment})(request_ref, stop_event=stop_event)


def factory(*, watchdog_guard=None):
    def guarded(operation='v066.run', **identity):
        if watchdog_guard is not None:
            watchdog_guard(operation, **identity)
        return scope.require_grading_allowed(operation, **identity)
    return Grading(scope.dispatch_view(guarded))


def score_request(request, *, validate_only=False):
    scope.require_grading_allowed('v105.run', slot_id=request.get('slot_id'), instance_id=request['instance_id'])
    policy = scope.dispatch_view(scope.require_grading_allowed)
    scoring = scorer(policy)
    folder = Path(request['directory']).resolve()
    if folder != scope.GRADING_ROOT / request['resource_key'] or (folder / 'quiescence.json').exists():
        raise ValueError('Foreign or consumed scoring identity')
    execution = scoring.resolve_execution_request(request)
    from .software_benchmark_rescore_v095 import host_limits
    limits = host_limits(execution['cpuset_cpus'])
    if validate_only:
        scoring.validate_request(execution)
        return {'passed': True, 'actual_original_validate_request_executed': True,
                'host_limits': limits, 'Docker_operations': 0, 'model_calls': 0}
    write_new(folder / 'v105-host-limits.json', limits)
    return scoring.score_request(request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--manifest', action='store_true')
    group.add_argument('--prepare-qualifications', action='store_true')
    group.add_argument('--request', type=Path)
    group.add_argument('--validate-request', type=Path)
    args = parser.parse_args()
    if args.manifest:
        value = scorer(scope.dispatch_view(scope.require_grading_allowed)).installation_manifest()
    elif args.prepare_qualifications:
        value = prepare_environment_qualifications_local()
    else:
        request = json.loads((args.request or args.validate_request).read_bytes())
        value = score_request(request, validate_only=args.validate_request is not None)
        if args.request:
            value = {key: value[key] for key in ('resource_key', 'status', 'resolved')}
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
