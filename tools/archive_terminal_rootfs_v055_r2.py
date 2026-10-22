"""Bind the unchanged lossless archival implementation to 51 new terminal clones.

This wrapper binds an independent namespace, plan and exact third-volume path.
Original content verification, claim locks, quiescence, same-volume payload
placement, release and restore implementations remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
RUN = ROOT / 'runs/software-benchmark-v055'
OUT = RUN / 'terminal-rootfs-archive-r2'
ALLOWLIST = RUN / 'terminal-rootfs-archive-audit-r2/allowlist.json'
ALLOWLIST_SHA = '3adde46a9d2964b94312866abef405000e4a79f154c0cdb4345ac5ee4c4f987d'
ORIGINAL = ROOT / 'tools/archive_terminal_rootfs_v055_r1.py'
ORIGINAL_SHA = 'a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13'
VERSION = 'v055-terminal-rootfs-lossless-archive-r2'
COUNT = 51
DEVICES = {'queue-r1': 66306, 'secondary-volume-r1': 66307, 'tertiary-volume-r1': 66308}
PATH_RE = re.compile(r'(?:queue-r1|secondary-volume-r1|tertiary-volume-r1)/workers/generation-[a-f0-9]{24}/episode/(?:public-test-[0-9]+/)?actor/rootfs')
OLD_PLANS = {
    RUN / 'terminal-rootfs-archive-r1/plan.json': '2842e8a4ce9476706fce081e9c1b710f29be89dd2caf86c014b850200bd6d8fb',
    RUN / 'primary-terminal-rootfs-archive-r1/plan.json': '14fe3818af99ff344d03c0af18671437a8e9d96b610ef2ba3a9e2b005913fa0d',
}


def original():
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != ORIGINAL_SHA:
        raise ValueError('Frozen original archival implementation changed')
    spec = importlib.util.spec_from_file_location('terminal_archive_r2_original', ORIGINAL)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    base.OUT, base.VERSION, base.PATH_RE = OUT, VERSION, PATH_RE
    return base


def fixed_allowlist(base):
    if ALLOWLIST.resolve() != ALLOWLIST or base.sha(ALLOWLIST) != ALLOWLIST_SHA:
        raise ValueError('Exact new terminal 51-item allowlist changed')
    value = json.loads(ALLOWLIST.read_bytes())
    rows = value['roots']
    if (value['version'] != 'v055-new-terminal-rootfs-fixed-51-r2'
            or len(rows) != COUNT or len({r['rootfs'] for r in rows}) != COUNT
            or value['allocated_bytes'] != 169918124032):
        raise ValueError('Only the fixed 51 new terminal clones are eligible')
    old_sources, old_ids = set(), set()
    for path, expected in OLD_PLANS.items():
        if base.sha(path) != expected:
            raise ValueError('An earlier frozen plan changed')
        old = json.loads(path.read_bytes())
        old_sources.update(r['rootfs'] for r in old['items'])
        old_ids.update(r['item_id'] for r in old['items'])
    for row in rows:
        source = base.source_path(row['rootfs'])
        volume = source.relative_to(RUN).parts[0]
        item_id = hashlib.sha256(str(source).encode()).hexdigest()[:24]
        if (row['historical_all_quiet'] is not True or row['historical_errors']
                or row['resource_released'] is not True
                or row['root_identity']['device'] != DEVICES[volume]
                or row['rootfs'] in old_sources or item_id in old_ids):
            raise ValueError('Allowlist crossed its exact terminal ownership or old plan scope')
    return value


def validate_plan(base, value):
    allowed = fixed_allowlist(base)
    if (value.get('namespace_wrapper') != base.ref(__file__)
            or value.get('source') != base.ref(ORIGINAL)
            or value.get('allowlist_source') != base.ref(ALLOWLIST)
            or value.get('version') != VERSION
            or len(value.get('items', [])) != COUNT
            or {r['rootfs'] for r in value['items']} != {r['rootfs'] for r in allowed['roots']}):
        raise ValueError('Plan does not bind this wrapper and the exact 51-item scope')
    if len({r['item_id'] for r in value['items']}) != COUNT:
        raise ValueError('Plan contains duplicate archive identities')
    for item in value['items']:
        root = base.source_path(item['rootfs'])
        expected_id = hashlib.sha256(str(root).encode()).hexdigest()[:24]
        volume = root.relative_to(RUN).parts[0]
        expected_payload = RUN / volume / 'terminal-rootfs-archive-r1' / expected_id
        if (item['item_id'] != expected_id or item['archive_directory'] != str(expected_payload)
                or item['root_identity']['device'] != DEVICES[volume]):
            raise ValueError('Plan crossed its exact source volume and registered device')
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
                     'archive_directory': str(RUN / root.relative_to(RUN).parts[0] / 'terminal-rootfs-archive-r1' / item_id),
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
             'payload_same_registered_source_filesystem_required': True,
             'old_63_and_primary_53_plans_and_receipts_not_modified': True,
             'registered_devices': DEVICES}
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
