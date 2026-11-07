"""Formal scoring after pure recovery of normally closed v146 candidate exports.

Uses the qualified official evaluator and original images; no generation,
host mounts, daemon changes, new volumes, or writes to original results.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

from . import software_benchmark_dispatch_v066 as dispatch
from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v131 as groups
from . import software_benchmark_grading_v143 as previous
from . import software_benchmark_grading_v146 as active
from . import software_benchmark_rescore_v147 as qualified
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_benchmark_rescore_v095 import host_limits

ROOT = dispatch.ROOT
VERSION = 'v154-provider-construction-and-offline-build-scoring-r1'
RUN = ROOT/'runs/software-benchmark-v154/three-score-recovery-r1'
PLAN = RUN/'plan.json'
AUTH = RUN/'authorization.json'
SOURCE = RUN/'runtime-sources.json'
GRADING = RUN/'grading'
CONSTRAINTS = {**previous.scope.CONSTRAINTS,
    'maximum_containers': 9, 'maximum_named_volumes': 0,
    'maximum_active_containers': 2, 'active_grader_limit': 2,
    'maximum_combined_reserved_cpu': 8,
    'maximum_combined_reserved_memory_bytes': 40*1024**3,
    'maximum_real_tls_sessions': 6,
    'real_tls_all_sessions_connections': 3072,
    'real_tls_all_sessions_payload_bytes': 384*1024**2,
    'fresh_generation_slots': 0, 'new_model_calls_for_preparation': 0,
    'new_services_or_slices': 0, 'physical_gpus': []}


def load(ref):
    return json.loads(checked(ref).read_bytes())


def allowed(operation='v066.run', *, slot_id=None, instance_id=None):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Ordinary-user bounded experiment Docker only')
    if operation not in {'v066.run', 'v066.score', 'v066.delivery.score', 'v066.control', 'v066.grader.create',
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
        if role != 'grader' or type(index) is not int or index not in range(2):
            raise ValueError('Only two four-CPU scoring lanes exist')
        return previous.scope.cpu_set('grader', index)

    def budget(active, cpu, memory, spool=0):
        if len(active) >= 2 or cpu != 4 or memory != 16*1024**3 or spool:
            raise dispatch.ResourceBusy('The two bounded graders are occupied')
        physical = ns['physical_capacity']()
        if (not physical['passed'] or physical['memory_available_bytes'] < 84*1024**3):
            raise dispatch.ResourceBusy('Actual shared-host headroom prevents grading')
        return {'reserved_cpu_after': 4*(len(active)+1),
                'reserved_memory_bytes_after': 20*1024**3*(len(active)+1),
                'physical_at_admission': physical}

    ns.update(require_v066_allowed=allowed, cpu_set=cpu_set, _budget=budget)
    inherited = ns['claim_resource']

    def claim(key, *, lane=None):
        if lane not in (0,1):
            raise ValueError('A concrete scoring lane is mandatory')
        if load(reference(PLAN))['resources'][key]['role']!='control':
            admission = load(reference(RUN/'admissions'/(key+'.json')))
            validate_admission(admission)
        return inherited(key, lane=lane)

    ns['claim_resource'] = claim
    return base.module_from(ns, __name__+'.policy')


def scope_view():
    return SimpleNamespace(ROOT=ROOT, BATCH_ROOT=RUN, PLAN_FILE=PLAN,
        COORDINATOR_ROOT=RUN/'coordinator', GRADING_ROOT=GRADING,
        NETWORK_RESOLUTION_FILE=previous.scope.NETWORK_RESOLUTION_FILE,
        CA_PROFILE_FILE=previous.scope.CA_PROFILE_FILE,
        previous=previous.scope.previous, original=previous.scope.original, __file__=__file__, load=load,
        MAX_GRADERS=2, CONSTRAINTS=CONSTRAINTS,
        validate_original_probe_reuse=previous.scope.validate_original_probe_reuse)



def private_environment(policy):
    # This exact scope has only Requests1766 and a non-Requests task. Return
    # the actual qualified180 provider, including .tls.EnvironmentContainer;
    # changing provider()/request_fields alone does not bind Containers.create.
    view=scope_view()
    return clone_function(qualified.private_environment,
        {**qualified.private_environment.__globals__,'scope_view':lambda:view,'__file__':__file__})(policy)


def offline_build_adapter():
    from . import software_benchmark_grading_repairs_v141 as repair
    destination='/pws-v154-build-wheels'
    namespace=clone_namespace(repair,PYTEST_TASK='pytest-dev__pytest-6197',
        VERSION='v154-pytest6197-offline-build-dependencies-r1',WHEELHOUSE=destination,
        PIP_ENVIRONMENT={**repair.PIP_ENVIRONMENT,'PIP_FIND_LINKS':'file://'+destination},__file__=__file__)
    return base.module_from(namespace,__name__+'.offline_build')


def validate_transport_evidence(receipt,quiet,observed,identity,folder,**kwargs):
    validator=clone_function(qualified.validate_transport_evidence,
        {**qualified.validate_transport_evidence.__globals__,'scope_view':scope_view})
    return validator(receipt,quiet,observed,identity,folder,**kwargs)


def build_scorer(*, manifest_provider=None):
    scope, bound = scope_view(), policy()
    ns = clone_namespace(base, scope=scope, VERSION=VERSION, MODULE=__name__, __file__=__file__)
    ns['private_environment'] = clone_function(private_environment,
        {**globals(), 'scope': scope})
    scorer = ns['scorer'](bound, manifest_provider=manifest_provider)
    inner = scorer.validate_request.__globals__
    groups.bind_group_identity(inner)
    inner['MAX_GRADERS'] = 2
    inner['validate_request'] = groups._lane_validator(inner)
    original_manifest = scorer.installation_manifest

    def manifest():
        if manifest_provider:
            return manifest_provider()
        return {**original_manifest(), 'supplemental_stopped_candidate_adapter': reference(__file__),
            'endpoint': 'recovered_normal_closed_export', 'original_scores_unchanged': True,
            'previous_qualified_scorer': reference(previous.__file__),
            'new_controls_required': True, 'previous_idle180_control_plan':reference(qualified.PLAN),
            'actual_TLS_constructor_bound_to_selected_manifest':True,
            'pytest6197_offline_build_plan':reference(RUN/'offline-build-plan.json'),
            'normal_export_recovery_validator':reference(ROOT/'src/proworksim/software_benchmark_closed_export_recovery_v149.py'),
            'normal_closed_controller_required':True, 'other_environments':reference(active.scope.PLAN_FILE), 'scoring_transport_idle_seconds': 180,
            'idle_timeout_increase_is_mitigation_not_HTTP_completion_proof': True,
            'selective_reset_binding': reference(groups.reset_binding.__file__),
            'selective_reset_tasks': sorted(groups.reset_binding.reset.TASKS),
            'maximum_real_tls_sessions': 6, 'new_model_calls': 0}

    source=inspect.getsource(base.original.validate_qualification)
    source=source.replace('"control-" + task + "-" + kind','"control-v154-" + task + "-" + kind')
    source=source.replace('from .software_benchmark_grading_qualification_v060 import validate_transport_evidence',
        'from .software_benchmark_rescore_v154 import validate_transport_evidence')
    compiled={}
    exec(compile(source,__file__+':fresh-controls','exec'),inner,compiled)
    concrete_qualification=compiled['validate_qualification']
    def qualification(ref,config,plan_ref):
        if plan_ref!=reference(PLAN) or config['instance_id'] not in {'psf__requests-1766','pytest-dev__pytest-6197'}:
            raise ValueError('Only this exact two-task fresh control scope is admitted')
        return concrete_qualification(ref,config,plan_ref)

    def candidate(request, resource, config, plan):
        from . import software_benchmark_closed_export_recovery_v149 as exports
        row=validate_admission(load(request['recovery_admission']))
        result=exports.validate_export_result_bounded(request['generation_result'],row)
        endpoint=resource['endpoint']
        field='candidate_lock' if endpoint=='code' else 'delivery_lock'
        if (request['slot_id']!=row['slot_id'] or request['candidate_lock']!=result.get(field)
                or result.get(field) is None
                or (endpoint=='delivery' and (result.get('submitted') is not True
                    or request.get('delivery_evidence')!=result.get('delivery_evidence')))):
            raise ValueError('Only the original normally ended code/legal-delivery version may be scored')
        lock=load(request['candidate_lock'])
        if (lock.get('version')!='software-benchmark-candidates-v054'
                or lock.get('task_id')!=row['instance_id']
                or lock.get('endpoint')!=('terminal_code' if endpoint=='code' else 'last_legal_submission')
                or lock.get('lock_before_grading') is not True
                or lock.get('candidate_selection_after_scoring') is not False):
            raise ValueError('Managed normal-close endpoint lock identity changed')
        patch=load(lock['patch_receipt'])
        if patch.get('round_trip_verified') is not True or patch.get('candidate_tree_sha256')!=lock['tree_sha256']:
            raise ValueError('Normal-close patch roundtrip identity changed')
        checked(patch['patch'])
        qualification(request['qualification'],config,request['plan'])
        if config['scorer_request_base']['image']['image_id']!=resource['image_id']:
            raise ValueError('Another image cannot score this task')
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
    offline_build_adapter().bind_offline_build_scorer(scorer,reference(RUN/'offline-build-plan.json'))
    # Preserve the same per-task reset used by the already-qualified v143 scorer.
    # The pure closure exporter uses the original managed v054 lock, whose
    # patch receipt is an immutable reference. Only dereference that receipt;
    # the patch bytes and every official evaluation operation remain identical.
    score_source=inspect.getsource(base.original._score)
    needle='patch = checked(lock["patch_receipt"]["patch"]).read_bytes()'
    if score_source.count(needle)!=1:
        raise ValueError('The concrete official patch loading site changed')
    revised=score_source.replace(needle,'patch = checked(load(lock["patch_receipt"])["patch"]).read_bytes()')
    compiled={}
    exec(compile(revised,__file__+':managed-lock-patch-reference','exec'),inner,compiled)
    inner['_score']=scorer._score=compiled['_score']
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


def validate_admission(value):
    from . import software_benchmark_closed_export_recovery_v149 as exports
    plan=load(reference(PLAN))
    row=next(r for r in plan['rows'] if r['slot_id']==value['slot_id'])
    result=exports.validate_export_result_bounded(value['export_result'],row)
    if result.get('completed_work_proven_before_export') is not True:
        raise PermissionError('Only an already normally closed model episode may be scored')
    endpoint=value['endpoint']
    if endpoint not in {'code','delivery'} or value.get('scoring_attempt') not in (1,2):
        raise PermissionError('Only the frozen formal code/delivery endpoints may enter')
    field='candidate_lock' if endpoint=='code' else 'delivery_lock'
    if (result.get(field) is None or value['candidate_lock']!=result[field]
            or (endpoint=='delivery' and result.get('submitted') is not True)):
        raise PermissionError('No exact original normal-close candidate or legal delivery')
    if value['scoring_attempt']==2:
        previous_request=load(value['prior_request'])
        prior_folder=Path(previous_request['directory'])
        expected_key=('score-' if endpoint=='code' else 'delivery-score-')+str(row['slot_index'])
        if (prior_folder!=GRADING/expected_key or previous_request['resource_key']!=expected_key
                or previous_request['candidate_lock']!=value['candidate_lock']
                or previous_request['generation_result']!=value['export_result']):
            raise PermissionError('Technical retry changed its original candidate identity')
        quiet=load(reference(prior_folder/'quiescence.json'))
        if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors')!=[]
                or quiet.get('create_result_unknown') is not False):
            raise PermissionError('Original owned scoring cleanup is incomplete')
        if (prior_folder/'receipt.json').exists():
            receipt=load(reference(prior_folder/'receipt.json'))
            if receipt.get('status')=='official_report' and type(receipt.get('resolved')) is bool:
                raise PermissionError('Normal scored failure/success must not be rescored')
        completion=load(value['prior_completion'])
        if completion.get('state')!='technical_unknown' or completion.get('cleanup_proven') is not True:
            raise PermissionError('A trustworthy technical scoring failure is required')
    return row


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
