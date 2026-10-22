"""Exact three-data-volume ext4 reservation adjustment with recorded rollback.

Only reserved-block count may be changed, from the observed 5% to 2%. Root and
other volumes are excluded. Plan and device UUID/geometry must match exactly.
No files are deleted, no mount is changed, and no task process is signalled.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
OUT = ROOT / 'runs/software-benchmark-v055/data-volume-reserve-r1'
VERSION = 'v055-exact-data-volume-root-reserve-r1'
DEVICES = (
    ('/data0', '/dev/nvme0n1p1', 66306, '042c9c16-c9a4-4e4c-84af-ec41ba28201b', 1875366225, 93768311),
    ('/data1', '/dev/nvme1n1p1', 66307, 'd4a715df-68ff-49df-b012-b9719f3a7843', 1875366144, 93768307),
    ('/data2', '/dev/nvme2n1', 66308, '022a620d-ec24-4872-89b7-91acb5165842', 1875366486, 93768324),
)


def now():
    return datetime.now(timezone.utc).isoformat()


def ref(path):
    data = Path(path).read_bytes()
    return {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def put(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    return ref(path)


def space(path):
    value = os.statvfs(path)
    return {'ordinary_available_bytes': value.f_bavail * value.f_frsize,
            'free_including_reserved_bytes': value.f_bfree * value.f_frsize,
            'fragment_bytes': value.f_frsize}


def read_volume(spec):
    mount, device, devnum, uuid, blocks, old = spec
    path = Path(mount)
    device_info = Path(device).stat()
    if not stat.S_ISBLK(device_info.st_mode) or device_info.st_rdev != devnum or path.stat().st_dev != devnum:
        raise ValueError('Exact data device and mounted filesystem identity must agree')
    if devnum == Path('/').stat().st_dev:
        raise ValueError('System root filesystem is never eligible')
    mounts = [line for line in Path('/proc/self/mountinfo').read_text().splitlines()
              if len(line.split()) > 5 and line.split()[4] == mount]
    if len(mounts) != 1:
        raise ValueError('Exact data mount is missing or ambiguous')
    left, right = mounts[0].split(' - ')
    fields = right.split()
    if fields[:2] != ['ext4', device] or left.split()[3] != '/' or 'rw' not in left.split()[5].split(','):
        raise ValueError('Only the exact writable ext4 data filesystem is eligible')
    result = subprocess.run(['sudo', '-n', '/usr/sbin/tune2fs', '-l', device], check=True,
                            capture_output=True, text=True, timeout=20,
                            env={**os.environ, 'LC_ALL': 'C'})
    values = dict((key.strip(), value.strip()) for line in result.stdout.splitlines()
                  if ':' in line for key, value in [line.split(':', 1)])
    if (values['Filesystem UUID'] != uuid or int(values['Block count']) != blocks
            or int(values['Block size']) != 4096 or values['Filesystem state'] != 'clean'
            or not values['Reserved blocks uid'].startswith('0 ')
            or not values['Reserved blocks gid'].startswith('0 ')):
        raise ValueError('Filesystem geometry, root reserve owner or clean-state identity changed')
    return {'observed_utc': now(), 'mount': mount, 'device': device, 'device_number': devnum,
            'uuid': uuid, 'blocks': blocks, 'block_bytes': 4096,
            'reserved_blocks': int(values['Reserved block count']),
            'mountinfo': mounts[0], 'space': space(mount),
            'tune2fs_stdout': result.stdout, 'tune2fs_stderr': result.stderr}


def make_plan():
    if os.getuid() != 1021 or os.geteuid() != 1021:
        raise PermissionError('Only the project owner prepares or executes this scoped plan')
    rows = []
    for spec in DEVICES:
        before = read_volume(spec)
        old = spec[-1]
        target = spec[-2] * 2 // 100
        if before['reserved_blocks'] != old or not 0 < target < old:
            raise ValueError('Reservation differs from the independently observed original 5%')
        rows.append({'before': before, 'old_reserved_blocks': old, 'target_reserved_blocks': target,
                     'target_percent': 2, 'expected_new_ordinary_available_bytes': (old-target)*4096,
                     'apply_argv': ['sudo', '-n', '/usr/sbin/tune2fs', '-r', str(target), spec[1]],
                     'rollback_argv': ['sudo', '-n', '/usr/sbin/tune2fs', '-r', str(old), spec[1]]})
    return put(OUT/'plan.json', {'version': VERSION, 'created_utc': now(), 'source': ref(__file__),
        'volumes': rows, 'filesystem_parameter_changed': 'reserved_block_count_only',
        'reserved_owner_uid_changed': False, 'project_100_128_GiB_floors_changed': False,
        'system_root_or_data3_changed': False, 'format_unmount_remount_fsck': False,
        'existing_files_moved_or_deleted': False, 'worker_or_GPU_signals': 0,
        'expected_total_new_ordinary_available_bytes': sum(r['expected_new_ordinary_available_bytes'] for r in rows),
        'authorization_basis': 'User authorized all necessary experiment resource operations and requested repeated disk/prewarm recovery; reversible data-volume setting only.'})


def load_plan(sha):
    current = ref(OUT/'plan.json')
    if current['sha256'] != sha:
        raise ValueError('Explicit fixed plan SHA is required')
    plan = json.loads((OUT/'plan.json').read_bytes())
    if plan['version'] != VERSION or plan['source'] != ref(__file__) or len(plan['volumes']) != len(DEVICES):
        raise ValueError('Fixed adjustment source or plan changed')
    for row, spec in zip(plan['volumes'], DEVICES):
        if (row['before']['device'] != spec[1] or row['before']['uuid'] != spec[3]
                or row['old_reserved_blocks'] != spec[-1]
                or row['target_reserved_blocks'] != spec[-2]*2//100
                or row['apply_argv'] != ['sudo', '-n', '/usr/sbin/tune2fs', '-r', str(spec[-2]*2//100), spec[1]]
                or row['rollback_argv'] != ['sudo', '-n', '/usr/sbin/tune2fs', '-r', str(spec[-1]), spec[1]]):
            raise ValueError('Device or exact reserved-block action escaped its fixed scope')
    return plan, current


def apply_one(sha, mount):
    if os.getuid() != 1021 or os.geteuid() != 1021:
        raise PermissionError('Only the project owner may coordinate the fixed sudo commands')
    plan, plan_ref = load_plan(sha)
    index = next((i for i, spec in enumerate(DEVICES) if spec[0] == mount), None)
    if index is None:
        raise ValueError('Only the three exact planned data volumes are eligible')
    spec, row = DEVICES[index], plan['volumes'][index]
    stem = mount.strip('/')
    with (OUT/'adjustment.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = read_volume(spec)
        if before['reserved_blocks'] != row['old_reserved_blocks']:
            raise ValueError('Reservation was already adjusted or changed externally; do not repeat')
        intent = put(OUT/(stem+'-intent.json'), {'utc': now(), 'plan': plan_ref, 'before': before,
            'argv': row['apply_argv'], 'rollback_argv': row['rollback_argv'], 'worker_signals': 0})
        result = subprocess.run(row['apply_argv'], capture_output=True, text=True, timeout=30,
                                env={**os.environ, 'LC_ALL': 'C'})
        after = read_volume(spec)
        actual = after['space']['ordinary_available_bytes']-before['space']['ordinary_available_bytes']
        concurrent_free = after['space']['free_including_reserved_bytes']-before['space']['free_including_reserved_bytes']
        attributed = actual-concurrent_free
        passed = (result.returncode == 0 and after['reserved_blocks'] == row['target_reserved_blocks']
                  and attributed == row['expected_new_ordinary_available_bytes'])
        receipt = put(OUT/(stem+'-applied.json'), {'utc': now(), 'plan': plan_ref, 'intent': intent,
            'command_returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
            'before': before, 'after': after, 'normal_available_delta_bytes': actual,
            'concurrent_physical_free_delta_bytes': concurrent_free,
            'attributed_available_capacity_increase_bytes': attributed,
            'expected_available_capacity_increase_bytes': row['expected_new_ordinary_available_bytes'],
            'passed': passed, 'rollback_argv': row['rollback_argv'], 'worker_or_GPU_signals': 0,
            'files_deleted_or_moved': 0, 'mount_remount_or_fsck_performed': False})
        if not passed:
            raise RuntimeError('Post-adjustment proof failed; inspect retained receipt before any further volume change')
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    sub.add_parser('plan')
    item = sub.add_parser('apply')
    item.add_argument('--plan-sha256', required=True)
    item.add_argument('--mount', required=True, choices=[x[0] for x in DEVICES])
    args = parser.parse_args()
    print(json.dumps(make_plan() if args.operation == 'plan' else apply_one(args.plan_sha256, args.mount)))


if __name__ == '__main__':
    main()
