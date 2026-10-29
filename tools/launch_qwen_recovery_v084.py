"""Start only the new 32 GiB primary; never operate any resident model unit."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess

from proworksim import software_benchmark_qwen_scope_v084 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment

VERSION = 'v084-owned-Qwen-unit-r1'
SPEC = scope.PRIMARY_ROOT/'coordinator-unit.json'


def fixed_spec():
    return {'version': VERSION, 'unit': scope.PRIMARY_UNIT, 'user_id': os.getuid(),
        'source': reference(__file__), 'entrypoint': reference(scope.ROOT/'tools/run_qwen_recovery_v084.py'),
        'cpu_affinity': list(map(int, scope.original.cpu_set('coordinator').split(','))),
        'CPUQuota': 400, 'MemoryMax': scope.MEMORY_BYTES, 'MemorySwapMax': 0, 'TasksMax': 512,
        'maximum_grading_workers': 1, 'Restart': 'no', 'model_lifecycle_operations': 0}


def command(spec):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only an ordinary user may create this unit')
    fixed = fixed_spec()
    if any(spec.get(k) != v for k, v in fixed.items()) or not isinstance(spec.get('token'), str):
        raise ValueError('Exact prepared Qwen unit changed')
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit='+scope.PRIMARY_UNIT,
        '--description=ProWorkSim v084 Qwen coordinator '+spec['token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=mixed', '--property=CPUQuota=400%',
        '--property=CPUAffinity='+' '.join(map(str, spec['cpu_affinity'])),
        '--property=MemoryMax=32G', '--property=MemorySwapMax=0', '--property=TasksMax=512',
        '--property=OOMPolicy=stop', '--property=TimeoutStopSec=420',
        '--property=WorkingDirectory='+str(scope.ROOT),
        '--property=StandardOutput=append:'+str(scope.PRIMARY_ROOT/'coordinator.stdout.log'),
        '--property=StandardError=append:'+str(scope.PRIMARY_ROOT/'coordinator.stderr.log'),
        str(scope.ROOT/'.venv/bin/python'), '-B', str(scope.ROOT/'tools/run_offline_scorer_v058.py'),
        spec['entrypoint']['path'], '--execute']


def prepare():
    scope.PRIMARY_ROOT.mkdir(parents=True, exist_ok=True)
    if SPEC.exists():
        spec = json.loads(SPEC.read_bytes())
    else:
        spec = {**fixed_spec(), 'token': secrets.token_hex(16)}
        write_new(SPEC, spec)
    return {'specification': reference(SPEC), 'command': command(spec), 'services_started': 0}


def launch():
    scope.require_allowed('v084.run')
    if any((scope.PRIMARY_ROOT/name).exists() for name in ('launch-intent.json', 'execution-started.json')):
        raise ValueError('A consumed Qwen coordinator cannot be replayed')
    spec = json.loads(SPEC.read_bytes())
    argv = command(spec)
    result = subprocess.run(['systemctl', '--user', 'show', scope.PRIMARY_UNIT, '--no-pager',
        '--property=ActiveState,MainPID'], env=user_manager_environment(), capture_output=True, text=True, timeout=20)
    props = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or props.get('ActiveState') != 'inactive' or props.get('MainPID') != '0':
        raise ValueError('The exact new primary is not proved inactive')
    write_new(scope.PRIMARY_ROOT/'launch-intent.json', {'authorization': reference(scope.AUTH_FILE),
        'specification': reference(SPEC), 'inactive_unit': props, 'command': argv})
    started = subprocess.run(argv, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
    outcome = {'version': VERSION, 'returncode': started.returncode, 'stdout': started.stdout,
        'stderr': started.stderr, 'model_services_reloaded': False}
    write_new(scope.PRIMARY_ROOT/'launch-result.json', outcome)
    if started.returncode:
        raise RuntimeError('Owned new Qwen unit startup failed; inspect retained receipt')
    return outcome


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(launch(), ensure_ascii=False))
