"""Validate the single pinned pure-Python build wheel; no host installation."""
from __future__ import annotations

from email.parser import BytesParser
import hashlib
from pathlib import Path, PurePosixPath
import zipfile

from .software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = 'v099-sphinx-offline-build-dependency-r1'
WHEEL_NAME = 'flit_core-3.9.0-py3-none-any.whl'
WHEEL_SHA256 = '7aada352fb0c7f5538c4fafeddf314d3a6a92ee8e2b1de70482329e42de70301'
WHEEL_BYTES = 63141
TARGET = '/pws-v099-build-wheels/' + WHEEL_NAME
PIP_ENVIRONMENT = {'PIP_NO_INDEX': '1', 'PIP_FIND_LINKS': 'file:///pws-v099-build-wheels',
                   'PIP_DISABLE_PIP_VERSION_CHECK': '1'}


def inspect_wheel(path):
    path = Path(path)
    if (path.name != WHEEL_NAME or path.stat().st_size != WHEEL_BYTES
            or hashlib.sha256(path.read_bytes()).hexdigest() != WHEEL_SHA256):
        raise ValueError('Offline wheel differs from the pinned 3.9.0 release')
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Corrupt offline wheel member')
        metadata = BytesParser().parsebytes(archive.read('flit_core-3.9.0.dist-info/METADATA'))
        wheel = BytesParser().parsebytes(archive.read('flit_core-3.9.0.dist-info/WHEEL'))
        if (metadata['Name'].replace('_', '-').lower() != 'flit-core'
                or metadata['Version'] != '3.9.0' or metadata['Requires-Python'] != '>=3.6'
                or metadata.get_all('Requires-Dist', [])
                or wheel['Root-Is-Purelib'] != 'true'
                or wheel.get_all('Tag') != ['py3-none-any']):
            raise ValueError('Pinned wheel Python, dependency, or platform metadata differs')
    return {'wheel': reference(path), 'name': 'flit_core', 'version': '3.9.0',
        'requires_python': '>=3.6', 'requires_dist': [], 'tag': 'py3-none-any'}


def manifest(path):
    return {'version': VERSION, 'instance_id': 'sphinx-doc__sphinx-11510',
        **inspect_wheel(path), 'target_container_python': '3.9.20',
        'original_build_requires': ['flit_core>=3.7'], 'container_destination': TARGET,
        'container_environment': PIP_ENVIRONMENT,
        'official_pip_command_changed': False, 'network_mode': 'none',
        'host_installation': False, 'host_bind_mount': False,
        'additional_dependencies_may_be_discovered_at_runtime': True,
        'runtime_qualified': False}


def freeze(path, destination):
    return write_new(destination, manifest(path))


def stage_owned(container, *, owned_container_ids, instance_id, manifest_ref, copy_to_container):
    """Future new-scope hook only: copy via the existing byte transfer helper.

    Must be called after creation/ownership validation of the fresh scoring
    container. No root/daemon operations or container creation occur here.
    """
    import json
    planned = json.loads(checked(manifest_ref).read_bytes())
    wheel = checked(planned['wheel'])
    if (planned != manifest(wheel) or instance_id != planned['instance_id']
            or container.id not in owned_container_ids):
        raise ValueError('Offline dependency transfer is outside its exact owned scorer')
    copy_to_container(container, wheel, PurePosixPath(TARGET))
    return {'version': VERSION, 'container_id': container.id,
        'wheel': planned['wheel'], 'destination': TARGET, 'copied_by_existing_transfer': True}
