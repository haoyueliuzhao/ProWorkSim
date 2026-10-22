"""Bind the unchanged lossless archival implementation to 53 primary clones.

This wrapper changes only the private metadata namespace and plan identity.
Original content verification, claim locks, quiescence, same-volume payload
placement, release and restore implementations remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
RUN = ROOT / 'runs/software-benchmark-v055'
OUT = RUN / 'primary-terminal-rootfs-archive-r1'
ALLOWLIST = RUN / 'primary-terminal-rootfs-archive-audit-r1/allowlist.json'
ALLOWLIST_SHA = '69925d56ffafd76de4faf86ea719248f6b6c39b1f885131a03a2e163a0b79072'
ORIGINAL = ROOT / 'tools/archive_terminal_rootfs_v055_r1.py'
ORIGINAL_SHA = 'a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13'
VERSION = 'v055-primary-terminal-rootfs-lossless-archive-r1'
COUNT = 53
PRIMARY_DEVICE = 66306


def original():
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != ORIGINAL_SHA:
        raise ValueError('Frozen original archival implementation changed')
    spec = importlib.util.spec_from_file_location('primary_terminal_archive_original', ORIGINAL)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    base.OUT, base.VERSION = OUT, VERSION
    return base


def fixed_allowlist(base):
    if ALLOWLIST.resolve() != ALLOWLIST or base.sha(ALLOWLIST) != ALLOWLIST_SHA:
        raise ValueError('Exact primary 53-item allowlist changed')
    value = json.loads(ALLOWLIST.read_bytes())
    rows = value['roots']
    if (value['version'] != 'v055-primary-terminal-rootfs-fixed-53-r1'
            or len(rows) != COUNT or len({r['rootfs'] for r in rows}) != COUNT):
        raise ValueError('Only the fixed 53 primary clones are eligible')
    for row in rows:
        source = base.source_path(row['rootfs'])
        if (not source.is_relative_to(RUN / 'queue-r1/workers')
                or row['historical_all_quiet'] is not True or row['historical_errors']
                or row['resource_released'] is not True):
            raise ValueError('Allowlist crossed its primary terminal ownership scope')
    return value


def validate_plan(base, value):
    allowed = fixed_allowlist(base)
    if (value.get('namespace_wrapper') != base.ref(__file__)
            or value.get('source') != base.ref(ORIGINAL)
            or value.get('allowlist_source') != base.ref(ALLOWLIST)
            or value.get('version') != VERSION
            or len(value.get('items', [])) != COUNT
            or {r['rootfs'] for r in value['items']} != {r['rootfs'] for r in allowed['roots']}):
        raise ValueError('Plan does not bind this wrapper and the exact 53-item scope')
    if len({r['item_id'] for r in value['items']}) != COUNT:
        raise ValueError('Plan contains duplicate archive identities')
    for item in value['items']:
        root = base.source_path(item['rootfs'])
        expected_id = hashlib.sha256(str(root).encode()).hexdigest()[:24]
        expected_payload = RUN / 'queue-r1/terminal-rootfs-archive-r1' / expected_id
        if (item['item_id'] != expected_id or item['archive_directory'] != str(expected_payload)
                or item['root_identity']['device'] != PRIMARY_DEVICE):
            raise ValueError('Plan crossed the exact primary payload identity')
    return value


def prepare(base):
    if os.geteuid() != 1021 or os.getuid() != 1021:
        raise PermissionError('Only the project owner prepares this independent plan')
    allowed = fixed_allowlist(base)
    rows = []
    for item in allowed['roots']:
        root = base.source_path(item['rootfs'])
        row = base.current_row(item['slot_id'])
        claim = Path(item['quiescence']['path']).parent
        refs = [base.ref(claim / name) for name in ('claim.json', 'entered.json', 'state.json',
                                                   'scope-registry.json', 'quiescence.json')]
        refs += [item['result'], item['resource_slice'], base.ref(item['rootfs_manifest_path'])]
        for evidence in refs:
            base.checked(evidence)
        item_id = hashlib.sha256(str(root).encode()).hexdigest()[:24]
        rows.append({**{k: item[k] for k in ('slot_id', 'rootfs', 'episode_root', 'result',
                                             'quiescence', 'resource_slice')},
                     'item_id': item_id,
                     'archive_directory': str(RUN / 'queue-r1/terminal-rootfs-archive-r1' / item_id),
                     'root_identity': base.root_identity(root), 'row_sha256': base.row_sha(row),
                     'rootfs_manifest': base.ref(item['rootfs_manifest_path']), 'retained_evidence': refs,
                     'allocated_bytes_observed_du': item['rootfs_allocated_bytes']})
    value = {'version': VERSION, 'created_unix': time.time(), 'source': base.ref(ORIGINAL),
             'namespace_wrapper': base.ref(__file__), 'allowlist_source': base.ref(ALLOWLIST),
             'items': rows, 'excluded': [],
             'quiescence_reader': base.ref(ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'),
             'codec': 'GNU-pax-tar+zstd-level1', 'archive_and_release_separate': True,
             'resources_per_worker': {'CPUQuota': '200%', 'MemoryMax': '2G', 'IOWeight': '10', 'Nice': '10'},
             'maximum_parallel_workers': 2, 'model_calls': 0,
             'original_experiment_records_modified': False,
             'allocated_bytes_observed_du': allowed['allocated_bytes'],
             'payload_same_primary_filesystem_required': True,
             'old_63_item_plan_and_receipts_not_modified': True}
    validate_plan(base, value)
    base.new_directory(OUT)
    return base.put(OUT / 'plan.json', value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('plan', 'preflight', 'archive', 'release', 'restore'))
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--item-id')
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    base = original()
    if base.sha(__file__) != args.source_sha256:
        raise ValueError('Explicit exact namespace wrapper SHA is required')
    if args.operation == 'plan':
        print(json.dumps(prepare(base)))
        return
    if args.plan is None or args.sha256 is None:
        parser.error('A frozen plan and SHA are required')
    value = validate_plan(base, base.load_plan(args.plan, args.sha256, ORIGINAL_SHA))
    if args.operation == 'preflight':
        observations = []
        for item in value['items']:
            with base.claim_lock(item):
                observations.append({'item_id': item['item_id'], **base.live_quiet(value, item)})
        print(json.dumps({'version': VERSION, 'plan': base.ref(args.plan), 'items': observations,
                          'archive_calls': 0, 'release_calls': 0, 'signals': 0, 'model_calls': 0}))
        return
    matching = [r for r in value['items'] if r['item_id'] == args.item_id]
    if len(matching) != 1:
        raise ValueError('Exactly one frozen item is required')
    item = matching[0]
    if args.operation == 'archive':
        result = base.archive_one(value, item)
    elif args.operation == 'release':
        result = base.release_one(value, item)
    else:
        result = base.restore_one(value, item, args.destination)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
