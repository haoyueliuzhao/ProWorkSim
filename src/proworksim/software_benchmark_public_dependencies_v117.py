"""Offline public Requests test dependencies, shared by both new actor arms.

Only public requirements and cached public distribution wheels are inputs. No
scoring script, acceptance test, reference patch, CA revision or relay is copied.
The payload supplements the original interpreter; it never installs on the host
or replaces the repository's Requests/pytest code.
"""
from __future__ import annotations

from email.parser import BytesParser
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import zipfile

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .storage import digest, json_bytes

VERSION = 'v117-public-requests-dependency-overlay-r1'
TASK = 'psf__requests-2931'
ACTOR_ROOT = '/opt/pws-runtime/public-dependencies/v117'
PINS = {'pytest-httpbin': '0.0.7', 'httpbin': '0.4.0', 'flask': '1.1.4',
        'werkzeug': '0.16.1', 'jinja2': '2.11.3', 'markupsafe': '2.0.1',
        'itsdangerous': '1.1.0', 'click': '7.1.2', 'decorator': '5.3.1', 'six': '1.17.0'}


def _name(value):
    return value.lower().replace('_', '-').replace('.', '-')


def _safe_member(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or '\\' in name
            or any(x in {'', '.', '..'} for x in name.split('/'))
            or any(c in name for c in '\r\n\x00')):
        raise ValueError('A wheel member is outside its public relative namespace')
    return name


def prepare_payload(source_manifest, package_inventory, output):
    """Read an original public baseline plus the local, hashed wheel inventory."""
    from packaging.requirements import Requirement
    source_path = Path(source_manifest).resolve()
    source = json.loads(source_path.read_bytes())
    if len(source.get('tasks', [])) != 1 or not source['tasks'][0]['task_id'].startswith('psf__requests-'):
        raise ValueError('This dependency profile requires one original Requests public baseline')
    task = source['tasks'][0]
    instance_id = task['task_id']
    tree_ref = dict(task['initial_tree'])
    tree_ref['path'] = str(source_path.parent/tree_ref['path'])
    tree = json.loads(checked(tree_ref).read_bytes())
    files = tree['files']
    requirements, fixture = files['requirements.txt'], files['test_requests.py']
    declared = {Requirement(line.strip()).name.lower(): Requirement(line.strip())
                for line in requirements.splitlines() if line.strip() and not line.startswith('#')}
    for name in ('pytest-httpbin', 'httpbin'):
        if name not in declared or str(declared[name].specifier) != '=='+PINS[name]:
            raise ValueError('The public baseline does not declare the frozen fixture dependencies')
    if 'def httpbin(httpbin):' not in fixture or 'def httpsbin_url(httpbin_secure):' not in fixture:
        raise ValueError('The original public fixture contract changed')
    inventory = json.loads(Path(package_inventory).read_bytes())
    selected, archive_files, requirements_seen = [], {}, {}
    for name, version in PINS.items():
        matches = [row for row in inventory['files']
                   if _name(row['name']) == name and row['version'] == version]
        if len(matches) != 1:
            raise ValueError('Missing/ambiguous cached public dependency: '+name+'=='+version)
        row = matches[0]
        wheel = checked({key: row[key] for key in ('path', 'sha256', 'bytes')})
        with zipfile.ZipFile(wheel) as archive:
            metadata_paths = [x for x in archive.namelist() if x.endswith('.dist-info/METADATA')]
            if len(metadata_paths) != 1:
                raise ValueError('One wheel distribution metadata record is required')
            metadata = BytesParser().parsebytes(archive.read(metadata_paths[0]))
            if _name(metadata['Name']) != name or metadata['Version'] != version:
                raise ValueError('Cached wheel metadata differs from its fixed public dependency')
            requires = metadata.get_all('Requires-Dist', [])
            for text in requires:
                requirement = Requirement(text)
                if requirement.marker is not None and not requirement.marker.evaluate(
                        {'python_version': '3.9', 'python_full_version': '3.9.20', 'extra': ''}):
                    continue
                dependency = _name(requirement.name)
                if dependency not in PINS or PINS[dependency] not in requirement.specifier:
                    raise ValueError('The cached public dependency closure is incomplete: '+text)
            requirements_seen[name] = requires
            for member in archive.infolist():
                if member.is_dir():
                    continue
                path = _safe_member(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16) or '.data/' in path:
                    raise ValueError('Only ordinary directly importable public wheel files are supported')
                if path.split('/')[0] in {'requests', 'pytest', '_pytest', 'sitecustomize.py'}:
                    raise ValueError('A public fixture may not shadow the task or test runner')
                if path in archive_files:
                    raise ValueError('Public dependency wheels have colliding contents')
                archive_files[path] = archive.read(member)
        selected.append({'name': name, 'version': version, 'source': reference(wheel)})
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    site = output/'site'
    site.mkdir()
    for name, data in archive_files.items():
        path = site/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest = {'version': VERSION, 'instance_id': instance_id, 'actor_root': ACTOR_ROOT,
        'original_source_manifest': reference(source_path),
        'requirements_sha256': digest(requirements.encode()),
        'public_fixture_sha256': digest(fixture.encode()),
        'interpreter_major_minor': [3, 9], 'preserve_original_pytest': True,
        'packages': selected, 'public_dependency_graph': requirements_seen,
        'files': {name: {'sha256': digest(data), 'bytes': len(data)}
                  for name, data in sorted(archive_files.items())},
        'plugin_entrypoint': 'httpbin = pytest_httpbin.plugin',
        'network_policy_unchanged': True, 'listeners_started_during_prepare': False,
        'certificates_replaced': False, 'task_files_modified': False,
        'hidden_material_included': False, 'official_scoring_environment_changed': False,
        'known_limits': [
            'Original image pytest 7.4.4 is preserved; public requirements pytest 2.8.1 is not installed.',
            'Local HTTP/HTTPS fixture use requires the existing private actor loopback; no host listener or external route.',
            'Bundled legacy fixture certificates are unchanged; TLS validity is not certified by collection-only checks.',
            'Only Requests2931 has this public dependency profile; no blanket claim covers other tasks.']}
    write_new(output/'manifest.json', manifest)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, data in [('manifest.json', json_bytes(manifest)),
                           *[('site/'+name, data) for name, data in sorted(archive_files.items())]]:
            item = tarfile.TarInfo(name)
            item.size, item.mode, item.mtime, item.uid, item.gid = len(data), 0o444, 0, 0, 0
            archive.addfile(item, io.BytesIO(data))
    (output/'payload.tar').write_bytes(buffer.getvalue())
    return {'version': VERSION, 'instance_id': instance_id, 'actor_root': ACTOR_ROOT,
            'manifest': reference(output/'manifest.json'), 'archive': reference(output/'payload.tar')}


def explain_public_fixture_failure(output):
    """Diagnostic only: retain raw nonzero output and never classify it as passed."""
    if ("recursive dependency involving fixture 'httpbin' detected" in output
            and 'httpbin_secure' not in output.partition('available fixtures:')[2].partition('\n')[0]):
        return {'version': VERSION, 'kind': 'public_fixture_dependency_unavailable',
            'evidence': 'Public httpbin wrapper has no registered upstream pytest-httpbin fixture.',
            'model_code_failure_established': False, 'automatic_retry': False,
            'guidance': 'This environment error does not prove your repair failed. Do not rewrite the public fixture to hide it; preserve the result and test independently executable public cases.'}
    return None
