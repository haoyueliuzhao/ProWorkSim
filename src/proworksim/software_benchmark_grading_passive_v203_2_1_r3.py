"""Independent two-control official scorer for Requests2317 private CA r3."""
from functools import lru_cache
import inspect
import json
from pathlib import Path
import textwrap
from types import FunctionType

from . import software_benchmark_grading_v105 as base
from . import software_benchmark_scope_passive_requests_v203_2_1_r3 as scope
from . import software_benchmark_environment_passive_v203_2_1_r3 as repair
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_benchmark_grading_v131 import _lane_validator

VERSION = 'v203.2.1-requests2317-independent-official-scoring-r3'
MODULE = 'proworksim.software_benchmark_grading_passive_v203_2_1_r3'
_ns = clone_namespace(base, scope=scope, VERSION=VERSION, MODULE=MODULE, __file__=__file__)
_parent_scorer, _parent_host, _parent_environment = _ns['scorer'], _ns['host'], _ns['private_environment']


def control_key(kind):
    if kind not in ('gold', 'empty'):
        raise ValueError('Only the two declared control kinds are allowed')
    return 'control-ca-r3-' + repair.TASK + '-' + kind


def private_environment(policy):
    return repair.private_environment(policy, scope, _parent_environment)


def scorer(policy, *, manifest_provider=None):
    value = _parent_scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    namespace['MAX_GRADERS'] = 2
    namespace['validate_request'] = _lane_validator(namespace)
    from .software_namespace_witness_v183 import bind_scorer
    bind_scorer(value)
    repair.bind_scorer_environment(value)
    # Keep the native own-batch capacity validator. r3 uses disjoint CPU lanes
    # and a separate conservative combined-capacity gate; no r2 lease is touched.
    source = inspect.getsource(base.original.validate_qualification)
    needle = '"control-" + task + "-" + kind'
    if source.count(needle) != 1:
        raise ValueError('Exact original qualification key changed')
    source = source.replace(needle, '"control-ca-r3-" + task + "-" + kind')
    local = {}
    exec(compile(source, __file__ + ':fresh-control-identity', 'exec'), namespace, local)
    native = local['validate_qualification']

    def validate_qualification(ref, config, plan_ref):
        if config['instance_id'] != repair.TASK:
            raise ValueError('Independent r3 can qualify only Requests2317')
        result = native(ref, config, plan_ref)
        originals = []
        for item in result['controls']:
            proof_path = Path(item['initial_container']['path']).parent / 'requests2317-private-ca-r3/preflight.json'
            proof = json.loads(checked(reference(proof_path)).read_bytes())
            quiet = scope.load(item['quiescence'])
            probe = proof.get('actual_TLS_probe', {})
            final = quiet.get('requests2317_final_CA', {})
            if (proof.get('version') != repair.VERSION or proof.get('manifest') != repair.manifest()
                    or proof.get('original_files_changed') is not False
                    or probe.get('verify_mode') != 2 or probe.get('check_hostname') is not True
                    or probe.get('verification_settings_unchanged') is not True
                    or final.get('valid') is not True or final.get('files_sha256') != probe.get('files_sha256')):
                raise ValueError('Requests control lacks verification-preserving CA evidence')
            originals.append(proof['baseline_CA']['original_sha256'])
        if len(originals) != 2 or len(set(originals)) != 1:
            raise ValueError('Gold/empty must use identical original trust roots')
        return result

    prior_manifest = namespace['installation_manifest']
    def installation_manifest():
        result = prior_manifest()
        if manifest_provider is not None:
            return result
        return {**result, 'independent_r3_scorer': reference(__file__),
                'private_CA_revision': repair.manifest(), 'public_network': 'none',
                'maximum_real_tls_sessions': 0, 'maximum_control_containers': 2,
                'independent_capacity_lease_root': str(scope.BATCH_ROOT / 'resource-claims'),
                'active_r2_lease_or_state_modified': False,
                'original_official_tests_and_scoring_rules_changed': False,
                'no_model_calls_or_generation_authority': True}
    namespace.update(validate_qualification=validate_qualification, installation_manifest=installation_manifest)
    for name in ('validate_request', 'validate_capacity_claim', 'validate_qualification', 'installation_manifest'):
        setattr(value, name, namespace[name])
    return value


