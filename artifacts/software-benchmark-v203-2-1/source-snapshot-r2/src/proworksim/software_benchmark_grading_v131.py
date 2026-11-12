"""Five fixed organizations use separately locked final-code and legal-delivery grading.

Only the two reset tasks dispatch through their v114 evaluator adapter. Every
other task, especially live TLS, retains the concrete official evaluator.
All new candidates, controls, cleanup claims and child processes use v131.
"""
from __future__ import annotations

import ast
import argparse
import fcntl
from functools import lru_cache
import inspect
import json
from pathlib import Path
import re
import textwrap
import time
from types import FunctionType, ModuleType

from . import software_benchmark_grading_v105 as previous
from . import software_benchmark_scope_v131 as scope
from . import software_benchmark_project_closure_v131 as closure
from . import software_benchmark_environment_v131 as current_environment
from . import software_benchmark_grading_repairs_v114 as reset_binding
from . import software_benchmark_grading_v119 as qualified_prior
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_candidates_v054 import write_new
from . import software_benchmark_requests_tls_v068 as lifecycle
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function

VERSION = 'v131-fixed-organization-official-scoring-r1'
DEPLOYMENT_VERSION = 'v131-team-closure-and-qualified-scoring-environment-r1'
FRESH_CONTROL_TASKS = frozenset({'psf__requests-1766', 'psf__requests-1921'})
_namespace = clone_namespace(previous, scope=scope, VERSION=VERSION,
    REUSE_VERSION='v131-reused-v119-qualified-control-r1',
    EQUIVALENCE_VERSION='v131-explicit-v119-environment-equivalence-r1',
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
    return 'control-v131-'+task+'-'+kind

def equivalence_value(manifest_ref, *, harness_source=None):
    del harness_source  # No new upstream import is needed for this source-bound continuation.
    old_ref = reference(qualified_prior.scope.COORDINATOR_ROOT/'scorer-manifest.json')
    old, new = scope.load(old_ref), scope.load(manifest_ref)
    keys = ('parent', 'archive_adapter', 'limits', 'cap_add', 'cap_drop', 'no_new_privileges',
        'requests_capabilities_by_task', 'official_tests_and_scoring_rules_changed',
        'host_namespace_mount_or_daemon_operations', 'original_scoring_adapter',
        'selective_reset_binding', 'selective_reset_tasks',
        'TLS_lifecycle_binding', 'host_poll_adapter')
    if any(old.get(key) != new.get(key) for key in keys):
        raise ValueError('Official scoring, resources, reset, delivery or transport differ from the qualified run')
    before = Path(qualified_prior.current_environment.__file__).read_text()
    after = Path(current_environment.__file__).read_text().replace('v131', 'v119').replace(
        'v119_current_DNS_and_bounded_endpoint_probe', 'v118_current_DNS_and_bounded_endpoint_probe')
    if ast.dump(ast.parse(before), include_attributes=False) != ast.dump(ast.parse(after), include_attributes=False):
        raise ValueError('Environment scope changed beyond its explicit continuation namespace')
    if reference(scope.CA_PROFILE_FILE) != reference(qualified_prior.scope.CA_PROFILE_FILE):
        raise ValueError('The completed live TLS controls cannot qualify another CA or public endpoint')
    return {'version': _namespace['EQUIVALENCE_VERSION'], 'old_manifest': old_ref,
        'new_manifest': manifest_ref, 'new_plan': reference(scope.PLAN_FILE),
        'unchanged_manifest_fields': list(keys), 'prior_qualified_plan': reference(qualified_prior.scope.PLAN_FILE),
        'new_environment_adapter': reference(current_environment.__file__),
        'old_environment_adapter': reference(qualified_prior.current_environment.__file__),
        'environment_change': 'Only v119 to v131 scope/version namespace; normalized AST identical',
        'new_frozen_network_resolution': reference(scope.NETWORK_RESOLUTION_FILE),
        'fresh_controls_required_for': sorted(FRESH_CONTROL_TASKS),
        'delivery_validation_change': 'New fixed-organization chain; official grading tests and per-container limits unchanged',
        'same_effective_CA_profile': reference(scope.CA_PROFILE_FILE),
        'new_controls': 0, 'new_model_calls': 0, 'Docker_operations': 0}


def qualification_value(task, proof_ref, plan):
    """Validate this task's completed v119 qualification, including its real TLS pair."""
    if task in FRESH_CONTROL_TASKS:
        raise ValueError('Live external Requests tasks require this batch gold/empty pair')
    if task not in plan['environments']:
        raise ValueError('Task outside the authorized independent recovery panel')
    old_plan_ref = reference(qualified_prior.scope.PLAN_FILE)
    old_plan = scope.load(old_plan_ref)
    old_config_ref = old_plan['environments'][task]['configuration']
    old_config = scope.load(old_config_ref)
    new_config = scope.load(plan['environments'][task]['configuration'])
    if _namespace['environment_identity'](old_config) != _namespace['environment_identity'](new_config):
        raise ValueError('Continuation image, baseline, dataset or scorer input changed')
    proof = scope.load(proof_ref)
    if proof != equivalence_value(proof['new_manifest']):
        raise ValueError('Prepared continuation environment equivalence changed')
    old_ref = reference(qualified_prior.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
    original = qualified_prior.scorer(qualified_prior.scope.dispatch_view(qualified_prior.scope.require_grading_allowed))
    admitted = original.validate_qualification(old_ref, old_config, old_plan_ref)
    new_environment = private_environment(scope.dispatch_view(scope.require_grading_allowed))
    old_fields, new_fields = original.environment.request_fields(task), new_environment.request_fields(task)
    if old_fields.get('network_resolution') != new_fields.get('network_resolution'):
        raise ValueError('Existing TLS qualification belongs to another public destination')
    old_revision, new_revision = old_fields.get('environment_revision'), new_fields.get('environment_revision')
    if (old_revision is None) != (new_revision is None):
        raise ValueError('Requests environment policy disappeared or appeared unexpectedly')
    if old_revision is not None:
        old_value, new_value = scope.load(old_revision), scope.load(new_revision)
        administrative = {'adapter', 'policy', 'transport', 'legacy_fixture_adapter',
                          'dispatch_guard', 'authorization_bound_by', 'version'}
        if ({k: v for k, v in old_value.items() if k not in administrative}
                != {k: v for k, v in new_value.items() if k not in administrative}):
            raise ValueError('Actual public fixture dependencies, CA policy or capabilities changed')
    return {'version': _namespace['REUSE_VERSION'], 'instance_id': task, 'passed': True,
        'plan': reference(scope.PLAN_FILE), 'original_qualification': old_ref,
        'original_configuration': old_config_ref, 'original_plan': old_plan_ref,
        'new_environment_identity': _namespace['environment_identity'](new_config),
        'equivalence_proof': proof_ref, 'prior_qualification_version': admitted['version'],
        'original_actual_control_or_reuse_evidence_validated': True,
        'current_environment_revision': new_revision, 'previous_environment_revision': old_revision,
        'model_calls': 0, 'new_controls': 0, 'original_results_or_qualifications_overwritten': False}


def fresh_qualification_validator(namespace):
    source = inspect.getsource(previous.original.validate_qualification)
    key = '"control-" + task + "-" + kind'
    importer = 'from .software_benchmark_grading_qualification_v060 import validate_transport_evidence'
    if source.count(key) != 1 or source.count(importer) != 1:
        raise ValueError('The concrete qualification source changed')
    source = source.replace(key, '"control-v131-" + task + "-" + kind').replace(importer,
        'from .software_benchmark_environment_v131 import validate_transport_evidence')
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
                'authorization_bound_by': 'v131 fixed organization and exact new task/attempt candidates; no old authority'}

    # Update both the public module view and the actual validator's namespace.
    environment.offline.environment_manifest = offline_manifest
    environment.offline.validate_environment.__globals__['environment_manifest'] = offline_manifest
    environment.tls.run_official = lifecycle.run_official
    return current_environment.bind_environment(environment, private)


_parent_scorer = _namespace['scorer']


def bind_group_identity(namespace):
    original_planned = namespace['_planned']
    original_generation = namespace['_generation_result']
    original_candidate = namespace['validate_candidate_request']

    def planned(request):
        plan, resource, config = original_planned(request)
        if resource['role'] != 'control':
            row = next(row for row in plan['rows'] if row['slot_id'] == request['slot_id'])
            group = row['organization_id']
            if (group != row['group_id'] or config.get('organization_id') != group
                    or config.get('group_id') != group or request.get('organization_id') != group
                    or request.get('group_id') != group
                    or config.get('arm') != 'PROJECT'
                    or resource.get('slot_id') != row['slot_id']):
                raise ValueError('A team candidate cannot cross its organization, issue or attempt')
        return plan, resource, config

    def generation(request, config, plan):
        row, result, folder = original_generation(request, config, plan)
        if (result.get('organization_id') != row['organization_id']
                or result.get('group_id') != row['group_id']):
            raise ValueError('The stopped generation did not retain its fixed organization identity')
        return row, result, folder

    def candidate(request, resource, config, plan):
        locked = original_candidate(request, resource, config, plan)
        if resource['role'] == 'score':
            _, result, folder = generation(request, config, plan)
            # Code correctness does not require legal delivery; it still needs
            # this group's actual archived team closure and selected member tree.
            namespace['validate_project_delivery'](result, config, folder)
        return locked

    namespace.update(_planned=planned, _generation_result=generation,
                     validate_candidate_request=candidate)


def bind_container_parent(namespace):
    """Only add the exact new aggregate parent after upstream option validation."""
    from . import software_benchmark_api_parent_v131 as parent
    if parent.SLICE != scope.CONTAINER_PARENT:
        raise ValueError('The scorer aggregate parent differs from its new scope')
    source = textwrap.dedent(inspect.getsource(previous.original.Containers.create))
    needle = 'self.tracking.update(claim=claim_ref, create_result_unknown=True)'
    if source.count(needle) != 1:
        raise ValueError('The original bounded grader construction changed')
    source = source.replace(needle, 'options = aggregate_parent.container_options(options)\n    '+needle)
    compiled = {}
    namespace['aggregate_parent'] = parent
    exec(compile(source, __file__+':exact-aggregate-parent', 'exec'), namespace, compiled)
    namespace['Containers'].create = compiled['create']
    original_attrs = namespace['validate_attrs']

    def validate_attrs(attrs, observation):
        parent.validate_container_parent(attrs)
        return original_attrs(attrs, observation)

    namespace['validate_attrs'] = validate_attrs
    offline = namespace['environment'].offline
    original_offline = offline.validate_container_config

    def validate_container_config(attrs, request, limits, profile):
        parent.validate_container_parent(attrs)
        return original_offline(attrs, request, limits, profile)

    original_offline.__globals__['validate_container_config'] = validate_container_config
    offline.validate_container_config = validate_container_config
    return parent


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
        if (Path(path).name in {'receipt.json', 'identity.json'} and isinstance(value, dict)
                and value.get('slot_id') is not None and value.get('resource_key')):
            plan = scope.load(reference(scope.PLAN_FILE))
            row = next(row for row in plan['rows'] if row['slot_id'] == value['slot_id'])
            value.update(organization_id=row['organization_id'], group_id=row['group_id'])
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
    bind_group_identity(namespace)
    parent = bind_container_parent(namespace)
    value.__dict__.update(_planned=namespace['_planned'], _generation_result=namespace['_generation_result'],
                          validate_candidate_request=namespace['validate_candidate_request'],
                          validate_attrs=namespace['validate_attrs'], Containers=namespace['Containers'])
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
            'old_model_attempts_replayed_in_place': False,
            'independent_recovery_of_consumed_calls_explicitly_authorized': True,
            'original_called_attempts_overwritten': False,
            'new_PROJECT_generation_candidates_only': True,
            'fresh_gold_empty_required_for': sorted(FRESH_CONTROL_TASKS),
            'new_gold_empty_allowed': True,
            'reuse_completed_v119_qualification': True,
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
            'managed_closure_identity_change': 'Fixed organization identity, member_001 unique code candidate and legal team submission chain',
            'aggregate_container_parent': scope.CONTAINER_PARENT,
            'aggregate_parent_validator': reference(parent.__file__),
            'group_task_candidate_cache_identity_required': True}

    cleanup = bind_physical_cleanup(namespace)
    namespace.update(validate_request=validator, installation_manifest=installation_manifest,
                     cleanup=cleanup, write_new=bind_receipt_writer(namespace))
    value.__dict__.update(validate_request=validator, installation_manifest=installation_manifest,
                          validate_delivery_evidence=closure.validate_delivery_evidence, cleanup=cleanup,
                          validate_qualification=namespace['validate_qualification'], write_new=namespace['write_new'])
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
    scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
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

