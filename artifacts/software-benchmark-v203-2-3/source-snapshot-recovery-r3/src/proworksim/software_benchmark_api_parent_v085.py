"""A new audited lifecycle of the same explicitly authorized API-only slice.

The completed v076 lifecycle and release proof remain immutable. This adapter
does not adopt a live object or increase the original privilege/resource scope.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import time

from . import software_benchmark_api_parent_v076 as _prior
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace

ROOT = _prior.ROOT
RUN = ROOT / 'runs/software-benchmark-v085/api-parent-cycle-r1'
CREATED = RUN / 'created.json'
RELEASED = RUN / 'released.json'
AUTHORIZATION = _prior.AUTHORIZATION
PROPOSAL = _prior.PROPOSAL
SLICE, CGROUP = _prior.SLICE, _prior.CGROUP
MEMORY_BYTES, SWAP_BYTES, TASKS_MAX = _prior.MEMORY_BYTES, 0, _prior.TASKS_MAX
CYCLE_AUTHORIZATION = ROOT / 'artifacts/software-benchmark-v085/parent-cycle-r1/authorization.json'
CYCLE_VERSION = 'v085-same-scope-API-parent-lifecycle-r1'
_namespace = clone_namespace(_prior, RUN=RUN, CREATED=CREATED, RELEASED=RELEASED)


def validate_cycle(value, *, source, prior_authority, prior_release):
    expected = {'version': CYCLE_VERSION, 'status': 'approved_by_existing_explicit_scope',
        'source': source, 'original_authorization': prior_authority,
        'predecessor_released': prior_release, 'slice': SLICE,
        'memory_max_bytes': MEMORY_BYTES, 'memory_swap_max_bytes': 0,
        'tasks_max': TASKS_MAX, 'simultaneous_objects': 1,
        'adopt_existing_object': False, 'modify_existing_host_configuration': False}
    if any(value.get(key) != item for key, item in expected.items()):
        raise PermissionError('The replacement lifecycle differs from the exact persistent grant')
    return value


def _approved_cycle():
    authority, proposal = _prior.approved()
    release_ref = reference(_prior.RELEASED)
    released = json.loads(checked(release_ref).read_bytes())
    if (released.get('returncode') != 0 or released.get('after', {}).get('LoadState') != 'not-found'
            or released.get('other_objects_modified') is not False):
        raise PermissionError('The predecessor has not proved exact empty release')
    validate_cycle(json.loads(CYCLE_AUTHORIZATION.read_bytes()), source=reference(__file__),
        prior_authority=reference(AUTHORIZATION), prior_release=release_ref)
    return authority, proposal


_namespace['approved'] = _approved_cycle


def prepare_cycle():
    _prior.approved()
    release = json.loads(checked(reference(_prior.RELEASED)).read_bytes())
    if (release.get('returncode') != 0 or release.get('after', {}).get('LoadState') != 'not-found'
            or release.get('other_objects_modified') is not False):
        raise PermissionError('Require a proven released original parent')
    if CYCLE_AUTHORIZATION.exists():
        _approved_cycle()
        return reference(CYCLE_AUTHORIZATION)
    value = {'version': CYCLE_VERSION, 'status': 'approved_by_existing_explicit_scope',
        'source': reference(__file__), 'original_authorization': reference(AUTHORIZATION),
        'predecessor_released': reference(_prior.RELEASED), 'slice': SLICE,
        'memory_max_bytes': MEMORY_BYTES, 'memory_swap_max_bytes': 0, 'tasks_max': TASKS_MAX,
        'simultaneous_objects': 1, 'adopt_existing_object': False,
        'modify_existing_host_configuration': False, 'prepared_unix': time.time(),
        'basis': 'User explicitly authorized this exact new slice and empty-only cleanup; '
                 'restore the same boundary after its successful empty release, retaining both lifecycle receipts',
        'new_container_or_model_operations': 0, 'create_command': _prior.creation_command(
            json.loads(checked(reference(PROPOSAL)).read_bytes())['description']),
        'stop_command': _prior.stopping_command()}
    CYCLE_AUTHORIZATION.parent.mkdir(parents=True, exist_ok=True)
    return write_new(CYCLE_AUTHORIZATION, value)


def create(*, runner=subprocess.run):
    _approved_cycle()
    folder = _prior.original.BATCH_ROOT / 'resource-claims'
    with (folder / 'allocation.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for path in folder.glob('active-*.json'):
            item = json.loads(path.read_bytes())
            if ':DEEPSEEK_' in item.get('spec', {}).get('slot_id', ''):
                raise PermissionError('An API resource remains active; parent replacement refused')
        return _namespace['create'](runner=runner)


# All runtime methods refer to the private lifecycle globals. The old creation
# and release markers continue to describe the old object, never the new one.
require_qualified = _namespace['require_qualified']
pressure_probe = _namespace['pressure_probe']
container_options = _namespace['container_options']
validate_container_parent = _namespace['validate_container_parent']
stop_empty = _namespace['stop_empty']
inspect_systemd = _namespace['inspect_systemd']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--create-approved', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare_cycle() if args.prepare else create(), ensure_ascii=False))
