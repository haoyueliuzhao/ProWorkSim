"""Public stdlib helper: validate the frozen fixture profile, adjust test env only."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath

VERSION = 'v117-public-requests-dependency-overlay-r1'
TASK = 'psf__requests-2931'
ACTOR_ROOT = '/opt/pws-runtime/public-dependencies/v117'
DESCRIPTOR_PATH = Path('/pws/control/public-test-dependencies.json')


def validate_descriptor(descriptor, *, instance_id, baseline_files=None, root=ACTOR_ROOT):
    """Called at actor admission with the ORIGINAL public baseline, never a patch."""
    if descriptor is None:
        if instance_id == TASK:
            raise ValueError('Requests2931 needs its frozen public pytest-httpbin dependency profile')
        return None
    if (not instance_id.startswith('psf__requests-') or descriptor.get('version') != VERSION
            or descriptor.get('instance_id') != instance_id or descriptor.get('actor_root') != ACTOR_ROOT):
        raise ValueError('Public fixture profile task or destination differs')
    root = Path(root)
    path = root/'manifest.json'
    if root.is_symlink() or path.is_symlink():
        raise ValueError('Public fixture manifest must be a regular copied file')
    raw = path.read_bytes()
    reference = descriptor['manifest']
    if hashlib.sha256(raw).hexdigest() != reference['sha256'] or len(raw) != reference['bytes']:
        raise ValueError('Public fixture manifest bytes differ')
    manifest = json.loads(raw)
    if (manifest.get('version') != VERSION or manifest.get('instance_id') != instance_id
            or manifest.get('actor_root') != ACTOR_ROOT
            or manifest.get('hidden_material_included') is not False
            or manifest.get('certificates_replaced') is not False):
        raise ValueError('Public fixture manifest changed scope')
    if baseline_files is not None:
        for name, key in (('requirements.txt', 'requirements_sha256'), ('test_requests.py', 'public_fixture_sha256')):
            if hashlib.sha256(baseline_files[name].encode()).hexdigest() != manifest[key]:
                raise ValueError('Public dependencies do not bind this original public baseline')
    for name, expected in manifest['files'].items():
        relative = PurePosixPath(name)
        if (relative.is_absolute() or any(x in {'', '.', '..'} for x in name.split('/'))
                or '\\' in name or any(c in name for c in '\r\n\x00')):
            raise ValueError('Invalid public dependency path')
        path = root/'site'
        for part in relative.parts:
            path /= part
            if path.is_symlink():
                raise ValueError('Public dependency files must not follow symlinks')
        raw = path.read_bytes()
        if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError('Public fixture bytes changed: '+name)
    return {'version': VERSION, 'instance_id': instance_id,
        'manifest_sha256': reference['sha256'], 'site': str(root/'site'),
        'original_pytest_unchanged': True, 'original_task_files_unchanged': True,
        'network_scope_unchanged': True, 'certificates_replaced': False}


def effective_test_environment(environment, profile):
    result = copy.deepcopy(environment)
    if profile is None:
        return result
    if result.get('PYTHONPATH') or result.get('PYTEST_DISABLE_PLUGIN_AUTOLOAD'):
        raise ValueError('The public fixture cannot silently override another Python/plugin policy')
    result['PYTHONPATH'] = profile['site']
    result['PYTHONDONTWRITEBYTECODE'] = '1'
    return result


def native_profile(instance_id):
    """Convenience launcher files remain mutable under native terminal permissions."""
    if not DESCRIPTOR_PATH.exists():
        return validate_descriptor(None, instance_id=instance_id)
    return validate_descriptor(json.loads(DESCRIPTOR_PATH.read_bytes()), instance_id=instance_id)
