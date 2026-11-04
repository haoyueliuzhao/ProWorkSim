"""Start the authorized replacement lifecycle after complete old-owner release."""
from __future__ import annotations

import json
import os
import subprocess
import time

from proworksim import software_benchmark_scope_v132 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment


def specification():
    return {'version': scope.VERSION, 'unit': scope.API_UNIT, 'uid': os.getuid(),
        'entrypoint': reference(scope.ROOT/'tools/run_fixed_organization_v132.py'),
        'cpu_affinity': scope.host_cpu_pool()[:8], 'cpu_quota_percent': 800,
        'memory_max_bytes': 32*scope.GIB, 'memory_high_bytes': 30*scope.GIB,
        'memory_swap_max_bytes': 0, 'tasks_max': 512, 'nofile': 16384,
        'restart': 'no', 'system_parent_slice': None, 'root_operations': 0, 'GPU_operations': 0}


def command(spec):
    expected = specification()
    if (os.getuid() == 0 or set(spec) != set(expected)|{'ownership_token'}
            or any(spec.get(key) != value for key, value in expected.items())
            or not isinstance(spec['ownership_token'], str) or len(spec['ownership_token']) != 32):
        raise PermissionError('Replacement lifecycle has a different owner or resource profile')
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit='+scope.API_UNIT,
        '--description=ProWorkSim v132 original-team recovery '+spec['ownership_token'],
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


def launch():
    scope.require_allowed()
    from proworksim.software_benchmark_api_parent_v131 import require_qualified
    require_qualified()
    if any((scope.API_ROOT/name).exists() for name in ('launch-intent.json', 'execution-started.json')):
        raise ValueError('Consumed recovery lifecycle cannot restart')
    spec = scope.load(reference(scope.API_ROOT/'coordinator-unit.json'))
    argv = command(spec)
    result = subprocess.run(['systemctl', '--user', 'show', scope.API_UNIT,
        '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(),
        text=True, capture_output=True, timeout=15, check=True)
    states = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if states.get('ActiveState') != 'inactive' or states.get('MainPID') != '0':
        raise PermissionError('Original service is still active; never overlap owners')
    lease = scope.reserve_api_coordinator()
    write_new(scope.API_ROOT/'launch-intent.json', {'version': scope.VERSION, 'unix': time.time(),
        'authorization': reference(scope.AUTH_FILE), 'unit': reference(scope.API_ROOT/'coordinator-unit.json'),
        'owner': lease, 'observed_inactive': states, 'command': argv})
    started = subprocess.run(argv, env=user_manager_environment(), text=True,
                             capture_output=True, timeout=30)
    receipt = {'version': scope.VERSION, 'returncode': started.returncode,
        'stdout': started.stdout, 'stderr': started.stderr, 'owner': lease, 'unit': scope.API_UNIT,
        'shared_host_changes': False, 'system_slice_operations': 0, 'GPU_operations': 0}
    write_new(scope.API_ROOT/'launch-result.json', receipt)
    started.check_returncode()
    return receipt


if __name__ == '__main__':
    print(json.dumps(launch(), ensure_ascii=False))
