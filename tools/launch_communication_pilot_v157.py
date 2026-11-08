"""Start one bounded ordinary-user API owner; no system service or GPU changes."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import time

from proworksim import software_benchmark_scope_v157 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v157-role-pilot120-launcher-r1'
SPEC = scope.API_ROOT/'coordinator-unit.json'


def specification():
    return {'version': VERSION, 'unit': scope.API_UNIT, 'uid': os.getuid(),
        'entrypoint': reference(scope.ROOT/'tools/run_communication_pilot_v157.py'),
        'cpu_affinity': scope.host_cpu_pool()[:8], 'cpu_quota_percent': 800,
        'memory_max_bytes': scope.API_MEMORY_BYTES, 'memory_high_bytes': scope.API_MEMORY_HIGH_BYTES,
        'memory_swap_max_bytes': 0, 'tasks_max': 512, 'nofile': 16384,
        'restart': 'no', 'kill_mode': 'mixed', 'stop_seconds': 420,
        'system_parent_slice': None, 'root_operations': 0, 'GPU_operations': 0}


def command(spec):
    expected = specification()
    if (os.getuid() == 0 or set(spec) != set(expected)|{'ownership_token'}
            or any(spec.get(k) != value for k, value in expected.items())
            or not isinstance(spec.get('ownership_token'), str) or len(spec['ownership_token']) != 32):
        raise ValueError('Exact ordinary-user API service specification changed')
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit='+scope.API_UNIT,
        '--description=ProWorkSim v157 three-arm pilot nonthinking owner '+spec['ownership_token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=mixed', '--property=CPUQuota=800%',
        '--property=CPUAffinity='+' '.join(map(str, spec['cpu_affinity'])),
        '--property=MemoryMax=32G', '--property=MemoryHigh=30G', '--property=MemorySwapMax=0',
        '--property=TasksMax=512', '--property=LimitNOFILE=16384', '--property=OOMPolicy=stop',
        '--property=TimeoutStopSec=420', '--property=WorkingDirectory='+str(scope.ROOT),
        '--property=StandardOutput=append:'+str(scope.API_ROOT/'coordinator.stdout.log'),
        '--property=StandardError=append:'+str(scope.API_ROOT/'coordinator.stderr.log'),
        str(scope.ROOT/'.venv/bin/python'), '-B', str(scope.ROOT/'tools/run_offline_scorer_v096.py'),
        spec['entrypoint']['path'], '--execute']


def prepare():
    scope.API_ROOT.mkdir(parents=True, exist_ok=True)
    value = scope.load(reference(SPEC)) if SPEC.exists() else {**specification(), 'ownership_token': secrets.token_hex(16)}
    scope.retain(SPEC, value)
    return {'specification': reference(SPEC), 'command': command(value), 'operations': 0}


def launch():
    scope.require_allowed()
    if any((scope.API_ROOT/name).exists() for name in ('launch-intent.json', 'execution-started.json')):
        raise ValueError('Never automatically replay an entered manager identity')
    spec = scope.load(reference(SPEC))
    argv = command(spec)
    observed = subprocess.run(['systemctl', '--user', 'show', scope.API_UNIT, '--no-pager',
        '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20)
    values = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
    if observed.returncode or values.get('ActiveState') != 'inactive' or values.get('MainPID') != '0':
        raise ValueError('The exact new user service is not inactive')
    lease = scope.reserve_api_coordinator()
    write_new(scope.API_ROOT/'launch-intent.json', {'version': VERSION, 'unix': time.time(),
        'authorization': reference(scope.AUTH_FILE), 'specification': reference(SPEC),
        'reservation': lease, 'observed_inactive': values, 'command': argv})
    result = subprocess.run(argv, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
    receipt = {'version': VERSION, 'returncode': result.returncode, 'stdout': result.stdout,
        'stderr': result.stderr, 'unit': scope.API_UNIT, 'reservation': lease,
        'host_configuration_changes': 0, 'system_slice_operations': 0, 'GPU_operations': 0}
    write_new(scope.API_ROOT/'launch-result.json', receipt)
    if result.returncode:
        raise RuntimeError('Launch failed; preserve identity and inspect before another attempt')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else launch(), ensure_ascii=False))
