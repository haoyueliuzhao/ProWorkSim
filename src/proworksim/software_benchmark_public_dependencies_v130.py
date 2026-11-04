"""New public-only Requests compatibility payload from already frozen packages."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import Path

from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'artifacts/software-benchmark-v118/public-dependencies-r1'
OUTPUT = ROOT/'artifacts/software-benchmark-v130/public-dependencies-r1'
VERSION = 'v130-public-requests-compatibility-r1'
TASK = 'psf__requests-2931'
ACTOR_ROOT = '/opt/pws-runtime/public-dependencies/v130'
PLUGIN = 'pws_public_compat_v130'
PLUGIN_SOURCE = ROOT/'tools/public_test_compat_v130.py'


def _hash(raw):
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def prepare():
    """Copy checked public files; change one fixture expression and add a plugin."""
    prior_path = SOURCE/'manifest.json'
    prior = json.loads(prior_path.read_bytes())
    if (prior['instance_id'] != TASK or prior['version'] != 'v118-public-requests-localhost-fixture-r1'
            or prior['task_files_modified'] is not False or prior['hidden_material_included'] is not False):
        raise ValueError('Only the prior public baseline-bound payload can be extended')
    files = {}
    for name, expected in prior['files'].items():
        path = SOURCE/'site'/name
        if path.is_symlink():
            raise ValueError('Public dependencies cannot follow symlinks')
        files[name] = checked({'path': str(path), **expected}).read_bytes()
    # Historical Flask jsonify constructed a mapping from MultiDict.lists().
    # Materialize that mapping before passing it to current Flask JSON support.
    target = 'httpbin/core.py'
    old = b'    response = jsonify(headers.lists())\n'
    new = b'    response = jsonify(dict(headers.lists()))\n'
    if files[target].count(old) != 1:
        raise ValueError('The exact frozen public httpbin statement changed')
    files[target] = files[target].replace(old, new, 1)
    record_name = 'httpbin-0.4.0.dist-info/RECORD'
    records = list(csv.reader(io.StringIO(files[record_name].decode())))
    count = 0
    for row in records:
        if row[0] == target:
            raw = files[target]
            row[1:] = ['sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('='), str(len(raw))]
            count += 1
    if count != 1:
        raise ValueError('The original wheel RECORD must bind the patched fixture')
    stream = io.StringIO(newline='')
    csv.writer(stream, lineterminator='\n').writerows(records)
    files[record_name] = stream.getvalue().encode()
    files[PLUGIN+'.py'] = PLUGIN_SOURCE.read_bytes()
    dist = 'pws_public_compat_v130-1.0.dist-info/'
    files[dist+'METADATA'] = b'Metadata-Version: 2.1\nName: pws-public-compat-v130\nVersion: 1.0\n\n'
    files[dist+'entry_points.txt'] = b'[pytest11]\npws-public-compat-v130 = pws_public_compat_v130\n'
    files[dist+'top_level.txt'] = b'pws_public_compat_v130\n'
    changed = sorted(name for name in prior['files'] if _hash(files[name]) != prior['files'][name])
    if changed != sorted([target, record_name]):
        raise ValueError('Unexpected changes to existing public dependencies')
    compatibility = {'version': VERSION, 'plugin_module': PLUGIN,
        'pytest_distribution_version': '7.4.4', 'pytest_distribution_files_changed': False,
        'legacy_string_raises_restored': True, 'modern_pytest_raises_delegated_unchanged': True,
        'httpbin_response_headers_iterable_materialized': True,
        'changed_original_files': changed, 'added_files': sorted(set(files)-set(prior['files'])),
        'plugin_source': reference(PLUGIN_SOURCE), 'test_assertions_removed_or_rewritten': False,
        'exception_or_failure_suppression': False, 'task_files_changed': False,
        'official_scoring_changed': False, 'network_scope_changed': False}
    manifest = {**prior, 'version': VERSION, 'actor_root': ACTOR_ROOT,
        'source_v118_manifest': reference(prior_path),
        'files': {name: _hash(raw) for name, raw in sorted(files.items())},
        'public_compatibility': compatibility, 'preserve_original_pytest_distribution': True,
        'pytest_runtime_legacy_compatibility_added': True,
        'plugin_entrypoints': ['httpbin = pytest_httpbin.plugin',
                              'pws-public-compat-v130 = pws_public_compat_v130'],
        'known_limits': [
            'Only the admitted public Requests baseline and frozen pytest7.4.4 are supported.',
            'String-form raises is restored in the isolated public-test process; the original pytest distribution and modern raises forms are retained.',
            'No task source, hidden tests or official grading environment is modified.',
            'The existing public fixture CA and actor network isolation are unchanged.',
            'Offline CPU controls do not certify a future real actor or the whole task test suite.']}
    path = OUTPUT/'manifest.json'
    if OUTPUT.exists():
        if not path.is_file() or json.loads(path.read_bytes()) != manifest:
            raise ValueError('Never merge into a stale or partial v130 public payload')
        for name, expected in manifest['files'].items():
            checked({'path': str(OUTPUT/'site'/name), **expected})
        return reference(path)
    OUTPUT.mkdir(parents=True)
    for name, raw in files.items():
        path = OUTPUT/'site'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return write_new(OUTPUT/'manifest.json', manifest)


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
