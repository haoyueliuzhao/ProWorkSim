"""Materialize the authenticated, cached Noble compiler packages in a private overlay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
APT = ROOT / 'runs/software-benchmark-v054/ref-toolchain-apt'
OUTPUT = ROOT / 'runs/software-benchmark-v054/ref-toolchain'


def fields(text):
    return dict(line.split(': ', 1) for line in text.splitlines()
                if ': ' in line and not line.startswith(' '))


def main():
    if OUTPUT.exists():
        raise FileExistsError('Compiler overlay is once-only; do not overwrite an earlier installation')
    log = (APT / 'download.log').read_text()
    if 'Download complete and in download only mode' not in log or '\nE:' in log:
        raise ValueError('Authenticated APT download has not completed')
    planned = [shlex.split(line) for line in (APT / 'plan.txt').read_text().splitlines()
               if line.startswith("'https:")]
    packages = []
    for uri, filename, size, _ in planned:
        if urlsplit(uri).hostname != 'mirrors.tuna.tsinghua.edu.cn' or Path(filename).name != filename:
            raise ValueError('Only the fixed domestic mirror cache is accepted')
        path = APT / 'var/cache/apt/archives' / filename
        if path.stat().st_size != int(size):
            raise ValueError('Cached archive size differs from the authenticated plan')
        metadata = fields(subprocess.check_output(['dpkg-deb', '--field', str(path)], text=True))
        packages.append({'package': metadata['Package'], 'version': metadata['Version'],
                         'archive': str(path), 'source_url': uri, 'bytes': int(size)})
    metadata = subprocess.check_output([
        'apt-cache', '-o', 'Dir=' + str(APT), '-o', 'Dir::Etc::sourcelist=' + str(APT / 'etc/apt/sources.list'),
        '-o', 'Dir::Etc::sourceparts=-', '-o', 'Dir::Etc::Parts=-', 'show',
        *[p['package'] for p in packages]], text=True)
    indexed = {}
    for block in metadata.split('\n\n'):
        row = fields(block)
        if 'Package' in row and 'Version' in row:
            indexed[row['Package'], row['Version']] = row
    OUTPUT.mkdir(parents=True)
    for package in packages:
        row = indexed[package['package'], package['version']]
        if int(row['Size']) != package['bytes'] or len(row['SHA256']) != 64:
            raise ValueError('APT cache metadata identity differs')
        package['sha256_from_authenticated_index'] = row['SHA256']
        subprocess.run(['dpkg-deb', '--extract', package['archive'], str(OUTPUT)], check=True)
    receipt = {'packages': packages, 'package_count': len(packages),
               'package_bytes': sum(p['bytes'] for p in packages),
               'archive_payload_rehashed': False, 'verification': 'APT signed InRelease and package SHA256 validation',
               'installed_in_system': False, 'proxy_used': False, 'origin_fallback': False,
               'base_runtime_precedence': True, 'model_calls': 0,
               'download_log_sha256': hashlib.sha256(log.encode()).hexdigest()}
    target = ROOT / 'artifacts/software-benchmark-v054/native-environment/ref-toolchain-packages.json'
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'packages': len(packages), 'bytes': receipt['package_bytes'], 'overlay': str(OUTPUT)}))


if __name__ == '__main__':
    main()
