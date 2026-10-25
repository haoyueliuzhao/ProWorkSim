"""Launch only this batch's resource-bounded, ordinary-user coordinator unit."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess

from proworksim import software_benchmark_dispatch_v061 as policy
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_ref_resident_v061 import user_manager_environment

ROOT, BATCH_ROOT = policy.ROOT, policy.BATCH_ROOT
SPEC = BATCH_ROOT / 'coordinator-unit.json'
UNIT = 'proworksim-v061-recovery.service'
VERSION = 'v061-owned-recovery-coordinator-unit-r1'


def prepare():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Use the existing ordinary user manager')
    if SPEC.exists():
        body = json.loads(SPEC.read_bytes())
        if (body.get('version') != VERSION or body.get('unit') != UNIT
                or body.get('source') != reference(__file__) or body.get('plan') != reference(policy.PLAN_FILE)):
            raise ValueError('Prepared coordinator unit changed')
        return body
    body = {'version': VERSION, 'unit': UNIT, 'plan': reference(policy.PLAN_FILE),
        'source': reference(__file__), 'ownership_token': secrets.token_hex(16),
        'user_id': os.getuid(), 'cpu_quota_percent': 400, 'memory_max_bytes': 16 * 1024**3,
        'memory_swap_max_bytes': 0, 'tasks_max': 512, 'restart': 'no',
        'timeout_stop_seconds': 420, 'kill_mode': 'mixed', 'existing_user_manager_changed': False,
        'shared_host_configuration_changed': False}
    write_new(SPEC, body)
    return body


def command(spec):
    if spec.get('unit') != UNIT or spec.get('user_id') != os.getuid():
        raise ValueError('Unexpected coordinator ownership')
    checked(spec['source'])
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit=' + UNIT,
        '--description=ProWorkSim v061 coordinator ' + spec['ownership_token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=mixed', '--property=CPUQuota=400%',
        '--property=MemoryMax=16G', '--property=MemorySwapMax=0', '--property=TasksMax=512',
        '--property=OOMPolicy=stop', '--property=TimeoutStopSec=420',
        '--property=WorkingDirectory=' + str(ROOT),
        '--property=StandardOutput=append:' + str(BATCH_ROOT / 'coordinator.stdout.log'),
        '--property=StandardError=append:' + str(BATCH_ROOT / 'coordinator.stderr.log'),
        str(ROOT / '.venv/bin/python'), '-B', str(ROOT / 'tools/run_offline_scorer_v058.py'),
        str(ROOT / 'tools/run_unknown_recovery_v061.py'), '--execute']


def launch():
    policy.require_v061_allowed('v061.run')
    spec = prepare()
    argv = command(spec)
    write_new(BATCH_ROOT / 'coordinator-launch-intent.json', {'specification': reference(SPEC), 'command': argv})
    result = subprocess.run(argv, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
    record = {'version': VERSION, 'returncode': result.returncode, 'stdout': result.stdout,
              'stderr': result.stderr, 'unit': UNIT, 'specification': reference(SPEC)}
    write_new(BATCH_ROOT / 'coordinator-launch-result.json', record)
    if result.returncode != 0:
        raise RuntimeError('Owned coordinator launch failed: ' + result.stderr[-1200:])
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    if args.prepare == args.launch:
        parser.error('Choose exactly one of --prepare and --launch')
    print(json.dumps(prepare() if args.prepare else launch(), ensure_ascii=False))
