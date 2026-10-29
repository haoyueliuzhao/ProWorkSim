"""Drain only old API work and run its original unused slots with eight starts."""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
import importlib.util
import inspect
import json
import signal
import threading
import time

from proworksim import software_benchmark_api_scope_v079 as scope
from proworksim import software_benchmark_api_handoff_v079 as handoff
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.storage import atomic_write, json_bytes
from proworksim.software_benchmark_qualification_guard_v079 import require_unchanged_terminal

VERSION = 'v079-API-only-eight-startup-continuation-r1'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prior = module('v079_frozen_adaptive_runner', 'run_adaptive_v076.py')


def api_run_binding():
    """Exactly one import substitution, private scope and private API identity."""
    source = inspect.getsource(prior._run)
    tree, changed, isolated, owner_pressure = ast.parse(source), 0, 0, 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'proworksim.software_benchmark_episodes_v076':
            if [(name.name, name.asname) for name in node.names] != [('EpisodeBindings', None)]:
                raise ValueError('Unexpected original episode import')
            node.module = 'proworksim.software_benchmark_episodes_v079'
            changed += 1
        if isinstance(node, ast.ImportFrom) and node.module == 'proworksim.software_benchmark_pressure_v076':
            if [(name.name, name.asname) for name in node.names] != [('PressureWatchdog', None)]:
                raise ValueError('Unexpected original pressure import')
            node.module = 'proworksim.software_benchmark_pressure_v079'
            owner_pressure += 1
        if isinstance(node, ast.FunctionDef) and node.name == 'ceiling':
            expected = ast.parse("if qualified_source.snapshot.get('failure') is not None:\n    return 0").body[0]
            for candidate in ast.walk(node):
                if isinstance(candidate, ast.If) and ast.dump(candidate, include_attributes=False) == ast.dump(expected, include_attributes=False):
                    candidate.body = ast.parse("require_unchanged_terminal(inventory['qualifications'], qualified_source.snapshot)").body
                    isolated += 1
    if changed != 1 or isolated != 1 or owner_pressure != 1:
        raise ValueError('Require the three exact API binding/failure-isolation/owner-pressure changes')
    namespace = {**prior._run.__globals__, 'scope': scope, 'VERSION': VERSION,
        'runtime_api': private_function(prior.runtime_api, scope=scope, VERSION=VERSION),
        'require_unchanged_terminal': require_unchanged_terminal}
    exec(compile(ast.fix_missing_locations(tree), 'v079-private-API-runner', 'exec'), namespace)
    return namespace['_run']


def snapshot(name, value):
    atomic_write(scope.API_ROOT/name, json_bytes({'version': VERSION, 'unix': time.time(), **value}))


def handoff_and_prepare():
    scope.require_allowed('v079.handoff')
    scope.verify_host_limits('api')
    if (scope.BATCH_ROOT/'plan-seal.json').exists():
        return
    if (scope.API_ROOT/'bootstrap-started.json').exists():
        raise ValueError('A bootstrap identity cannot be replayed')
    reservation = scope.reserve_api_coordinator()
    stop = threading.Event()
    previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        write_new(scope.API_ROOT/'bootstrap-started.json', {'version': VERSION, 'unix': time.time(),
            'authorization': reference(scope.AUTH_FILE), 'reservation': reservation,
            'Qwen_lifecycle_operations': 0, 'temporary_additional_management_memory_bytes': scope.API_MEMORY_BYTES})
        stopped = handoff.wait_and_stop(stop=stop)
        prepared = module('v079_post_API_handoff_inventory', 'prepare_api_startup_v079.py').inventory()
        write_new(scope.API_ROOT/'bootstrap-completed.json', {'version': VERSION, 'unix': time.time(),
            'handoff': stopped, 'inventory_preparation': prepared, 'Qwen_lifecycle_operations': 0,
            'old_API_inflight_cancelled': False, 'parent_slice_recreated': False})
    except Exception as error:
        try:
            restored = handoff.rollback()
        except Exception as recovery_error:
            restored = {'performed': False, 'error': str(recovery_error)}
        try:
            released = scope.release_api_coordinator(reservation)
        except Exception as release_error:
            released = {'error': str(release_error)}
        snapshot('bootstrap-failure.json', {'error': {'type': type(error).__name__, 'message': str(error)},
            'pre_signal_rollback': restored, 'coordinator_release': released,
            'Qwen_affected': False, 'parent_slice_retained': True})
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def run():
    handoff_and_prepare()
    with ExitStack() as cleanup:
        return api_run_binding()('api', cleanup)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
