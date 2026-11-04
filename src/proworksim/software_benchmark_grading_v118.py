"""Fresh fifty-task PROJECT grading, with exact reuse of qualified controls.

Only the two reset tasks dispatch through their v114 evaluator adapter. Every
other task, especially live TLS, retains the concrete official evaluator.
All new candidates, controls, cleanup claims and child processes use v118.
"""
from __future__ import annotations

import ast
from functools import lru_cache
import inspect
import json
from pathlib import Path
import re
from types import FunctionType, ModuleType

from . import software_benchmark_grading_v105 as previous
from . import software_benchmark_scope_v118 as scope
from . import software_benchmark_project_closure_v117 as closure
from . import software_benchmark_environment_v118 as current_environment
from . import software_benchmark_grading_repairs_v114 as reset_binding
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_candidates_v054 import write_new
from . import software_benchmark_requests_tls_v068 as lifecycle
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function

VERSION = 'v118-project-repaired-official-scoring-r1'
DEPLOYMENT_VERSION = 'v118-selective-reset-concrete-TLS-scoring-r1'
FRESH_CONTROL_TASKS = frozenset(('psf__requests-1766', 'psf__requests-1921'))
_namespace = clone_namespace(previous, scope=scope, VERSION=VERSION,
    REUSE_VERSION='v118-reused-qualified-control-r1',
    EQUIVALENCE_VERSION='v118-explicit-qualified-environment-equivalence-r1',
    MODULE=__name__, __file__=__file__)


def _lane_validator(namespace):
    """Change exactly the CPU-set enumeration; preserve every other check."""
    source = inspect.getsource(previous.original.validate_request)
    needle = 'range(4)'
    if source.count(needle) != 1:
        raise ValueError('Unexpected original grading-lane validator source')
    revised = source.replace(needle, 'range(MAX_GRADERS)')
    before, after = ast.parse(source), ast.parse(revised)
    changed = 0
    for node in ast.walk(after):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'range':
            if len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == 'MAX_GRADERS':
                node.args[0] = ast.Constant(value=4)
                changed += 1
    if changed != 1 or ast.dump(before, include_attributes=False) != ast.dump(after, include_attributes=False):
        raise ValueError('Only the grading CPU-set enumeration may change')
    compiled = {}
    exec(compile(revised, __file__ + ':two-lane-validator', 'exec'), namespace, compiled)
    return compiled['validate_request']


_parent_environment = _namespace['private_environment']
_parent_qualification_value = _namespace['qualification_value']
_parent_equivalence = _namespace['equivalence_value']
_parent_host = _namespace['host']


def control_key(task, kind):
    if kind not in ('gold', 'empty') or not isinstance(task, str) or not task:
        raise ValueError('Only a declared gold/empty control identity is allowed')
    return 'control-v118-'+task+'-'+kind


def equivalence_value(manifest_ref, *, harness_source=None):
    proof = _parent_equivalence(manifest_ref, harness_source=harness_source)
    return {**proof, 'fresh_controls_required_for': sorted(FRESH_CONTROL_TASKS),
        'selective_test_reset_source': reference(reset_binding.__file__),
        'test_reset_mechanism': reference(reset_binding.reset.__file__),
        'reset_tasks_reuse_only_successful_v114_controls': sorted(reset_binding.reset.TASKS),
        'scoring_transport_and_CA': reference(current_environment.__file__)}


