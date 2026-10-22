"""Independent three-volume accounting for newly dispatched generation workers.

In-flight directories keep their observed devices. Qwen, preparation, scoring
and ledgers stay on primary. Only future DeepSeek generation can use either
registered extra volume. Available bytes exclude filesystem-reserved blocks.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from . import software_benchmark_disk_volumes_v055_r1 as previous
from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_queue_v055 import ROOT, load, now

stages = previous.stages
VERSION = 'v055-device-bound-three-volume-disk-r2'
MANIFEST_VERSION = 'v055-three-worker-volumes-r2'
TERTIARY_VERSION = 'v055-tertiary-worker-volume-r1'
POLICY = stages.POLICY
STAGE_POLICY = stages.STAGE_POLICY
SECONDARY_ROOT = previous.SECONDARY_ROOT
TERTIARY_ROOT = ROOT / 'runs/software-benchmark-v055/tertiary-volume-r1'
TERTIARY_SOURCE_ROOT = Path('/data2/proworksim-zhuxinrui/v055-spare-volume-r1')
TARGET_VOLUMES = frozenset({'primary', 'secondary', 'tertiary'})
VOLUME_POLICY = {**previous.VOLUME_POLICY, 'version': VERSION,
    'future_deepseek_generations': ['secondary', 'tertiary'],
    'registered_volume_count': 3, 'available_bytes_basis': 'f_bavail_times_f_frsize',
    'filesystem_reserved_blocks_available_to_uid1021': False,
    'all_three_devices_must_differ': True}
disk_dispatch_lock = stages.disk_dispatch_lock
admission = stages.admission
generation_estimate = stages.generation_estimate
_VOLUME_REF = None


def assert_distinct_devices(identities):
    if set(identities) != TARGET_VOLUMES:
        raise ValueError('Exactly the primary, secondary and tertiary volumes are required')
    devices = [identities[name]['device'] for name in sorted(TARGET_VOLUMES)]
    if any(type(value) is not int for value in devices) or len(set(devices)) != 3:
        raise ValueError('Registered volumes must be three distinct real devices')


def available_space(path):
    value = os.statvfs(path)
    available = value.f_bavail * value.f_frsize
    free = value.f_bfree * value.f_frsize
    if available < 0 or available > free:
        raise ValueError('Filesystem available-space counters are inconsistent')
    return {'free_bytes': available, 'free_including_reserved_bytes': free,
        'filesystem_reserved_unavailable_bytes': free - available,
        'available_bytes_basis': 'f_bavail_times_f_frsize'}


def check_tertiary_marker(value, volume):
    # The pre-existing read/write probe marker uses `identity`, not `uuid`.
    # Bind its original version and complete ownership/device fields without
    # rewriting that already recorded marker.
    if (value.get('version') != 'v055-spare-volume-identity-r1'
            or value.get('uuid', value.get('identity')) != volume['uuid']
            or value.get('source_directory') != str(TERTIARY_SOURCE_ROOT)
            or value.get('device') != 66308
            or value.get('owner_uid') != 1021 or value.get('owner_gid') != 1022):
        raise ValueError('Original tertiary marker identity/version/device/owner changed')


def _live_identity(manifest, *, mountinfo=None):
    if (manifest.get('version') != MANIFEST_VERSION
            or manifest.get('all_three_devices_must_differ') is not True
            or manifest.get('mount_loss_fallback') is not False
            or manifest.get('inflight_directories_moved') is not False
            or manifest.get('helper_source') != reference(__file__)):
        raise ValueError('Unknown or modified three-volume manifest')
    secondary = load(manifest['secondary_registration'])
    identities = previous._live_identity(secondary, mountinfo=mountinfo)
    volume = load(manifest['tertiary_registration'])
    primary, secondary_root = ROOT, SECONDARY_ROOT
    target, source = TERTIARY_ROOT, TERTIARY_SOURCE_ROOT
    if (volume.get('version') != TERTIARY_VERSION
            or volume.get('primary_path') != str(primary)
            or volume.get('project_mountpoint') != str(target)
            or volume.get('source_directory') != str(source)
            or volume.get('mounted') is not True
            or volume.get('existing_data_moved') is not False
            or volume.get('inflight_paths_modified') is not False
            or volume.get('device_identity_must_match_on_dispatch') is not True
            or volume.get('owner_uid') != 1021 or volume.get('owner_gid') != 1022
            or volume.get('tertiary_device') != 66308):
        raise ValueError('Unrecognized explicitly registered data2 tertiary volume')
    for path in (primary, secondary_root, target, source):
        if path.resolve() != path or not path.is_dir():
            raise ValueError('A registered volume path is missing or became a symlink')
    real, mounted = source.stat(), target.stat()
    if (primary.stat().st_dev != volume['primary_device']
            or secondary_root.stat().st_dev != volume['secondary_device']
            or mounted.st_dev != volume['tertiary_device']
            or (real.st_dev, real.st_ino, real.st_uid, real.st_gid)
                != (mounted.st_dev, mounted.st_ino, mounted.st_uid, mounted.st_gid)
            or mounted.st_uid != 1021 or mounted.st_gid != 1022):
        raise ValueError('Tertiary bind source/device/inode/owner identity changed')
    marker = volume['marker']
    if marker['path'] != str(target / 'volume-identity.json'):
        raise ValueError('Tertiary marker escaped the exact registered mount')
    info = Path(marker['path']).lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_dev != mounted.st_dev:
        raise ValueError('Tertiary marker is not a regular file on the expected device')
    value = json.loads(checked(marker).read_bytes())
    check_tertiary_marker(value, volume)
    text = Path('/proc/self/mountinfo').read_text() if mountinfo is None else mountinfo
    found = [line for line in text.splitlines() if len(line.split()) > 4 and line.split()[4] == str(target)]
    if len(found) != 1 or previous._mount_key(found[0]) != previous._mount_key(volume['mountinfo_line']):
        raise ValueError('Exact tertiary bind mount identity is absent')
    identities['tertiary'] = {'path': str(target), 'device': mounted.st_dev,
        'source_directory': str(source), 'uuid': volume['uuid']}
    assert_distinct_devices(identities)
    return identities


def configure(manifest_reference):
    """Bind one sealed three-volume manifest for this dedicated host process."""
    global _VOLUME_REF
    if _VOLUME_REF is not None and _VOLUME_REF != manifest_reference:
        raise ValueError('A coordinator process cannot switch its registered volumes')
    identities = _live_identity(load(manifest_reference))
    _VOLUME_REF = dict(manifest_reference)
    return {'registration': _VOLUME_REF, 'identity': identities}


def _placement(record, *, family, volumes):
    if family not in {'v054', 'v055'}:
        raise ValueError('Unknown experiment placement family')
    key = 'worker_directory' if family == 'v054' else 'directory'
    path = Path(record[key])
    allowed = ROOT / f'runs/software-benchmark-{family}'
    if path.resolve() != path or not path.is_dir() or not path.is_relative_to(allowed):
        raise ValueError('Active worker directory is missing or outside its experiment')
    if path.is_relative_to(TERTIARY_ROOT):
        label = 'tertiary'
    elif path.is_relative_to(SECONDARY_ROOT):
        label = 'secondary'
    else:
        label = 'primary'
    if family == 'v054' and label != 'primary':
        raise ValueError('Qwen retains its original primary placement')
    device = path.stat().st_dev
    if device != volumes[label]['device']:
        raise ValueError('Actual worker device disagrees with its registered volume path')
    return label, {'worker_directory': str(path), 'device': device}


def partition_snapshot(snapshot, v054_state, v055_state, volumes, *, placement=_placement):
    assert_distinct_devices(volumes)
    # The original partitioner iterates every registered volume and already
    # charges unknown placement to all of them while blocking admission.
    return previous.partition_snapshot(snapshot, v054_state, v055_state, volumes, placement=placement)


def shared_disk_snapshot(*, v055_state=None, v054_state=None, cache=None, target_volume='primary'):
    """Observe under the original shared lock; unknown identities fail closed."""
    if target_volume not in TARGET_VOLUMES:
        raise ValueError('Unknown target volume')
    try:
        if _VOLUME_REF is None:
            raise ValueError('Three-volume manifest has not been configured')
        identities = _live_identity(load(_VOLUME_REF))
        if v054_state is None:
            v054_state = json.loads((ROOT / 'runs/software-benchmark-v054/formal-queue-r1/state.json').read_bytes())
        if v055_state is None:
            v055_state = json.loads((ROOT / 'runs/software-benchmark-v055/queue-r1/state.json').read_bytes())
        snapshot = stages.shared_disk_snapshot(v054_state=v054_state, v055_state=v055_state, cache=cache)
        grouped, errors = partition_snapshot(snapshot, v054_state, v055_state, identities)
        for value in grouped.values():
            value.update(available_space(value['path']))
        selected = grouped[target_volume]
        error = snapshot['metadata_error']
        if errors:
            error = {'scope': 'volume_placement', 'errors': errors}
        return {**snapshot, 'volume_policy': VOLUME_POLICY, 'volume_registration': _VOLUME_REF,
            'target_volume': target_volume, 'volumes': grouped, 'free_bytes': selected['free_bytes'],
            'free_including_reserved_bytes': selected['free_including_reserved_bytes'],
            'active_peak_reserved_bytes': selected['active_peak_reserved_bytes'],
            'metadata_error': error, 'volume_identity_verified_utc': now()}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {'observed_utc': now(), 'policy': POLICY, 'stage_policy': STAGE_POLICY,
            'volume_policy': VOLUME_POLICY, 'volume_registration': _VOLUME_REF,
            'target_volume': target_volume, 'volumes': {}, 'free_bytes': 0,
            'active_peak_reserved_bytes': 0, 'v054_generations': [], 'v055_generations': [],
            'v055_preparations': [], 'metadata_error': {'scope': 'volume_identity_or_observation',
                'type': type(error).__name__, 'message': str(error)}, 'silent_primary_fallback': False}
