"""Scoped v114 rescoring and explicitly separate stopped-code supplements.

The official grader, test bytes, candidates and original control evidence stay
unchanged. This private binding admits the exact new PROJECT closure identity,
enumerates two grading lanes and separates physical cleanup from CA measurement.
The same v111 task/candidate inventory remains under the new v114 recovery plan and
coordinator. No old attempts reopen and no scoring or qualification rule changes.
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
from . import software_benchmark_scope_v114 as scope
from . import software_benchmark_project_closure_v110 as closure
from . import software_benchmark_grading_repairs_v114 as reset_binding
from . import software_benchmark_stopped_recovery_v114 as stopped
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_candidates_v054 import write_new
from . import software_benchmark_requests_tls_v068 as lifecycle
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function

VERSION = 'v114-recovery-official-scoring-r1'
DEPLOYMENT_VERSION = 'v114-unknown-recovery-scoring-binding-r1'
FRESH_CONTROL_TASKS = frozenset(('psf__requests-1766', 'psf__requests-1921',
                                 'sphinx-doc__sphinx-10614', 'pylint-dev__pylint-6528'))
RECOVERED_MEASUREMENT = 'supplemental_stopped_code_recovery'
CLOSED_RESCORES = {7232: 'sphinx-doc__sphinx-10614', 7283: 'pylint-dev__pylint-6528'}
NEW_GENERATIONS = frozenset((7238, 7239, 7266, 7267))
_namespace = clone_namespace(previous, scope=scope, VERSION=VERSION,
    REUSE_VERSION='v114-reused-v062-control-qualification-r1',
    EQUIVALENCE_VERSION='v114-explicit-v062-official-environment-equivalence-r1',
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
_parent_host = _namespace['host']
_parent_equivalence = _namespace['equivalence_value']


def environment_revision():
    from . import software_benchmark_environment_v114
    return software_benchmark_environment_v114


def control_key(task, kind):
    if task not in FRESH_CONTROL_TASKS or kind not in ('gold', 'empty'):
        raise ValueError('Only the eight frozen fresh recovery controls are allowed')
    return 'control-v114-'+task+'-'+kind


def equivalence_value(manifest_ref, *, harness_source=None):
    proof = _parent_equivalence(manifest_ref, harness_source=harness_source)
    return {**proof, 'reuse_only_for': sorted(stopped.TASKS.values()),
            'fresh_controls_required_for': sorted(FRESH_CONTROL_TASKS),
            'reset_revision': reference(reset_binding.__file__),
            'refreshed_environment_revision': reference(environment_revision().__file__)}


def qualification_value(task, proof_ref, plan):
    """Reuse immutable offline evidence, but refresh two live HTTP/TLS controls.

    This rule is fixed before any new model result. Old HTTP controls cannot
    establish today's external service behavior after observed HTTP 502s.
    It adds no candidate retry, CA bypass, new endpoint or automatic repair.
    """
    if task in FRESH_CONTROL_TASKS:
        raise ValueError('v114 requires one fresh gold/empty pair for the changed reset or HTTP endpoint')
    if task not in stopped.TASKS.values():
        raise ValueError('Only the two unchanged stopped-code environments may reuse qualification')
    return _parent_qualification_value(task, proof_ref, plan)


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
                'authorization_bound_by': 'v114 recovery plan and request; no old resource authority is reopened'}

    # Update both the public module view and the actual validator's namespace.
    environment.offline.environment_manifest = offline_manifest
    environment.offline.validate_environment.__globals__['environment_manifest'] = offline_manifest
    environment.tls.run_official = lifecycle.run_official
    return environment_revision().bind_environment(environment, private)


_parent_scorer = _namespace['scorer']


def validate_recovery_candidate(request, resource, config, plan):
    """Validate a separate stopped-code endpoint without inventing closed generation."""
    index = config.get('slot_index')
    if (index not in stopped.TASKS or config.get('instance_id') != stopped.TASKS[index]
            or config.get('arm') != 'REF' or resource.get('role') != 'score'
            or resource.get('endpoint') != stopped.ENDPOINT
            or request.get('resource_key') != f'score-v114-{index}'
            or request.get('measurement_kind') != RECOVERED_MEASUREMENT):
        raise ValueError('Only the two explicitly supplemental stopped-code resources are admitted')
    specifications = [item for item in plan.get('score_recoveries', [])
                      if item.get('kind') == stopped.ENDPOINT and item.get('row', {}).get('slot_index') == index]
    if len(specifications) != 1:
        raise ValueError('The recovery plan must name this supplemental source exactly once')
    ref = specifications[0].get('result')
    folder = stopped.OUTPUT/str(index)
    if (not isinstance(ref, dict) or request.get('recovery_result') != ref
            or Path(ref['path']).resolve() != folder/'recovery-result.json'):
        raise ValueError('Supplemental scoring must bind the one new frozen recovery result')
    recovered = scope.load(ref)
    row = next(row for row in plan['rows'] if row['slot_index'] == index)
    if specifications[0].get('row') != row or specifications[0].get('endpoint') != 'code':
        raise ValueError('The display endpoint cannot alter the frozen supplemental row')
    original_folder = scope.BATCH_ROOT/'episodes'/str(index)
    original_ref = reference(original_folder/'result.json')
    if (recovered.get('version') != stopped.VERSION or recovered.get('status') != 'supplemental_candidate_locked'
            or recovered.get('endpoint') != stopped.ENDPOINT
            or recovered.get('original_generation_status') != 'technical_unknown'
            or recovered.get('replaces_original_endpoint') is not False
            or recovered.get('model_resampling') is not False or recovered.get('bad_action_replayed') is not False
            or recovered.get('model_calls') != 0 or recovered.get('scoring_calls') != 0
            or recovered.get('round_trip_verified') is not True
            or any(recovered.get(key) != row[key] for key in ('slot_id', 'slot_index', 'instance_id', 'condition_id', 'configuration'))
            or recovered.get('original_result') != original_ref
            or request.get('generation_result') != original_ref
            or request.get('original_generation_result') != original_ref
            or request.get('candidate_lock') != recovered.get('candidate_lock')
            or Path(recovered['candidate_lock']['path']).resolve() != folder/'lock.json'
            or Path(recovered['source']['path']).resolve() != folder/'recovery-source.json'):
        raise ValueError('The supplemental endpoint changed its independent status or source attempt')
    lock, source, original = (scope.load(recovered[name]) for name in ('candidate_lock', 'source', 'original_result'))
    evidence = source['original_evidence']
    if (source.get('version') != stopped.VERSION or source.get('endpoint') != stopped.ENDPOINT
            or source.get('original_official_final_candidate') is not False
            or source.get('original_bad_tool_call_executed') is not False
            or source.get('old_result_changed') is not False
            or any(source.get(key) != 0 for key in ('model_calls', 'tool_calls', 'scoring_calls'))
            or evidence.get('original_result') != original_ref
            or source.get('plan') != reference(scope.BATCH_ROOT/'execution-plan-v113.json')):
        raise ValueError('Stopped-code source proof no longer binds the original failure')
    child, interrupted, writers, quiet, baseline_provenance = (
        scope.load(evidence[name]) for name in
        ('controller_result', 'interrupted', 'writer_quiescence', 'quiescence', 'baseline_provenance'))
    stopped.validate_records(index, source['slot'], original, child, interrupted, writers, quiet, baseline_provenance)
    if (any(source['slot'].get(key) != row.get(key) for key in
            ('slot_id', 'slot_index', 'instance_id', 'arm', 'condition_id', 'seed', 'configuration'))
            or recovered['actual_original_tokens'] != child['ledger']['complete_actual_tokens']):
        raise ValueError('Supplemental scoring cannot replace task identity or original accounting')
    rejected = stopped.rejected_action_evidence(original_folder, scope.load(evidence['final_provider_response']))
    if source.get('rejected_action_evidence') != rejected:
        raise ValueError('The malformed model action is not proven rejected without execution')
    patch = lock.get('patch_receipt', {})
    if (lock.get('version') != stopped.VERSION or lock.get('endpoint') != stopped.ENDPOINT
            or lock.get('lock_before_grading') is not True
            or lock.get('candidate_selection_after_scoring') is not False
            or lock.get('original_generation_status') != 'technical_unknown'
            or lock.get('replaces_original_endpoint') is not False
            or any(lock.get(key) != 0 for key in ('model_calls', 'tool_calls', 'grading_calls'))
            or any(lock['slot'].get(key) != row.get(key) for key in
                   ('slot_id', 'slot_index', 'instance_id', 'condition_id', 'arm', 'seed', 'configuration'))
            or lock.get('baseline') != evidence.get('baseline')
            or lock.get('baseline') != baseline_provenance.get('snapshot')
            or lock.get('quiescence') != evidence['writer_quiescence']
            or lock.get('recovery_source') != recovered['source']
            or Path(lock['candidate']['path']).resolve() != folder/'candidate-bundle.json'
            or lock.get('tree_sha256') != recovered['candidate_tree_sha256']
            or patch.get('candidate_tree_sha256') != lock['tree_sha256']
            or patch.get('patch') != recovered['patch']
            or Path(patch['patch']['path']).resolve() != folder/'candidate.patch'
            or patch.get('round_trip_verified') is not True or patch.get('utf8_strict') is not True
            or patch.get('candidate_content_changed') is not False):
        raise ValueError('The sole stopped candidate lost its unique lock or lossless patch proof')
    checked = previous.checked(patch['patch'])
    checked.read_bytes().decode('utf-8', 'strict')
    return lock


def bind_recovery_validation(namespace):
    old_planned = namespace['_planned']
    old_candidate = namespace['validate_candidate_request']

    def planned(request):
        if request.get('plan') != reference(scope.PLAN_FILE):
            raise ValueError('Scoring belongs to another recovery plan')
        plan = scope.load(request['plan'])
        resource = plan['resources'].get(request['resource_key'], {})
        if resource.get('endpoint') != stopped.ENDPOINT:
            if request.get('recovery_result') is not None or request.get('original_generation_result') is not None:
                raise ValueError('Ordinary closed scoring cannot acquire supplemental evidence')
            return old_planned(request)
        row = next(row for row in plan['rows'] if row['slot_id'] == resource.get('slot_id'))
        config = scope.load(request['configuration'])
        if (resource.get('role') != 'score' or config['instance_id'] != resource['instance_id']
                or request['configuration'] != row['configuration']
                or request.get('slot_id') != row['slot_id'] or request.get('source_slot_id') != row['source_slot_id']
                or request.get('measurement_kind') != RECOVERED_MEASUREMENT):
            raise ValueError('Recovered scoring resource/task identity changed')
        return plan, resource, config

    def candidate(request, resource, config, plan):
        if resource.get('endpoint') != stopped.ENDPOINT:
            return old_candidate(request, resource, config, plan)
        lock = validate_recovery_candidate(request, resource, config, plan)
        namespace['validate_qualification'](request['qualification'], config, request['plan'])
        if config['scorer_request_base']['image']['image_id'] != resource['image_id']:
            raise ValueError('Recovered scoring must use the original exact task image')
        return lock

    namespace.update(_planned=planned, validate_candidate_request=candidate)


def bind_supplemental_writer(namespace):
    inherited = namespace['write_new']

    def writer(path, value):
        if (Path(path).name in {'receipt.json', 'identity.json'} and isinstance(value, dict)
                and value.get('endpoint') == stopped.ENDPOINT):
            prepared = value.get('request')
            if prepared is None:
                prepared = scope.load(value['identity'])['request']
            request = scope.load(prepared)
            if request.get('measurement_kind') != RECOVERED_MEASUREMENT:
                raise ValueError('Supplemental receipt cannot masquerade as a complete primary endpoint')
            value.update(recovery_result=request['recovery_result'],
                original_generation_result=request['original_generation_result'],
                original_generation_status='technical_unknown', replaces_original_endpoint=False,
                model_resampling=False)
        return inherited(path, value)

    return writer


def fresh_qualification_validator(namespace):
    source = inspect.getsource(previous.original.validate_qualification)
    needle = '"control-" + task + "-" + kind'
    if source.count(needle) != 1:
        raise ValueError('The exact native control resource-key expression changed')
    source = source.replace(needle, '"control-v114-" + task + "-" + kind')
    compiled = {}
    exec(compile(source, __file__+':fresh-control-prefix', 'exec'), namespace, compiled)
    native = compiled['validate_qualification']

    def validate(ref, config, plan_ref):
        value = scope.load(ref)
        if value.get('version') == _namespace['REUSE_VERSION']:
            return _namespace['validate_reused_qualification'](ref, config, plan_ref)
        if value.get('version') != VERSION or config['instance_id'] not in FRESH_CONTROL_TASKS:
            raise ValueError('No legacy qualification or unplanned fresh control may authorize recovery scoring')
        return native(ref, config, plan_ref)

    return validate


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
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence,
                     MAX_GRADERS=scope.MAX_GRADERS)
    validator = _lane_validator(namespace)
    namespace['validate_qualification'] = fresh_qualification_validator(namespace)
    bind_recovery_validation(namespace)
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
            'old_attempts_or_grading_backlog_resumed': False,
            'fresh_gold_empty_required_for': sorted(FRESH_CONTROL_TASKS),
            'other_controls_reused_only_after_exact_environment_equivalence': True,
            'original_scoring_adapter': reference(previous.original.__file__),
            'grading_lane_count': scope.MAX_GRADERS,
            'grading_validation_change': 'Exactly range(4) -> range(MAX_GRADERS); MAX_GRADERS=2',
            'official_scoring_function_changed': False,
            'TLS_lifecycle_binding': reference(lifecycle.__file__),
            'physical_cleanup_measurement_separation': reference(__file__),
            'bounded_HTTP_502_validity_note': 'Only two TLS tasks; actual failed status assertions; official result preserved',
            'managed_closure_identity_change': 'Only frozen v110 strategy PROJECT task/seed identities accepted in the new v111 plan'}

    cleanup = bind_physical_cleanup(namespace)
    namespace.update(validate_request=validator, installation_manifest=installation_manifest,
                     cleanup=cleanup, write_new=bind_receipt_writer(namespace))
    namespace['write_new'] = bind_supplemental_writer(namespace)
    value.__dict__.update(validate_request=validator, installation_manifest=installation_manifest,
                          validate_delivery_evidence=closure.validate_delivery_evidence, cleanup=cleanup,
                          validate_qualification=namespace['validate_qualification'],
                          validate_candidate_request=namespace['validate_candidate_request'],
                          _planned=namespace['_planned'], write_new=namespace['write_new'])
    dataset = json.loads(previous.checked(reference(
        scope.ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json')).read_bytes())
    rows = [row for row in dataset if row['instance_id'] in reset_binding.reset.TASKS]
    passthrough = set(stopped.TASKS.values()) | {'psf__requests-1766', 'psf__requests-1921'}
    return reset_binding.bind_scorer(value, rows, passthrough_tasks=passthrough)


def prepare_environment_qualifications_local():
    policy = scope.dispatch_view(scope.require_grading_allowed)
    scoring = scorer(policy)
    scoring.environment.prepare()
    manifest = scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json', scoring.installation_manifest())
    proof = scope.retain(scope.COORDINATOR_ROOT/'qualification-equivalence.json', equivalence_value(manifest))
    plan = scope.load(reference(scope.PLAN_FILE))
    if (set(plan['environments']) != FRESH_CONTROL_TASKS | set(stopped.TASKS.values())
            or set(plan.get('fresh_control_tasks', [])) != FRESH_CONTROL_TASKS):
        raise ValueError('Recovery requires exactly four changed and two unchanged environments')
    qualifications, controls, reasons = {}, [], {}
    for task in sorted(plan['environments']):
        if task in FRESH_CONTROL_TASKS:
            reasons[task] = {'status': 'requires_new_controls',
                            'reason': 'changed test reset or frozen external service endpoint'}
            for kind in ('gold', 'empty'):
                key = control_key(task, kind)
                resource = plan['resources'].get(key, {})
                if (resource.get('role') != 'control' or resource.get('instance_id') != task
                        or resource.get('patch_kind') != kind):
                    raise ValueError('A fresh control lacks its exact declared new resource')
                request = {'version': VERSION, 'resource_key': key, 'instance_id': task, 'slot_id': None,
                    'plan': reference(scope.PLAN_FILE), 'configuration': plan['environments'][task]['configuration'],
                    'patch_kind': kind, 'limits': scoring.LIMITS, 'scorer_manifest': manifest,
                    'cpuset_cpus': None, 'directory': str(scope.GRADING_ROOT/key), 'candidate_lock': None,
                    **scoring.environment.request_fields(task)}
                controls.append(scope.retain(scope.GRADING_ROOT/key/'request.json', request))
        else:
            value = qualification_value(task, proof, plan)
            ref = scope.retain(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'), value)
            qualifications[task] = {'status': 'qualified', 'qualification': ref, 'reused_controls': True}
    result = {'version': VERSION, 'qualifications': qualifications, 'controls': controls,
        'reuse_failures': reasons, 'equivalence': proof, 'model_calls': 0, 'Docker_operations': 0,
        'TLS_controls_require_original_CA_or_explicitly_frozen_authorized_CA': True,
        'TLS_controls_should_be_serialized': True, 'automatic_HTTP_retries': False}
    scope.retain(scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json', result)
    return result


def host(policy, scoring):
    value = _parent_host(policy, scoring)

    def prepare_manifest():
        return scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json', _namespace['cold_manifest']())

    def resource_for(plan, row, *, endpoint):
        role = 'delivery_score' if endpoint == 'delivery' else 'score'
        exact_endpoint = 'delivery' if endpoint == 'delivery' else endpoint
        matches = [(key, item) for key, item in plan['resources'].items()
                   if item.get('role') == role and item.get('slot_id') == row['slot_id']
                   and item.get('endpoint') == exact_endpoint]
        if len(matches) != 1:
            raise ValueError('Each scoring endpoint must have one exact fresh resource')
        key, resource = matches[0]
        index = row['slot_index']
        expected = (f'delivery-score-{index}' if endpoint == 'delivery' else
                    f'score-v114-{index}' if index in CLOSED_RESCORES or endpoint == stopped.ENDPOINT
                    else f'score-{index}')
        if key != expected or resource['instance_id'] != row['instance_id']:
            raise ValueError('A legacy or foreign scoring resource cannot be reused')
        return key, resource

    def base_request(plan, row, key, *, endpoint, candidate_lock, generation_result, measurement_kind):
        task = row['instance_id']
        qualification = reference(scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
        scoring.validate_qualification(qualification, scope.load(row['configuration']), reference(scope.PLAN_FILE))
        return {'version': VERSION, 'resource_key': key, 'instance_id': task,
            'plan': reference(scope.PLAN_FILE), 'configuration': row['configuration'],
            'candidate_lock': candidate_lock, 'generation_result': generation_result,
            'measurement_kind': measurement_kind, 'source_slot_id': row['source_slot_id'],
            'slot_id': row['slot_id'], 'qualification': qualification, 'limits': scoring.LIMITS,
            'scorer_manifest': prepare_manifest(), 'cpuset_cpus': None,
            'directory': str(scope.GRADING_ROOT/key), 'patch_kind': None,
            **scoring.environment.request_fields(task)}

    def prepare_score(result_ref, *, endpoint='code'):
        if endpoint not in ('code', 'delivery'):
            raise ValueError('Ordinary closed scoring has code/delivery endpoints only')
        plan, result = scope.load(reference(scope.PLAN_FILE)), scope.load(result_ref)
        rows = [row for row in plan['rows'] if row['slot_id'] == result.get('slot_id')]
        if len(rows) != 1:
            raise ValueError('Closed scoring result outside the frozen recovery inventory')
        row = rows[0]
        index = row['slot_index']
        if (index not in NEW_GENERATIONS | set(CLOSED_RESCORES)
                or result.get('status') != 'closed' or result.get('configuration') != row['configuration']
                or result.get('measurement_kind') != 'full_verified_comparison'
                or Path(result_ref['path']).resolve() != scope.BATCH_ROOT/'episodes'/str(index)/'result.json'):
            raise ValueError('Only original closed or new first-call closed candidates use the primary endpoint')
        if index in CLOSED_RESCORES:
            specs = [item for item in plan['score_recoveries'] if item.get('kind') == 'original_locked'
                     and item.get('row') == row and item.get('result') == result_ref and item.get('endpoint') == 'code']
            if len(specs) != 1 or endpoint != 'code':
                raise ValueError('Original closed rescore source is not the unique frozen request')
        if endpoint == 'delivery':
            proof = scoring.validate_project_delivery(result, scope.load(row['configuration']), Path(result_ref['path']).parent)
            if row['arm'] != 'PROJECT' or proof.get('submitted') is not True:
                raise ValueError('An absent legal delivery is recorded without scoring')
        key, _ = resource_for(plan, row, endpoint=endpoint)
        request = base_request(plan, row, key, endpoint=endpoint,
            candidate_lock=result['candidate_lock' if endpoint == 'code' else 'delivery_candidate_lock'],
            generation_result=result_ref, measurement_kind=row['measurement_kind'])
        request['delivery_evidence'] = result.get('delivery_evidence') if endpoint == 'delivery' else None
        if index in CLOSED_RESCORES:
            old = reference(scope.BATCH_ROOT/'grading'/f'score-{index}'/'request.json')
            prior = scope.load(old)
            if any(request[key] != prior[key] for key in ('configuration', 'generation_result', 'candidate_lock')):
                raise ValueError('Closed rescoring cannot substitute original candidate bytes')
            request['rescore_of'] = old
        return scope.retain(scope.GRADING_ROOT/key/'request.json', request)

    def prepare_recovery_score(recovery_ref):
        recovered = scope.load(recovery_ref)
        plan = scope.load(reference(scope.PLAN_FILE))
        rows = [row for row in plan['rows'] if row['slot_id'] == recovered.get('slot_id')]
        if len(rows) != 1:
            raise ValueError('Stopped-code supplement outside this plan')
        row = rows[0]
        key, resource = resource_for(plan, row, endpoint=stopped.ENDPOINT)
        request = base_request(plan, row, key, endpoint=stopped.ENDPOINT,
            candidate_lock=recovered['candidate_lock'], generation_result=recovered['original_result'],
            measurement_kind=RECOVERED_MEASUREMENT)
        request.update(recovery_result=recovery_ref, original_generation_result=recovered['original_result'],
                       delivery_evidence=None)
        validate_recovery_candidate(request, resource, scope.load(row['configuration']), plan)
        return scope.retain(scope.GRADING_ROOT/key/'request.json', request)

    def prepare_score_recovery(specification):
        plan = scope.load(reference(scope.PLAN_FILE))
        if plan.get('score_recoveries', []).count(specification) != 1:
            raise ValueError('A recovery job must be the one exact frozen specification')
        if specification.get('kind') == 'original_locked':
            return prepare_score(specification['result'], endpoint='code')
        if specification.get('kind') == stopped.ENDPOINT:
            return prepare_recovery_score(specification['result'])
        raise ValueError('No model retry or alternative recovery endpoint is allowed')

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

    value.__dict__.update(prepare_manifest=prepare_manifest, prepare_score=prepare_score,
        prepare_recovery_score=prepare_recovery_score, prepare_score_recovery=prepare_score_recovery,
        qualify=qualify)
    return value


def run_request(self, request_ref, stop_event=None):
    """Start only a freshly scoped grader subprocess for this prepared request."""
    request = scope.load(request_ref)
    scope.require_grading_allowed('v114.run', slot_id=request.get('slot_id'),
                                  instance_id=request['instance_id'])

    def fixed_python(arguments):
        if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
            raise ValueError('Only the unchanged official scoring child may be redirected')
        return _namespace['command'](arguments[2:])

    return clone_function(self.base.run_request, {**self.base.run_request.__globals__,
        'fixed_python': fixed_python, 'bootstrap_environment': _namespace['clean_environment']})(
            request_ref, stop_event=stop_event)


def score_request(request, *, validate_only=False):
    scope.require_grading_allowed('v114.run', slot_id=request.get('slot_id'),
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
    write_new(folder/'v114-host-limits.json', limits)
    return scoring.score_request(request)


_namespace.update(private_environment=private_environment, scorer=scorer,
                  qualification_value=qualification_value, score_request=score_request,
                  host=host, prepare_environment_qualifications_local=prepare_environment_qualifications_local,
                  equivalence_value=equivalence_value)
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
