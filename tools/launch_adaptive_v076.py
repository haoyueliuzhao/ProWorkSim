"""Launch two bounded ordinary-user coordinators without touching resident GPUs."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import time

from proworksim import software_benchmark_adaptive_scope_v076 as scope
from proworksim import software_benchmark_dispatch_v066 as original
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v076-adaptive-owned-coordinator-units-r1'
ROLES = ('primary', 'api')


def ordinary_user():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the original ordinary-user service manager is authorized')


def folder(role):
    if role not in ROLES:
        raise ValueError('Unknown adaptive coordinator role')
    return scope.PRIMARY_ROOT if role == 'primary' else scope.API_ROOT


def unit(role):
    return scope.PRIMARY_UNIT if role == 'primary' else scope.API_UNIT


def fixed_spec(role):
    affinity = list(map(int, original.cpu_set('coordinator').split(','))) if role == 'primary' else scope.cpu_affinity()
    return {'version': VERSION, 'role': role, 'unit': unit(role), 'user_id': os.getuid(),
        'source': reference(__file__), 'entrypoint': reference(scope.ROOT / 'tools/run_adaptive_v076.py'),
        'recovery_root': str(scope.BATCH_ROOT), 'reporting_root': str(folder(role)),
        'cpu_affinity': affinity, 'cpu_quota_percent': 400, 'memory_max_bytes': 16 * scope.GIB,
        'memory_swap_max_bytes': 0, 'tasks_max': 512, 'restart': 'no',
        'timeout_stop_seconds': 420, 'kill_mode': 'mixed', 'resident_lifecycle_operations': 0}


def validate_spec(spec):
    ordinary_user()
    fixed = fixed_spec(spec.get('role'))
    token = spec.get('ownership_token')
    if (set(spec) != set(fixed) | {'ownership_token'}
            or any(spec.get(key) != value for key, value in fixed.items())
            or not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token)):
        raise ValueError('The exact prepared adaptive service specification changed')
    checked(spec['source'])
    checked(spec['entrypoint'])
    return spec['role']


def command(spec):
    role = validate_spec(spec)
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit=' + unit(role),
        '--description=ProWorkSim v076 ' + role + ' coordinator ' + spec['ownership_token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=mixed', '--property=CPUQuota=400%',
        '--property=CPUAffinity=' + ' '.join(map(str, spec['cpu_affinity'])),
        '--property=MemoryMax=16G', '--property=MemorySwapMax=0', '--property=TasksMax=512',
        '--property=OOMPolicy=stop', '--property=TimeoutStopSec=420',
        '--property=WorkingDirectory=' + str(scope.ROOT),
        '--property=StandardOutput=append:' + str(folder(role) / 'coordinator.stdout.log'),
        '--property=StandardError=append:' + str(folder(role) / 'coordinator.stderr.log'),
        str(scope.ROOT / '.venv/bin/python'), '-B', str(scope.ROOT / 'tools/run_offline_scorer_v058.py'),
        spec['entrypoint']['path'], '--execute', '--role', role]


def prepare():
    ordinary_user()
    units = {}
    for role in ROLES:
        path = folder(role) / 'coordinator-unit.json'
        if path.exists():
            spec = json.loads(path.read_bytes())
            validate_spec(spec)
        else:
            if any((folder(role) / name).exists() for name in ('execution-started.json', 'launch-intent.json')):
                raise ValueError('Entered coordinator identity cannot acquire a new specification')
            folder(role).mkdir(parents=True, exist_ok=True)
            spec = {**fixed_spec(role), 'ownership_token': secrets.token_hex(16)}
            write_new(path, spec)
        units[role] = {'specification': reference(path), 'command': command(spec)}
    return {'version': VERSION, 'units': units, 'runtime_operations': 0}


def inactive(role):
    result = subprocess.run(['systemctl', '--user', 'show', unit(role), '--no-pager',
        '--property=LoadState,ActiveState,SubState,MainPID'], env=user_manager_environment(),
        capture_output=True, text=True, timeout=20)
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or props.get('MainPID') != '0' or props.get('ActiveState') != 'inactive':
        raise RuntimeError('The exact new adaptive unit is not proved inactive')
    return props


def primary_ready(timeout=45):
    deadline = time.monotonic() + timeout
    while True:
        if scope.PRIMARY_CURSOR.exists():
            value = json.loads(scope.PRIMARY_CURSOR.read_bytes())
            if value.get('failure') is not None:
                raise RuntimeError('The new primary reports a shared failure')
            if value.get('phase') in {'starting', 'running', 'waiting'} and isinstance(value.get('qualifications'), dict):
                return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(.2)


def launch(selected='all'):
    ordinary_user()
    if selected not in (*ROLES, 'all'):
        raise ValueError('Choose primary, api or all')
    bootstrap = not (scope.BATCH_ROOT / 'plan-seal.json').is_file()
    if bootstrap:
        if selected != 'primary':
            raise ValueError('Before handoff, launch only the bounded primary bootstrap')
        from proworksim import software_benchmark_api_parent_v076 as parent
        parent.require_qualified()
        if not (scope.HANDOFF_ROOT / 'gate.json').is_file():
            raise ValueError('The old task admission gate must precede automatic bootstrap')
    elif not (scope.HANDOFF_ROOT / 'ready-restored.json').is_file():
        raise ValueError('Original resident discovery must be restored after the quiet handoff')
    roles = ROLES if selected == 'all' else (selected,)
    specs = {}
    for role in roles:
        if any((folder(role) / name).exists() for name in ('execution-started.json', 'launch-intent.json')):
            raise ValueError('A consumed adaptive coordinator cannot be replayed')
        spec = json.loads((folder(role) / 'coordinator-unit.json').read_bytes())
        validate_spec(spec)
        specs[role] = spec
    results = {}
    for role in roles:
        scope.require_allowed('v076.handoff' if bootstrap else 'v076.api.run' if role == 'api' else 'v076.run')
        if role == 'api' and not primary_ready():
            return {'version': VERSION, 'launched': results, 'api_status': 'waiting_for_primary_cursor'}
        observed = inactive(role)
        reservation = (scope.reserve_primary_bootstrap() if bootstrap else
                       scope.reserve_api_coordinator() if role == 'api' else None)
        argv = command(specs[role])
        write_new(folder(role) / 'launch-intent.json', {'version': VERSION, 'role': role,
            'authorization': reference(scope.AUTH_FILE), 'specification': reference(folder(role) / 'coordinator-unit.json'),
            'inactive_unit': observed, 'coordinator_reservation': reservation, 'command': argv,
            'natural_handoff_bootstrap': bootstrap})
        response = subprocess.run(argv, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
        result = {'version': VERSION, 'role': role, 'unit': unit(role),
            'returncode': response.returncode, 'stdout': response.stdout, 'stderr': response.stderr,
            'coordinator_reservation': reservation, 'resident_units_stopped_or_reloaded': False,
            'natural_handoff_bootstrap': bootstrap}
        write_new(folder(role) / 'launch-result.json', result)
        results[role] = result
        if response.returncode:
            raise RuntimeError('Adaptive owned unit launch failed; successful other roles are unchanged')
    return {'version': VERSION, 'launched': results, 'shared_host_configuration_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--role', choices=(*ROLES, 'all'), default='all')
    args = parser.parse_args()
    if args.prepare == args.launch:
        parser.error('Choose exactly one of --prepare or --launch')
    print(json.dumps(prepare() if args.prepare else launch(args.role), ensure_ascii=False))
