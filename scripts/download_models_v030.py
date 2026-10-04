"""Acquire exactly two frozen BF16 code-agent checkpoints with durable ranges.

Official ModelScope.cn transports bytes whose full identity remains the frozen
HF LFS SHA. Small tokenizer/config files are verified before any shard starts.
The old HF cache is never consumed as verified ranges or removed.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import requests

from proworksim.storage import atomic_write, json_bytes, read_json
from scripts.download_candidate_v015 import RangeJournal

MODELS = {
    'swe-next-14b': ('TIGER-Lab/SWE-Next-14B', '5d9484d6b0e20786629fccf6de9f190f5fb5ebc7'),
    'devstral-small-2507': ('mistralai/Devstral-Small-2507', 'bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39'),
}
MS_WEIGHT_REVISIONS = {
    'swe-next-14b': '9a2331e309eba573dace3c20f6bc80c05067563b',
    'devstral-small-2507': 'fd677dc8b6f1abd36f93342a552529b686439b66',
}
FILE_WORKERS = 4
RANGE_WORKERS = 8
CHUNK_BYTES = 32 * 1024**2


def sha_file(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(16 * 1024**2), b''):
            value.update(chunk)
    return value.hexdigest()


def selected_files(metadata):
    """Never acquire the alternate consolidated copy or example assets."""
    return {row['rfilename']: {'bytes': row['size'], 'lfs': row.get('lfs'),
                              'blob_id': row.get('blobId')}
            for row in metadata['siblings']
            if '/' not in row['rfilename']
            and row['rfilename'] not in {'.gitattributes', 'consolidated.safetensors'}}


def weight_file(name):
    return name.startswith('model-') and name.endswith('.safetensors')


def transport_files(candidate, snapshot, selected):
    repo, _ = MODELS[candidate]
    if snapshot['repo'] != repo or snapshot['domain'] != 'modelscope.cn' or snapshot['status'] != 200:
        raise ValueError('Transport metadata is not the frozen same-name official source')
    remote = {row['Name']: row for row in snapshot['payload']['Data']['Files']}
    for name, frozen in selected.items():
        if not frozen['lfs']:
            if not frozen['blob_id']:
                raise ValueError('Missing official HF Git blob identity: ' + name)
            continue
        row = remote.get(name, {})
        if row.get('Sha256') != frozen['lfs']['sha256'] or row.get('Size') != frozen['bytes']:
            raise ValueError('Transport differs from frozen HF content identity: ' + name)
        if weight_file(name) and row.get('Revision') != MS_WEIGHT_REVISIONS[candidate]:
            raise ValueError('Transport weight revision differs: ' + name)
        if not row.get('Revision'):
            raise ValueError('Missing fixed transport revision: ' + name)
    return remote


def verify_file(path, frozen):
    """Check actual bytes; a preallocated length is never completion evidence."""
    path = Path(path)
    before = path.stat()
    if path.is_symlink() or before.st_size != frozen['bytes']:
        raise ValueError('Official file size/type differs: ' + path.name)
    sha = hashlib.sha256()
    git = hashlib.sha1(f'blob {before.st_size}\0'.encode())
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(16 * 1024**2), b''):
            sha.update(chunk)
            if not frozen['lfs']:
                git.update(chunk)
    actual = sha.hexdigest()
    if frozen['lfs']:
        if actual != frozen['lfs']['sha256']:
            raise ValueError('Official LFS content identity differs: ' + path.name)
    elif git.hexdigest() != frozen['blob_id']:
        raise ValueError('Official HF Git blob identity differs: ' + path.name)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('File changed during verification: ' + path.name)
    return {'bytes': after.st_size, 'sha256': actual, 'mtime_ns': after.st_mtime_ns}


def stream_range(session, url, start, end, size, fd):
    """Accept only the exact requested range, with bounded writes."""
    with session.get(url, headers={'Range': f'bytes={start}-{end}'},
                     stream=True, timeout=(15, 90)) as response:
        response.raise_for_status()
        expected = f'bytes {start}-{end}/{size}'
        if response.status_code != 206 or response.headers.get('Content-Range') != expected:
            raise ValueError('Server did not return the exact requested range')
        offset, hasher = start, hashlib.sha256()
        for chunk in response.iter_content(1024**2):
            if offset + len(chunk) > end + 1:
                raise ValueError('Range response exceeded declared boundary')
            hasher.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.pwrite(fd, view, offset)
                if written <= 0:
                    raise OSError('Could not write checkpoint range')
                offset += written
                view = view[written:]
        if offset != end + 1:
            raise ValueError('Range response ended before declared boundary')
    return hasher.hexdigest()


class Download:
    def __init__(self, candidate, metadata_root, asset_root, report_root, transport_root):
        self.candidate = candidate
        self.repo, self.revision = MODELS[candidate]
        metadata_path = Path(metadata_root) / self.repo.replace('/', '--') / 'model-info.json'
        metadata = read_json(metadata_path)
        if metadata['id'] != self.repo or metadata['sha'] != self.revision:
            raise ValueError('Official metadata differs from the frozen candidate revision')
        self.selected = selected_files(metadata)
        expected_shards = 6 if candidate == 'swe-next-14b' else 10
        if sum(weight_file(name) for name in self.selected) != expected_shards:
            raise ValueError('Frozen candidate shard set is incomplete')
        transport_path = Path(transport_root) / (self.repo.replace('/', '--') + '--modelscope.cn.json')
        self.remote = transport_files(candidate, read_json(transport_path), self.selected)
        self.root = Path(asset_root).resolve() / (candidate + '-' + self.revision[:12])
        self.root.mkdir(parents=True, exist_ok=True)
        self.report = Path(report_root).resolve() / (candidate + '.json')
        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.range_progress = {}
        self.last_report = 0.0
        self.manifest = {
            'version': 'official-code-agent-download-v0.30', 'candidate_id': candidate,
            'repo_id': self.repo, 'declared_hf_revision': self.revision,
            'model_path': str(self.root), 'remote_files': self.selected,
            'status': 'downloading_metadata', 'started_at': time.time(),
            'max_file_workers': FILE_WORKERS, 'max_range_workers_per_file': RANGE_WORKERS,
            'range_chunk_bytes': CHUNK_BYTES, 'files': {},
            'source_metadata_sha256': sha_file(metadata_path),
            'transport_metadata_sha256': sha_file(transport_path),
            'download_transport': 'Official ModelScope.cn fixed-revision ranges; frozen HF full SHA identity',
            'modelscope_weight_revision': MS_WEIGHT_REVISIONS[candidate],
            'preserved_unverified_fallback': str(self.root / '.cache/huggingface/download'),
            'scope': 'Official BF16 sharded checkpoint only; no consolidated duplicate, third-party quantization or remote model code.',
        }
        self.update()

    def update(self, **changes):
        with self.lock:
            self.manifest.update(changes)
            self.manifest['observed_at'] = time.time()
            atomic_write(self.report, json_bytes(self.manifest))

    def record_file(self, name, record):
        with self.lock:
            self.manifest['files'][name] = record
            self.manifest['complete_file_bytes'] = sum(row['bytes'] for row in self.manifest['files'].values())
            self.manifest['observed_at'] = time.time()
            atomic_write(self.report, json_bytes(self.manifest))
        print(json.dumps({'candidate': self.candidate, 'file': name, 'status': 'verified', **record}), flush=True)

    def source_url(self, name):
        if self.selected[name]['lfs']:
            revision = self.remote[name]['Revision']
            return f'https://www.modelscope.cn/models/{self.repo}/resolve/{revision}/{name}'
        return f'https://huggingface.co/{self.repo}/resolve/{self.revision}/{name}'

    def metadata_file(self, item):
        name, frozen = item
        path = self.root / name
        if path.exists():
            self.record_file(name, verify_file(path, frozen))
            return
        temporary = path.with_name(path.name + '.v030-small-incomplete')
        for attempt in range(4):
            try:
                with requests.get(self.source_url(name), stream=True, timeout=(15, 90)) as response:
                    response.raise_for_status()
                    size = 0
                    with temporary.open('wb') as stream:
                        for chunk in response.iter_content(1024**2):
                            size += len(chunk)
                            if size > frozen['bytes']:
                                raise ValueError('Metadata response exceeded frozen size: ' + name)
                            stream.write(chunk)
                        stream.flush()
                        os.fsync(stream.fileno())
                record = verify_file(temporary, frozen)
                temporary.replace(path)
                self.record_file(name, record)
                return
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)

    def metadata(self):
        with ThreadPoolExecutor(max_workers=FILE_WORKERS) as pool:
            list(pool.map(self.metadata_file, [(name, row) for name, row in self.selected.items()
                                               if not weight_file(name)]))
        self.update(status='metadata_ready', metadata_ready_at=time.time())
        print(json.dumps({'candidate': self.candidate, 'status': 'metadata_ready',
                          'model_path': str(self.root)}), flush=True)

    def progress(self, name, byte_count):
        with self.lock:
            self.range_progress[name] = max(self.range_progress.get(name, 0), byte_count)
            if time.monotonic() - self.last_report >= 10:
                self.manifest['durable_range_bytes'] = sum(self.range_progress.values())
                self.manifest['durable_ranges_note'] = 'Locally hash-checked committed ranges, not yet full-file HF SHA approval.'
                self.manifest['observed_at'] = time.time()
                atomic_write(self.report, json_bytes(self.manifest))
                self.last_report = time.monotonic()

    def shard(self, item):
        name, frozen = item
        path = self.root / name
        if path.exists():
            self.record_file(name, verify_file(path, frozen))
            return
        part = path.with_name(path.name + '.modelscope-incomplete')
        journal = RangeJournal(part, size=frozen['bytes'], expected_sha256=frozen['lfs']['sha256'],
                               chunk_bytes=CHUNK_BYTES)
        self.progress(name, sum(row['end'] - int(start) + 1
                                for start, row in journal.data['ranges'].items()))
        local = threading.local()

        def fetch(bounds):
            start, end = bounds
            if not hasattr(local, 'session'):
                local.session = requests.Session()
            for attempt in range(4):
                try:
                    digest = stream_range(local.session, self.source_url(name), start, end,
                                          frozen['bytes'], journal.fd)
                    journal.commit(start, end, digest)
                    self.progress(name, journal.data['verified_downloaded_bytes'])
                    return
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2**attempt)
        try:
            with ThreadPoolExecutor(max_workers=RANGE_WORKERS) as pool:
                list(pool.map(fetch, journal.pending()))
        finally:
            journal.close()
        record = verify_file(part, frozen)
        part.replace(path)
        journal.data['whole_file_sha256_verified'] = record['sha256']
        atomic_write(journal.path, json_bytes(journal.data))
        self.record_file(name, record)

    def weights(self):
        self.update(status='downloading_weights', weights_started_at=time.time())
        with ThreadPoolExecutor(max_workers=FILE_WORKERS) as pool:
            list(pool.map(self.shard, [(name, row) for name, row in self.selected.items()
                                      if weight_file(name)]))
        if set(self.manifest['files']) != set(self.selected):
            raise ValueError('Incomplete fixed file set')
        for name, row in self.manifest['files'].items():
            actual = (self.root / name).stat()
            if actual.st_size != row['bytes'] or actual.st_mtime_ns != row['mtime_ns']:
                raise ValueError('Verified file changed before manifest completion: ' + name)
        self.update(status='complete', finished_at=time.time(),
                    downloaded_bytes=sum(row['bytes'] for row in self.manifest['files'].values()),
                    durable_range_bytes=sum(self.range_progress.values()))
        atomic_write(self.root / 'proworksim-manifest.json', json_bytes(self.manifest))
        print(json.dumps({'candidate': self.candidate, 'status': 'complete',
                          'bytes': self.manifest['downloaded_bytes']}), flush=True)


def run_stage(jobs, method):
    def run(job):
        try:
            getattr(job, method)()
        except BaseException as error:
            job.update(status='download_or_verification_failed', ended_at=time.time(),
                       error={'type': type(error).__name__, 'message': str(error)})
            raise
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, jobs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-root', type=Path, required=True)
    parser.add_argument('--asset-root', type=Path, required=True)
    parser.add_argument('--report-root', type=Path, required=True)
    parser.add_argument('--transport-metadata-root', type=Path,
                        default=Path('runs/v030-model-research/transport-probes'))
    parser.add_argument('--metadata-only', action='store_true')
    args = parser.parse_args()
    args.asset_root.mkdir(parents=True, exist_ok=True)
    with (args.asset_root / '.download-models-v030.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        jobs = [Download(candidate, args.metadata_root, args.asset_root, args.report_root,
                         args.transport_metadata_root) for candidate in MODELS]
        run_stage(jobs, 'metadata')
        if not args.metadata_only:
            run_stage(jobs, 'weights')


if __name__ == '__main__':
    main()
