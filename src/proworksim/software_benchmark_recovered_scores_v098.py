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

VERSION = 'v098-isolated-official-candidate-rescoring-r1'
ROOT = original_policy.ROOT
SOURCE = Path(__file__).resolve()
RUN_ROOT = ROOT/'runs/software-benchmark-v098/recovered-candidates-r1'
PLAN_FILE = RUN_ROOT/'plan.json'
AUTH_FILE = ROOT/'config/v098-core-rescore-authorization.json'
SOURCE_FILE = RUN_ROOT/'runtime-sources.json'
HOST_MEMORY_BYTES = 4*1024**3
READY_FILE = ROOT/'artifacts/software-benchmark-v095/candidate-recovery-batch-r1/combined-ready-results.json'
OWNER_INDICES = {3171, 3459, 3514}


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
        if self.fixture is None and not self.root.is_relative_to((ROOT/'runs/software-benchmark-v098').resolve()):
            raise PermissionError('Rescoring stays inside the separately declared v098 run root')
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
        ready = load(self.plan['candidate_recovery_index'])
        expected = {r['slot_index']: r['recovered_result'] for r in ready['rows'] if r['slot_index'] != 6068}
        if (self.plan['candidate_recovery_index'] != reference(READY_FILE) or len(expected) != 25
                or {r['slot_index'] for r in self.plan['rows']} != set(expected)
                or any(j['generation_result'] != expected[next(r['slot_index'] for r in self.plan['rows']
                    if r['slot_id'] == j['slot_id'])] for j in self.jobs.values())):
            raise PermissionError('Only the 25 separately sealed original candidates are admitted')

    def allowed(self, operation='v066.run', *, slot_id=None, instance_id=None):
        if os.getuid() == 0 or os.geteuid() == 0:
            raise PermissionError('The scoring host must remain an ordinary user')
        if operation not in {'v066.run', 'v066.score', 'v066.delivery.score', 'v066.grader.create',
                             'v066.grader.start', 'v098.score'}:
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
    from .software_benchmark_resources_v076 import CapacityProbe
    probe = CapacityProbe()

    def budget(active, cpu, memory, spool=0):
        # Preserve global grader lanes and hard container limits. API ceilings
        # are not measurements of current RAM/CPU use.
        if cpu != 4 or memory != 16*original_policy.GIB or spool != 0:
            raise PermissionError('Only a four-CPU/16GiB grader can reserve this capacity')
        physical = probe.snapshot()
        graders = sum(x.get('spec', {}).get('role') in {'score', 'delivery_score', 'control'} for x in active)
        margin = (graders+1)*20*original_policy.GIB
        reserved_spool = sum(x.get('reserved_spool_bytes', 0) for x in active)
        if (physical['cpu_sample_fresh'] is not True or physical['host_cpu_utilization_percent'] >= 85
                or physical['memory_available_bytes'] < 128*original_policy.GIB+margin
                or physical['disk_free_bytes'] < 128*original_policy.GIB+reserved_spool):
            raise original_policy.ResourceBusy('Actual host capacity does not admit another bounded grader')
        return {'actual_capacity_admission': True, 'physical_at_admission': physical,
            'pending_grader_memory_margin_bytes': margin, 'reserved_payload_spool_bytes_after': reserved_spool,
            'API_quota_sum_is_not_actual_usage': True}

    namespace['_budget'] = budget
    value = ModuleType('proworksim.v098_private_scoring_policy')
    value.__dict__.update(namespace)
    return value


