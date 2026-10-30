"""Prepare or launch only the approved ordinary-user official-rescoring owner."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

from proworksim import software_benchmark_rescore_v095 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_ref_resident_v066 import user_manager_environment


def specification(context):
    pool = scoring.original_policy.host_cpu_pool()
    cpus = sorted(set(pool[76:92]+pool[168:170]))
    return {'version': scoring.VERSION, 'unit': 'proworksim-v095-'+context.root.name+'.service',
        'user_id': os.getuid(), 'cpu_affinity': cpus, 'cpu_quota_percent': 1800,
        'memory_max_bytes': 24*1024**3, 'memory_high_bytes': 20*1024**3,
        'memory_swap_max_bytes': 0, 'tasks_max': 1024, 'nofile': 8192,
        'plan': context.plan_ref, 'entrypoint': reference(scoring.ROOT/'tools/run_rescore_v095.py'),
        'score_child_cpu': 4, 'score_child_address_space_bytes': 4*1024**3,
        'container_cpu': 4, 'container_memory_bytes': 16*1024**3,
        'maximum_concurrent_graders': 4, 'initial_health_gate_concurrency': 2,
        'model_calls': 0, 'GPU_operations': 0, 'root_operations': 0,
        'new_system_slice': False, 'host_configuration_changes': 0, 'restart': 'no'}


def command(context, spec):
    expected = specification(context)
    if os.getuid() == 0 or any(spec.get(key) != value for key, value in expected.items()):
        raise PermissionError('Only the frozen ordinary-user grading resource scope may launch')
    output = context.root/'coordinator'
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit='+spec['unit'],
        '--description=ProWorkSim v095 preserved-candidate rescoring '+spec['ownership_token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=mixed', '--property=CPUQuota=1800%',
        '--property=CPUAffinity='+' '.join(map(str, spec['cpu_affinity'])),
        '--property=MemoryMax=24G', '--property=MemoryHigh=20G', '--property=MemorySwapMax=0',
        '--property=TasksMax=1024', '--property=LimitNOFILE=8192', '--property=OOMPolicy=stop',
        '--property=TimeoutStopSec=180', '--property=RuntimeMaxSec=28800',
        '--property=WorkingDirectory='+str(scoring.ROOT),
        '--property=StandardOutput=append:'+str(output/'stdout.log'),
        '--property=StandardError=append:'+str(output/'stderr.log'),
        str(scoring.ROOT/'.venv/bin/python'), '-B', str(scoring.ROOT/'tools/run_offline_scorer_v058.py'),
        spec['entrypoint']['path'], '--plan', context.plan_ref['path'], '--execute']


def prepare(context):
    output = context.root/'coordinator'
    output.mkdir(exist_ok=True)
    spec = {**specification(context), 'ownership_token': secrets.token_hex(16)}
    spec_ref = write_new(output/'unit-specification.json', spec)
    return {'specification': spec_ref, 'command': command(context, spec), 'service_operations': 0}


def launch(context):
    context.allowed()
    output = context.root/'coordinator'
    if any((output/name).exists() for name in ('launch-intent.json', 'started.json')):
        raise PermissionError('This owner identity cannot restart')
    spec_ref = reference(output/'unit-specification.json')
    spec = scoring.load(spec_ref)
    result = subprocess.run(['systemctl', '--user', 'show', spec['unit'], '--no-pager',
        '--property=MainPID,ActiveState'], env=user_manager_environment(), capture_output=True, text=True, timeout=20)
    state = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if result.returncode or state.get('MainPID') != '0' or state.get('ActiveState') not in ('inactive', 'failed'):
        raise PermissionError('New scoring owner is not inactive')
    argv = command(context, spec)
    write_new(output/'launch-intent.json', {'specification': spec_ref, 'plan': context.plan_ref,
        'authorization': reference(context.auth_file), 'command': argv, 'unix': time.time()})
    result = subprocess.run(argv, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
    value = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
        'unit': spec['unit'], 'new_system_slice': False, 'root_operations': 0}
    write_new(output/'launch-result.json', value)
    if result.returncode:
        raise RuntimeError('Scoring owner launch failed; preserve its exact launch evidence')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=scoring.PLAN_FILE)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    context = scoring.Context(reference(args.plan))
    print(json.dumps(prepare(context) if args.prepare else launch(context), ensure_ascii=False))
