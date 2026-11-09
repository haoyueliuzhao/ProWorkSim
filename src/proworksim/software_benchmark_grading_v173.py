"""One no-model official score for the originally closed17002 committed tree."""
from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

from . import software_benchmark_scope_v173 as scope
from . import software_benchmark_grading_v170 as previous
from . import software_benchmark_closed_export_recovery_v172 as exports
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v131 as cleanup_binding
from .software_benchmark_candidates_v054 import reference, checked
from .software_benchmark_expansion_episode_v069 import clone_function
from .software_benchmark_rescore_v095 import host_limits

VERSION = 'v173-closed-work-observer-only-official-score-r1'
RESULT = exports.OUTPUT/'17002/recovery-result.json'
QUAL = previous.scope.COORDINATOR_ROOT/'qualifications'/(scope.TASK+'.json')


def result():
    row = scope.load(reference(scope.PLAN_FILE))['rows'][0]
    return exports.validate_export_result_bounded(reference(RESULT), row)


def scorer():
    value = previous.scorer(scope.dispatch_view())
    ns = value.score_request.__globals__
    ns['VERSION'] = VERSION
    inherited_manifest = value.installation_manifest

    def manifest():
        return {**inherited_manifest(), 'normal_export_recovery_adapter': reference(__file__),
            'recovery_scope': reference(scope.__file__), 'recovered_candidate': reference(RESULT),
            'normal_export_validator': reference(exports.__file__), 'new_model_calls': 0,
            'measurement_coverage_upgraded': False, 'grading_lane_count': 1}

    def qualification(ref, config, plan_ref):
        if ref != reference(QUAL) or plan_ref != reference(scope.PLAN_FILE):
            raise ValueError('Only the unchanged qualified Xarray environment is admitted')
        before = scope.load(reference(previous.scope.COORDINATOR_ROOT/'scorer-manifest.json'))
        after = manifest()
        keys = ('parent', 'archive_adapter', 'limits', 'cap_drop', 'no_new_privileges',
            'official_tests_and_scoring_rules_changed', 'host_namespace_mount_or_daemon_operations',
            'pilot_environment_adapter', 'selective_reset_by_task', 'selective_reset_actual_hashes',
            'legacy_boundary_probe', 'fresh_baseline_normalization_tasks')
        if any(before.get(k) != after.get(k) for k in keys):
            raise ValueError('Actual official test/environment logic changed')
        return previous.validate_reused_qualification(ref, config, reference(previous.scope.PLAN_FILE))

    def candidate(request, resource, config, plan):
        recovered = result()
        if (request.get('generation_result') != reference(RESULT)
            or request.get('candidate_lock') != recovered['candidate_lock']
            or resource.get('role') != 'score' or resource.get('slot_id') != scope.SLOT
            or config['instance_id'] != scope.TASK or config['slot_id'] != scope.SLOT
            or request['group_id'] != 'C0' or request['organization_id'] != 'REVIEW2'
            or config['scorer_request_base']['image']['image_id'] != resource['image_id']):
            raise ValueError('No other tree, member, condition or endpoint may be scored')
        lock = scope.load(recovered['candidate_lock'])
        if lock.get('endpoint') != 'terminal_code' or lock['task_id'] != scope.TASK:
            raise ValueError('Expected the original unique final member001 candidate')
        qualification(request['qualification'], config, request['plan'])
        return lock

    ns.update(installation_manifest=manifest, validate_qualification=qualification,
              validate_candidate_request=candidate)
    # The original managed lock stores its patch receipt by immutable reference.
    # Only dereference that receipt; official patch bytes/tests stay unchanged.
    source = inspect.getsource(base.original._score)
    needle = 'patch = checked(lock["patch_receipt"]["patch"]).read_bytes()'
    if source.count(needle) != 1:
        raise ValueError('Official patch load site changed')
    compiled = {}
    exec(compile(source.replace(needle,
        'patch = checked(load(lock["patch_receipt"])["patch"]).read_bytes()'),
        __file__+':managed-lock', 'exec'), ns, compiled)
    ns['_score'] = compiled['_score']
    for name in ('validate_capacity_claim', 'validate_request'):
        source = inspect.getsource(getattr(base.original, name))
        if source.count('range(4)') != 1:
            raise ValueError('Original lane validation changed')
        compiled = {}
        exec(compile(source.replace('range(4)', 'range(1)'), __file__+':one-lane', 'exec'), ns, compiled)
        ns[name] = compiled[name]
    ns['cleanup'] = clone_function(cleanup_binding.bind_physical_cleanup,
        {**cleanup_binding.bind_physical_cleanup.__globals__, 'VERSION': VERSION})(ns)
    for name in ('installation_manifest', 'validate_qualification', 'validate_candidate_request',
                 '_score', 'validate_capacity_claim', 'validate_request', 'cleanup'):
        setattr(value, name, ns[name])
    return value