def owner_audit(job, result, row):
    """Bind three missing owner records to the original completed child, never an intermediate tree."""
    audit = load(job['administrative_recovery_audit'])
    folder = original_policy.BATCH_ROOT/'episodes'/str(row['slot_index'])
    if (row['slot_index'] not in OWNER_INDICES
            or audit.get('version') != 'v095-original-closed-child-owner-result-recovery-r1'
            or audit.get('original_result_absent') is not True or (folder/'result.json').exists()
            or result.get('original_result') is not None
            or result.get('administrative_closure_audit') != job['administrative_recovery_audit']
            or result.get('original_administrative_owner_recovery') != audit.get('original_owner_recovery')
            or result.get('candidate_lock') != audit.get('candidate_lock')
            or result.get('delivery_candidate_lock') != audit.get('delivery_candidate_lock')
            or result.get('controller_result') != audit.get('original_controller')
            or result.get('writer_quiescence') != audit.get('writer_quiescence')
            or result.get('quiescence') != audit.get('cleanup')
            or audit.get('new_model_calls') != 0 or audit.get('new_container_operations') != 0):
        raise ValueError('Missing owner result has no exact original closed-child recovery audit')
    owner = load(audit['original_owner_recovery'])
    child = load(audit['original_controller'])
    archive = load(audit['archive_verification'])
    cash = audit['actual_cash_reconciliation']
    if (owner.get('slot_id') != row['slot_id'] or owner.get('slot_index') != row['slot_index']
            or owner.get('quiescent') is not True or owner.get('cleanup_errors') != []
            or owner.get('evidence') != audit['original_retained_evidence']
            or load(result['quiescence']) != {**owner['cleanup'], 'original_owner_evidence': audit['original_owner_recovery']}
            or child.get('status') != 'closed' or child.get('slot_id') != row['slot_id']
            or result.get('controller_exit_code') != 0 or archive.get('full_archive_verified') is not True
            or cash.get('read_only') is not True or cash.get('uncertain_requests') != 0
            or cash.get('ledger_rows_changed') is not False):
        raise ValueError('Original child closure, cash reconciliation or cleanup is incomplete')
    checked(audit['original_retained_evidence'])
    writers = load(result['writer_quiescence'])
    controllers = [x for x in writers.get('writers', []) if x.get('role') == 'controller']
    if (writers.get('all_quiet') is not True or writers.get('errors') != [] or len(controllers) != 1
            or controllers[0]['state'].get('Running') is not False or controllers[0]['state'].get('Pid') != 0
            or controllers[0]['state'].get('ExitCode') != 0):
        raise ValueError('Original controller did not exit cleanly')
    claim = load(controllers[0]['claim'])
    if claim.get('spec', {}).get('slot_id') != row['slot_id'] or claim.get('spec', {}).get('role') != 'controller':
        raise ValueError('The stopped controller belongs to another attempt')
    names = {'controller_result': 'controller-result.json'}
    if row['arm'] == 'PROJECT':
        names.update(delivery_evidence='delivery-evidence.json', delivery_snapshot='project-delivery-snapshot.json')
    elif child.get('native_finished') is not True or child.get('normal_completion') is not True:
        raise ValueError('The original native candidate did not finish normally')
    for field, member in names.items():
        ref = result[field]
        checked(ref)
        if archive['endpoint_members'].get(member) != {k: ref[k] for k in ('sha256', 'bytes')}:
            raise ValueError('Recovered evidence does not match the already verified original archive member')
    return audit


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
            if audit.get('version') == 'v095-original-closed-child-owner-result-recovery-r1':
                owner_audit(job, result, row)
            elif (audit.get('administrative_artifact_recovery_eligible') is not True
                    or audit.get('unique_original_candidate_preserved') is not True
                    or audit.get('model_rerun') is not False or audit.get('model_calls_added') != 0
                    or audit.get('candidate_content_changed') is not False
                    or audit.get('actor_interrupted_tree_used') is not False
                    or audit.get('candidate_lock') != result['candidate_lock']
                    or result.get('administrative_closure_audit') != job['administrative_recovery_audit']
                    or result.get('original_result') != audit.get('original_result')
                    or Path(audit['original_result']['path']).resolve() != folder/'result.json'):
                raise ValueError('Administrative recovery is not the exact original terminal code artifact')
            if audit.get('original_result'):
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
        if job.get('administrative_recovery_audit'):
            audit = load(job['administrative_recovery_audit'])
            if audit.get('version') != 'v095-original-closed-child-owner-result-recovery-r1':
                if audit.get('submitted') is not False or result.get('delivery_candidate_lock') is not None:
                    raise ValueError('The recovered sync failure cannot invent legal delivery')
                return {'submitted': False, 'same_tree': None, 'legal_delivery_evidence': False}
            row = next(r for r in context.plan['rows'] if r['slot_id'] == config['slot_id'])
            owner_audit(job, result, row)
            evidence, snapshot, baseline = (load(result[name]) for name in (
                'delivery_evidence', 'delivery_snapshot', 'project_baseline_snapshot'))
            if any(x.get('slot_id') != config['slot_id'] or x.get('instance_id') != config['instance_id']
                   for x in (evidence, snapshot)):
                raise ValueError('Recovered delivery belongs to another task')
            proof = original_scorer.validate_delivery_evidence(evidence, snapshot, baseline)
            code = original_scorer._locked_candidate(result['candidate_lock'], config, endpoint='terminal_code')
            code_bundle = load(code['candidate'])
            code_native = original_scorer.native_tree_manifest(code_bundle['files'], code_bundle['entry_metadata'])
            code_managed = original_scorer.managed_tree_manifest(code_bundle['files'], code_bundle['entry_metadata'])
            if (result['project_baseline_snapshot'] != code.get('baseline')
                    or evidence.get('terminal_tree_sha256') != code_managed['tree_sha256']
                    or code['tree_sha256'] != code_native['tree_sha256'] or proof['submitted'] is not True):
                raise ValueError('Recovered delivery is not bound to its exact terminal code and baseline')
            delivery = original_scorer._locked_candidate(result['delivery_candidate_lock'], config, endpoint='last_legal_delivery')
            native = original_scorer.native_tree_manifest(snapshot['candidate']['files'], snapshot['candidate']['entry_metadata'])
            managed = original_scorer.managed_tree_manifest(snapshot['candidate']['files'], snapshot['candidate']['entry_metadata'])
            same_files = (snapshot['candidate']['files'] == code_bundle['files']
                and snapshot['candidate']['entry_metadata'] == code_bundle['entry_metadata'])
            if (delivery['tree_sha256'] != native['tree_sha256']
                    or proof.get('managed_tree_sha256') != managed['tree_sha256']
                    or delivery['patch_receipt']['base_tree_sha256'] != code['patch_receipt']['base_tree_sha256']
                    or proof['same_tree'] is not same_files):
                raise ValueError('Recovered legal delivery differs from its exact independently exported version')
            return {**proof, 'native_delivery_tree_sha256': delivery['tree_sha256'],
                'original_closed_owner_audit': job['administrative_recovery_audit']}
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
            if job.get('administrative_recovery_audit') is None:
                raise ValueError('Only the exact audited relocated code lock may be outside the original output')
            if load(job['administrative_recovery_audit']).get(field) != request['candidate_lock']:
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
    value = ModuleType('proworksim.v098_private_official_scorer')
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
    write_new(Path(request['directory'])/'v098-host-limits.json', limits)
    value = scored.score_request(request)
    print(json.dumps({key: value[key] for key in ('resource_key', 'status', 'resolved')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
