"""Two terminal primary caches, with the sealed r2 current-quiescence proof.

This independent namespace never changes the old sixteen-item plan or helper.
The original rootfs deleter retains its exact cache lock and all nine-consumer,
manifest, no-mount, symlink, PID, scope and resource-slice checks.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'runs/software-benchmark-v055/primary-prewarm-relief-cache-r1'
VERSION = 'v055-primary-prewarm-relief-two-terminal-caches-r1'
RECOVERY_PATH = ROOT / 'tools/reclaim_terminal_cache_v055_r2.py'
RECOVERY_SHA = '368d9dac7a2714f48188599cf31c01def3e13b426620d16c8ebe57b7d70d7b67'
TARGETS = {
    'pydata__xarray-6744': ('705510eaefa1dadc', 5135515648),
    'sphinx-doc__sphinx-9602': ('9830169f0038655d', 2958376960),
}


def target_path(name):
    if name not in TARGETS:
        raise ValueError('Only the two explicitly selected terminal caches are allowed')
    return ROOT / 'runs/software-benchmark-v054/native-lazy-cache' / name / TARGETS[name][0] / 'rootfs'


def recovery():
    if hashlib.sha256(RECOVERY_PATH.read_bytes()).hexdigest() != RECOVERY_SHA:
        raise ValueError('Previously qualified current-quiescence helper changed')
    spec = importlib.util.spec_from_file_location('prewarm_relief_sealed_recovery_r2', RECOVERY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Overrides affect only this private finite process, never the sealed file.
    module.OUT, module.VERSION = OUT, VERSION
    module.ALLOCATED = {name: row[1] for name, row in TARGETS.items()}
    return module


def validate_plan(plan, base, helper):
    if (plan.get('version') != VERSION or plan.get('invocation_wrapper') != base.ref(__file__)
            or plan.get('source') != base.ref(RECOVERY_PATH)
            or plan.get('original_helper', {}).get('sha256') != helper.ORIGINAL_SHA
            or [row['instance_id'] for row in plan['allowlist']] != list(TARGETS)):
        raise ValueError('Two-item recovery plan identity changed')
    for row in plan['allowlist']:
        name = row['instance_id']
        if (row['payload'] != str(target_path(name)) or row['device'] != 66306
                or row['allocated_bytes_observed_du'] != TARGETS[name][1]):
            raise ValueError('Plan escaped an exact authorized cache rootfs')


def prepare():
    if os.geteuid() != 1021:
        raise PermissionError('Prepare only as the project owner')
    helper = recovery()
    base = helper.original()
    old, new = base.snapshot()
    registry = base.registry()
    rows = []
    for name, (mapping_prefix, allocated) in TARGETS.items():
        selected = base.task_rows(old, new, name)
        if registry[name]['baseline_mapping']['sha256'][:16] != mapping_prefix:
            raise ValueError('Authorized target no longer matches its original baseline')
        rootfs = target_path(name)
        identity = rootfs.lstat()
        if not stat.S_ISDIR(identity.st_mode) or rootfs.resolve() != rootfs or identity.st_dev != 66306:
            raise ValueError('Only original primary real cache directories are allowed')
        rows.append({'instance_id': name, 'payload': str(rootfs), 'device': identity.st_dev,
            'inode': identity.st_ino, 'allocated_bytes_observed_du': allocated,
            'terminal_projection_sha256': base.projection(*selected),
            'lazy_preparation': base.ref(rootfs.parent / 'lazy-preparation.json')})
    plan = {'version': VERSION, 'created_utc': base.now(), 'source': base.ref(RECOVERY_PATH),
        'invocation_wrapper': base.ref(__file__),
        'original_helper': base.ref(ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'),
        'allowlist': rows, 'allocated_bytes_observed_du': sum(row[1] for row in TARGETS.values()),
        'measurement': 'parent audit sudo du -s -B1 -x on the two exact immutable terminal cache rootfs',
        'scope': 'only these two shared terminal cache rootfs, no episode records or Docker images',
        'prior_failures_preserved': True, 'fresh_quiescence_required_under_original_cache_lock': True,
        'original_sixteen_cache_plan_and_sources_unchanged': True}
    validate_plan(plan, base, helper)
    OUT.mkdir(exist_ok=False)
    return base.write_new(OUT / 'plan.json', plan)


def run_one(plan_path, plan_sha, name, source_sha):
    helper = recovery()
    base = helper.original()
    target_path(name)
    if source_sha != base.ref(__file__)['sha256'] or plan_path.resolve() != OUT / 'plan.json':
        raise ValueError('Wrapper source or fixed plan path changed')
    plan_ref = base.ref(plan_path)
    if plan_ref['sha256'] != plan_sha:
        raise ValueError('Fixed two-item plan SHA changed')
    validate_plan(base.checked(plan_ref), base, helper)
    return helper.run_one(plan_path, plan_sha, name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--instance')
    parser.add_argument('--source-sha256')
    args = parser.parse_args()
    if args.prepare:
        result = prepare()
    else:
        if not all((args.plan, args.sha256, args.instance, args.source_sha256)):
            parser.error('A fixed plan, source seal and exact instance are required')
        try:
            result = run_one(args.plan, args.sha256, args.instance, args.source_sha256)
        except Exception as error:
            base = recovery().original()
            name = args.instance if args.instance in TARGETS else 'invalid-instance'
            path = OUT / (name + '.failed.json')
            result = {'version': VERSION, 'instance_id': args.instance, 'observed_utc': base.now(),
                'status': 'deferred', 'error': {'type': type(error).__name__, 'message': str(error)},
                'automatic_retry': False, 'prior_records_not_modified': True}
            if path.parent.exists() and not path.exists():
                base.write_new(path, result)
            print(json.dumps(result), flush=True)
            raise SystemExit(1)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
