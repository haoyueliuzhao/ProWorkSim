"""Finite six-template final cleanup with the unchanged r2 fresh proof/deleter.

No missing locks are created, no historical quiet/failed evidence is rewritten,
and no astropy pre-entry recovery path is part of this allowlist.
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
OUT = ROOT / 'runs/software-benchmark-v055/final-shared-cache-recovery-r4'
AUDIT = OUT / 'preaudit.json'
AUDIT_SHA = '2bfb877b47574c68ffc6f94c20ae1b2a7b0a9d4bbc50a8f9d97029175fa12bbc'
HELPER = ROOT / 'tools/reclaim_terminal_cache_v055_r2.py'
HELPER_SHA = '368d9dac7a2714f48188599cf31c01def3e13b426620d16c8ebe57b7d70d7b67'
VERSION = 'v055-final-six-shared-cache-current-quiescence-r4'
TARGETS = {
    'django__django-13344': ('3c7420d774b6f859', 3036549120),
    'django__django-14053': ('d1e1e82ec5bfd879', 3137957888),
    'django__django-16136': ('983258ee39ad4862', 3180957696),
    'django__django-16877': ('a1f1762081160eee', 3241091072),
    'pytest-dev__pytest-7236': ('3a3909f4c0385d3d', 2806165504),
    'sphinx-doc__sphinx-9230': ('31cf6b57ba41a36c', 2954891264),
}


def target_path(name):
    if name not in TARGETS:
        raise ValueError('Only the six exact original shared cache roots are allowed')
    return ROOT / 'runs/software-benchmark-v054/native-lazy-cache' / name / TARGETS[name][0] / 'rootfs'


def helper():
    if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA:
        raise ValueError('Qualified fresh-proof implementation changed')
    spec = importlib.util.spec_from_file_location('final_cache_original_fresh_proof', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT, module.VERSION = OUT, VERSION
    module.ALLOCATED = {name: value[1] for name, value in TARGETS.items()}
    return module


def audit(base):
    ref = base.ref(AUDIT)
    if ref['sha256'] != AUDIT_SHA:
        raise ValueError('The single pre-audit changed')
    rows = base.checked(ref)['results']
    if [row['instance_id'] for row in rows] != list(TARGETS):
        raise ValueError('The pre-audit changed the finite allowlist')
    for row in rows:
        name = row['instance_id']
        if (row['rootfs'] != str(target_path(name)) or row['device'] != 66306
                or row['allocated_bytes'] != TARGETS[name][1] or row['fresh_quiescence'] is not True
                or row['nine_consumers_terminal'] is not True):
            raise ValueError('Only the exact pre-audited terminal payloads are allowed')
    return ref, rows


def prepare():
    if os.geteuid() != 1021:
        raise PermissionError('Prepare only as project owner')
    recovery = helper()
    base = recovery.original()
    audit_ref, audited = audit(base)
    old, new = base.snapshot()
    registry = base.registry()
    rows = []
    for observed in audited:
        name = observed['instance_id']
        rootfs = target_path(name)
        identity = rootfs.lstat()
        if (not stat.S_ISDIR(identity.st_mode) or rootfs.resolve() != rootfs
                or (identity.st_dev, identity.st_ino) != (observed['device'], observed['inode'])
                or registry[name]['baseline_mapping']['sha256'][:16] != TARGETS[name][0]):
            raise ValueError('The original observed template directory identity changed')
        rows.append({'instance_id': name, 'payload': str(rootfs), 'device': identity.st_dev,
            'inode': identity.st_ino, 'allocated_bytes_observed_du': TARGETS[name][1],
            'terminal_projection_sha256': base.projection(*base.task_rows(old, new, name)),
            'lazy_preparation': base.ref(rootfs.parent / 'lazy-preparation.json')})
    return base.write_new(OUT / 'plan.json', {'version': VERSION, 'created_utc': base.now(),
        'source': base.ref(HELPER), 'invocation_wrapper': base.ref(__file__), 'pre_audit': audit_ref,
        'original_helper': base.ref(ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'), 'allowlist': rows,
        'allocated_bytes_observed_du': sum(row[1] for row in TARGETS.values()),
        'measurement': 'one sudo du -s -B1 -x invocation on the six exact immutable terminal cache rootfs',
        'scope': 'only six original shared native-lazy-cache rootfs; no astropy recovery or episode evidence',
        'prior_failures_preserved': True, 'fresh_quiescence_required_under_original_cache_lock': True,
        'missing_locks_must_not_be_created': True, 'proof_does_not_reclassify_old_generation_results': True})


def run_one(plan_path, plan_sha, name, source_sha):
    recovery = helper()
    base = recovery.original()
    target_path(name)
    if source_sha != base.ref(__file__)['sha256'] or plan_path.resolve() != OUT / 'plan.json':
        raise ValueError('Source seal or fixed plan path changed')
    plan_ref = base.ref(plan_path)
    plan = base.checked(plan_ref)
    if (plan_ref['sha256'] != plan_sha or plan.get('invocation_wrapper') != base.ref(__file__)
            or plan.get('pre_audit') != audit(base)[0]
            or [row['instance_id'] for row in plan['allowlist']] != list(TARGETS)):
        raise ValueError('The independently sealed six-item plan changed')
    for row in plan['allowlist']:
        if (row['payload'] != str(target_path(row['instance_id'])) or row['device'] != 66306
                or row['allocated_bytes_observed_du'] != TARGETS[row['instance_id']][1]):
            raise ValueError('Plan crossed an exact authorized original cache root')
    return recovery.run_one(plan_path, plan_sha, name)


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
            parser.error('Fixed plan, exact instance and source seal are all required')
        try:
            result = run_one(args.plan, args.sha256, args.instance, args.source_sha256)
        except Exception as error:
            base = helper().original()
            result = {'version': VERSION, 'instance_id': args.instance, 'observed_utc': base.now(),
                'status': 'deferred', 'error': {'type': type(error).__name__, 'message': str(error)},
                'automatic_retry': False, 'prior_records_not_modified': True}
            if args.instance in TARGETS:
                path = OUT / (args.instance + '.failed.json')
                if not path.exists():
                    base.write_new(path, result)
            print(json.dumps(result), flush=True)
            raise SystemExit(1)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
