"""Candidate-preserving official rescoring in an isolated scorer interpreter."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
from types import ModuleType, SimpleNamespace

from . import software_benchmark_dispatch_v066 as original_policy
from . import software_benchmark_scorer_v066 as original_scorer
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v095-isolated-official-candidate-rescoring-r1'
ROOT = original_policy.ROOT
SOURCE = Path(__file__).resolve()
RUN_ROOT = ROOT/'runs/software-benchmark-v095/core-rescore-r1'
PLAN_FILE = RUN_ROOT/'plan.json'
AUTH_FILE = ROOT/'config/v095-core-rescore-authorization.json'
SOURCE_FILE = RUN_ROOT/'runtime-sources.json'
HOST_MEMORY_BYTES = 4*1024**3


def load(ref):
    return json.loads(checked(ref).read_bytes())


def installation_manifest():
    # Called by a fresh dedicated child, never by the API/counter owner.
    value = original_scorer.installation_manifest()
    return {**value, 'guard': reference(SOURCE), 'rescoring_adapter': reference(SOURCE),
        'scorer_interpreter_profile': 'fixed_offline_launcher_without_API_tokenizer_overlay',
        'candidate_bytes_changed': False, 'official_tests_and_scoring_rules_changed': False}


class Context:
    def __init__(self, plan_ref, *, fixture=None):
        self.plan_ref = plan_ref
        self.plan = load(plan_ref)
        self.root = Path(self.plan['administrative_root']).resolve()
        if self.plan.get('version') != VERSION:
            raise PermissionError('Unknown rescoring plan')
        self.fixture = Path(fixture).resolve() if fixture is not None else None
        if self.fixture is None and not self.root.is_relative_to((ROOT/'runs/software-benchmark-v095').resolve()):
            raise PermissionError('Rescoring stays inside the separately declared v095 run root')
        self.auth_file = Path(self.plan['authorization_path'])
        self.source_file = Path(self.plan['source_index_path'])
        self.grading_root = self.root/'grading'
        self.claim_root = original_policy.BATCH_ROOT
        if self.fixture is not None:
            self.claim_root = self.fixture/'shared-capacity'
        self.jobs = {job['resource_key']: job for job in self.plan['jobs']}
        if (len(self.jobs) != len(self.plan['jobs']) or set(self.jobs) != set(self.plan['resources'])
                or any(item['role'] not in {'score', 'delivery_score'} for item in self.plan['resources'].values())):
            raise PermissionError('Only the exact fixed candidate scoring identities are allowed')

    def allowed(self, operation='v066.run', *, slot_id=None, instance_id=None):
        if os.getuid() == 0 or os.geteuid() == 0:
            raise PermissionError('The scoring host must remain an ordinary user')
        if operation not in {'v066.run', 'v066.score', 'v066.delivery.score', 'v066.grader.create',
                             'v066.grader.start', 'v095.score'}:
            raise PermissionError('No generation, network relay or control creation is in this scoring scope')
        authority = load(reference(self.auth_file))
        if (authority.get('version') != VERSION or authority.get('status') != 'approved'
                or authority.get('plan') != self.plan_ref
                or authority.get('source_index') != reference(self.source_file)
                or authority.get('maximum_score_containers') != len(self.jobs)
                or authority.get('maximum_concurrent_graders') != 4
                or authority.get('new_model_calls') != 0 or authority.get('host_configuration_changes') != 0):
            raise PermissionError('Exact independent rescoring authorization is absent or changed')
        for item in load(authority['source_index'])['files']:
            checked(item)
        if (slot_id is not None and slot_id not in {j['slot_id'] for j in self.jobs.values()}
                or instance_id is not None and instance_id not in self.plan['environments']):
            raise PermissionError('Candidate is outside the frozen rescoring list')
        return {**authority, 'constraints': self.plan['constraints']}


def policy(context):
    namespace = clone_namespace(original_policy, VERSION=VERSION,
        PLAN_FILE=Path(context.plan_ref['path']), AUTHORIZATION_FILE=context.auth_file,
        BATCH_ROOT=context.claim_root, GRADING_ROOT=context.grading_root,
        CONSTRAINTS=context.plan['constraints'], __file__=str(SOURCE))
    namespace['require_v066_allowed'] = context.allowed
    value = ModuleType('proworksim.v095_private_scoring_policy')
    value.__dict__.update(namespace)
    return value


def build_scorer(context, bound_policy=None):
    bound_policy = bound_policy or policy(context)
    namespace = clone_namespace(original_scorer, policy=bound_policy)

    def job_for(request):
        job = context.jobs.get(request.get('resource_key'))
        if job is None or request.get('slot_id') != job['slot_id']:
            raise PermissionError('The scoring request has no exact preserved-candidate mapping')
        for key in ('configuration', 'generation_result', 'candidate_lock', 'qualification'):
            if request.get(key) != job[key]:
                raise PermissionError('A scoring endpoint cannot replace its locked '+key)
        return job

    def validate_qualification(ref, config, plan_ref):
        if plan_ref != context.plan_ref:
            raise ValueError('Qualification belongs to another rescoring plan')
        matches = [j for j in context.jobs.values() if j['slot_id'] == config['slot_id']]
        if not matches or any(j['configuration'] != reference(Path(matches[0]['configuration']['path']))
                              or j['qualification'] != ref for j in matches):
            raise ValueError('Qualification is not the preserved original control')
        job = matches[0]
        if config != load(job['configuration']):
            raise ValueError('Original executable configuration changed')
        if job['source_family'] == 'recovery_v094':
            from .software_benchmark_recovery_runtime_v094 import grading
            return grading.validate_qualification(ref, config, job['origin_plan'])
        return original_scorer.validate_qualification(ref, config, job['origin_plan'])

    def generation_result(request, config, plan):
        job = job_for(request)
        row = next(r for r in plan['rows'] if r['slot_id'] == request['slot_id'])
        folder = original_policy.BATCH_ROOT/'episodes'/str(row['slot_index'])
        result = load(request['generation_result'])
        if job.get('administrative_recovery_audit') is None:
            if Path(request['generation_result']['path']).resolve() != folder/'result.json':
                raise ValueError('Only the original generation result may supply this candidate')
        else:
            audit = load(job['administrative_recovery_audit'])
            if (audit.get('administrative_artifact_recovery_eligible') is not True
                    or audit.get('unique_original_candidate_preserved') is not True
                    or audit.get('model_rerun') is not False or audit.get('model_calls_added') != 0
                    or audit.get('candidate_content_changed') is not False
                    or audit.get('actor_interrupted_tree_used') is not False
                    or audit.get('candidate_lock') != request['candidate_lock']
                    or result.get('administrative_closure_audit') != job['administrative_recovery_audit']
                    or result.get('original_result') != audit.get('original_result')
                    or Path(audit['original_result']['path']).resolve() != folder/'result.json'):
                raise ValueError('Administrative recovery is not the exact original terminal code artifact')
            checked(audit['original_result'])
            checked(audit['archive_verification'])
        if (result.get('status') != 'closed' or result.get('slot_id') != row['slot_id']
                or result.get('configuration') != row['configuration']
                or result.get('source_slot_id') != row['source_slot_id']
                or result.get('measurement_kind') != 'full_verified_comparison'
                or config.get('measurement_kind') != 'full_verified_comparison'):
            raise ValueError('Candidate lacks its exact completed or administratively closed identity')
        quiet = load(result['quiescence'])
        if quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False:
            raise ValueError('Generation cleanup is not proven')
        return row, result, folder

    def validate_project_delivery(result, config, folder):
        job = next(j for j in context.jobs.values() if j['slot_id'] == config['slot_id'])
        source_policy = SimpleNamespace(**{**vars(bound_policy), 'PLAN_FILE': Path(job['origin_plan']['path'])})
        return private_function(original_scorer.validate_project_delivery, policy=source_policy)(result, config, folder)

    def validate_candidate_request(request, resource_spec, config, plan):
        job = job_for(request)
        _, result, folder = generation_result(request, config, plan)
        delivery = resource_spec['role'] == 'delivery_score'
        endpoint, field = ('last_legal_delivery', 'delivery_candidate_lock') if delivery else ('terminal_code', 'candidate_lock')
        if request['candidate_lock'] != result.get(field) or result.get(field) is None:
            raise ValueError('The request does not identify the unique locked endpoint')
        lock = original_scorer._locked_candidate(request['candidate_lock'], config, endpoint=endpoint)
        if not Path(request['candidate_lock']['path']).resolve().is_relative_to(folder):
            if delivery or job.get('administrative_recovery_audit') is None:
                raise ValueError('Only the exact audited relocated code lock may be outside the original output')
            if load(job['administrative_recovery_audit'])['candidate_lock'] != request['candidate_lock']:
                raise ValueError('A different relocated lock cannot be substituted')
        if delivery:
            if config['arm'] != 'PROJECT' or request.get('delivery_evidence') != result.get('delivery_evidence'):
                raise ValueError('No matching managed delivery evidence')
            if not validate_project_delivery(result, config, folder)['submitted']:
                raise ValueError('No legal delivery exists')
        elif config.get('arm') not in {'REF', 'PROJECT'}:
            raise ValueError('Unknown generation interface')
        validate_qualification(request['qualification'], config, request['plan'])
        if config['scorer_request_base']['image']['image_id'] != resource_spec['image_id']:
            raise ValueError('Scoring image changed')
        return lock

    namespace.update(installation_manifest=installation_manifest, _generation_result=generation_result,
        validate_qualification=validate_qualification, validate_project_delivery=validate_project_delivery,
        validate_candidate_request=validate_candidate_request)

    class ObservedContainer(original_scorer.ObservedContainer):
        start = private_function(original_scorer.ObservedContainer.start, **namespace)

    class Containers(original_scorer.Containers):
        create = private_function(original_scorer.Containers.create,
            **{**namespace, 'ObservedContainer': ObservedContainer})

    namespace.update(ObservedContainer=ObservedContainer, Containers=Containers)
    value = ModuleType('proworksim.v095_private_official_scorer')
    value.__dict__.update(namespace)
    return value


def host_limits(cpuset):
    cpus = {int(number) for number in cpuset.split(',')}
    if len(cpus) != 4:
        raise PermissionError('A grader host process requires its exact four-CPU lane')
    os.sched_setaffinity(0, cpus)
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    upper = HOST_MEMORY_BYTES if hard == resource.RLIM_INFINITY else min(hard, HOST_MEMORY_BYTES)
    resource.setrlimit(resource.RLIMIT_AS, (upper, upper))
    return {'cpu_affinity': sorted(os.sched_getaffinity(0)), 'address_space_bytes': upper}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--manifest', action='store_true')
    mode.add_argument('--request', type=Path)
    mode.add_argument('--validate-request', type=Path)
    parser.add_argument('--cpu-fixture', type=Path)
    args = parser.parse_args()
    if args.manifest:
        print(json.dumps(installation_manifest(), ensure_ascii=False))
        return
    if args.request and args.cpu_fixture:
        raise PermissionError('A CPU fixture can never start real scoring')
    request = json.loads((args.request or args.validate_request).read_bytes())
    context = Context(request['plan'], fixture=args.cpu_fixture)
    scored = build_scorer(context)
    execution = scored.resolve_execution_request(request)
    limits = host_limits(execution['cpuset_cpus'])
    if args.validate_request:
        scored.validate_request(execution)
        print(json.dumps({'passed': True, 'actual_original_validate_request_executed': True,
            'resource_key': request['resource_key'], 'host_limits': limits,
            'manifest_equal': load(request['scorer_manifest']) == installation_manifest(),
            'Docker_operations': 0, 'model_calls': 0}, ensure_ascii=False))
        return
    write_new(Path(request['directory'])/'v095-host-limits.json', limits)
    value = scored.score_request(request)
    print(json.dumps({key: value[key] for key in ('resource_key', 'status', 'resolved')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
