"""Score original closed team candidates after a host export measurement repair.

No model replay, new control, candidate choice or extra resource identity is
introduced. Official evaluators, reset handling, CA and bounded TLS remain v131.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
from functools import lru_cache
import inspect
import json
from pathlib import Path
import textwrap
import time

from . import software_benchmark_grading_v131 as prior
from . import software_benchmark_scope_v132 as scope
from . import software_benchmark_candidate_recovery_v132 as recovery
from . import software_benchmark_scoring_registry_v132 as registry
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_function

VERSION = 'v132-original-team-candidate-scoring-recovery-r1'
BLOCKED_TASK = registry.BLOCKED_TASK
MODULE = __name__


def command(arguments):
    return [str(scope.ROOT/'.venv/bin/python'), '-B',
            str(scope.ROOT/'tools/run_offline_scorer_v096.py'), '-m', MODULE, *arguments]


@lru_cache(maxsize=1)
def cold_manifest():
    namespace = {**prior.previous.cold_manifest.__wrapped__.__globals__,
                 'scope': scope, 'command': command}
    return clone_function(prior.previous.cold_manifest.__wrapped__, namespace)()


@lru_cache(maxsize=1)
def original_scorer():
    # Keep the original validator's VERSION, paths and control IDs intact.
    # This object is used only for evidence validation, never execution.
    return prior.scorer(prior.scope.dispatch_view(prior.scope.require_grading_allowed))


def validate_qualification(ref, config, plan_ref):
    task = config['instance_id']
    expected = prior.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json')
    if (task == BLOCKED_TASK or plan_ref != reference(scope.PLAN_FILE)
            or Path(ref['path']).resolve() != expected):
        raise ValueError('Only a genuinely passed original qualification may be reused; 1766 remains isolated')
    return original_scorer().validate_qualification(ref, config, plan_ref)


def _generation_result(request, config, plan):
    row = next(row for row in plan['rows'] if row['slot_id'] == request['slot_id'])
    ref = request['generation_result']
    value = scope.load(ref)
    folder = scope.BATCH_ROOT/'episodes'/str(row['slot_index'])
    if value.get('measurement_recovery_only') is True:
        result = recovery.validate_recovered_result(ref, original_plan_ref=request.get('plan', reference(scope.PLAN_FILE)))
        if (result.get('original_episode_folder') != str(folder)
                or any(result.get(key) != row.get(key) for key in (
                    'slot_id', 'configuration', 'source_slot_id', 'group_id', 'organization_id'))):
            raise ValueError('The validated measurement repair belongs to another original team')
        return row, result, folder
    return original_scorer()._generation_result(request, config, plan)


def _candidate_validator(namespace):
    original = prior.previous.original.validate_candidate_request
    source = inspect.getsource(original)
    needle = 'if not Path(request["candidate_lock"]["path"]).resolve().is_relative_to(folder):'
    if source.count(needle) != 1:
        raise ValueError('The original unique-lock confinement check changed')
    source = source.replace(needle,
        'lock_folder = (Path(request["generation_result"]["path"]).resolve().parent\n'
        '                   if result.get("measurement_recovery_only") is True else folder)\n'
        '    if not Path(request["candidate_lock"]["path"]).resolve().is_relative_to(lock_folder):')
    compiled = {}
    exec(compile(source, __file__+':exact-sidecar-lock', 'exec'), namespace, compiled)
    checked = compiled['validate_candidate_request']

    def validate(request, resource, config, plan):
        locked = checked(request, resource, config, plan)
        if resource['role'] == 'score':
            _, result, folder = _generation_result(request, config, plan)
            # Preserve archive-byte verification and the actual organization
            # closure even when the code endpoint has no legal submission.
            namespace['validate_project_delivery'](result, config, folder)
        return locked
    return validate


def scorer(policy, *, manifest_provider=None):
    value = prior.scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    namespace.update(VERSION=VERSION, _generation_result=_generation_result,
                     validate_qualification=validate_qualification)
    original_planned = value._planned

    def planned(request):
        plan, resource, config = original_planned(request)
        if resource['role'] not in {'score', 'delivery_score'} or config['instance_id'] == BLOCKED_TASK:
            raise ValueError('No new controls or unqualified 1766 grading are permitted')
        return plan, resource, config

    namespace['_planned'] = planned
    namespace['validate_candidate_request'] = _candidate_validator(namespace)
    inherited_manifest = value.installation_manifest

    def installation_manifest():
        if manifest_provider is not None:
            return copy.deepcopy(manifest_provider())
        return {**inherited_manifest(), 'version': VERSION,
            'recovery_scoring_adapter': reference(__file__),
            'recovery_scope': reference(scope.__file__),
            'recovery_claim_registry': reference(registry.__file__),
            'measurement_recovery_validator': reference(recovery.__file__),
            'original_frozen_scoring_manifest': reference(prior.scope.COORDINATOR_ROOT/'scorer-manifest.json'),
            'new_PROJECT_generation_candidates_only': False,
            'original_closed_candidates_measurement_repair': True,
            'old_model_attempts_replayed_in_place': False,
            'independent_recovery_of_consumed_calls_explicitly_authorized': False,
            'fresh_gold_empty_required_for': [], 'new_gold_empty_allowed': False,
            'same_original_resource_keys_and_two_grader_leases': True,
            'reuses_original_qualified_environments': 49,
            'unqualified_environments': [BLOCKED_TASK]}

    # Preserve the v131 conservative HTTP classification and physical cleanup,
    # while giving new receipts the new measurement-version identity.
    writer_factory = clone_function(prior.bind_receipt_writer,
        {**prior.bind_receipt_writer.__globals__, 'scope': scope, 'VERSION': VERSION})
    cleanup_factory = clone_function(prior.bind_physical_cleanup,
        {**prior.bind_physical_cleanup.__globals__, 'scope': scope, 'VERSION': VERSION})
    namespace['write_new'] = write_new
    namespace.update(installation_manifest=installation_manifest,
                     write_new=writer_factory(namespace), cleanup=cleanup_factory(namespace))
    # Reset adapter copies module attributes over globals. Synchronize every
    # actual binding first; otherwise stale candidate validators win silently.
    for key in ('VERSION', '_planned', '_generation_result', 'validate_candidate_request',
                'validate_qualification', 'installation_manifest', 'write_new', 'cleanup'):
        setattr(value, key, namespace[key])
    concrete = value._v118_concrete_score
    namespace['_score'] = concrete
    value._score = concrete
    dataset = json.loads(checked(reference(
        scope.ROOT/'artifacts/software-benchmark-v054/source/trusted-evaluation.json')).read_bytes())
    reset = prior.reset_binding.bind_scorer(value,
        [row for row in dataset if row['instance_id'] in prior.reset_binding.reset.TASKS], passthrough_tasks=())

    def selected_score(request, resource, config, tracking):
        if config['instance_id'] in prior.reset_binding.reset.TASKS:
            return reset._score(request, resource, config, tracking)
        return concrete(request, resource, config, tracking)

    namespace['_score'] = selected_score
    value._score = selected_score
    value._v132_reset_scorer = reset
    return value


def prepare_environment_qualifications_local():
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    current = scorer(registry.policy_view())
    manifest = scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json', current.installation_manifest())
    qualifications = {}
    for task in sorted(plan['environments']):
        if task == BLOCKED_TASK:
            continue
        ref = reference(prior.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
        config = scope.load(plan['environments'][task]['configuration'])
        validate_qualification(ref, config, plan_ref)
        if current.environment.request_fields(task) != original_scorer().environment.request_fields(task):
            raise ValueError('The resumed official test environment changed')
        qualifications[task] = {'status': 'qualified', 'qualification': ref, 'reused_controls': True}
    value = {'version': VERSION, 'qualifications': qualifications, 'controls': [],
        'reuse_failures': {BLOCKED_TASK: {'status': 'not_qualified',
            'original_status': reference(prior.scope.API_ROOT/'qualification-status.json')}},
        'scorer_manifest': manifest, 'original_plan': plan_ref,
        'new_controls': 0, 'model_calls': 0, 'Docker_operations': 0,
        'TLS_controls_should_be_serialized': True, 'automatic_HTTP_retries': False}
    scope.retain(scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json', value)
    return value


def verify_prepared_identity():
    decisions_ref = reference(scope.COORDINATOR_ROOT/'qualification-reuse-decisions.json')
    decisions = scope.load(decisions_ref)
    manifest = reference(scope.COORDINATOR_ROOT/'scorer-manifest.json')
    if scope.load(manifest) != scorer(registry.policy_view()).installation_manifest():
        raise ValueError('The prepared recovery scorer is stale')
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.load(plan_ref)
    if (set(decisions['qualifications']) != set(plan['environments'])-{BLOCKED_TASK}
            or decisions.get('controls') != [] or decisions.get('new_controls') != 0
            or decisions.get('scorer_manifest') != manifest):
        raise ValueError('The continuation may only reuse 49 genuinely qualified environments')
    for task, entry in decisions['qualifications'].items():
        validate_qualification(entry['qualification'], scope.load(plan['environments'][task]['configuration']), plan_ref)
    return {'version': VERSION, 'passed': True, 'preparation': decisions_ref,
            'scorer_manifest': manifest, 'qualified_environments': 49, 'new_controls': 0,
            'model_calls': 0, 'Docker_operations': 0, 'network_connections': 0}


class Grading:
    def __init__(self, policy):
        self.policy = policy
        self.scorer = scorer(policy, manifest_provider=cold_manifest)
        # Only clone the host namespace; its run loop and cleanup remain the
        # original bounded child lifecycle, not an additional service.
        ns = {**prior.previous.host.__globals__, 'scope': scope, 'VERSION': VERSION,
              'cold_manifest': cold_manifest}
        self.base = clone_function(prior.previous.host, ns)(policy, self.scorer)
        self.base.prepare_score = self.prepare_score
        ns = self.base.delivery_disposition.__globals__
        ns.update(prepare_score=self.prepare_score, prepare_manifest=self.prepare_manifest)
        source = inspect.getsource(self.base.delivery_disposition)
        needle = 'scorer.validate_project_delivery(result, config, Path(result_ref["path"]).parent)'
        if source.count(needle) != 1:
            raise ValueError('Original delivery disposition archive binding changed')
        source = source.replace(needle, 'scorer.validate_project_delivery(result, config, '
            'Path(result["original_episode_folder"]) if result.get("measurement_recovery_only") '
            'is True else Path(result_ref["path"]).parent)')
        compiled = {}
        exec(compile(textwrap.dedent(source), __file__+':recovered-delivery-disposition', 'exec'), ns, compiled)
        self.base.delivery_disposition = compiled['delivery_disposition']

    def __getattr__(self, name):
        return getattr(self.base, name)

    def prepare_manifest(self):
        return scope.retain(scope.COORDINATOR_ROOT/'scorer-manifest.json', cold_manifest())

    def prepare_environment_qualifications(self):
        import subprocess
        completed = subprocess.run(command(['--prepare-qualifications']), cwd=scope.ROOT,
            env=prior.previous.clean_environment(), capture_output=True, text=True, timeout=180)
        if completed.returncode:
            raise RuntimeError('Cold original qualification validation failed: '+completed.stderr[-2500:])
        return json.loads(completed.stdout)

    def qualify(self, task):
        plan_ref = reference(scope.PLAN_FILE)
        plan = scope.load(plan_ref)
        ref = reference(prior.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
        validate_qualification(ref, scope.load(plan['environments'][task]['configuration']), plan_ref)
        return ref

    def prepare_score(self, result_ref, *, endpoint='code'):
        if endpoint not in {'code', 'delivery'}:
            raise ValueError('Only original code and legal-delivery endpoints exist')
        result = scope.load(result_ref)
        plan_ref = reference(scope.PLAN_FILE)
        plan = scope.load(plan_ref)
        row = next(row for row in plan['rows'] if row['slot_id'] == result['slot_id'])
        config = scope.load(row['configuration'])
        _, result, folder = _generation_result({'generation_result': result_ref,
            'slot_id': row['slot_id'], 'plan': plan_ref}, config, plan)
        qualification = self.qualify(row['instance_id'])
        if endpoint == 'delivery':
            proof = self.scorer.validate_project_delivery(result, config, folder)
            if proof.get('submitted') is not True:
                raise ValueError('Absent delivery is recorded without a grading container')
        key = ('score-' if endpoint == 'code' else 'delivery-score-')+str(row['slot_index'])
        request = {'version': VERSION, 'resource_key': key, 'instance_id': row['instance_id'],
            'plan': plan_ref, 'configuration': row['configuration'],
            'candidate_lock': result['candidate_lock' if endpoint == 'code' else 'delivery_candidate_lock'],
            'generation_result': result_ref, 'measurement_kind': row['measurement_kind'],
            'source_slot_id': row['source_slot_id'], 'slot_id': row['slot_id'],
            'organization_id': row['organization_id'], 'group_id': row['group_id'],
            'qualification': qualification, 'limits': self.scorer.LIMITS,
            'scorer_manifest': self.prepare_manifest(), 'cpuset_cpus': None,
            'directory': str(scope.GRADING_ROOT/key), 'patch_kind': None,
            'delivery_evidence': result.get('delivery_evidence') if endpoint == 'delivery' else None,
            **self.scorer.environment.request_fields(row['instance_id'])}
        self.scorer._planned(request)
        return scope.retain(scope.GRADING_ROOT/key/'request.json', request)

    def run_request(self, request_ref, stop_event=None):
        request = scope.load(request_ref)
        scope.require_grading_allowed('v132.run', slot_id=request['slot_id'], instance_id=request['instance_id'])
        self.scorer._planned(request)

        def fixed_python(arguments):
            if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
                raise ValueError('Only the one bounded official scorer child may run')
            return command(arguments[2:])

        execute = clone_function(self.base.run_request, {**self.base.run_request.__globals__,
            'fixed_python': fixed_python, 'bootstrap_environment': prior.previous.clean_environment})
        if request['instance_id'] not in prior.FRESH_CONTROL_TASKS:
            return execute(request_ref, stop_event=stop_event)
        # Share the original lock, not a second independent pair of TLS lanes.
        with (prior.scope.COORDINATOR_ROOT/'tls-scoring.lock').open('a+b') as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if stop_event is not None and stop_event.wait(0.25):
                        return {'status': 'not_started_cancelled', 'resource_key': request['resource_key']}
                    if stop_event is None:
                        time.sleep(0.25)
            try:
                return execute(request_ref, stop_event=stop_event)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def factory(*, watchdog_guard=None):
    return Grading(registry.policy_view(watchdog_guard))


def score_request(request, *, validate_only=False):
    scope.require_grading_allowed('v132.run', slot_id=request['slot_id'], instance_id=request['instance_id'])
    current = scorer(registry.policy_view())
    folder = Path(request['directory']).resolve()
    if folder != scope.GRADING_ROOT/request['resource_key'] or (folder/'quiescence.json').exists():
        raise ValueError('A foreign or consumed scoring identity cannot re-enter')
    execution = current.resolve_execution_request(request)
    from .software_benchmark_rescore_v095 import host_limits
    limits = host_limits(execution['cpuset_cpus'])
    if validate_only:
        current.validate_request(execution)
        return {'passed': True, 'actual_original_validate_request_executed': True,
                'host_limits': limits, 'Docker_operations': 0, 'model_calls': 0}
    write_new(folder/'v132-host-limits.json', limits)
    return current.score_request(request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--manifest', action='store_true')
    modes.add_argument('--prepare-qualifications', action='store_true')
    modes.add_argument('--verify-preparation', action='store_true')
    modes.add_argument('--request', type=Path)
    modes.add_argument('--validate-request', type=Path)
    args = parser.parse_args()
    if args.manifest:
        value = scorer(registry.policy_view()).installation_manifest()
    elif args.prepare_qualifications:
        value = prepare_environment_qualifications_local()
    elif args.verify_preparation:
        value = verify_prepared_identity()
    else:
        value = score_request(json.loads((args.request or args.validate_request).read_bytes()),
                              validate_only=args.validate_request is not None)
        if args.request:
            value = {key: value[key] for key in ('resource_key', 'status', 'resolved')}
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