def verify_prepared_identity():
    """Pure final-seal check; 48 reused qualifications and four new control requests."""
    policy = scope.dispatch_view(scope.require_grading_allowed)
    scoring = scorer(policy)
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    folder = scope.COORDINATOR_ROOT/'provider-bindings/environments'
    expected = {folder/'offline.json': scoring.environment.offline.environment_manifest(),
        folder/'tls.json': scoring.environment.tls.environment_manifest(),
        scope.COORDINATOR_ROOT/'scorer-manifest.json': scoring.installation_manifest()}
    checked_refs = []
    for path, value in expected.items():
        ref = reference(path)
        if scope.load(ref) != value:
            raise ValueError('Stale prepared scorer identity: '+str(path))
        checked_refs.append(ref)
    bindings = reference(folder/'bindings.json')
    if scope.load(bindings) != {'offline': reference(folder/'offline.json'),
            'tls': reference(folder/'tls.json'), 'network_resolutions': {
                task: reference(scope.NETWORK_RESOLUTION_FILE) for task in sorted(scoring.environment.TLS_TASKS)}}:
        raise ValueError('The prepared public endpoint binding differs')
    manifest = reference(scope.COORDINATOR_ROOT/'scorer-manifest.json')
    equivalence = reference(scope.COORDINATOR_ROOT/'qualification-equivalence.json')
    if scope.load(equivalence) != equivalence_value(manifest):
        raise ValueError('The prepared environment equivalence changed')
    decisions_ref = reference(scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json')
    decisions = scope.load(decisions_ref)
    if (set(decisions['qualifications']) != set(plan['environments'])-FRESH_CONTROL_TASKS
            or set(decisions['reuse_failures']) != FRESH_CONTROL_TASKS or len(decisions['controls']) != 4):
        raise ValueError('Expected exactly 48 reused environments and two fresh control pairs')
    for task, value in decisions['qualifications'].items():
        scoring.validate_qualification(value['qualification'],
            scope.load(plan['environments'][task]['configuration']), plan_ref)
        checked_refs.append(value['qualification'])
    expected_keys = {control_key(task,kind) for task in FRESH_CONTROL_TASKS for kind in ('gold','empty')}
    actual_keys = set()
    for ref in decisions['controls']:
        request = scope.load(ref)
        _, resource, _ = scoring._planned(request)
        actual_keys.add(request['resource_key'])
        if (resource['role'] != 'control' or request.get('scorer_manifest') != manifest
                or request.get('cpuset_cpus') is not None or request.get('candidate_lock') is not None
                or request.get('directory') != str(scope.GRADING_ROOT/request['resource_key'])
                or any(request.get(key) != value for key,value in
                       scoring.environment.request_fields(request['instance_id']).items())):
            raise ValueError('Prepared control identity changed')
        checked_refs.append(ref)
    if actual_keys != expected_keys:
        raise ValueError('The four fresh controls do not cover the exact live TLS pair')
    return {'version': DEPLOYMENT_VERSION, 'passed': True,
        'current_scoring_source': reference(__file__), 'current_scope_source': reference(scope.__file__),
        'current_environment_source': reference(current_environment.__file__),
        'verified_prepared_artifacts': checked_refs+[bindings,decisions_ref,equivalence],
        'reused_qualified_environments': 48, 'fresh_control_requests': 4,
        'fresh_controls_executed': 0, 'model_calls': 0, 'Docker_operations': 0,
        'network_connections': 0, 'artifacts_created_or_modified': 0}

def host(policy, scoring):
    value = _parent_host(policy, scoring)
    original_prepare = value.prepare_score
    namespace = {**original_prepare.__globals__, **inspect.getclosurevars(original_prepare).nonlocals}
    source = textwrap.dedent(inspect.getsource(original_prepare))
    needle = 'return scope.retain(scope.GRADING_ROOT / key / \'request.json\', request)'
    if source.count(needle) != 1:
        raise ValueError('The unchanged host candidate preparation body changed')
    source = source.replace(needle, "request.update(organization_id=row['organization_id'], group_id=row['group_id'])\n    "+needle)
    compiled = {}
    exec(compile(source, __file__+':team-score-request', 'exec'), namespace, compiled)
    value.prepare_score = compiled['prepare_score']
    value.delivery_disposition.__globals__.update(prepare_score=value.prepare_score, write_new=scoring.write_new)

    def qualify(task):
        plan_ref = reference(scope.PLAN_FILE)
        plan = scope.load(plan_ref)
        if task not in FRESH_CONTROL_TASKS:
            ref = reference(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
            scoring.validate_qualification(ref, scope.load(plan['environments'][task]['configuration']), plan_ref)
            return ref
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
    scope.require_grading_allowed('v131.run', slot_id=request.get('slot_id'),
                                  instance_id=request['instance_id'])

    def fixed_python(arguments):
        if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
            raise ValueError('Only the unchanged official scoring child may be redirected')
        return _namespace['command'](arguments[2:])

    execute = clone_function(self.base.run_request, {**self.base.run_request.__globals__,
        'fixed_python': fixed_python, 'bootstrap_environment': _namespace['clean_environment']})
    if request['instance_id'] not in FRESH_CONTROL_TASKS:
        return execute(request_ref, stop_event=stop_event)
    scope.COORDINATOR_ROOT.mkdir(parents=True, exist_ok=True)
    with (scope.COORDINATOR_ROOT/'tls-scoring.lock').open('a+b') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if stop_event is not None and stop_event.wait(0.25):
                    return {'status':'not_started_cancelled','resource_key':request['resource_key']}
                if stop_event is None:
                    time.sleep(0.25)
        try:
            return execute(request_ref, stop_event=stop_event)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def score_request(request, *, validate_only=False):
    scope.require_grading_allowed('v131.run', slot_id=request.get('slot_id'),
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
    write_new(folder/'v131-host-limits.json', limits)
    return scoring.score_request(request)


def recovery_main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--manifest', action='store_true')
    group.add_argument('--prepare-qualifications', action='store_true')
    group.add_argument('--verify-preparation', action='store_true')
    group.add_argument('--request', type=Path)
    group.add_argument('--validate-request', type=Path)
    args = parser.parse_args()
    if args.verify_preparation:
        value = verify_prepared_identity()
    elif args.manifest:
        value = scorer(scope.dispatch_view(scope.require_grading_allowed)).installation_manifest()
    elif args.prepare_qualifications:
        value = prepare_environment_qualifications_local()
    else:
        request = json.loads((args.request or args.validate_request).read_bytes())
        value = score_request(request, validate_only=args.validate_request is not None)
        if args.request:
            value = {key: value[key] for key in ('resource_key', 'status', 'resolved')}
    print(json.dumps(value, ensure_ascii=False))


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
_namespace['main'] = recovery_main
main = _namespace['main']
globals().update({key: value for key, value in _namespace.items() if not key.startswith('__')})


if __name__ == '__main__':
    main()
