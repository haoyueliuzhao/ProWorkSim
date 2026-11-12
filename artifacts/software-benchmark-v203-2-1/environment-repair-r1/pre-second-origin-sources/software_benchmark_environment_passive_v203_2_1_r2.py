"""Scoring-only repairs for Requests2317/Pylint4661; never modify task bytes.

Requests uses the existing complete httpbin application and real TCP/TLS sockets
inside its private network=none grader. Pylint receives one verified local appdirs
wheel through an offline pip wheelhouse. No host install, external relay, actor
capability or model-visible answer/hint is introduced. Real gold/empty admission
remains required; fixture source preparation alone does not qualify either task.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import io
import json
from pathlib import Path
import tarfile
import textwrap
from types import ModuleType

from . import software_benchmark_requests_offline_v066 as original_offline
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function
from .software_benchmark_grading_repairs_v141 import inspect_wheel

VERSION = 'v203.2.1-r2-private-scoring-environment-repair-r1'
REQUESTS_TASK = 'psf__requests-2317'
PYLINT_TASK = 'pylint-dev__pylint-4661'
REPAIR_TASKS = frozenset({REQUESTS_TASK, PYLINT_TASK})
ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / 'artifacts/software-benchmark-v203-2-1/environment-repair-r1'
WHEEL = ARTIFACT / 'wheelhouse/appdirs-1.4.4-py2.py3-none-any.whl'
WHEEL_SHA256 = '651552e0bcd9302aba4f2fd5945e56fc764f060a4c8feec0a0d93108a1fd5a7d'
WHEELHOUSE = '/opt/proworksim-passive-score-wheels'
PIP_ENVIRONMENT = {'PIP_NO_INDEX': '1', 'PIP_FIND_LINKS': 'file://' + WHEELHOUSE,
                   'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PIP_NO_INPUT': '1',
                   'PIP_CONFIG_FILE': '/dev/null'}
REQUESTS_PROFILE = {'httpbin': '0.7.0', 'pytest_httpbin': '0.0.7',
                    'standalone_httpbin': True, 'admission_enabled': True, 'blockers': []}


def wheel_manifest():
    ref = reference(WHEEL)
    if ref['sha256'] != WHEEL_SHA256:
        raise ValueError('The locally sourced appdirs wheel changed')
    metadata = inspect_wheel(ref, target_python='3.9.20')
    if metadata['name'] != 'appdirs' or metadata['version'] != '1.4.4' or metadata['requires_dist']:
        raise ValueError('Unexpected appdirs distribution or additional dependencies')
    return {'version': VERSION, 'instance_id': PYLINT_TASK, 'target_python': '3.9.20',
            'adapter': reference(__file__), 'wheel': ref,
            'wheel_source': reference(ARTIFACT / 'appdirs-wheel-provenance.json'),
            'wheel_metadata': metadata, 'destination': WHEELHOUSE + '/' + WHEEL.name,
            'pip_environment': PIP_ENVIRONMENT, 'official_pip_command_changed': False,
            'candidate_or_gold_bytes_changed': False, 'host_installation': False,
            'external_network': False, 'runtime_qualified': False}


def offline_pip_environment(values):
    result = dict(row.split('=', 1) for row in values) if isinstance(values, list) else dict(values or {})
    for key in ('PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL', 'PIP_TRUSTED_HOST', 'PIP_NO_BUILD_ISOLATION'):
        result.pop(key, None)
    for key, value in PIP_ENVIRONMENT.items():
        if key in result and result[key] != value:
            raise ValueError('Conflicting scorer-only offline pip configuration')
    return {**result, **PIP_ENVIRONMENT}


def wheel_archive():
    manifest = wheel_manifest()
    raw = checked(manifest['wheel']).read_bytes()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        entry = tarfile.TarInfo(WHEEL.name)
        entry.size, entry.mode, entry.uid, entry.gid, entry.mtime = len(raw), 0o444, 0, 0, 0
        archive.addfile(entry, io.BytesIO(raw))
    return output.getvalue()


def private_environment(policy, scope, parent_factory):
    """Build private namespaces around the frozen complete offline fixture."""
    router = parent_factory(policy)
    namespace = clone_namespace(original_offline, require_v066_allowed=policy.require_v066_allowed,
                                PROFILES={REQUESTS_TASK: copy.deepcopy(REQUESTS_PROFILE)})
    original_manifest = namespace['environment_manifest']

    def requests_manifest():
        return {**original_manifest(), 'version': VERSION, 'adapter': reference(__file__),
                'original_fixture_adapter': reference(original_offline.__file__),
                'dispatch_guard': reference(scope.__file__),
                'authorization_bound_by': 'new r2 scope and exact Requests2317 scorer identity',
                'external_network': False, 'fresh_gold_empty_controls_required': True,
                'candidate_CA_compatibility_verified': False}

    namespace['environment_manifest'] = requests_manifest
    methods = {name: clone_function(function, namespace)
               for name, function in vars(original_offline.EnvironmentContainer).items()
               if inspect.isfunction(function)}
    namespace['EnvironmentContainer'] = type('PassiveRequestsFixtureContainer',
                                             (original_offline.EnvironmentContainer,), methods)
    offline = ModuleType(__name__ + '.private_requests')
    offline.__dict__.update(namespace)
    offline.__file__ = __file__
    route_namespace = router.request_fields.__globals__
    route_namespace.update(offline=offline, TASKS=frozenset({REQUESTS_TASK}),
                           OFFLINE_TASKS=frozenset({REQUESTS_TASK}), TLS_TASKS=frozenset())

    def prepare():
        path = scope.GRADING_ROOT / 'environments'
        return scope.retain(path / 'bindings.json', {
            'offline': scope.retain(path / 'requests2317-offline.json', requests_manifest()),
            'pylint_wheel': scope.retain(path / 'pylint4661-appdirs.json', wheel_manifest()),
            'tls': None, 'network_resolutions': {}})

    def request_fields(task):
        binding = json.loads(checked(reference(scope.GRADING_ROOT / 'environments/bindings.json')).read_bytes())
        ref = binding['offline'] if task == REQUESTS_TASK else binding['pylint_wheel'] if task == PYLINT_TASK else None
        return {'environment_revision': ref, 'network_resolution': None}

    def validate_request(request, task):
        expected = request_fields(task)
        if any(request.get(key) != value for key, value in expected.items()):
            raise ValueError('Scorer-only task environment identity changed')
        if task == REQUESTS_TASK:
            offline.validate_environment(expected['environment_revision'])
        elif task == PYLINT_TASK:
            if json.loads(checked(expected['environment_revision']).read_bytes()) != wheel_manifest():
                raise ValueError('Pylint offline wheel provenance changed')
        return offline if task == REQUESTS_TASK else None

    def capabilities(task):
        return ['NET_ADMIN', 'NET_BIND_SERVICE'] if task == REQUESTS_TASK else []

    route_namespace.update(prepare=prepare, request_fields=request_fields,
                           validate_request=validate_request, capabilities=capabilities)
    router.__dict__.update(route_namespace)
    router.__file__ = __file__
    return router


def bind_scorer_environment(scorer):
    """Bind actual create/start paths; no Docker call is made while binding."""
    namespace = scorer.validate_request.__globals__
    prior = namespace['ObservedContainer']

    class PylintWheelContainer(prior):
        def start(self, *args, **kwargs):
            result = super().start(*args, **kwargs)
            if self.preparation['mapping']['instance_id'] != PYLINT_TASK:
                return result
            actual_environment = dict(value.split('=', 1) for value in self.delegate.attrs['Config'].get('Env', []))
            if any(actual_environment.get(key) != value for key, value in PIP_ENVIRONMENT.items()):
                raise ValueError('The actual Pylint grader lacks its offline wheelhouse environment')
            python = self.preparation['mapping']['public_python']
            execute = namespace['archive'].checked_exec
            execute(self.delegate, ['mkdir', '-p', WHEELHOUSE], timeout_note='Private Pylint wheelhouse')
            if self.delegate.put_archive(WHEELHOUSE, wheel_archive()) is not True:
                raise ValueError('The exact Pylint grader did not accept its dependency wheel')
            target = WHEELHOUSE + '/' + WHEEL.name
            probe = ('import hashlib,json,sys; p=' + repr(target) + '; '
                     "print(json.dumps({'python':'.'.join(map(str,sys.version_info[:3])),"
                     "'wheel_sha256':hashlib.sha256(open(p,'rb').read()).hexdigest()}))")
            proof = json.loads(execute(self.delegate, [python, '-B', '-c', probe],
                                       timeout_note='Uploaded Pylint wheel identity'))
            if proof != {'python': '3.9.20', 'wheel_sha256': WHEEL_SHA256}:
                raise ValueError('Pylint wheel bytes or original testbed Python changed')
            write_new(Path(self.preparation['path']).with_name('pylint4661-offline-wheel.json'), {
                'version': VERSION, 'container_id': self.delegate.id,
                'manifest': wheel_manifest(), 'actual_environment': PIP_ENVIRONMENT,
                'actual_interpreter_and_wheel': proof, 'official_command_unchanged': True,
                'task_files_changed': False, 'host_installation': False, 'network_calls': 0})
            return result

    source = textwrap.dedent(inspect.getsource(namespace['Containers'].create))
    needle = 'task = self.observation["mapping"]["instance_id"]\n    options["cap_add"] = environment.capabilities(task)'
    replacement = needle + '''
    if task == REQUESTS_TASK:
        options["extra_hosts"] = {"httpbin.org": "127.0.0.1"}
    elif task == PYLINT_TASK:
        options["environment"] = offline_pip_environment(options.get("environment"))'''
    if source.count(needle) != 1:
        raise ValueError('Exact task-specific scorer creation boundary changed')
    source = source.replace(needle, replacement)
    local = {}
    namespace.update(REQUESTS_TASK=REQUESTS_TASK, PYLINT_TASK=PYLINT_TASK,
                     offline_pip_environment=offline_pip_environment,
                     ObservedContainer=PylintWheelContainer)
    exec(compile(source, __file__ + ':private-scorer-create', 'exec'), namespace, local)
    containers = type('PassiveRepairContainers', (namespace['Containers'],), {'create': local['create']})
    namespace.update(Containers=containers)
    scorer.Containers, scorer.ObservedContainer = containers, PylintWheelContainer
    scorer.passive_environment_create_sha256 = hashlib.sha256(source.encode()).hexdigest()
    return scorer
