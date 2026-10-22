"""Finite, evidence-bound lossless archive of terminal v055 exception rootfs.

Production entry points never default to scanning or deleting anything. A sealed
plan, exact item, exact implementation SHA and sudo owner are mandatory. Archive
and release are separate operations. The original unique workspace survives any
failed verification; no queue result, claim, candidate or bill is rewritten.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
RUN = ROOT / 'runs/software-benchmark-v055'
OUT = RUN / 'terminal-rootfs-archive-r1'
STATE = RUN / 'queue-r1/state.json'
VERSION = 'v055-terminal-rootfs-lossless-archive-r1'
CHUNK = 1024 * 1024
UID, GID = 1021, 1022
PATH_RE = re.compile(r'(?:queue-r1|secondary-volume-r1)/workers/generation-[a-f0-9]{24}/episode/(?:public-test-[0-9]+/)?actor/rootfs')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data := stream.read(CHUNK):
            h.update(data)
    return h.hexdigest()


def ref(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def checked(value):
    if ref(value['path']) != value:
        raise ValueError('Sealed evidence changed')
    return json.loads(Path(value['path']).read_bytes())


def put(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    with Path(path).open('xb') as stream:
        os.fchown(stream.fileno(), UID, GID)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_parent(path)
    return ref(path)


def new_directory(path, *, parents=False):
    path = Path(path)
    if parents and not path.parent.exists():
        new_directory(path.parent, parents=True)
    path.mkdir(mode=0o700, exist_ok=False)
    os.chown(path, UID, GID, follow_symlinks=False)


def archive_space_bound(rows):
    size = sum(r['size'] for r in rows.values() if r['type'] == 'file' and not r.get('hardlink_to'))
    return size + len(rows) * 8192 + 16 * 1024**2


def require_archive_space(rows, free_bytes):
    if free_bytes < archive_space_bound(rows) + 100 * 1024**3:
        raise RuntimeError('Archive lacks space for worst-case output plus 100 GiB recovery reserve')


def fsync_parent(path):
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def root_identity(path):
    st = Path(path).lstat()
    if not stat.S_ISDIR(st.st_mode) or Path(path).resolve() != Path(path):
        raise ValueError('Source root must be a real directory')
    return {'device': st.st_dev, 'inode': st.st_ino, 'mode': stat.S_IMODE(st.st_mode),
            'uid': st.st_uid, 'gid': st.st_gid, 'mtime_ns': st.st_mtime_ns,
            'ctime_ns': st.st_ctime_ns}


def source_path(path):
    path = Path(path)
    if not path.is_absolute() or not PATH_RE.fullmatch(str(path.relative_to(RUN))):
        raise ValueError('Rootfs escaped the exact generation clone path grammar')
    if path.resolve() != path or path.is_symlink():
        raise ValueError('Rootfs ancestors must not be symlinks')
    return path


def no_mounts(path):
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        value = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), line.split()[4])
        mount = Path(value)
        if mount == path or mount.is_relative_to(path):
            raise ValueError('A mounted filesystem prevents rootfs archival')


def current_row(slot):
    rows = [r for r in json.loads(STATE.read_bytes())['rows'] if r['slot']['slot_id'] == slot]
    if len(rows) != 1:
        raise ValueError('The original unique slot is missing')
    row = rows[0]
    scores = row['scores'].values() if isinstance(row['scores'], dict) else row['scores']
    if row['generation']['status'] != 'technical_unknown' or any(s['status'] not in {'official_report', 'technical_unknown'} for s in scores):
        raise ValueError('Only terminal exception generation with terminal scoring is eligible')
    return row


def row_sha(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_reader(plan):
    value = plan['quiescence_reader']
    if ref(value['path']) != value:
        raise ValueError('Frozen quiescence reader changed')
    spec = importlib.util.spec_from_file_location('pws_terminal_archive_quiet', value['path'])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_quiet(plan, item):
    root = source_path(item['rootfs'])
    if root_identity(root) != item['root_identity']:
        raise ValueError('The planned root directory identity changed')
    row = current_row(item['slot_id'])
    if row_sha(row) != item['row_sha256']:
        raise ValueError('Original terminal queue projection changed')
    if Path(row['generation']['directory']) != Path(item['episode_root']).parent:
        raise ValueError('Generation directory differs from planned episode')
    for evidence in item['retained_evidence']:
        if Path(evidence['path']).is_relative_to(root):
            raise ValueError('Retained evidence cannot be inside the rootfs')
        checked(evidence)
    manifest = checked(item['rootfs_manifest'])
    if manifest.get('prepared_root') != str(root):
        raise ValueError('Manifest does not bind this clone')
    quiet = checked(item['quiescence'])
    if quiet.get('all_quiet') is not True or quiet.get('errors') or not quiet.get('scopes'):
        raise ValueError('Historical complete writer quiescence is unproven')
    result = checked(item['result'])
    if result.get('resource_release', {}).get('released') is not True:
        raise ValueError('Original episode resource release is missing')
    reader = load_reader(plan)
    jobs = [row['generation']['unit']]
    scores = row['scores'].values() if isinstance(row['scores'], dict) else row['scores']
    jobs += [s['unit'] for s in scores if s.get('unit')]
    observed = reader.system_show(jobs, 'user')
    if any(x.get('MainPID') != '0' or x.get('ActiveState') not in {'inactive', 'failed'} for x in observed.values()):
        raise RuntimeError('Original generation or scoring worker is active')
    scopes = quiet['scopes']
    scope_states = {}
    for manager in ('user', 'system'):
        units = [s['unit'] for s in scopes if s.get('manager', 'user') == manager]
        scope_states.update(reader.system_show(units, manager))
    for scope in scopes:
        actual = scope_states[scope['unit']]
        if (actual.get('ActiveState') not in {'inactive', 'failed'} or actual.get('MainPID') != '0'
                or actual.get('InvocationID') not in ('', scope['invocation_id'])
                or actual.get('ControlGroup') not in ('', scope['cgroup'])
                or reader.populated(scope['cgroup'])):
            raise RuntimeError('A registered scope is active or has changed identity')
        for key in ('main', 'outer_launcher'):
            if reader.process_identity(scope[key]['pid']) == scope[key]:
                raise RuntimeError('A registered process is still alive')
    resource = checked(item['resource_slice'])
    group = resource['cgroup']
    if not re.fullmatch(r'/proworksimv054ep[a-f0-9]{32}\.slice', group):
        raise ValueError('Unknown resource slice')
    events = Path('/sys/fs/cgroup' + group) / 'cgroup.events'
    if events.exists() and dict(x.split() for x in events.read_text().splitlines()).get('populated') != '0':
        raise RuntimeError('Episode descendant slice remains populated')
    no_mounts(root)
    return {'observed_unix': time.time(), 'row_sha256': item['row_sha256'],
            'all_registered_workers_scopes_and_slice_quiet': True, 'no_rootfs_mounts': True}


@contextmanager
def claim_lock(item):
    path = Path(item['quiescence']['path']).parent / 'scope-registry.lock'
    if path.resolve() != path or not path.is_relative_to(RUN / 'episode-claims'):
        raise ValueError('Claim lock escaped the original registry')
    with path.open('r+b') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def extents(path, size):
    result, offset = [], 0
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        while offset < size:
            try:
                start = os.lseek(fd, offset, os.SEEK_DATA)
            except OSError as error:
                if error.errno == 6:
                    break
                raise
            end = min(os.lseek(fd, start, os.SEEK_HOLE), size)
            result.append([start, end - start])
            offset = end
    finally:
        os.close(fd)
    return result


def metadata(path):
    st = path.lstat()
    kind = 'dir' if stat.S_ISDIR(st.st_mode) else 'file' if stat.S_ISREG(st.st_mode) else 'symlink' if stat.S_ISLNK(st.st_mode) else None
    if kind is None:
        raise ValueError('Unsupported special filesystem node: ' + str(path))
    value = {'type': kind, 'mode': stat.S_IMODE(st.st_mode), 'uid': st.st_uid, 'gid': st.st_gid,
             'mtime_ns': st.st_mtime_ns, 'ctime_ns': st.st_ctime_ns, 'dev': st.st_dev,
             'ino': st.st_ino, 'nlink': st.st_nlink, 'size': st.st_size,
             'allocated_bytes': st.st_blocks * 512,
             'xattrs': {name: base64.b64encode(os.getxattr(path, name, follow_symlinks=False)).decode()
                        for name in sorted(os.listxattr(path, follow_symlinks=False))}}
    if kind == 'symlink':
        value['target'] = os.readlink(path)
    return value


def inventory(root, *, include_content):
    rows, hard = {}, {}
    root_dev = root.lstat().st_dev
    stack = [root]
    while stack:
        path = stack.pop()
        before = metadata(path)
        if before['dev'] != root_dev:
            raise ValueError('A filesystem boundary exists inside the source')
        name = 'rootfs' if path == root else 'rootfs/' + str(path.relative_to(root))
        if before['type'] == 'dir':
            stack.extend(sorted(path.iterdir(), reverse=True))
        if before['type'] == 'file':
            key = (before['dev'], before['ino'])
            if key in hard:
                before['hardlink_to'] = hard[key]
            else:
                hard[key] = name
                if include_content:
                    before['sha256'] = sha(path)
                    before['data_extents'] = extents(path, before['size'])
        after = metadata(path)
        if any(before[k] != after[k] for k in after):
            raise RuntimeError('Source changed during inventory')
        rows[name] = before
    counts = Counter((r['dev'], r['ino']) for r in rows.values() if r['type'] == 'file')
    if any(r['nlink'] != counts[(r['dev'], r['ino'])] for r in rows.values() if r['type'] == 'file'):
        raise ValueError('A regular file has a hardlink outside this unique rootfs')
    return rows


def unchanged(root, rows):
    current = inventory(root, include_content=False)
    expected = {n: {k: v for k, v in r.items() if k not in {'sha256', 'data_extents'}} for n, r in rows.items()}
    if current != expected:
        raise RuntimeError('Full source membership or metadata changed; retain original')


def encode(root, archive, stderr):
    with archive.open('xb') as output, stderr.open('xb') as errors:
        os.fchown(output.fileno(), UID, GID)
        os.fchown(errors.fileno(), UID, GID)
        tar = subprocess.Popen(['/usr/bin/tar', '--format=pax', '--acls', '--xattrs', '--xattrs-include=*',
                                '--sparse', '--numeric-owner', '--sort=name', '-cf', '-', '-C', str(root.parent), root.name],
                               stdout=subprocess.PIPE, stderr=errors)
        zstd = subprocess.Popen(['/usr/bin/zstd', '-q', '-1', '-T1', '-c'], stdin=tar.stdout, stdout=output, stderr=errors)
        tar.stdout.close()
        zcode, tcode = zstd.wait(), tar.wait()
        output.flush()
        os.fsync(output.fileno())
    if zcode or tcode:
        raise RuntimeError('Tar or compression failed; preserve partial archive and original')


def verify(archive, rows):
    seen = set()
    decoder = subprocess.Popen(['/usr/bin/zstd', '-q', '-dc', str(archive)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=decoder.stdout, mode='r|', encoding='utf-8', errors='surrogateescape') as stream:
            for member in stream:
                name = member.name.rstrip('/')
                if name not in rows or name in seen:
                    raise ValueError('Archive has an unexpected or duplicate member')
                seen.add(name)
                expected = rows[name]
                kind = 'dir' if member.isdir() else 'symlink' if member.issym() else 'file' if member.isfile() or member.islnk() else None
                actual = {'type': kind, 'mode': member.mode, 'uid': member.uid, 'gid': member.gid,
                          'mtime_ns': int(Decimal(member.pax_headers.get('mtime', str(member.mtime))) * 10**9)}
                if any(actual[k] != expected[k] for k in actual):
                    raise ValueError('Archive type/uid/gid/mode/nanosecond mtime differs: ' + name)
                if member.islnk():
                    if member.linkname != expected.get('hardlink_to') or member.linkname not in seen:
                        raise ValueError('Archive hardlink topology differs')
                    target = rows[member.linkname]
                    if target['xattrs'] != expected['xattrs']:
                        raise ValueError('Hardlink xattrs differ')
                    continue
                actual_xattrs = {k[len('SCHILY.xattr.'):]: base64.b64encode(v.encode('utf-8', 'surrogateescape')).decode()
                                 for k, v in member.pax_headers.items() if k.startswith('SCHILY.xattr.')}
                if actual_xattrs != expected['xattrs']:
                    raise ValueError('Archive xattr/ACL raw bytes differ: ' + name)
                if kind == 'symlink' and member.linkname != expected['target']:
                    raise ValueError('Archive symlink target differs')
                if kind == 'file':
                    if expected.get('hardlink_to') or member.size != expected['size']:
                        raise ValueError('Archive regular file size/topology differs')
                    h = hashlib.sha256()
                    data_stream = stream.extractfile(member)
                    while data := data_stream.read(CHUNK):
                        h.update(data)
                    if h.hexdigest() != expected['sha256']:
                        raise ValueError('Full archive content readback differs: ' + name)
                    if member.sparse is not None:
                        if [list(x) for x in member.sparse if x[1]] != expected['data_extents']:
                            raise ValueError('Archive sparse extent map differs: ' + name)
                    elif sum(x[1] for x in expected['data_extents']) < expected['size']:
                        raise ValueError('Archive lost source sparse holes: ' + name)
        # Consume the complete compression frame, including tar padding.
        while decoder.stdout.read(CHUNK):
            pass
        stderr = decoder.stderr.read()
        if decoder.wait() or stderr:
            raise ValueError('Archive decompressor did not close cleanly')
    finally:
        decoder.stdout.close()
        decoder.stderr.close()
        if decoder.poll() is None:
            decoder.kill()
            decoder.wait()
    if seen != set(rows):
        raise ValueError('Archive is missing source members')
    return {'full_decompression_content_and_metadata_verified': True, 'members': len(seen),
            'verified_fields': ['membership', 'sha256', 'uid', 'gid', 'mode', 'mtime_ns',
                                'symlink_target', 'hardlink_topology', 'xattrs_including_raw_ACL', 'sparse_extents']}


def plan(allowlist, expected_sha):
    if sha(allowlist) != expected_sha:
        raise ValueError('Read-only allowlist seal differs')
    data = json.loads(Path(allowlist).read_bytes())
    rows, excluded = [], []
    for item in data['roots']:
        if not item.get('historical_all_quiet') or item.get('historical_errors'):
            excluded.append({'rootfs': item['rootfs'], 'reason': 'historical_quiescence_incomplete'})
            continue
        root = source_path(item['rootfs'])
        row = current_row(item['slot_id'])
        claim = Path(item['quiescence']['path']).parent
        refs = [ref(claim / name) for name in ('claim.json', 'entered.json', 'state.json', 'scope-registry.json', 'quiescence.json')]
        refs += [item['result'], item['resource_slice'], ref(item['rootfs_manifest_path'])]
        item_id = hashlib.sha256(str(root).encode()).hexdigest()[:24]
        volume = root.relative_to(RUN).parts[0]
        archive_directory = RUN / volume / 'terminal-rootfs-archive-r1' / item_id
        rows.append({**{k: item[k] for k in ('slot_id', 'rootfs', 'episode_root', 'result', 'quiescence', 'resource_slice')},
                     'item_id': item_id, 'archive_directory': str(archive_directory),
                     'root_identity': root_identity(root), 'row_sha256': row_sha(row),
                     'rootfs_manifest': ref(item['rootfs_manifest_path']), 'retained_evidence': refs})
    if not rows or len({r['rootfs'] for r in rows}) != len(rows):
        raise ValueError('Plan must have a nonempty exact unique allowlist')
    new_directory(OUT)
    return put(OUT / 'plan.json', {'version': VERSION, 'created_unix': time.time(), 'source': ref(__file__),
        'allowlist_source': ref(allowlist), 'items': rows, 'excluded': excluded,
        'quiescence_reader': ref(ROOT / 'tools/reclaim_benchmark_cache_v055_r1.py'),
        'codec': 'GNU-pax-tar+zstd-level1', 'archive_and_release_separate': True,
        'resources_per_worker': {'CPUQuota': '200%', 'MemoryMax': '2G', 'IOWeight': '10', 'Nice': '10'},
        'maximum_parallel_workers': 2, 'model_calls': 0, 'original_experiment_records_modified': False})


def load_plan(path, expected_sha, source_sha):
    if os.geteuid() != 0 or os.environ.get('SUDO_UID') != str(UID):
        raise PermissionError('Only the registered project owner may invoke this finite privileged helper')
    if Path(path) != OUT / 'plan.json' or Path(__file__).resolve() != ROOT / 'tools/archive_terminal_rootfs_v055_r1.py':
        raise ValueError('Only the explicit production plan and implementation are accepted')
    if sha(path) != expected_sha or sha(__file__) != source_sha:
        raise ValueError('Plan or source SHA changed')
    value = json.loads(Path(path).read_bytes())
    if value['version'] != VERSION or value['source'] != ref(__file__):
        raise ValueError('Plan does not bind this implementation')
    return value


def read_inventory(directory, proof):
    if ref(directory / 'members.json.gz') != proof['source_members']:
        raise ValueError('Member inventory changed')
    with gzip.open(directory / 'members.json.gz', 'rt') as stream:
        return json.load(stream)


def archive_one(plan_value, item):
    root = source_path(item['rootfs'])
    directory = OUT / item['item_id']
    with claim_lock(item):
        quiet_before = live_quiet(plan_value, item)
        new_directory(directory)
        payload_directory = Path(item['archive_directory'])
        expected_parent = RUN / root.relative_to(RUN).parts[0] / 'terminal-rootfs-archive-r1'
        if payload_directory != expected_parent / item['item_id'] or payload_directory.resolve() != payload_directory:
            raise ValueError('Payload archive escaped its registered source volume')
        new_directory(payload_directory, parents=True)
        if payload_directory.stat().st_dev != root.stat().st_dev:
            raise ValueError('Archive payload must stay on the same real filesystem as the source')
        rows = inventory(root, include_content=True)
        # A compression failure must not consume the filesystem's last blocks.
        # Bound by the uncompressed unique file sizes plus generous pax headers;
        # sparse sources make this conservative rather than optimistic.
        require_archive_space(rows, shutil.disk_usage(payload_directory).free)
        with gzip.open(directory / 'members.json.gz', 'xt', compresslevel=1) as stream:
            os.chown(directory / 'members.json.gz', UID, GID, follow_symlinks=False)
            json.dump(rows, stream, sort_keys=True, separators=(',', ':'))
        encoded = payload_directory / 'rootfs.tar.zst'
        encode(root, encoded, directory / 'encode.stderr')
        proof = verify(encoded, rows)
        unchanged(root, rows)
        quiet_after = live_quiet(plan_value, item)
        return put(directory / 'verified.json', {'version': VERSION, 'item_id': item['item_id'],
            'original_rootfs': item['rootfs'], 'original_root_identity': item['root_identity'],
            'plan': ref(OUT / 'plan.json'), 'source_members': ref(directory / 'members.json.gz'),
            'archive': ref(encoded), 'verification': proof, 'quiet_before': quiet_before, 'quiet_after': quiet_after,
            'source_allocated_bytes': sum(x['allocated_bytes'] for x in rows.values() if not x.get('hardlink_to')),
            'verified_unix': time.time(), 'source_retained': True})


def release_one(plan_value, item):
    root = source_path(item['rootfs'])
    directory = OUT / item['item_id']
    proof = json.loads((directory / 'verified.json').read_bytes())
    if proof['plan'] != ref(OUT / 'plan.json') or proof['original_rootfs'] != str(root) or not proof['verification']['full_decompression_content_and_metadata_verified']:
        raise ValueError('Release requires the exact successful archive proof')
    if ref(proof['archive']['path']) != proof['archive']:
        raise ValueError('Verified compressed archive changed before release')
    rows = read_inventory(directory, proof)
    with claim_lock(item):
        quiet = live_quiet(plan_value, item)
        unchanged(root, rows)
        marker = root.with_name('rootfs.lossless-archive-r1.json')
        marker_ref = put(marker, {'version': VERSION, 'original_rootfs': str(root),
            'archive_verification': ref(directory / 'verified.json'), 'plan': ref(OUT / 'plan.json'),
            'default_restore_directory': str(directory / 'restored'), 'new_directory_restore_only': True,
            'original_experiment_status_unchanged': True})
        if not shutil.rmtree.avoids_symlink_attacks:
            raise RuntimeError('Safe descriptor-based recursive removal is unavailable')
        # Whole-tree stat/xattr equality and live quiescence above precede release;
        # keep the original registry lock until the sole expanded copy is gone.
        if root_identity(root) != item['root_identity']:
            raise ValueError('Root identity changed immediately before release')
        shutil.rmtree(root)
        fsync_parent(root)
        return put(directory / 'released.json', {'version': VERSION, 'released_unix': time.time(),
            'rootfs_removed': not root.exists(), 'original_rootfs': str(root), 'archive': proof['archive'],
            'verification': ref(directory / 'verified.json'), 'restore_marker': marker_ref, 'fresh_quiescence': quiet,
            'source_allocated_bytes': proof['source_allocated_bytes'], 'compressed_bytes': proof['archive']['bytes'],
            'experimental_records_modified': False})


def restore_one(plan_value, item, destination):
    directory = OUT / item['item_id']
    destination = Path(destination) if destination else directory / 'restored'
    if not destination.is_absolute() or destination.resolve() != destination or not destination.is_relative_to(OUT):
        raise ValueError('Restore is restricted to a new directory inside this archive area')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Restore never overwrites an existing directory')
    proof = json.loads((directory / 'verified.json').read_bytes())
    if proof['plan'] != ref(OUT / 'plan.json') or ref(proof['archive']['path']) != proof['archive']:
        raise ValueError('Restore archive identity differs')
    rows = read_inventory(directory, proof)
    new_directory(destination, parents=True)
    subprocess.run(['/usr/bin/tar', '--zstd', '--extract', '--file', proof['archive']['path'], '--directory', str(destination),
                    '--numeric-owner', '--same-owner', '--same-permissions', '--acls', '--xattrs', '--xattrs-include=*',
                    '--sparse', '--keep-old-files'], check=True)
    actual = inventory(destination / 'rootfs', include_content=True)
    def portable(value):
        return {n: {k: v for k, v in r.items() if k not in {'dev', 'ino', 'ctime_ns', 'allocated_bytes', 'size'}
                    or (k == 'size' and r['type'] == 'file')} for n, r in value.items()}
    if portable(actual) != portable(rows):
        raise ValueError('Restored complete content or metadata differs; retain failed restore for diagnosis')
    return put(destination / 'restore-receipt.json', {'version': VERSION, 'restored_unix': time.time(),
        'original_rootfs': item['rootfs'], 'restored_rootfs': str(destination / 'rootfs'),
        'archive': proof['archive'], 'full_restored_tree_verified': True, 'old_records_modified': False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    p = commands.add_parser('plan')
    p.add_argument('--allowlist', required=True, type=Path)
    p.add_argument('--sha256', required=True)
    for operation in ('archive', 'release', 'restore'):
        p = commands.add_parser(operation)
        p.add_argument('--plan', required=True, type=Path)
        p.add_argument('--sha256', required=True)
        p.add_argument('--source-sha256', required=True)
        p.add_argument('--item-id', required=True)
        if operation == 'restore':
            p.add_argument('--destination', type=Path)
    args = parser.parse_args()
    if args.operation == 'plan':
        print(json.dumps(plan(args.allowlist, args.sha256)))
        return
    value = load_plan(args.plan, args.sha256, args.source_sha256)
    matching = [x for x in value['items'] if x['item_id'] == args.item_id]
    if len(matching) != 1:
        raise ValueError('The exact item must be in the sealed allowlist')
    item = matching[0]
    if args.operation == 'archive':
        result = archive_one(value, item)
    elif args.operation == 'release':
        result = release_one(value, item)
    else:
        result = restore_one(value, item, args.destination)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
