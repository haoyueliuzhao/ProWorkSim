"""Recover three finished shared caches with the unchanged r2 fresh proof.

The finite wrapper changes only its private namespace and fixed allowlist.
It keeps the original cache lock, nine-consumer checks and safe deleter, and
preserves historical failed proofs instead of changing experiment outcomes.
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
OUT = ROOT / 'runs/software-benchmark-v055/cache-history-recovery-r3'
AUDIT = ROOT / 'runs/software-benchmark-v055/cache-history-recovery-audit-r3/qualified.json'
AUDIT_SHA = '41fa620394bc114ac56d75f6dc33c6031f6770b1abd44b29b5a13c7f27ffae7c'
VERSION = 'v055-history-three-terminal-cache-recovery-r3'
RECOVERY_PATH = ROOT / 'tools/reclaim_terminal_cache_v055_r2.py'
RECOVERY_SHA = '368d9dac7a2714f48188599cf31c01def3e13b426620d16c8ebe57b7d70d7b67'
TARGETS = {
    'django__django-14170': ('0c045a12657b5644', 3138809856),
    'django__django-15957': ('f446b2c801214e39', 3181043712),
    'sphinx-doc__sphinx-7748': ('e216dafb31a35f58', 2954887168),
}


def target_path(name):
    if name not in TARGETS:
        raise ValueError('Only the exact three historical terminal caches are allowed')
    return ROOT / 'runs/software-benchmark-v054/native-lazy-cache' / name / TARGETS[name][0] / 'rootfs'


def recovery():
    if hashlib.sha256(RECOVERY_PATH.read_bytes()).hexdigest() != RECOVERY_SHA:
        raise ValueError('Previously qualified fresh-quiescence helper changed')
    spec = importlib.util.spec_from_file_location('history_cache_sealed_recovery_r2', RECOVERY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT, module.VERSION = OUT, VERSION
    module.ALLOCATED = {name: row[1] for name, row in TARGETS.items()}
    return module


def audit(base):
    ref = base.ref(AUDIT)
    if ref['sha256'] != AUDIT_SHA:
        raise ValueError('Fixed pre-audit changed')
    value = base.checked(ref)
    if [row['instance_id'] for row in value] != list(TARGETS):
        raise ValueError('Pre-audit crossed the exact three names')
    for row in value:
        if (row['rootfs'] != str(target_path(row['instance_id']))
                or row['allocated_bytes'] != TARGETS[row['instance_id']][1]
                or row['fresh_quiescence'] is not True or len(row['nine_consumers']) != 9):
            raise ValueError('Pre-audit crossed the exact observed cache identity')
    return ref


def prior_completion(base, name):
    """Never delete or count an already absent payload a second time."""
    rootfs = target_path(name)
    if rootfs.exists() or rootfs.is_symlink():
        return None
    for path in (base.OUTPUT / (name + '.completed.json'), OUT / (name + '.completed.json')):
        if path.is_file():
            ref = base.ref(path)
            value = base.checked(ref)
            if value.get('instance_id') != name or not str(value.get('status', '')).startswith('reclaimed'):
                raise ValueError('Absent payload has an inconsistent completed receipt')
            return ref
    raise ValueError('Absent payload lacks a trusted existing completion')


def validate_plan(plan, base, helper):
    if (plan.get('version') != VERSION or plan.get('invocation_wrapper') != base.ref(__file__)
            or plan.get('source') != base.ref(RECOVERY_PATH) or plan.get('pre_audit') != audit(base)
            or plan.get('original_helper', {}).get('sha256') != helper.ORIGINAL_SHA
            or [row['instance_id'] for row in plan['allowlist']] != list(TARGETS)):
        raise ValueError('Three-item recovery plan identity changed')
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
    audit_ref = audit(base)
    old, new = base.snapshot()
    registry = base.registry()
    rows = []
    for name, (mapping_prefix, allocated) in TARGETS.items():
        selected = base.task_rows(old, new, name)
        if registry[name]['baseline_mapping']['sha256'][:16] != mapping_prefix:
            raise ValueError('Selected target differs from the official baseline mapping')
        rootfs = target_path(name)
        previous = prior_completion(base, name)
        identity = None if previous else rootfs.lstat()
        if identity is not None and (not stat.S_ISDIR(identity.st_mode)
                or rootfs.resolve() != rootfs or identity.st_dev != 66306):
            raise ValueError('Only original primary real cache directories are allowed')
        rows.append({'instance_id': name, 'payload': str(rootfs), 'device': 66306,
            'inode': identity.st_ino if identity else None, 'allocated_bytes_observed_du': allocated,
            'terminal_projection_sha256': base.projection(*selected),
            'lazy_preparation': base.ref(rootfs.parent / 'lazy-preparation.json'),
            'already_completed': previous})
    plan = {'version': VERSION, 'created_utc': base.now(), 'source': base.ref(RECOVERY_PATH),
        'invocation_wrapper': base.ref(__file__), 'pre_audit': audit_ref,
        'original_helper': base.ref(ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'),
        'allowlist': rows, 'allocated_bytes_observed_du': sum(row[1] for row in TARGETS.values()),
        'measurement': 'earlier single sudo du -s -B1 -x audit of the three exact immutable terminal cache rootfs',
        'scope': 'only three shared terminal cache rootfs; episode evidence and Docker images retained',
        'prior_failures_preserved': True, 'fresh_quiescence_required_under_original_cache_lock': True,
        'original_sixteen_and_two_cache_plans_and_sources_unchanged': True}
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
        raise ValueError('Fixed three-item plan SHA changed')
    validate_plan(base.checked(plan_ref), base, helper)
    previous = prior_completion(base, name)
    if previous:
        return {'instance_id': name, 'status': 'skipped_already_completed',
                'prior_completion': previous, 'new_reclaimed_bytes': 0}
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
