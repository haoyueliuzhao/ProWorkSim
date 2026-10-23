"""Exact three-root archive adapter and one terminal astropy template reclaim.

The proven archive codec and descriptor-safe releaser are reused unchanged.
Only the recovery namespace, manager routing and sealed terminal projection are
adapted. No generic scan or arbitrary deletion path is accepted.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
RUN = ROOT / 'runs/software-benchmark-v055'
RECOVERY = RUN / 'pre-entry-recovery-r1'
OUT = RECOVERY / 'cleanup-r1'
ARCHIVE = OUT / 'archives'
SOURCE = ROOT / 'tools/archive_terminal_rootfs_v055_r1.py'
SOURCE_SHA = 'a1929b16a0deb0884e08ea66b542451d7bd8780ef6a6e936fd47a1661b233e13'
RECOVERY_SHA = 'b5be9b6a9fa502b3c3606520495a15f491bcefc8982074026e2d8543704b8013'
SUMMARY_SHA = '388e7e4968b84e58749b59dac45c74e799d66a234b0f3180bf1d2b88efc3933a'
READER = ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'
INSTANCE = 'astropy__astropy-12907'
VERSION = 'v055-preentry-terminal-rootfs-archive-r1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path, name, sha=None):
    if sha is not None and digest(path) != sha:
        raise ValueError('Frozen cleanup dependency changed')
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def recovery():
    if digest(RECOVERY / 'plan.json') != RECOVERY_SHA or digest(RECOVERY / 'first-scoring/summary.json') != SUMMARY_SHA:
        raise ValueError('Only the fixed completed six-slot recovery is eligible')
    plan = json.loads((RECOVERY / 'plan.json').read_bytes())
    summary = json.loads((RECOVERY / 'first-scoring/summary.json').read_bytes())
    if (len(plan['slots']) != 6 or summary['generation_terminal'] != 6
            or summary['scoring_endpoints_terminal'] != 3
            or summary['scoring_endpoints_created'] != 3):
        raise ValueError('Recovery generation/scoring is not fully terminal')
    return plan, summary


def terminal_rows():
    plan, summary = recovery()
    results = {row['slot_id']: row for row in summary['generation_rows']}
    rows = {}
    for slot in plan['slots']:
        generation = results[slot['slot_id']]
        if generation['status'] != 'technical_unknown':
            continue
        claim = json.loads(Path(slot['original_claim']['path']).read_bytes())
        rows[slot['slot_id']] = {'slot': claim['slot'], 'generation': {
            'status': 'technical_unknown', 'directory': str(Path(slot['output_directory']).parent),
            'unit': f'proworksim-v055-preentry-recovery-r1-{slot["slot_index"]}.service',
            'result': generation['result']}, 'scores': []}
    if len(rows) != 3:
        raise ValueError('Exactly the three fixed unknown roots are admitted')
    return rows


def show_quiet(reader, units, manager):
    values = reader.system_show(units, manager)
    for value in values.values():
        if value.get('MainPID') != '0' or value.get('ActiveState') not in ('inactive', 'failed'):
            raise RuntimeError('A fixed original/recovery worker is not quiet')
        group = value.get('ControlGroup', '')
        if group:
            events = Path('/sys/fs/cgroup' + group) / 'cgroup.events'
            if events.exists() and 'populated 1' in events.read_text():
                raise RuntimeError('A fixed worker descendant cgroup remains populated')
    return values


def all_recovery_quiet(reader):
    plan, summary = recovery()
    old_units, new_units = [], []
    for slot in plan['slots']:
        job = reader.checked(slot['original_job'])
        reader.checked(slot['original_claim'])
        state = reader.checked(slot['original_claim_state'])
        if state.get('entered') is not False or state.get('phase') != 'claimed':
            raise ValueError('Original zero-model claim changed')
        old_units.append(job['unit'])
        new_units.append(f'proworksim-v055-preentry-recovery-r1-{slot["slot_index"]}.service')
    new_units.append('proworksim-v055-preentry-first-scoring-r1.service')
    observed = {'old_units': show_quiet(reader, old_units, 'user'),
                'recovery_units': show_quiet(reader, new_units, 'system')}
    locks = [RECOVERY / 'first-scoring/driver.lock']
    locks += list((RECOVERY / 'first-scoring/endpoints').glob('*/attempt.lock'))
    if len(locks) != 4:
        raise ValueError('Expected first-score driver plus three completed endpoint locks')
    import fcntl
    with ExitStack() as stack:
        for path in locks:
            stream = stack.enter_context(path.open('r+b'))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    observed['four_owned_scoring_locks_observed_unheld'] = True
    observed['original_claims_unchanged'] = True
    return observed


def engine():
    base = load_module(SOURCE, 'preentry_archive_base', SOURCE_SHA)
    base.OUT, base.VERSION = ARCHIVE, VERSION
    base.PATH_RE = re.compile(r'pre-entry-recovery-r1/workers/[a-f0-9]{24}/episode/actor/rootfs')
    rows = terminal_rows()
    permitted = {str(Path(row['generation']['directory']) / 'episode/actor/rootfs') for row in rows.values()}
    old_source_path, old_live, old_reader = base.source_path, base.live_quiet, base.load_reader
    def source_path(path):
        value = old_source_path(path)
        if str(value) not in permitted:
            raise ValueError('Path is not one of the fixed three recovery roots')
        return value
    def current_row(slot):
        current = terminal_rows()
        if slot not in current:
            raise ValueError('Slot is outside the fixed three terminal unknowns')
        return current[slot]
    @contextmanager
    def claim_lock(item):
        import fcntl
        sid_hash = hashlib.sha256(item['slot_id'].encode()).hexdigest()
        expected = RECOVERY / 'episode-claims' / sid_hash / 'scope-registry.lock'
        if Path(item['quiescence']['path']).parent / 'scope-registry.lock' != expected or expected.resolve() != expected:
            raise ValueError('Recovery registry lock identity differs')
        with (RECOVERY / (sid_hash + '.lock')).open('r+b') as worker, expected.open('r+b') as scope:
            fcntl.flock(worker, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(scope, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
    def load_reader(plan):
        reader = old_reader(plan)
        old_show = reader.system_show
        fixed_system_units = {row['generation']['unit'] for row in rows.values()}
        def show(units, manager='user'):
            if manager == 'user' and set(units) & fixed_system_units:
                system = [unit for unit in units if unit in fixed_system_units]
                user = [unit for unit in units if unit not in fixed_system_units]
                return {**old_show(system, 'system'), **old_show(user, 'user')}
            return old_show(units, manager)
        reader.system_show = show
        return reader
    def live_quiet(plan, item):
        observation = old_live(plan, item)
        # The metadata reader itself stays unchanged; only exact new system
        # unit routing above is different from old user generation units.
        reader = old_reader(plan)
        observation['whole_recovery_terminal_quiet'] = all_recovery_quiet(reader)
        return observation
    base.source_path, base.current_row, base.claim_lock = source_path, current_row, claim_lock
    base.load_reader, base.live_quiet = load_reader, live_quiet
    return base


def prepare(base):
    OUT.mkdir(parents=True, exist_ok=True)
    items = []
    for sid, row in terminal_rows().items():
        episode = Path(row['generation']['directory']) / 'episode'
        root = base.source_path(episode / 'actor/rootfs')
        claim = RECOVERY / 'episode-claims' / hashlib.sha256(sid.encode()).hexdigest()
        refs = [base.ref(claim / name) for name in ('claim.json', 'entered.json', 'state.json', 'scope-registry.json', 'quiescence.json')]
        result = base.ref(episode / 'result.json')
        resource = base.ref(episode / 'resource-slice.json')
        manifest = base.ref(episode / 'actor/rootfs-manifest.json')
        refs += [result, resource, manifest]
        item_id = hashlib.sha256(str(root).encode()).hexdigest()[:24]
        items.append({'slot_id': sid, 'rootfs': str(root), 'episode_root': str(episode),
            'result': result, 'quiescence': base.ref(claim / 'quiescence.json'), 'resource_slice': resource,
            'item_id': item_id, 'archive_directory': str(RECOVERY / 'terminal-rootfs-archive-r1' / item_id),
            'root_identity': base.root_identity(root), 'row_sha256': base.row_sha(row),
            'rootfs_manifest': manifest, 'retained_evidence': refs})
    value = {'version': VERSION, 'created_unix': time.time(), 'source': base.ref(SOURCE),
        'namespace_wrapper': base.ref(__file__), 'items': items, 'excluded': [],
        'recovery_plan': base.ref(RECOVERY / 'plan.json'), 'recovery_final_summary': base.ref(RECOVERY / 'first-scoring/summary.json'),
        'quiescence_reader': base.ref(READER), 'codec': 'GNU-pax-tar+zstd-level1',
        'maximum_parallel_workers': 2, 'model_calls': 0, 'original_experiment_records_modified': False,
        'all_rootfs_paths_fixed_to_three_new_recovery_unknowns': True}
    base.new_directory(ARCHIVE)
    return base.put(ARCHIVE / 'plan.json', value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('plan', 'preflight', 'archive', 'release', 'restore'))
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--item-id')
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    if digest(__file__) != args.source_sha256:
        raise ValueError('Explicit independent wrapper source seal required')
    base = engine()
    if args.operation == 'plan':
        print(json.dumps(prepare(base)))
        return
    value = base.load_plan(ARCHIVE / 'plan.json', args.plan_sha256, SOURCE_SHA)
    if value.get('namespace_wrapper') != base.ref(__file__) or len(value['items']) != 3:
        raise ValueError('Archive plan crossed the exact new namespace')
    if args.operation == 'preflight':
        observations = []
        for item in value['items']:
            with base.claim_lock(item):
                observations.append({'item_id': item['item_id'], **base.live_quiet(value, item)})
        print(json.dumps({'plan': base.ref(ARCHIVE / 'plan.json'), 'observations': observations, 'model_calls': 0, 'signals': 0}))
        return
    item = next(item for item in value['items'] if item['item_id'] == args.item_id)
    if args.operation == 'archive':
        result = base.archive_one(value, item)
    elif args.operation == 'release':
        result = base.release_one(value, item)
    else:
        result = base.restore_one(value, item, args.destination)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
