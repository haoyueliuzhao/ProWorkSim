"""Launch only the new ordinary-user API service, retaining Qwen and its GPUs."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import time

from proworksim import software_benchmark_api_scope_v088 as scope
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim import software_benchmark_rolling_handoff_v086 as handoff
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment
from proworksim.software_benchmark_qualification_guard_v079 import require_unchanged_terminal

VERSION = 'v088-owned-rolling-API-launcher-r1'
SPEC = scope.API_ROOT/'coordinator-unit.json'


def fixed_spec():
    return {'version': VERSION, 'role': 'api', 'unit': scope.API_UNIT, 'user_id': os.getuid(),
        'source': reference(__file__), 'entrypoint': reference(scope.ROOT/'tools/run_api_recovery_v088.py'),
        'reporting_root': str(scope.API_ROOT), 'cpu_affinity': scope.cpu_affinity(),
        'cpu_quota_percent': 800, 'memory_max_bytes': scope.API_MEMORY_BYTES,
        'memory_high_bytes': scope.API_MEMORY_HIGH_BYTES, 'memory_swap_max_bytes': 0,
        'tasks_max': 512, 'nofile_soft_limit': scope.NOFILE, 'restart': 'no', 'timeout_stop_seconds': 420, 'kill_mode': 'mixed',
        'Qwen_lifecycle_operations': 0, 'root_operations': 0}


def validate_spec(spec):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the existing ordinary-user manager is permitted')
    fixed = fixed_spec()
    token = spec.get('ownership_token')
    if (set(spec) != set(fixed) | {'ownership_token'} or any(spec.get(k) != v for k, v in fixed.items())
            or not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token)):
        raise ValueError('The new API user unit specification changed')
    checked(spec['entrypoint'])
    return spec


def command(spec):
    validate_spec(spec)
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit='+scope.API_UNIT,
        '--description=ProWorkSim v088 api coordinator '+spec['ownership_token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=mixed', '--property=CPUQuota=800%',
        '--property=CPUAffinity='+' '.join(map(str, spec['cpu_affinity'])),
        '--property=LimitNOFILE='+str(scope.NOFILE), '--property=MemoryMax=64G',
        '--property=MemoryHigh=32G', '--property=MemorySwapMax=0', '--property=TasksMax=512',
        '--property=OOMPolicy=stop', '--property=TimeoutStopSec=420',
        '--property=WorkingDirectory='+str(scope.ROOT),
        '--property=StandardOutput=append:'+str(scope.API_ROOT/'coordinator.stdout.log'),
        '--property=StandardError=append:'+str(scope.API_ROOT/'coordinator.stderr.log'),
        str(scope.ROOT/'.venv/bin/python'), '-B', str(scope.ROOT/'tools/run_offline_scorer_v058.py'),
        spec['entrypoint']['path'], '--execute']


def prepare():
    if SPEC.exists():
        spec = validate_spec(json.loads(SPEC.read_bytes()))
    else:
        if any((scope.API_ROOT/name).exists() for name in ('execution-started.json', 'launch-intent.json', 'bootstrap-started.json')):
            raise ValueError('A consumed service cannot acquire another specification')
        scope.API_ROOT.mkdir(parents=True, exist_ok=True)
        spec = {**fixed_spec(), 'ownership_token': secrets.token_hex(16)}
        write_new(SPEC, spec)
    return {'specification': reference(SPEC), 'command': command(spec), 'runtime_operations': 0}


def launch():
    scope.require_allowed('v088.run')
    parent.require_qualified()
    if not scope.PREDECESSOR_PROOF.exists() or not (scope.BATCH_ROOT/'plan-seal.json').exists():
        raise ValueError('Freeze acknowledged rolling ownership before launching the successor')
    if (scope.BATCH_ROOT/'plan-seal.json').exists() and not primary_ready():
        return {'version': VERSION, 'status': 'waiting_for_new_Qwen_cursor', 'launch_attempted': False}
    if not (scope.HANDOFF_ROOT/'stopped.json').exists():
        handoff.validate_launch_pause()
    if any((scope.API_ROOT/name).exists() for name in ('launch-intent.json', 'bootstrap-started.json', 'execution-started.json')):
        raise ValueError('No automatic coordinator replay')
    import resource
    if resource.getrlimit(resource.RLIMIT_NOFILE)[1] < scope.NOFILE:
        raise PermissionError('Current hard NOFILE cannot support the new private service limit')
    spec = validate_spec(json.loads(SPEC.read_bytes()))
    response = subprocess.run(['systemctl', '--user', 'show', scope.API_UNIT, '--no-pager',
        '--property=LoadState,ActiveState,SubState,MainPID'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20)
    props = dict(line.split('=', 1) for line in response.stdout.splitlines() if '=' in line)
    if response.returncode or props.get('MainPID') != '0' or props.get('ActiveState') != 'inactive':
        raise ValueError('The exact new user service is not inactive')
    reservation = scope.reserve_api_coordinator()
    argv = command(spec)
    write_new(scope.API_ROOT/'launch-intent.json', {'version': VERSION, 'unix': time.time(),
        'authorization': reference(scope.AUTH_FILE), 'specification': reference(SPEC),
        'reservation': reservation, 'observed_inactive': props, 'command': argv})
    result = subprocess.run(argv, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
    receipt = {'version': VERSION, 'unit': scope.API_UNIT, 'returncode': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr, 'reservation': reservation,
        'Qwen_lifecycle_operations': 0, 'parent_slice_changed': False}
    write_new(scope.API_ROOT/'launch-result.json', receipt)
    if result.returncode:
        raise RuntimeError('New API service launch failed; no automatic retry')
    return receipt


def primary_ready(timeout=45):
    deadline = time.monotonic()+timeout
    while True:
        if scope.PRIMARY_CURSOR.exists():
            value = json.loads(scope.PRIMARY_CURSOR.read_bytes())
            if value.get('failure') is not None:
                expected = scope.load(reference(scope.INVENTORY_FILE))['qualifications']
                require_unchanged_terminal(expected, value)
                return True
            if (value.get('phase') in {'starting', 'running', 'waiting', 'closed'}
                    and isinstance(value.get('qualifications'), dict)):
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(.2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else launch(), ensure_ascii=False))