def host(policy, scoring):
    value = _parent_host(policy, scoring)
    def qualify(task):
        if task != repair.TASK:
            raise ValueError('No other original task may enter r3')
        plan_ref = reference(scope.PLAN_FILE)
        plan = scope.load(plan_ref)
        controls = []
        for kind in ('gold', 'empty'):
            directory = scope.GRADING_ROOT / control_key(kind)
            controls.append({'patch_kind': kind,
                **{name: reference(directory / (name + '.json')) for name in ('receipt', 'quiescence', 'completion')},
                'initial_container': reference(directory / 'official-output/initial-container.json')})
        result = {'version': VERSION, 'instance_id': task, 'plan': plan_ref, 'controls': controls,
                  'passed': True, 'model_calls': 0}
        target = scope.COORDINATOR_ROOT / 'qualifications' / (task + '.json')
        proposal = scope.retain(target.with_name(task + '-proposal.json'), result)
        scoring.validate_qualification(proposal, scope.load(plan['environments'][task]['configuration']), plan_ref)
        return scope.retain(target, result)
    value.qualify = qualify
    return value


def prepare_environment_qualifications_local():
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    scoring = scorer(scope.dispatch_view())
    scoring.environment.prepare()
    manifest = scope.retain(scope.COORDINATOR_ROOT / 'scorer-manifest.json', scoring.installation_manifest())
    controls = []
    for kind in ('gold', 'empty'):
        key = control_key(kind)
        resource = plan['resources'][key]
        if resource['instance_id'] != repair.TASK or resource['role'] != 'control' or resource['patch_kind'] != kind:
            raise ValueError('The independent two-control identity changed')
        request = {'version': VERSION, 'resource_key': key, 'instance_id': repair.TASK, 'slot_id': None,
                   'plan': plan_ref, 'configuration': plan['environments'][repair.TASK]['configuration'],
                   'patch_kind': kind, 'limits': scoring.LIMITS, 'scorer_manifest': manifest,
                   'cpuset_cpus': None, 'directory': str(scope.GRADING_ROOT / key), 'candidate_lock': None,
                   **scoring.environment.request_fields(repair.TASK)}
        controls.append(scope.retain(scope.GRADING_ROOT / key / 'request.json', request))
    result = {'controls': controls, 'qualifications': {}, 'new_controls': 2, 'model_calls': 0,
              'independent_scope_no_r2_hot_patch': True, 'no_old_control_or_model_replay': True}
    scope.retain(scope.COORDINATOR_ROOT / 'control-plan.json', result)
    return result


_ns.update(private_environment=private_environment, scorer=scorer, host=host,
           prepare_environment_qualifications_local=prepare_environment_qualifications_local)
for _name in ('score_request', 'main'):
    _source = inspect.getsource(getattr(base, _name)).replace("'v105.run'", "'v066.run'")
    exec(compile(_source, __file__ + ':' + _name, 'exec'), _ns)
_ns['cold_manifest'] = lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__, _ns))
_methods = {key: clone_function(value, _ns) for key, value in vars(base.Grading).items() if isinstance(value, FunctionType)}
_source = textwrap.dedent(inspect.getsource(base.Grading.run_request)).replace("'v105.run'", "'v066.run'")
_local = {}
exec(compile(_source, __file__ + ':control-child', 'exec'), _ns, _local)
_methods['run_request'] = _local['run_request']
_ns['Grading'] = type('Grading', (base.Grading,), _methods)
globals().update({key: value for key, value in _ns.items() if not key.startswith('__')})

if __name__ == '__main__':
    _ns['main']()
