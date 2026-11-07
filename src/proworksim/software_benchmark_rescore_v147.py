"""Bounded, separately labelled scoring of stopped v143 managed candidates.

Uses the qualified official evaluator and original images; no generation,
host mounts, daemon changes, new volumes, or writes to original results.
"""
from __future__ import annotations

import argparse
import json
import inspect
import os
from pathlib import Path
from types import SimpleNamespace

from . import software_benchmark_dispatch_v066 as dispatch
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v131 as groups
from . import software_benchmark_grading_v143 as previous
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_benchmark_rescore_v095 import host_limits

ROOT = dispatch.ROOT
VERSION = 'v147-requests1766-idle180-scoring-r1'
RUN = ROOT/'runs/software-benchmark-v147/requests1766-idle180-r1'
PLAN = RUN/'plan.json'
AUTH = RUN/'authorization.json'
SOURCE = RUN/'runtime-sources.json'
GRADING = RUN/'grading'
CONSTRAINTS = {**previous.scope.CONSTRAINTS,
    'maximum_containers': 4, 'maximum_named_volumes': 0,
    'maximum_active_containers': 1, 'active_grader_limit': 1,
    'maximum_combined_reserved_cpu': 4,
    'maximum_combined_reserved_memory_bytes': 20*1024**3,
    'maximum_real_tls_sessions': 4,
    'real_tls_all_sessions_connections': 2048,
    'real_tls_all_sessions_payload_bytes': 256*1024**2,
    'fresh_generation_slots': 0, 'new_model_calls_for_preparation': 0,
    'new_services_or_slices': 0, 'physical_gpus': []}


def load(ref):
    return json.loads(checked(ref).read_bytes())