def reset_qualification_value(task, proof_ref, plan):
    """Read the successful v114 pair, checking its actual reset and environment."""
    from . import software_benchmark_grading_recovery_v114 as prior
    old_plan_ref = reference(prior.scope.PLAN_FILE)
    old_plan = scope.load(old_plan_ref)
    old_config = scope.load(old_plan['environments'][task]['configuration'])
    new_config = scope.load(plan['environments'][task]['configuration'])
    if _namespace['environment_identity'](old_config) != _namespace['environment_identity'](new_config):
        raise ValueError('The successful reset control image/dataset/baseline differs')
    old_ref = reference(prior.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
    old_scoring = prior.scorer(prior.scope.dispatch_view(prior.scope.require_grading_allowed))
    qualified = old_scoring.validate_qualification(old_ref, old_config, old_plan_ref)
    proof = scope.load(proof_ref)
    if proof != equivalence_value(proof['new_manifest'], harness_source=proof['official_harness_source']):
        raise ValueError('The underlying scorer is no longer equivalent to the actual controls')
    old_manifest = scope.load(reference(prior.scope.COORDINATOR_ROOT/'scorer-manifest.json'))
    expected_sources = {'test_reset_binding_source': reference(reset_binding.__file__),
        'test_reset_source': reference(reset_binding.reset.__file__),
        'unchanged_reset_mechanism_source': reference(reset_binding.reset.mechanism.__file__)}
    if any(old_manifest.get(key) != value for key, value in expected_sources.items()):
        raise ValueError('The successful control used a different per-path reset implementation')
    details = []
    for control in qualified['controls']:
        receipt = scope.load(control['receipt'])
        identity = scope.load(receipt['identity'])
        diagnostic = scope.load(receipt['diagnostic_repair'])
        observed = diagnostic.get('test_reset_plans', {}).get(task, {})
        if (diagnostic.get('test_reset_revision') != reset_binding.reset.VERSION
                or set(diagnostic.get('test_reset_plans', {})) != reset_binding.reset.TASKS
                or diagnostic.get('upstream_sha256') != proof['official_harness_source']['sha256']
                or observed.get('instance_id') != task
                or observed.get('replaced_reset_commands') != 2
                or observed.get('official_test_patch_changed') is not False
                or observed.get('test_commands_changed') is not False
                or observed.get('candidate_patch_changed') is not False
                or observed.get('grading_rules_changed') is not False
                or len(previous.original.cpus(identity['cpuset_cpus'])) != 4
                or identity['limits'] != previous.original.LIMITS):
            raise ValueError('The actual successful control lacks matching per-path reset evidence')
        details.append({'patch_kind': control['patch_kind'], 'original_identity': receipt['identity'],
            'actual_diagnostic_repair': receipt['diagnostic_repair'],
            'repaired_eval_sha256': observed['repaired_eval_sha256'],
            'official_test_patch_sha256': observed['official_test_patch_sha256'], 'CPU_count': 4})
    return {'version': _namespace['REUSE_VERSION'], 'instance_id': task, 'passed': True,
        'plan': reference(scope.PLAN_FILE), 'original_qualification': old_ref,
        'original_configuration': old_plan['environments'][task]['configuration'],
        'original_plan': old_plan_ref,
        'new_environment_identity': _namespace['environment_identity'](new_config),
        'equivalence_proof': proof_ref, 'original_controls_validated': details,
        'reset_source_identity': expected_sources, 'model_calls': 0, 'new_controls': 0,
        'original_results_or_qualifications_overwritten': False}


def qualification_value(task, proof_ref, plan):
    """Reuse immutable offline evidence, but refresh two live HTTP/TLS controls.

    This rule is fixed before any new model result. Old HTTP controls cannot
    establish today's external service behavior after observed HTTP 502s.
    It adds no candidate retry, CA bypass, new endpoint or automatic repair.
    """
    if task in FRESH_CONTROL_TASKS:
        raise ValueError('v118 requires a fresh gold/empty pair for the live external TLS environment')
    if task in reset_binding.reset.TASKS:
        return reset_qualification_value(task, proof_ref, plan)
    return _parent_qualification_value(task, proof_ref, plan)


def fresh_qualification_validator(namespace):
    source = inspect.getsource(previous.original.validate_qualification)
    key = '"control-" + task + "-" + kind'
    importer = 'from .software_benchmark_grading_qualification_v060 import validate_transport_evidence'
    if source.count(key) != 1 or source.count(importer) != 1:
        raise ValueError('The concrete qualification source changed')
    source = source.replace(key, '"control-v118-" + task + "-" + kind').replace(importer,
        'from .software_benchmark_environment_v118 import validate_transport_evidence')
    compiled = {}
    exec(compile(source, __file__+':new-control-qualification', 'exec'), namespace, compiled)
    native = compiled['validate_qualification']

    def validate(ref, config, plan_ref):
        value = scope.load(ref)
        if value.get('version') == _namespace['REUSE_VERSION']:
            if config['instance_id'] in FRESH_CONTROL_TASKS:
                raise ValueError('Historical TLS controls cannot qualify a new live TLS run')
            return _namespace['validate_reused_qualification'](ref, config, plan_ref)
        if value.get('version') != VERSION:
            raise ValueError('Only this new control pair or a checked reuse proof may qualify')
        return native(ref, config, plan_ref)

    return validate


def private_environment(policy):
    # Provider metadata and new scoring paths are owned by v111; no old
    # attempts, claims, score caches or result directories are reopened.
    private = ModuleType(__name__ + '.environment_policy')
    private.__dict__.update(vars(policy))
    private.GRADING_ROOT = scope.COORDINATOR_ROOT / 'provider-bindings'
    environment = _parent_environment(private)
    original_manifest = environment.offline.environment_manifest

    def offline_manifest():
        return {**original_manifest(),
                'authorization_bound_by': 'v118 fresh PROJECT plan and request; no old resource authority is reopened'}

    # Update both the public module view and the actual validator's namespace.
    environment.offline.environment_manifest = offline_manifest
    environment.offline.validate_environment.__globals__['environment_manifest'] = offline_manifest
    environment.tls.run_official = lifecycle.run_official
    return current_environment.bind_environment(environment, private)


_parent_scorer = _namespace['scorer']


def classify_http_502(receipt, folder):
    """Conservative validity note, never a rewrite of the official score."""
    task = receipt.get('instance_id')
    if task not in ('psf__requests-1766', 'psf__requests-1921'):
        return None
    result = receipt.get('official_result')
    if (not isinstance(result, (tuple, list)) or len(result) != 2
            or not isinstance(result[1], dict)
            or result[1].get(task, {}).get('resolved') is not False):
        return None
    log = (Path(folder) / 'official-output/logs/run_evaluation' /
           receipt['run_id'] / receipt['resource_key'] / task / 'test_output.txt')
    if not log.is_file() or not log.resolve().is_relative_to(Path(folder).resolve()):
        return None
    expected, observations = None, []
    with log.open(encoding='utf-8', errors='replace') as stream:
        for number, raw in enumerate(stream, 1):
            line = re.sub(r'\x1b\[[0-9;]*m', '', raw).rstrip()
            assertion = re.match(r'^\s*E\s+assert\s+502\s*==\s*(\d{3})\s*$', line)
            if assertion and assertion[1] != '502':
                expected = (number, int(assertion[1]))
            elif (expected is not None and number == expected[0] + 1
                    and re.match(r'^\s*E\s+\+\s+where\s+502\s*=\s*<Response \[502\]>\.status_code\b', line)):
                observations.append({'assertion_line': expected[0], 'actual_response_line': number,
                                     'expected_status': expected[1], 'actual_status': 502})
                expected = None
            else:
                expected = None
    if not observations:
        return None
    transport_ref = receipt.get('transport_result')
    transport = scope.load(transport_ref) if isinstance(transport_ref, dict) else {}
    network_errors = transport.get('network_errors') or []
    connection_errors = sum(bool(item.get('error')) for item in transport.get('connections', [])
                            if isinstance(item, dict))
    return {'version': 'v111-external-http-candidate-interaction-validity-r1',
        'classification': 'external_http_or_candidate_interaction_requires_review',
        'pure_environment_fault_proven': False, 'official_report_preserved': True,
        'test_output': reference(log), 'unexpected_actual_HTTP_502_assertions': observations,
        'transport': transport_ref, 'transport_ok': transport.get('ok'),
        'transport_network_error_count': len(network_errors),
        'transport_connection_error_count': connection_errors,
        'stronger_transport_failure_evidence_present': bool(network_errors or connection_errors),
        'candidate_bytes_changed': False, 'tests_changed': False, 'extra_network_calls': 0}


def bind_receipt_writer(namespace):
    original_write = namespace['write_new']

    def write_new(path, value):
        if (Path(path).name == 'receipt.json' and isinstance(value, dict)
                and value.get('version') == VERSION and value.get('model_calls') == 0):
            validity = classify_http_502(value, Path(path).parent)
            if validity is not None:
                value.update(status='technical_unknown', resolved=None, scoring_validity=validity)
        return original_write(path, value)

    return write_new


def bind_physical_cleanup(namespace):
    """CA measurements remain unknown without pretending a removed object is live."""
    environment, original_scorer, policy = (
        namespace[name] for name in ('environment', 'original_scorer', 'policy'))

    def cleanup(request, tracking):
        transport_errors = (environment.tls.cleanup_transport(tracking)
                            if tracking.get('environment_container') else [])
        measurement_errors = [error for error in transport_errors
                              if isinstance(error, str) and error.startswith('CA final identity: ')]
        physical_errors = [error for error in transport_errors if error not in measurement_errors]
        timer = tracking.get('deadline_timer')
        if timer:
            timer.cancel()
            timer.join(timeout=10)
        # This original routine still verifies/removes exact owned IDs and
        # rejects unknown creates; no CA error can substitute for its proof.
        proof = original_scorer.cleanup_scoring(request, tracking)
        proof.update(version=VERSION, resource_key=request['resource_key'],
                     deadline_reached=tracking.get('deadline_reached', False))
        proof['cleanup_errors'].extend(tracking.get('watchdog_errors', []))
        proof['cleanup_errors'].extend(physical_errors)
        proof['measurement_errors'] = measurement_errors
        proof['transport_result'] = tracking.get('transport_result')
        proof['TLS_lifecycle'] = tracking.get('tls_lifecycle')
        if timer and timer.is_alive():
            proof['cleanup_errors'].append('Container deadline timer remains alive')
        proof['quiescent'] = proof['quiescent'] and not proof['cleanup_errors']
        if tracking.get('claim'):
            policy.release_resource(tracking['claim'], quiescent=proof['quiescent'])
        return proof

    return cleanup


def scorer(policy, *, manifest_provider=None):
    value = _parent_scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    if (namespace['diagnostics'].make_repaired_run_instance
            is not previous.original.diagnostics.make_repaired_run_instance):
        raise ValueError('Non-reset tasks must retain the concrete official evaluator factory')
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence,
                     MAX_GRADERS=scope.MAX_GRADERS)
    validator = _lane_validator(namespace)
    namespace['validate_qualification'] = fresh_qualification_validator(namespace)
    native_manifest = namespace['installation_manifest']

    def installation_manifest():
        manifest = native_manifest()
        if manifest_provider is not None:
            return manifest
        return {**manifest, 'managed_delivery_validator': reference(closure.__file__),
            'deployment_repair_adapter': reference(__file__),
            'deployment_revision': DEPLOYMENT_VERSION,
            'unchanged_scoring_protocol_source': reference(scope.ROOT / 'src/proworksim/software_benchmark_grading_v111.py'),
            'audited_previous_repair': reference(scope.ROOT / 'src/proworksim/software_benchmark_grading_v108.py'),
            'new_resource_scope': reference(scope.__file__),
            'old_model_attempts_replayed': False,
            'new_PROJECT_generation_candidates_only': True,
            'fresh_gold_empty_required_for': sorted(FRESH_CONTROL_TASKS),
            'other_controls_reused_only_after_exact_environment_equivalence': True,
            'selective_reset_tasks': sorted(reset_binding.reset.TASKS),
            'selective_reset_binding': reference(reset_binding.__file__),
            'non_reset_concrete_evaluator_retained': True,
            'TLS_passthrough_evaluator_wrapper_installed': False,
            'scoring_environment_binding': reference(current_environment.__file__),
            'original_scoring_adapter': reference(previous.original.__file__),
            'grading_lane_count': scope.MAX_GRADERS,
            'grading_validation_change': 'Exactly range(4) -> range(MAX_GRADERS); MAX_GRADERS=2',
            'official_scoring_rules_and_test_patch_changed': False,
            'test_reset_executor_changed_only_for_declared_two_tasks': True,
            'TLS_lifecycle_binding': reference(lifecycle.__file__),
            'physical_cleanup_measurement_separation': reference(__file__),
            'bounded_HTTP_502_validity_note': 'Only two TLS tasks; actual failed status assertions; official result preserved',
            'managed_closure_identity_change': 'Only new v117 PROJECT task/seed identities accepted by the v118 plan'}

    cleanup = bind_physical_cleanup(namespace)
    namespace.update(validate_request=validator, installation_manifest=installation_manifest,
                     cleanup=cleanup, write_new=bind_receipt_writer(namespace))
    value.__dict__.update(validate_request=validator, installation_manifest=installation_manifest,
                          validate_delivery_evidence=closure.validate_delivery_evidence, cleanup=cleanup,
                          validate_qualification=namespace['validate_qualification'])
    dataset = json.loads(previous.checked(reference(
        scope.ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json')).read_bytes())
    rows = [row for row in dataset if row['instance_id'] in reset_binding.reset.TASKS]
    repaired = reset_binding.bind_scorer(value, rows, passthrough_tasks=())
    concrete_score = namespace['_score']

    def selected_score(request, resource, config, tracking):
        if config['instance_id'] in reset_binding.reset.TASKS:
            return repaired._score(request, resource, config, tracking)
        return concrete_score(request, resource, config, tracking)

    namespace['_score'] = selected_score
    value._score = selected_score
    value._v118_concrete_score = concrete_score
    value._v118_reset_scorer = repaired
    return value


def prepare_environment_qualifications_local():
    policy = scope.dispatch_view(scope.require_grading_allowed)
    scoring = scorer(policy)
    scoring.environment.prepare()
    manifest = scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json', scoring.installation_manifest())
    proof = scope.retain(scope.COORDINATOR_ROOT/'qualification-equivalence.json', equivalence_value(manifest))
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.load(plan_ref)
    qualifications, controls, reasons = {}, [], {}
    for task in sorted(plan['environments']):
        try:
            value = qualification_value(task, proof, plan)
            ref = scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'), value)
            qualifications[task] = {'status': 'qualified', 'qualification': ref, 'reused_controls': True}
            continue
        except (ValueError, KeyError, OSError) as error:
            reasons[task] = {'status': 'requires_new_controls', 'error': type(error).__name__+': '+str(error)}
        for kind in ('gold', 'empty'):
            key = control_key(task, kind)
            resource = plan['resources'].get(key, {})
            if (resource.get('role') != 'control' or resource.get('instance_id') != task
                    or resource.get('patch_kind') != kind):
                raise ValueError('Fresh qualification lacks an exact declared unused control resource')
            request = {'version': VERSION, 'resource_key': key, 'instance_id': task, 'slot_id': None,
                'plan': plan_ref, 'configuration': plan['environments'][task]['configuration'],
                'patch_kind': kind, 'limits': scoring.LIMITS, 'scorer_manifest': manifest,
                'cpuset_cpus': None, 'directory': str(scope.GRADING_ROOT/key), 'candidate_lock': None,
                **scoring.environment.request_fields(task)}
            controls.append(scope.retain(scope.GRADING_ROOT/key/'request.json', request))
    result = {'version': VERSION, 'qualifications': qualifications, 'controls': controls,
        'reuse_failures': reasons, 'equivalence': proof, 'model_calls': 0, 'Docker_operations': 0,
        'TLS_controls_should_be_serialized': True, 'automatic_HTTP_retries': False,
        'unqualified_tasks_cannot_start_generation': True}
    scope.retain(scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json', result)
    return result


def host(policy, scoring):
    value = _parent_host(policy, scoring)

    def qualify(task):
        plan_ref = reference(scope.PLAN_FILE)
        plan = scope.load(plan_ref)
        controls = []
        for kind in ('gold', 'empty'):
            folder = scope.GRADING_ROOT/control_key(task, kind)
            controls.append({'patch_kind': kind,
                **{name: reference(folder/(name+'.json')) for name in ('receipt', 'quiescence', 'completion')},
                'initial_container': reference(folder/'official-output/initial-container.json')})
        result = {'version': VERSION, 'instance_id': task, 'plan': plan_ref,
                  'controls': controls, 'passed': True, 'model_calls': 0}
        target = scope.COORDINATOR_ROOT/'qualifications'/(task+'.json')
        proposal = scope.retain(target.with_name(task+'-proposal.json'), result)
        scoring.validate_qualification(proposal, scope.load(plan['environments'][task]['configuration']), plan_ref)
        return scope.retain(target, result)

    value.qualify = qualify
    return value


def run_request(self, request_ref, stop_event=None):
    """Start only a freshly scoped grader subprocess for this prepared request."""
    request = scope.load(request_ref)
    scope.require_grading_allowed('v118.run', slot_id=request.get('slot_id'),
                                  instance_id=request['instance_id'])

    def fixed_python(arguments):
        if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
            raise ValueError('Only the unchanged official scoring child may be redirected')
        return _namespace['command'](arguments[2:])

    return clone_function(self.base.run_request, {**self.base.run_request.__globals__,
        'fixed_python': fixed_python, 'bootstrap_environment': _namespace['clean_environment']})(
            request_ref, stop_event=stop_event)


def score_request(request, *, validate_only=False):
    scope.require_grading_allowed('v118.run', slot_id=request.get('slot_id'),
                                  instance_id=request['instance_id'])
    policy = scope.dispatch_view(scope.require_grading_allowed)
    scoring = scorer(policy)
    folder = Path(request['directory']).resolve()
    if folder != scope.GRADING_ROOT/request['resource_key'] or (folder/'quiescence.json').exists():
        raise ValueError('Foreign or already consumed scoring identity')
    execution = scoring.resolve_execution_request(request)
    from .software_benchmark_rescore_v095 import host_limits
    limits = host_limits(execution['cpuset_cpus'])
    if validate_only:
        scoring.validate_request(execution)
        return {'passed': True, 'actual_original_validate_request_executed': True,
                'host_limits': limits, 'Docker_operations': 0, 'model_calls': 0}
    write_new(folder/'v118-host-limits.json', limits)
    return scoring.score_request(request)


_namespace.update(private_environment=private_environment, scorer=scorer,
                  qualification_value=qualification_value, score_request=score_request,
                  equivalence_value=equivalence_value, host=host,
                  prepare_environment_qualifications_local=prepare_environment_qualifications_local)
# The original lru wrapper closes over the old function; create a fresh wrapper
# around its cloned body so cold subprocesses import this deployment revision.
_namespace['cold_manifest'] = lru_cache(maxsize=1)(
    clone_function(previous.cold_manifest.__wrapped__, _namespace))
_namespace['Grading'] = type('Grading', (previous.Grading,), {
    key: clone_function(value, _namespace) for key, value in vars(previous.Grading).items()
    if isinstance(value, FunctionType)})
_namespace['Grading'].run_request = run_request
main = _namespace['main']
globals().update({key: value for key, value in _namespace.items() if not key.startswith('__')})


if __name__ == '__main__':
    main()
