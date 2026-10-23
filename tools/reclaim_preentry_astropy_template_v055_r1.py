"""Finite exact legacy-template reclaim after original and recovery consumers end."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
RECOVERY = ROOT / 'runs/software-benchmark-v055/pre-entry-recovery-r1'
OUT = RECOVERY / 'cleanup-r1/template-release'
INSTANCE = 'astropy__astropy-12907'
CACHE = ROOT / 'runs/software-benchmark-v054/native-lazy-r3'
ENTRY = CACHE / INSTANCE / '843dcc65484d2d05'
PAYLOAD = ENTRY / 'rootfs'
ALIAS = ROOT / 'runs/software-benchmark-v054/native-lazy-cache' / INSTANCE / '843dcc65484d2d05'
ORIGINAL = ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'
ORIGINAL_SHA = 'add7b61e57b7518f130eda86294b225a30dadacec70ad549dd6ed94649e300de'
QUIET_WRAPPER = ROOT / 'tools/cleanup_deepseek_preentry_v055_r1.py'
QUIET_WRAPPER_SHA = '85d975b5d6c6f9e93a462bb9eb7a104115003566adefd2d1753ecaf0b213bd3e'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name, expected):
    if digest(path) != expected:
        raise ValueError('Exact cleanup dependency changed')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bind():
    base = load(ORIGINAL, 'preentry_template_original', ORIGINAL_SHA)
    adapter = load(QUIET_WRAPPER, 'preentry_template_quiet', QUIET_WRAPPER_SHA)
    plan, _ = adapter.recovery()
    if plan['template']['prepared_root'] != str(PAYLOAD):
        raise ValueError('Only the fixed astropy qualified template is admitted')
    before = base.quiet_consumers
    def quiet(a, b, prep):
        if (len(a) != 3 or len(b) != 6 or any(row['slot']['instance_id'] != INSTANCE for row in a + b)
                or any(row['generation']['status'] != 'technical_unknown' for row in b)):
            raise ValueError('Original task identity or six historical pre-entry statuses changed')
        original_qwen = before(a, [], {})
        independent_recovery = adapter.all_recovery_quiet(base)
        return {'original_qwen_three_consumers': original_qwen,
                'original_deepseek_six_preentry_plus_new_six_recovery': independent_recovery,
                'original_deepseek_claims_remain_unentered': True,
                'six_recovery_generation_and_three_scores_terminal': True}
    base.quiet_consumers = quiet
    base.CACHE, base.OUTPUT = CACHE, OUT
    base.VERSION = 'v055-one-legacy-astropy-template-after-preentry-recovery-r1'
    return base, adapter, plan


def validate_exact_payload(base, plan):
    if (PAYLOAD.resolve() != PAYLOAD or not PAYLOAD.is_dir() or PAYLOAD.is_symlink()
            or PAYLOAD.stat().st_dev != plan['template']['device']):
        raise ValueError('Exact template payload identity differs')
    manifest = base.checked(plan['template']['manifest'])
    qualified = base.checked(plan['template']['qualification'])
    if (manifest['prepared_root'] != str(PAYLOAD) or qualified.get('passed') is not True
            or qualified['instance_id'] != INSTANCE):
        raise ValueError('Exact source manifest or initialization differs')
    base.no_mounts_under(PAYLOAD)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('preflight', 'release'))
    parser.add_argument('--source-sha256', required=True)
    args = parser.parse_args()
    if digest(__file__) != args.source_sha256 or os.geteuid() != 0 or os.environ.get('SUDO_UID') != '1021':
        raise PermissionError('The owner must invoke the exact finite helper through sudo')
    base, adapter, plan = bind()
    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(OUT, 1021, 1022)
    alias_lock = ALIAS.parents[1] / 'locks' / (INSTANCE + '.lock')
    alias_lock.parent.mkdir(parents=True, exist_ok=True)
    with alias_lock.open('a+b') as alias_guard:
        os.fchown(alias_guard.fileno(), 1021, 1022)
        fcntl.flock(alias_guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        validate_exact_payload(base, plan)
        old, new = base.snapshot()
        a, b, prep = base.task_rows(old, new, INSTANCE)
        if args.operation == 'preflight':
            with (CACHE / 'locks' / (INSTANCE + '.lock')).open('r+b') as original_guard:
                fcntl.flock(original_guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
                proof = base.quiet_consumers(a, b, prep)
                du = subprocess.run(['/usr/bin/du', '-sx', '--block-size=1', '--', str(PAYLOAD)],
                                    check=True, capture_output=True, text=True, timeout=120)
                st = PAYLOAD.stat()
                result = {'observed_utc': base.now(), 'source': base.ref(__file__),
                    'fixed_payload': str(PAYLOAD), 'payload_device': st.st_dev, 'payload_inode': st.st_ino,
                    'allocated_bytes': int(du.stdout.split()[0]), 'proof': proof,
                    'legacy_template_lock_held': True, 'cache_alias_lock_held': True,
                    'payload_deleted': False, 'model_calls': 0}
                print(json.dumps(base.write_new(OUT / 'preflight.json', result)))
            return
        preflight = json.loads((OUT / 'preflight.json').read_bytes())
        st = PAYLOAD.stat()
        if (preflight['source'] != base.ref(__file__) or preflight['fixed_payload'] != str(PAYLOAD)
                or (preflight['payload_device'], preflight['payload_inode']) != (st.st_dev, st.st_ino)):
            raise ValueError('Exact admitted payload changed before release')
        # The original helper takes its original legacy cache lock, proves fresh
        # quiescence again, writes an intent and uses descriptor-safe rmtree.
        result = base.privileged_one(INSTANCE, ORIGINAL_SHA)
        if result.get('status') != 'reclaimed':
            raise ValueError('Template release did not finish')
        alias_marker = ALIAS / 'cache-eviction-v055-r1.json'
        if alias_marker.exists():
            raise ValueError('Unexpected preexisting alias eviction marker; retain completed release receipt')
        marker = base.write_new(alias_marker, {'version': base.VERSION, 'instance_id': INSTANCE,
            'payload': str(PAYLOAD), 'payload_absent': True, 'source_tombstone': base.ref(ENTRY / 'cache-eviction-v055-r1.json'),
            'historical_qualification_retained': True, 'future_new_experiment_requires_new_preparation_generation': True})
        summary = {**result, 'allocated_bytes_reclaimed_before_small_metadata': preflight['allocated_bytes'],
            'preflight': base.ref(OUT / 'preflight.json'), 'namespace_wrapper': base.ref(__file__),
            'alias_tombstone': marker, 'images_models_sources_results_candidates_and_billing_retained': True}
        print(json.dumps(base.write_new(OUT / 'summary.json', summary)))


if __name__ == '__main__':
    main()
