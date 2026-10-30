"""Six-object, serial, original-candidate rescoring; approval is external."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace

from . import software_benchmark_dispatch_v066 as original_policy
from . import software_benchmark_scorer_v066 as original
from . import software_benchmark_grading_repairs_v099 as mechanisms
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_benchmark_rescore_v095 import host_limits

VERSION = 'v099-six-object-serial-official-rescore-r1'
ROOT = original_policy.ROOT
RUN_ROOT = ROOT / 'runs/software-benchmark-v099/two-task-rescore-r1'
PLAN_FILE = RUN_ROOT / 'plan.json'
AUTH_FILE = ROOT / 'config/v099-two-task-rescore-authorization.json'
SOURCE_FILE = RUN_ROOT / 'runtime-sources.json'
PROPOSAL_FILE = ROOT / 'artifacts/software-benchmark-v099/rescore-authorization-r1/proposal.json'
SLOTS = {1675: 'sphinx-doc__sphinx-11510', 5530: 'astropy__astropy-7336'}
CONSTRAINTS = {'maximum_containers': 6, 'maximum_active_containers': 1,
    'maximum_controls': 4, 'maximum_candidates': 2, 'maximum_named_volumes': 0,
    'maximum_model_residents': 0, 'maximum_actor_containers': 0,
    'maximum_controller_containers': 0, 'new_model_calls': 0,
    'container_cpu_count': 4, 'container_memory_bytes': 16 * 1024**3,
    'host_cpu_count': 4, 'host_address_space_bytes': 4 * 1024**3,
    'network_mode': 'none', 'cap_add': [], 'cap_drop': ['ALL'],
    'host_bind_mounts': 0, 'host_configuration_changes': 0,
    'new_services_or_slices': 0, 'network_connections': 0, 'maximum_real_tls_sessions': 0}


def load(ref):
    return json.loads(checked(ref).read_bytes())


class Context:
    def __init__(self, plan_ref, *, fixture=None):
        self.plan_ref, self.plan = plan_ref, load(plan_ref)
        self.fixture = Path(fixture).resolve() if fixture else None
        self.root = Path(self.plan['administrative_root']).resolve()
        if self.fixture:
            if not self.fixture.is_relative_to(Path('/tmp')) or not self.root.is_relative_to(self.fixture):
                raise PermissionError('CPU-only scope must live entirely under its /tmp fixture')
        elif self.root != RUN_ROOT.resolve():
            raise PermissionError('Only the frozen standalone v099 root may run')
        self.auth_file = self.fixture / 'CPU-AUTH.json' if self.fixture else AUTH_FILE
        self.source_file = self.fixture / 'sources.json' if self.fixture else SOURCE_FILE
        self.proposal_file = self.fixture / 'proposal.json' if self.fixture else PROPOSAL_FILE
        self.grading_root = self.root / 'grading'
        self.validate_plan()

    def validate_plan(self):
        value = self.plan
        if value.get('version') != VERSION or value.get('constraints') != CONSTRAINTS:
            raise PermissionError('Changed six-object plan or resource constraints')
        source = load(value['original_plan'])
        expected_rows, resources = [], {}
        for slot, task in SLOTS.items():
            row = next(r for r in source['rows'] if r['slot_index'] == slot)
            job = value['candidates'].get(str(slot))
            old_ref = reference(original_policy.GRADING_ROOT / f'score-{slot}/request.json')
            old = load(old_ref)
            if (row['instance_id'] != task or job is None or job['origin_request'] != old_ref
                    or any(job[key] != old[key] for key in ('configuration', 'generation_result', 'candidate_lock'))
                    or value['environments'][task] != source['environments'][task]):
                raise PermissionError('Only the two unchanged original candidates/configurations are admitted')
            original._locked_candidate(job['candidate_lock'], load(row['configuration']), endpoint='terminal_code')
            expected_rows.append(row)
            image = load(row['configuration'])['scorer_request_base']['image']['image_id']
            for kind in ('gold', 'empty'):
                resources[f'control-{task}-{kind}'] = {'role': 'control', 'instance_id': task,
                    'patch_kind': kind, 'image_id': image}
            resources[f'score-{slot}'] = {'role': 'score', 'instance_id': task, 'slot_id': row['slot_id'],
                                         'image_id': image, 'endpoint': 'code'}
        if (value.get('rows') != expected_rows or value.get('resources') != resources
                or set(value['environments']) != set(SLOTS.values()) or len(value['candidates']) != 2):
            raise PermissionError('Added, removed, or substituted v099 scoring identity')
        cpu_set = value.get('cpu_set', '').split(',')
        if len(cpu_set) != 4 or len(set(cpu_set)) != 4 or any(not x.isdecimal() for x in cpu_set):
            raise ValueError('An exact four-CPU lane must be frozen')
        if value['cpu_set'] != original_policy.cpu_set('grader', 0):
            raise ValueError('v099 must retain the original fixed grader lane')

    def allowed(self, operation='v066.run', *, slot_id=None, instance_id=None):
        if os.getuid() == 0 or os.geteuid() == 0:
            raise PermissionError('Scoring host must be an ordinary user')
        permitted = {'v066.run', 'v066.control', 'v066.score', 'v066.grader.create', 'v066.grader.start'}
        if self.fixture:
            permitted -= {'v066.grader.create', 'v066.grader.start'}
        if operation not in permitted:
            raise PermissionError('No models, transport, foreign containers, or undeclared operations')
        auth = load(reference(self.auth_file))
        if (auth.get('version') != VERSION or auth.get('status') != ('cpu-only' if self.fixture else 'approved')
                or auth.get('plan') != self.plan_ref or auth.get('constraints') != CONSTRAINTS
                or auth.get('source_index') != reference(self.source_file)
                or auth.get('proposal') != reference(self.proposal_file)
                or (not self.fixture and not auth.get('explicit_authorization'))):
            raise PermissionError('The exact six-object approval is absent or changed')
        proposal = load(auth['proposal'])
        if proposal.get('plan') != self.plan_ref or proposal.get('constraints') != CONSTRAINTS:
            raise PermissionError('The reviewed proposal differs')
        for ref in load(auth['source_index'])['files']:
            checked(ref)
        if (instance_id is not None and instance_id not in SLOTS.values()
                or slot_id is not None and slot_id not in {r['slot_id'] for r in self.plan['rows']}):
            raise PermissionError('Identity outside the exact two candidates/tasks')
        return auth


def policy(context):
    namespace = clone_namespace(original_policy, VERSION=VERSION, PLAN_FILE=Path(context.plan_ref['path']),
        AUTHORIZATION_FILE=context.auth_file, BATCH_ROOT=context.root, GRADING_ROOT=context.grading_root,
        COORDINATOR_RUN_ROOT=context.root, CONSTRAINTS=CONSTRAINTS, __file__=__file__)
    namespace['require_v066_allowed'] = context.allowed

    def cpu_set(role, index=0):
        if role != 'grader' or type(index) is not int or index not in range(4):
            raise ValueError('Only the single four-CPU grading lane exists')
        return context.plan['cpu_set']

    def claim_resource(key, *, lane=None):
        context.allowed('v066.run')
        if key not in context.plan['resources'] or lane not in (None, 0):
            raise ValueError('Unplanned grading object or lane')
        directory = context.root / 'resource-claims'
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'allocation.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            claim, lease = directory / (key + '.json'), directory / 'active-grader-0.json'
            if claim.exists():
                raise ValueError('Consumed grading identity cannot be replayed')
            if lease.exists():
                raise original_policy.ResourceBusy('The serial v099 grader is still owned')
            value = {'version': VERSION, 'key': key, 'spec': context.plan['resources'][key],
                'authorization': reference(context.auth_file), 'plan': context.plan_ref,
                'lane': 0, 'lease': str(lease), 'docker_name': 'pws-v099-' + hashlib.sha256(
                    (str(context.root) + ':' + key).encode()).hexdigest()[:24]}
            body = json.dumps(value, sort_keys=True).encode() + b'\n'
            for target in (claim, lease):
                with target.open('xb') as stream:
                    stream.write(body)
                    stream.flush()
                    os.fsync(stream.fileno())
            return reference(claim)

    namespace.update(cpu_set=cpu_set, claim_resource=claim_resource)
    value = ModuleType('proworksim.private_rescore_policy_v099')
    value.__dict__.update(namespace)
    return value


def build_scorer(context):
    bound_policy = policy(context)
    namespace = clone_namespace(original, policy=bound_policy)
    # Preserve the original result/lock/writer checks against the original episode
    # root. Only new scoring claims and controls belong to the standalone root.
    origin_policy = SimpleNamespace(**{**vars(bound_policy), 'BATCH_ROOT': original_policy.BATCH_ROOT})
    namespace['_generation_result'] = private_function(original._generation_result, policy=origin_policy)
    old_planned = namespace['_planned']

    def planned(request):
        result = old_planned(request)
        if result[1]['role'] == 'score':
            slot = next(r['slot_index'] for r in context.plan['rows'] if r['slot_id'] == request['slot_id'])
            job = context.plan['candidates'][str(slot)]
            if any(request[key] != job[key] for key in ('configuration', 'generation_result', 'candidate_lock')):
                raise ValueError('The exact original candidate identity changed')
        return result

    namespace['_planned'] = planned
    value = ModuleType('proworksim.original_scorer_with_v099_scope')
    value.__dict__.update(namespace)
    dataset = original.base.read_local_dataset(load(context.plan['rows'][0]['configuration'])['scorer_request_base']['dataset'])
    revised = mechanisms.bind_scorer(value, [dataset[task] for task in SLOTS.values()], context.plan['offline_dependency'])
    inherited = revised.installation_manifest

    def installation_manifest():
        return {**inherited(), 'independent_scope_adapter': reference(__file__),
                'standalone_scoring_constraints': CONSTRAINTS}

    revised.score_request.__globals__['installation_manifest'] = installation_manifest
    revised.installation_manifest = installation_manifest
    return revised


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--manifest', action='store_true')
    mode.add_argument('--request', type=Path)
    mode.add_argument('--validate-request', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--cpu-fixture', type=Path)
    args = parser.parse_args()
    if args.request and args.cpu_fixture:
        raise PermissionError('CPU fixtures cannot execute scoring')
    request = json.loads((args.request or args.validate_request).read_bytes()) if not args.manifest else None
    context = Context(reference(args.plan) if args.manifest else request['plan'], fixture=args.cpu_fixture)
    scorer = build_scorer(context)
    if args.manifest:
        print(json.dumps(scorer.installation_manifest(), ensure_ascii=False))
        return
    context.allowed('v066.run')
    execution = scorer.resolve_execution_request(request)
    limits = host_limits(execution['cpuset_cpus'])
    if args.validate_request:
        scorer.validate_request(execution)
        print(json.dumps({'passed': True, 'actual_original_validate_request_executed': True,
            'resource_key': request['resource_key'], 'host_limits': limits,
            'manifest_equal': load(request['scorer_manifest']) == scorer.installation_manifest(),
            'Docker_operations': 0, 'model_calls': 0}))
        return
    write_new(Path(request['directory']) / 'host-limits-v099.json', limits)
    value = scorer.score_request(request)
    print(json.dumps({key: value[key] for key in ('resource_key', 'status', 'resolved')}))


if __name__ == '__main__':
    main()