def prepare():
    original = scope.load(reference(previous.scope.PLAN_FILE))
    row = next(r for r in original['rows'] if r['slot_index'] == 17002)
    recovered = exports.validate_export_result_bounded(reference(RESULT), row)
    if recovered.get('submitted') is not True or recovered.get('same_tree') is not True:
        raise ValueError('This plan is only the already proven same-tree legal delivery')
    plan = {'version': scope.VERSION, 'constraints': scope.CONSTRAINTS, 'rows': [row],
        'environments': {scope.TASK: original['environments'][scope.TASK]},
        'resources': {key: {**original['resources'][old], 'endpoint': endpoint}
            for key, old, endpoint in [(scope.CODE_KEY, 'score-17002', 'code'),
                (scope.DELIVERY_KEY, 'delivery-score-17002', 'delivery')]},
        'host_cpu_pool': reference(scope.CPU_POOL_FILE), 'same_tree_delivery': True,
        'new_model_calls': 0, 'recovered_result': reference(RESULT)}
    plan_ref = scope.retain(scope.PLAN_FILE, scope.validate_plan(plan))
    current = scorer()
    manifest = scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json', current.installation_manifest())
    config = scope.load(row['configuration'])
    current.validate_qualification(reference(QUAL), config, plan_ref)
    request = {'version': VERSION, 'resource_key': scope.CODE_KEY, 'instance_id': scope.TASK,
        'slot_id': scope.SLOT, 'configuration': row['configuration'], 'generation_result': reference(RESULT),
        'candidate_lock': recovered['candidate_lock'], 'qualification': reference(QUAL),
        'measurement_kind': row['measurement_kind'], 'source_slot_id': row['source_slot_id'],
        'group_id': 'C0', 'organization_id': 'REVIEW2', 'plan': plan_ref, 'limits': current.LIMITS,
        'scorer_manifest': manifest, 'cpuset_cpus': None, 'patch_kind': None,
        'directory': str(scope.GRADING_ROOT/scope.CODE_KEY),
        **current.environment.request_fields(scope.TASK)}
    request_ref = scope.retain(scope.GRADING_ROOT/scope.CODE_KEY/'request.json', request)
    sources = [reference(__file__), reference(scope.__file__), reference(exports.__file__)]
    for ref in scope.load(reference(previous.scope.SOURCE_FILE))['files']:
        checked(ref)
        if ref not in sources:
            sources.append(ref)
    source_ref = scope.retain(scope.SOURCE_FILE, {'files': sources, 'active_runtime_changed': False})
    auth = scope.retain(scope.AUTH_FILE, {'version': 'v173-original17002-rescore-authority-r1',
        'status': 'approved', 'scope': reference(scope.__file__), 'plan': plan_ref,
        'source_index': source_ref, 'standing_policy': reference(scope.STANDING_POLICY_FILE),
        'resource_keys': [scope.CODE_KEY, scope.DELIVERY_KEY], 'constraints': scope.CONSTRAINTS,
        'maximum_score_containers': 2, 'expected_containers': 1, 'new_model_calls': 0,
        'shared_host_configuration_changes': 0, 'network_connections': 0,
        'prior_zero_container_socket_denial': reference(scope.ROOT/'runs/software-benchmark-v172/original-17002-rescore-r1/grading/score-original-17002-code-v172/quiescence.json'),
        'basis': 'Standing user permission for non-disruptive experimental Docker and completion of unfinished work'})
    return scope.retain(scope.COORDINATOR_ROOT/'preparation.json',
        {'request': request_ref, 'plan': plan_ref, 'authority': auth, 'Docker_operations': 0})


def execute():
    scope.require_grading_allowed('v173.run')
    current = scorer()
    prepared = scope.load(reference(scope.COORDINATOR_ROOT/'preparation.json'))
    ref = prepared['request']; request = scope.load(ref); folder = Path(request['directory'])
    if scope.main_grader_claims():
        raise scope.ResourceBusy('Wait for main scoring vacancy')
    scope.retain(scope.RELEASE_FILE, {'approved': True, 'plan': reference(scope.PLAN_FILE),
        'authority': reference(scope.AUTH_FILE), 'task': scope.TASK,
        'coordination_basis': 'root_confirmed_main_grader_slot_available'})
    claim = scope.dispatch_view().claim_resource(scope.CODE_KEY, lane=0)
    scope.retain(folder/'capacity-claim.json', {'prepared_request': ref, 'claim': claim})
    execution = current.resolve_execution_request(request)
    scope.retain(folder/'host-limits.json', host_limits(execution['cpuset_cpus']))
    # score_request validates the actual cold manifest, locks and capacity before Docker.
    current.score_request(request)
    quiet = scope.load(reference(folder/'quiescence.json'))
    if quiet.get('quiescent') is not True or quiet.get('cleanup_errors'):
        raise RuntimeError('Owned scoring cleanup is not complete')
    receipt_ref = reference(folder/'receipt.json'); receipt = scope.load(receipt_ref)
    recovered = result()
    verdict = exports.closure.validate_delivery_evidence(scope.load(recovered['delivery_evidence']),
        scope.load(recovered['delivery_snapshot']), scope.load(recovered['baseline_snapshot']))
    known = receipt.get('status') == 'official_report' and type(receipt.get('resolved')) is bool
    return scope.retain(scope.COORDINATOR_ROOT/'result.json', {'version': VERSION,
        'status': 'scored_original_closed_candidate' if known else 'scoring_technical_unknown',
        'recovered_result': reference(RESULT), 'code_receipt': receipt_ref,
        'R_code': receipt['resolved'] if known else None,
        'R_delivery': receipt['resolved'] if known and verdict['submitted'] and verdict['same_tree'] else None,
        'same_tree_delivery_proof': verdict, 'new_model_calls': 0, 'scoring_containers': 1,
        'original_observation_status': 'partial', 'measurement_coverage_upgraded': False,
        'quiescence': reference(folder/'quiescence.json'), 'original_failure_changed': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else execute(), ensure_ascii=False))
