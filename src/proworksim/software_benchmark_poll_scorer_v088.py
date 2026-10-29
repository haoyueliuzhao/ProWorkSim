"""Private high-FD host relay for the original authorized official scorer.

Tests, candidate, CA/TLS checks, network destinations, payload ceilings and
container relay source remain unchanged. No frozen module dictionary is edited.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from . import software_benchmark_grading_recovery_v068 as recovery
from . import software_benchmark_io_v088 as io_adapter
from .software_benchmark_candidates_v054 import reference, write_new
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v088-private-authorized-official-grading-host-poll-r1'


def scorer_callable():
    original = recovery.original_scorer
    original_tls = original.environment.tls
    transport = io_adapter.tcp_module()

    class EnvironmentContainer(original_tls.EnvironmentContainer):
        start = private_function(original_tls.EnvironmentContainer.start, transport=transport)

    tls = SimpleNamespace(**{**vars(original_tls), 'EnvironmentContainer': EnvironmentContainer,
                            'run_official': recovery.lifecycle.run_official})
    environment = SimpleNamespace(**{**vars(original.environment), 'tls': tls})
    namespace = clone_namespace(original, environment=environment)

    class Containers(original.Containers):
        create = private_function(original.Containers.create, environment=environment)

    namespace['Containers'] = Containers
    return namespace['score_request']


def score_request(request, *, guard=None):
    # Keep the same guard used by the previously deployed v068 scoring child.
    # The coordinating caller separately acquires the original exact resource.
    guard = guard or recovery._default_guard
    guard('v068.run', instance_id=request['instance_id'])
    folder = Path(request['directory']).resolve()
    if folder != recovery.primary.GRADING_ROOT/request['resource_key']:
        raise ValueError('High-FD scoring must retain its originally owned directory')
    if (folder/'quiescence.json').exists():
        raise ValueError('A consumed score cannot be replayed by the IO adapter')
    write_new(folder/'host-poll-runtime-v088.json', {'version': VERSION,
        'request': reference(folder/'request.json'), 'adapter': reference(__file__),
        'readiness_adapter': reference(io_adapter.__file__),
        'original_scorer': reference(recovery.original_scorer.__file__),
        'original_official_manifest': request['scorer_manifest'],
        'original_tests_candidates_CA_TLS_network_limits_and_container_source_changed': False,
        'frozen_module_globals_modified': False, 'models_executed': 0})
    runner = private_function(recovery.score_request, scorer_with_tls_lifecycle=scorer_callable)
    return runner(request, guard=guard)


class HighFDGrading:
    def __init__(self, delegate):
        self.delegate = delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def run_request(self, request_ref, stop_event=None):
        request = recovery.load(request_ref)
        self.delegate.guard('v068.run', instance_id=request['instance_id'])
        base = self.delegate.base

        def fixed_python(arguments):
            if arguments[:2] != ['-m', 'proworksim.software_benchmark_scorer_v066']:
                raise ValueError('Only the original bounded scoring child may be redirected')
            return base.fixed_python(['-m', 'proworksim.software_benchmark_poll_scorer_v088', *arguments[2:]])

        return private_function(base.run_request, fixed_python=fixed_python)(request_ref, stop_event=stop_event)


def bind_grading(grading):
    if not isinstance(grading, recovery.RecoveryGrading):
        raise TypeError('Require the original resource-guarded RecoveryGrading delegate')
    return HighFDGrading(grading)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    result = score_request(json.loads(parser.parse_args().request.read_bytes()))
    print(json.dumps({key: result[key] for key in ('resource_key', 'status', 'resolved')}))
