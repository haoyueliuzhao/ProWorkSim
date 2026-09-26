"""Fetch a frozen official checkpoint with durable, hash-checked range progress.

Uses pre-recorded HF revision/LFS identities; ModelScope is only an alternate
transport of matching bytes. A preallocated part file is never completion proof.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import requests


def atomic_json(path, data):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def file_sha(path, start=0, count=None):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        stream.seek(start)
        while count is None or count > 0:
            chunk = stream.read(4 * 1024**2 if count is None else min(count, 4 * 1024**2))
            if not chunk:
                break
            result.update(chunk)
            if count is not None:
                count -= len(chunk)
    return result.hexdigest()


class RangeJournal:
    def __init__(self, part, *, size, expected_sha256, chunk_bytes=32 * 1024**2):
        self.part = Path(part)
        self.path = self.part.with_name(self.part.name + '.ranges.json')
        self.size, self.chunk_bytes = size, chunk_bytes
        self.lock = threading.Lock()
        identity = {'version': 'candidate-range-journal-v0.15', 'bytes': size,
                    'expected_sha256': expected_sha256, 'chunk_bytes': chunk_bytes}
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {**identity, 'ranges': {}}
        if any(self.data.get(k) != v for k, v in identity.items()):
            raise ValueError('Range journal belongs to a different frozen file')
        self.fd = os.open(self.part, os.O_CREAT | os.O_RDWR, 0o644)
        os.ftruncate(self.fd, size)
        # Existing pre-journal bytes may be reused only if there is durable range
        # evidence. Logical length, allocated extents and zero-filled holes are
        # all deliberately insufficient here.
        valid = {}
        for start, end in self.ranges():
            row = self.data['ranges'].get(str(start))
            if row and row['end'] == end and file_sha(self.part, start, end-start+1) == row['sha256']:
                valid[str(start)] = row
        self.data['ranges'] = valid
        atomic_json(self.path, self.data)

    def ranges(self):
        return [(start, min(start+self.chunk_bytes, self.size)-1)
                for start in range(0, self.size, self.chunk_bytes)]

    def pending(self):
        return [(a, b) for a, b in self.ranges() if str(a) not in self.data['ranges']]

    def commit(self, start, end, sha256):
        os.fsync(self.fd)
        with self.lock:
            self.data['ranges'][str(start)] = {'end': end, 'sha256': sha256,
                                             'finished_unix': time.time()}
            self.data['verified_downloaded_bytes'] = sum(r['end']-int(s)+1 for s, r in self.data['ranges'].items())
            atomic_json(self.path, self.data)

    def close(self):
        os.close(self.fd)


def fetch_checkpoint(manifest_path, *, file_workers=4, range_workers=8):
    manifest_path = Path(manifest_path)
    data = json.loads(manifest_path.read_text())
    repo, root = data['repo_id'], Path(data['model_path'])
    frozen_revision = data['declared_hf_revision']
    response = requests.get(f'https://www.modelscope.cn/api/v1/models/{repo}/repo/files',
                            params={'Revision': 'master', 'Recursive': 'true'}, timeout=30)
    response.raise_for_status()
    metadata = response.json()
    atomic_json(manifest_path.with_name(manifest_path.stem + '-journal-modelscope-files.json'), metadata)
    alternate = {f['Name']: f for f in metadata['Data']['Files']}
    data.update(status='downloading', range_journal_version='candidate-range-journal-v0.15')
    atomic_json(manifest_path, data)

    def fetch_file(item):
        name, record = item
        path = root / name
        lfs = record.get('lfs')
        if path.exists() and path.stat().st_size == record['bytes']:
            if not lfs or file_sha(path) == lfs['sha256']:
                return
        if not lfs:
            url = f'https://huggingface.co/{repo}/resolve/{frozen_revision}/{name}'
            response = requests.get(url, timeout=(30, 120))
            response.raise_for_status()
            if len(response.content) != record['bytes']:
                raise ValueError('Frozen metadata size differs: ' + name)
            path.write_bytes(response.content)
            return
        source = alternate[name]
        if source['Sha256'] != lfs['sha256'] or source['Size'] != record['bytes']:
            raise ValueError('Official mirror differs from frozen HF LFS identity: ' + name)
        url = f'https://www.modelscope.cn/models/{repo}/resolve/{source["Revision"]}/{name}'
        journal = RangeJournal(path.with_name(path.name + '.modelscope-incomplete'),
                               size=record['bytes'], expected_sha256=lfs['sha256'])
        local = threading.local()

        def fetch_range(bounds):
            start, end = bounds
            if not hasattr(local, 'session'):
                local.session = requests.Session()
            for attempt in range(4):
                try:
                    with local.session.get(url, headers={'Range': f'bytes={start}-{end}'},
                                           stream=True, timeout=(30, 120)) as result:
                        result.raise_for_status()
                        if result.status_code != 206 or result.headers.get('Content-Range') != f'bytes {start}-{end}/{record["bytes"]}':
                            raise ValueError('Server did not return the exact requested range')
                        offset, hasher = start, hashlib.sha256()
                        for chunk in result.iter_content(1024**2):
                            if offset+len(chunk) > end+1:
                                raise ValueError('Range response exceeded declared boundary')
                            hasher.update(chunk)
                            view = memoryview(chunk)
                            while view:
                                written = os.pwrite(journal.fd, view, offset)
                                if written <= 0:
                                    raise OSError('Could not write checkpoint range')
                                offset += written
                                view = view[written:]
                        if offset != end+1:
                            raise ValueError('Range response ended before declared boundary')
                    journal.commit(start, end, hasher.hexdigest())
                    return
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(attempt+1)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=range_workers) as pool:
                list(pool.map(fetch_range, journal.pending()))
        finally:
            journal.close()
        if file_sha(journal.part) != lfs['sha256']:
            raise ValueError('Complete actual bytes differ from frozen official LFS SHA: ' + name)
        journal.part.replace(path)
        journal.data['whole_file_sha256_verified'] = lfs['sha256']
        atomic_json(journal.path, journal.data)
        print(json.dumps({'file': name, 'bytes': record['bytes'], 'status': 'verified'}), flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=file_workers) as pool:
        list(pool.map(fetch_file, data['remote_files'].items()))
    data['files'] = {name: {'bytes': (root/name).stat().st_size, 'sha256': file_sha(root/name)}
                     for name in data['remote_files']}
    data.update(status='complete', finished=time.time(),
                download_transport='Official ModelScope LFS, cross-checked frozen HF SHA; original HF metadata')
    atomic_json(manifest_path, data)
    atomic_json(root/'proworksim-manifest.json', data)
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--file-workers', type=int, default=4)
    parser.add_argument('--range-workers', type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.file_workers <= 8 or not 1 <= args.range_workers <= 16:
        parser.error('Download concurrency outside declared 1..8 files and 1..16 ranges')
    fetch_checkpoint(args.manifest, file_workers=args.file_workers, range_workers=args.range_workers)


if __name__ == '__main__':
    main()