def allowed(operation='v066.run', *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Ordinary-user bounded experiment Docker only')
    if operation not in {'v066.run', 'v066.score', 'v066.control', 'v066.grader.create',
                          'v066.grader.start', 'v066.transport'}:
        raise PermissionError('Only declared supplementary scoring operations are allowed')
    plan, auth = load(reference(PLAN)), load(reference(AUTH))
    if (auth.get('plan') != reference(PLAN) or auth.get('constraints') != CONSTRAINTS
            or auth.get('status') != 'authorized_by_current_user_instructions'
            or auth.get('source_index') != reference(SOURCE)):
        raise PermissionError('Frozen scoring-only authority differs')
    for ref in load(auth['source_index'])['files']:
        checked(ref)
    if (slot_id is not None and slot_id not in {r['slot_id'] for r in plan['rows']}
            or instance_id is not None and instance_id not in plan['environments']):
        raise PermissionError('Foreign scoring task')
    if operation == 'v066.transport' and instance_id not in previous.TLS_TASKS:
        raise PermissionError('Only the four declared Requests candidates use the TLS relay')
    return {**auth, 'plan': reference(PLAN), 'constraints': CONSTRAINTS}


def policy():
    ns = clone_namespace(dispatch, VERSION=VERSION, BATCH_ROOT=RUN, PLAN_FILE=PLAN,
        GRADING_ROOT=GRADING, COORDINATOR_RUN_ROOT=RUN/'coordinator',
        AUTHORIZATION_FILE=AUTH, SOURCE_INDEX_FILE=SOURCE,
        CONSTRAINTS=CONSTRAINTS, __file__=__file__)

    def cpu_set(role, index=0):
        if role != 'grader' or type(index) is not int or index not in range(1):
            raise ValueError('Only one four-CPU scoring lane exists')
        return previous.scope.cpu_set('grader', index)

    def budget(active, cpu, memory, spool=0):
        if len(active) >= 1 or cpu != 4 or memory != 16*1024**3 or spool:
            raise dispatch.ResourceBusy('The serial bounded grader is occupied')
        physical = ns['physical_capacity']()
        if (not physical['passed'] or physical['memory_available_bytes'] < 84*1024**3):
            raise dispatch.ResourceBusy('Actual shared-host headroom prevents grading')
        return {'reserved_cpu_after': 4*(len(active)+1),
                'reserved_memory_bytes_after': 20*1024**3*(len(active)+1),
                'physical_at_admission': physical}

    ns.update(require_v066_allowed=allowed, cpu_set=cpu_set, _budget=budget)
    inherited = ns['claim_resource']

    def claim(key, *, lane=None):
        if lane != 0:
            raise ValueError('A concrete scoring lane is mandatory')
        return inherited(key, lane=lane)

    ns['claim_resource'] = claim
    return base.module_from(ns, __name__+'.policy')


def scope_view():
    return SimpleNamespace(ROOT=ROOT, BATCH_ROOT=RUN, PLAN_FILE=PLAN,
        COORDINATOR_ROOT=RUN/'coordinator', GRADING_ROOT=GRADING,
        NETWORK_RESOLUTION_FILE=previous.scope.NETWORK_RESOLUTION_FILE,
        CA_PROFILE_FILE=previous.scope.CA_PROFILE_FILE,
        previous=previous.scope.previous, original=previous.scope.original, __file__=__file__, load=load,
        MAX_GRADERS=1, CONSTRAINTS=CONSTRAINTS,
        validate_original_probe_reuse=previous.scope.validate_original_probe_reuse)



def private_environment(policy):
    inherited = clone_function(previous.private_environment,
        {**previous.private_environment.__globals__, 'scope':scope_view(), '__file__':__file__})
    environment = inherited(policy)
    transport = environment.tls.transport
    OriginalLimits = transport.Limits

    class Limits(OriginalLimits):
        def __init__(self, **values):
            if values.get('idle_seconds',60) == 60:
                values['idle_seconds'] = 180
            super().__init__(**values)

        def validate(self):
            OriginalLimits(max_connections=self.max_connections, max_bytes=self.max_bytes,
                max_active=self.max_active, wall_seconds=self.wall_seconds,
                idle_seconds=min(self.idle_seconds,60), connect_seconds=self.connect_seconds).validate()
            if type(self.idle_seconds) not in (int,float) or not 0 < self.idle_seconds <= 180:
                raise transport.RelayError('Idle bound exceeds this isolated 180-second revision')
            return self

    transport.Limits = Limits
    original_relay = transport.relay_many
    def relay(*args, **kwargs):
        limits = kwargs.get('limits')
        if kwargs.get('instance_id') != 'psf__requests-1766' or not isinstance(limits,Limits):
            raise ValueError('The longer idle bound is confined to this Requests1766 scorer')
        limits.validate()
        if limits.idle_seconds != 180 or limits.wall_seconds != 1800:
            raise ValueError('Only the declared idle bound changed')
        result = original_relay(*args, **kwargs)
        result['scoring_transport_revision'] = VERSION
        result['idle_seconds'] = 180
        result['wall_seconds'] = 1800
        result['HTTP_completion_inferred_from_byte_counts'] = False
        return result
    transport.relay_many = relay
    old_manifest = environment.tls.environment_manifest
    def manifest():
        return {**old_manifest(), 'bounded_idle_revision':reference(__file__),
            'only_task':'psf__requests-1766','idle_seconds':180,'total_wall_seconds':1800,
            'network_payload_limits_unchanged':True,'fresh_gold_empty_required':True}
    environment.tls.environment_manifest = manifest
    environment.tls.validate_environment.__globals__['environment_manifest'] = manifest
    return environment


def validate_transport_evidence(receipt, quiet, observed, identity, folder, **kwargs):
    validator = clone_function(previous.validate_transport_evidence,
        {**previous.validate_transport_evidence.__globals__, 'scope':scope_view()})
    result = validator(receipt, quiet, observed, identity, folder, **kwargs)
    if (result.get('scoring_transport_revision') != VERSION or result.get('idle_seconds') != 180
            or result.get('wall_seconds') != 1800):
        raise ValueError('Actual completed transport did not use the isolated reviewed bounds')
    return result


def build_scorer(*, manifest_provider=None):
    scope, bound = scope_view(), policy()
    ns = clone_namespace(base, scope=scope, VERSION=VERSION, MODULE=__name__, __file__=__file__)
    ns['private_environment'] = clone_function(private_environment,
        {**globals(), 'scope': scope})
    scorer = ns['scorer'](bound, manifest_provider=manifest_provider)
    inner = scorer.validate_request.__globals__
    groups.bind_group_identity(inner)
    inner['MAX_GRADERS'] = 1
    inner['validate_request'] = groups._lane_validator(inner)
    original_manifest = scorer.installation_manifest

    def manifest():
        if manifest_provider:
            return manifest_provider()
        return {**original_manifest(), 'supplemental_stopped_candidate_adapter': reference(__file__),
            'endpoint': 'recovered_stopped_code', 'original_generation_unknown_preserved': True,
            'previous_qualified_scorer': reference(previous.__file__),
            'new_controls_required': True, 'scoring_transport_idle_seconds': 180,
            'idle_timeout_increase_is_mitigation_not_HTTP_completion_proof': True,
            'selective_reset_binding': reference(groups.reset_binding.__file__),
            'selective_reset_tasks': sorted(groups.reset_binding.reset.TASKS),
            'maximum_real_tls_sessions': 4, 'new_model_calls': 0}

    source = inspect.getsource(base.original.validate_qualification)
    source = source.replace('"control-" + task + "-" + kind', '"control-v147-" + task + "-" + kind')
    source = source.replace('from .software_benchmark_grading_qualification_v060 import validate_transport_evidence',
        'from .software_benchmark_rescore_v147 import validate_transport_evidence')
    compiled = {}
    exec(compile(source, __file__+':fresh-control-qualification', 'exec'), inner, compiled)
    native_qualification = compiled['validate_qualification']

    def qualification(ref, config, plan_ref):
        if config['instance_id'] != 'psf__requests-1766' or plan_ref != reference(PLAN):
            raise ValueError('Only the fresh single-task control pair may qualify')
        return native_qualification(ref, config, plan_ref)

    def candidate(request, resource, config, plan):
        from . import software_benchmark_stopped_recovery_v145 as recovery
        from .software_benchmark_recovered_validation_v145 import validate_recovery_result_bounded
        row = next(r for r in plan['rows'] if r['slot_id'] == request['slot_id'])
        job = plan['candidates'][str(row['slot_index'])]
        if (resource['role'] != 'score' or resource.get('endpoint') != recovery.ENDPOINT
                or request['generation_result'] != job['result']
                or request['candidate_lock'] != job['candidate_lock']
                or request['measurement_kind'] != recovery.ENDPOINT):
            raise ValueError('Only the once-locked stopped candidate is admitted')
        original_row = next(r for r in load(reference(previous.scope.PLAN_FILE))['rows']
                            if r['slot_id'] == row['slot_id'])
        recovered = load(job['result'])
        if recovered['candidate_lock'] != job['candidate_lock']:
            raise ValueError('The requested lock is not the unique recovered result lock')
        lock = validate_recovery_result_bounded(job['result'], original_row)
        if (lock['slot'] != original_row or lock.get('lock_before_grading') is not True
                or lock.get('candidate_selection_after_scoring') is not False
                or config['scorer_request_base']['image']['image_id'] != resource['image_id']):
            raise ValueError('Candidate or original image identity changed')
        checked(lock['patch_receipt']['patch'])
        qualification(request['qualification'], config, request['plan'])
        return lock

    inner.update(validate_candidate_request=candidate, validate_qualification=qualification,
                 installation_manifest=manifest)
    writer_ns = {**groups.bind_receipt_writer.__globals__, 'scope': scope, 'VERSION': VERSION}
    writer_ns['classify_http_502'] = clone_function(groups.classify_http_502, writer_ns)
    inner['write_new'] = clone_function(groups.bind_receipt_writer, writer_ns)(inner)
    inner['cleanup'] = clone_function(groups.bind_physical_cleanup,
        {**groups.bind_physical_cleanup.__globals__, 'VERSION': VERSION})(inner)
    for name in ('validate_request','validate_candidate_request','validate_qualification',
                 'installation_manifest','cleanup','write_new','_planned'):
        setattr(scorer, name, inner[name])
    # Preserve the same per-task reset used by the already-qualified v143 scorer.
    dataset = load(reference(ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json'))
    reset = groups.reset_binding.bind_scorer(scorer,
        [r for r in dataset if r['instance_id'] in groups.reset_binding.reset.TASKS], passthrough_tasks=())
    concrete = inner['_score']

    def selected_score(request, resource, config, tracking):
        if config['instance_id'] in groups.reset_binding.reset.TASKS:
            return reset._score(request, resource, config, tracking)
        return concrete(request, resource, config, tracking)

    inner['_score'] = scorer._score = selected_score
    return scorer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', action='store_true')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--validate-request', type=Path)
    parser.add_argument('--preflight-plan', action='store_true')
    args = parser.parse_args()
    scorer = build_scorer()
    if args.manifest:
        print(json.dumps(scorer.installation_manifest()))
        return
    if args.preflight_plan:
        allowed()
        plan = load(reference(PLAN))
        for row in load(reference(RUN/'requests.json'))['rows']:
            request = load(row['request'])
            _, resource, config = scorer._planned(request)
            scorer.validate_base(config)
            scorer.environment.validate_request(request, config['instance_id'])
            if load(request['scorer_manifest']) != scorer.installation_manifest():
                raise ValueError('Cold scorer differs from its frozen manifest')
            scorer.validate_candidate_request(request, resource, config, plan)
        print(json.dumps({'passed': True, 'candidates': len(plan['rows']), 'Docker_operations': 0}))
        return
    if not (args.request or args.validate_request):
        parser.error('An exact request is required')
    allowed()
    request = json.loads((args.request or args.validate_request).read_bytes())
    execution = scorer.resolve_execution_request(request)
    limits = host_limits(execution['cpuset_cpus'])
    if args.validate_request:
        scorer.validate_request(execution)
        print(json.dumps({'passed': True, 'Docker_operations': 0}))
        return
    write_new(Path(request['directory'])/'host-limits.json', limits)
    print(json.dumps(scorer.score_request(request)))


if __name__ == '__main__':
    main()
