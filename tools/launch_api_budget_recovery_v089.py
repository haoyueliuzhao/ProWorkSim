"""Launch one ordinary-user recovery owner, never any Qwen resident."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import time

from proworksim import software_benchmark_api_scope_v089 as scope
from proworksim import software_benchmark_deepseek_budget_v089 as budget
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v089-owned-budget-recovery-launcher-r1'
SPEC = scope.API_ROOT/'coordinator-unit.json'


def fixed_spec():
    return {'version': VERSION, 'role': 'api', 'unit': scope.API_UNIT, 'user_id': os.getuid(),
        'source': reference(__file__), 'entrypoint': reference(scope.ROOT/'tools/run_api_budget_recovery_v089.py'),
        'reporting_root': str(scope.API_ROOT), 'cpu_affinity': scope.cpu_affinity(),
        'cpu_quota_percent': 800, 'memory_max_bytes': scope.API_MEMORY_BYTES,
        'memory_high_bytes': scope.API_MEMORY_HIGH_BYTES, 'memory_swap_max_bytes': 0,
        'tasks_max': 512, 'nofile_soft_limit': scope.NOFILE, 'restart': 'no', 'kill_mode': 'mixed',
        'Qwen_lifecycle_operations': 0, 'root_operations': 0}


def command(spec):
    fixed = fixed_spec()
    if (os.getuid() == 0 or set(spec) != set(fixed)|{'ownership_token'}
            or any(spec.get(k) != v for k, v in fixed.items())
            or not isinstance(spec.get('ownership_token'), str) or len(spec['ownership_token']) != 32):
        raise ValueError('The exact ordinary-user recovery specification changed')
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit='+scope.API_UNIT,
        '--description=ProWorkSim v089 api coordinator '+spec['ownership_token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=mixed', '--property=CPUQuota=800%',
        '--property=CPUAffinity='+' '.join(map(str, spec['cpu_affinity'])),
        '--property=LimitNOFILE=16384', '--property=MemoryMax=64G', '--property=MemoryHigh=32G',
        '--property=MemorySwapMax=0', '--property=TasksMax=512', '--property=OOMPolicy=stop',
        '--property=TimeoutStopSec=420', '--property=WorkingDirectory='+str(scope.ROOT),
        '--property=StandardOutput=append:'+str(scope.API_ROOT/'coordinator.stdout.log'),
        '--property=StandardError=append:'+str(scope.API_ROOT/'coordinator.stderr.log'),
        str(scope.ROOT/'.venv/bin/python'), '-B', str(scope.ROOT/'tools/run_offline_scorer_v058.py'),
        spec['entrypoint']['path'], '--execute']


def prepare():
    scope.API_ROOT.mkdir(parents=True, exist_ok=True)
    if SPEC.exists():
        spec = json.loads(SPEC.read_bytes())
    else:
        spec = {**fixed_spec(), 'ownership_token': secrets.token_hex(16)}
        write_new(SPEC, spec)
    return {'specification': reference(SPEC), 'command': command(spec), 'runtime_operations': 0}


def launch():
    scope.require_allowed()
    amendment = budget.require_amendment()
    scope.parent_module().require_qualified()
    if any((scope.API_ROOT/n).exists() for n in ('launch-intent.json', 'execution-started.json')):
        raise ValueError('No recovery-manager identity replay')
    spec = json.loads(SPEC.read_bytes())
    argv = command(spec)
    r = subprocess.run(['systemctl', '--user', 'show', scope.API_UNIT, '--no-pager',
        '--property=ActiveState,SubState,MainPID'], env=user_manager_environment(), capture_output=True,
        text=True, timeout=20)
    properties = dict(x.split('=', 1) for x in r.stdout.splitlines() if '=' in x)
    if r.returncode or properties.get('ActiveState') != 'inactive' or properties.get('MainPID') != '0':
        raise ValueError('The exact new owner is not inactive')
    reservation = scope.reserve_api_coordinator()
    write_new(scope.API_ROOT/'launch-intent.json', {'unix': time.time(), 'authorization': reference(scope.AUTH_FILE),
        'specification': reference(SPEC), 'reservation': reservation, 'amendment': amendment,
        'observed_inactive': properties, 'command': argv})
    r = subprocess.run(argv, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
    value = {'version': VERSION, 'unit': scope.API_UNIT, 'returncode': r.returncode,
        'stdout': r.stdout, 'stderr': r.stderr, 'reservation': reservation,
        'Qwen_lifecycle_operations': 0, 'parent_slice_changed': False}
    write_new(scope.API_ROOT/'launch-result.json', value)
    if r.returncode:
        raise RuntimeError('Recovery launch failed; inspect preserved receipt without automatic replay')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else launch(), ensure_ascii=False))
