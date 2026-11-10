"""Losslessly archive large, quiescent v055 world snapshots as the ordinary owner.

This never touches current experiments, candidate trees, API records, scores,
containers, mounts, services, or rootfs. Originals are released only after a
complete archive readback. Archived members can be restored individually.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
VOLUME = ROOT / 'runs/software-benchmark-v055/secondary-volume-r1'
WORKERS = VOLUME / 'workers'
OUT = VOLUME / 'completed-world-archives-v194'
ART = ROOT / 'artifacts/software-benchmark-v194/history-archive-r1'
PLAN = ART / 'plan.json'
GIB = 1024**3
VERSION = 'v194-owner-only-completed-world-snapshot-archive-r1'


def digest_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest_file(path), 'bytes': path.stat().st_size}


def checked(value):
    path = Path(value['path'])
    if ref(path) != value:
        raise ValueError('Retained source identity changed: ' + str(path))
    return path


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return ref(path)


def progress(value):
    path = ART / 'progress.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temp, path)


def identity(path):
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
        raise ValueError('Only individually owned regular snapshot files may be archived')
    if os.listxattr(path, follow_symlinks=False):
        raise ValueError('Extended metadata needs a different archival protocol')
    return {k: v for k, v in {
        'size': s.st_size, 'allocated': s.st_blocks*512, 'dev': s.st_dev,
        'ino': s.st_ino, 'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid,
        'gid': s.st_gid, 'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns,
    }.items()}


def member_path(root, relative):
    path = root / relative
    if path.resolve() != path or not path.is_relative_to(root) or '..' in Path(relative).parts:
        raise ValueError('Snapshot path escaped its exact historical world')
    return path


def unchanged(root, rows):
    for row in rows:
        actual = identity(member_path(root, row['relative']))
        if any(actual[k] != row[k] for k in actual):
            raise ValueError('Snapshot changed after preparation: ' + row['relative'])


def quiet(item):
    if os.geteuid() == 0 or os.getuid() == 0:
        raise PermissionError('This archive must never run as root')
    root = Path(item['path'])
    if (root.resolve() != root or root.parent.name != 'episode'
            or root.name != 'managed-world' or root.parent.parent.parent != WORKERS):
        raise ValueError('Only the declared historical v055 world directories are allowed')
    result = json.loads(checked(item['result']).read_bytes())
    q = json.loads(checked(item['quiescence']).read_bytes())
    if (result.get('status') != 'closed' or not q.get('all_quiet')
            or result['resource_release'].get('populated') is not False
            or result['resource_release'].get('released') is not True):
        raise ValueError('Historical episode is not closed and quiescent')
    slice_path = Path('/sys/fs/cgroup') / item['slice']
    if slice_path.exists():
        events = dict(x.split() for x in (slice_path / 'cgroup.events').read_text().splitlines())
        if events.get('populated') != '0':
            raise ValueError('Historical resource group still has processes')
    for mount_file in (Path('/proc/self/mountinfo'), Path('/proc/1/mountinfo')):
        for line in mount_file.read_text().splitlines():
            target = Path(line.split()[4].replace('\\040', ' '))
            if target == root or target.is_relative_to(root):
                raise ValueError('A mounted filesystem is not archive input')
    for protected in item['protected']:
        checked(protected)
    return root


class HashReader:
    def __init__(self, stream):
        self.stream = stream; self.hash = hashlib.sha256()
    def read(self, amount=-1):
        raw = self.stream.read(amount); self.hash.update(raw); return raw


def encode(root, rows, directory, *, disk_floor=100*GIB):
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory / 'snapshots.tar.zst'
    manifest = []
    with archive.open('xb') as output, (directory / 'compression.stderr').open('xb') as error:
        process = subprocess.Popen(['/usr/bin/zstd', '-q', '-3', '--long=29', '-T1', '-c'],
            stdin=subprocess.PIPE, stdout=output, stderr=error)
        try:
            with tarfile.open(fileobj=process.stdin, mode='w|', format=tarfile.PAX_FORMAT) as tar:
                for row in rows:
                    if shutil.disk_usage(root).free < disk_floor + row['size'] + 16*1024**2:
                        raise RuntimeError('Archival cannot consume the filesystem safety reserve')
                    unchanged(root, [row])
                    path = member_path(root, row['relative'])
                    info = tarfile.TarInfo(row['relative']); info.size = row['size']
                    info.mode, info.uid, info.gid = row['mode'], row['uid'], row['gid']
                    ns = row['mtime_ns']; info.mtime = ns//10**9
                    info.pax_headers['mtime'] = f'{ns//10**9}.{ns%10**9:09d}'
                    with path.open('rb') as source:
                        reader = HashReader(source); tar.addfile(info, reader)
                    unchanged(root, [row])
                    manifest.append({**row, 'sha256': reader.hash.hexdigest()})
            process.stdin.close()
            if process.wait(timeout=120):
                raise RuntimeError('Snapshot compression failed; originals retained')
            output.flush(); os.fsync(output.fileno())
        except BaseException:
            process.stdin.close()
            if process.poll() is None:
                process.terminate(); process.wait(timeout=15)
            raise
    return archive, manifest


def verify(archive, manifest):
    expected = {r['relative']: r for r in manifest}; seen = set()
    process = subprocess.Popen(['/usr/bin/zstd', '-q', '--long=29', '-dc', str(archive)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as tar:
            for member in tar:
                if not member.isfile() or member.name not in expected or member.name in seen:
                    raise ValueError('Unexpected archive member')
                row = expected[member.name]
                if (member.size, member.mode, member.uid, member.gid) != (row['size'], row['mode'], row['uid'], row['gid']):
                    raise ValueError('Archived metadata differs')
                stream = tar.extractfile(member)
                if hashlib.file_digest(stream, 'sha256').hexdigest() != row['sha256']:
                    raise ValueError('Full archive readback differs')
                seen.add(member.name)
        while process.stdout.read(1024**2):
            pass
        if process.wait(timeout=30) or seen != set(expected):
            raise ValueError('Archive frame or member set is incomplete')
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=15)
    return {'full_decompression_and_all_file_hashes_verified': True, 'files': len(seen)}


def release(root, manifest):
    # Check the complete set before deleting the first expanded file.
    unchanged(root, manifest)
    for row in manifest:
        path = member_path(root, row['relative'])
        unchanged(root, [row]); path.unlink()
    return sum(row['allocated'] for row in manifest)


def archive_one(item):
    root = quiet(item)
    with (root / 'world/control/world.lock').open('r+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged(root, item['files'])
        directory = OUT / item['item_id']
        archive, manifest = encode(root, item['files'], directory)
        proof = verify(archive, manifest)
        quiet(item); unchanged(root, manifest)
        verified = save(directory / 'verified.json', {'version': VERSION, 'item': item,
            'plan': ref(PLAN), 'archive': ref(archive), 'members': manifest, 'verification': proof})
        save(root / 'large-snapshots-archive-v194.json', {'version': VERSION, 'verified': verified,
            'original_paths_in_members': True, 'individual_restore_tool': str(Path(__file__).resolve()),
            'final_candidates_API_records_scores_outside_archive_unchanged': True})
        released = release(root, manifest)
        result = {'version': VERSION, 'item_id': item['item_id'], 'verified': verified,
            'source_allocated_bytes_released': released,
            'archive_allocated_bytes': archive.stat().st_blocks*512,
            'net_reclaimed_bytes_before_small_metadata': released-archive.stat().st_blocks*512,
            'original_results_or_scores_changed': False, 'root_operations': 0,
            'host_configuration_changes': 0, 'finished_unix': time.time()}
        save(directory / 'released.json', result)
        return result


def prepare(candidate_file):
    if PLAN.exists():
        raise ValueError('Do not overwrite an archival plan')
    candidates = json.loads(Path(candidate_file).read_bytes())[:80]
    items = []
    for candidate in candidates:
        root = Path(candidate['path']); ep = root.parent
        item = {**candidate, 'item_id': ep.parent.name.removeprefix('generation-'),
            'result': ref(candidate['result_path']),
            'protected': [ref(ep / name) for name in ('controller-result.json', 'candidates/lock.json')
                          if (ep / name).is_file()]}
        quiet(item); unchanged(root, item['files']); items.append(item)
    plan = {'version': VERSION, 'ordinary_uid': os.getuid(), 'source': ref(__file__), 'items': items,
        'maximum_items': 80, 'disk_safety_floor_bytes': 100*GIB,
        'maximum_input_allocated_bytes': sum(r['allocated'] for r in items),
        'authority': '用户已授权进一步清理或压缩无用历史数据；本次无损归档已结束实验的大型状态快照',
        'candidate_patches_scores_API_ledgers_and_current_v193_untouched': True,
        'root_or_host_configuration_operations': 0, 'new_model_calls': 0}
    return save(PLAN, plan)


def run():
    plan = json.loads(PLAN.read_bytes()); checked(plan['source'])
    if os.getuid() != plan['ordinary_uid'] or os.getuid() == 0:
        raise PermissionError('Wrong archival owner')
    OUT.mkdir(parents=True, exist_ok=True); results=[]; errors=[]
    for item in plan['items']:
        try:
            if (OUT / item['item_id']).exists():
                raise ValueError('Do not replay a consumed archival identity')
            results.append(archive_one(item))
        except Exception as error:
            errors.append({'item_id': item['item_id'], 'type': type(error).__name__, 'message': str(error)})
        value = {'version': VERSION, 'updated_unix': time.time(), 'status': 'running',
            'planned': len(plan['items']), 'completed': len(results), 'errors': errors,
            'net_reclaimed_bytes_before_small_metadata': sum(r['net_reclaimed_bytes_before_small_metadata'] for r in results),
            'volume_free_bytes': shutil.disk_usage(VOLUME).free}
        progress(value)
        if errors:
            break
    value['status'] = 'stopped_on_error' if errors else 'complete'
    progress(value); save(ART / 'final.json', value)
    return value


def restore(proof_file, member_name):
    proof = json.loads(Path(proof_file).read_bytes()); item = proof['item']; root = quiet(item)
    archive = checked(proof['archive'])
    row = next(r for r in proof['members'] if r['relative'] == member_name)
    target = member_path(root, member_name)
    if target.exists():
        raise ValueError('Restore never overwrites an existing file')
    process = subprocess.Popen(['/usr/bin/zstd', '-q', '--long=29', '-dc', str(archive)], stdout=subprocess.PIPE)
    temp = target.with_name(target.name + '.v194-restoring')
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as tar:
            for member in tar:
                if member.name != member_name:
                    continue
                with temp.open('xb') as output:
                    shutil.copyfileobj(tar.extractfile(member), output, length=1024**2)
                    output.flush(); os.fsync(output.fileno())
                break
        if digest_file(temp) != row['sha256']:
            raise ValueError('Restored content differs')
        os.chmod(temp, row['mode']); os.utime(temp, ns=(row['mtime_ns'], row['mtime_ns']))
        os.link(temp, target); temp.unlink()
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=15)
    return {'restored': str(target), 'sha256': digest_file(target), 'old_content_exact': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', type=Path)
    modes.add_argument('--run', action='store_true')
    modes.add_argument('--restore', type=Path)
    parser.add_argument('--member')
    args = parser.parse_args()
    value = prepare(args.prepare) if args.prepare else run() if args.run else restore(args.restore, args.member)
    print(json.dumps(value, ensure_ascii=False))
