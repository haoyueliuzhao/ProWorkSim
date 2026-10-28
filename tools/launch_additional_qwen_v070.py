"""Add one original unused Qwen resident; existing tasks/services stay live."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from proworksim import software_benchmark_dispatch_v066 as policy
from proworksim import software_benchmark_ref_resident_v066 as resident
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = policy.ROOT
OUT = ROOT / 'artifacts/software-benchmark-v070/local-expansion-r1'
AUTH = OUT / 'authorization.json'
INDEX = 3
GPU_INDEX = 4
GPU_UUID = 'GPU-c549008f-8bdb-8028-10e5-19e0f4cb619e'


def active_original_residents():
    values = []
    for path in sorted(resident.RUNS.glob('model-*/spec.json')):
        spec = json.loads(path.read_bytes())
        closed = path.parent / 'closed.json'
        released = policy.BATCH_ROOT / 'resource-claims' / f"model-{spec['index']}.released.json"
        if closed.exists() and json.loads(closed.read_bytes()).get('child_exited') is True and released.exists():
            continue
        values.append(spec)
    return values


def prepare():
    if os.getuid() == 0 or os.geteuid() == 0 or AUTH.exists():
        raise PermissionError('Prepare this one ordinary-user deployment once')
    policy.require_v066_allowed('v066.model.start')
    active = active_original_residents()
    if {value['index'] for value in active} != {1, 2}:
        raise ValueError('This supplement only adds the third resident beside original models 1 and 2')
    if (resident.RUNS / f'model-{INDEX}').exists() or (policy.BATCH_ROOT / 'resource-claims' / f'model-{INDEX}.json').exists():
        raise ValueError('The selected residency identity was already consumed')
    card = next((card for card in resident.gpu_capacity()
                 if card['gpu_index'] == GPU_INDEX and card['gpu_uuid'] == GPU_UUID), None)
    if card is None:
        raise policy.ResourceBusy('GPU4 does not currently meet original free-memory admission')
    if not resident.shared_capacity_for(1):
        raise policy.ResourceBusy('Original shared-memory/disk floor does not allow another resident')
    OUT.mkdir(parents=True, exist_ok=True)
    auth = {'status': 'approved', 'version': 'v070-one-additional-original-Qwen-resident-r1',
        'user_authorization': '本地评测也过慢；太慢了，提高并发', 'prepared_unix': time.time(),
        'existing_scope': reference(policy.AUTHORIZATION_FILE), 'source': reference(__file__),
        'original_resident_source': reference(resident.__file__),
        'index': INDEX, 'gpu_index': GPU_INDEX, 'gpu_uuid': GPU_UUID,
        'unit': resident.unit_name(INDEX), 'card_at_preparation': card,
        'old_residents': [reference(Path(value['root']) / 'spec.json') for value in active],
        'maximum_live_residents_this_supplement': 3, 'new_resident_count': 1,
        'memory_GiB': 96, 'CPU': 12, 'original_shared_CPU_memory_cap': [152, 832],
        'original_server_arguments': resident.server_arguments(resident.PORTS[INDEX]),
        'original_model_context': 131072, 'original_output_limit': 32768,
        'new_neutral_probe_max_calls': 1, 'new_neutral_probe_max_tokens': 2048,
        'model_visible_configuration_changed': False,
        'existing_model_or_episode_restarted': False, 'host_configuration_changed': False,
        'coordinator': 'existing v068 primary discovers original resident ready.json; its four-task ceiling remains unchanged',
        'cleanup': 'existing original resident lifecycle and primary shutdown own the exact new unit'}
    return write_new(AUTH, auth)


def launch():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError('Only the ordinary user may launch this owned model')
    auth = policy.load(reference(AUTH))
    if (auth['status'] != 'approved' or auth['source'] != reference(__file__)
            or auth['original_resident_source'] != reference(resident.__file__)
            or auth['index'] != INDEX or auth['gpu_uuid'] != GPU_UUID
            or auth['existing_scope'] != reference(policy.AUTHORIZATION_FILE)
            or {v['index'] for v in active_original_residents()} != {1, 2}):
        raise ValueError('The exact additional-resident grant changed')
    policy.require_v066_allowed('v066.model.start')
    card = next((card for card in resident.gpu_capacity()
                 if card['gpu_index'] == GPU_INDEX and card['gpu_uuid'] == GPU_UUID), None)
    if card is None:
        raise policy.ResourceBusy('Capacity changed; wait without consuming the identity')
    spec = resident.make_spec(INDEX, card)
    command = resident.unit_command(spec)
    folder = Path(spec['root'])
    write_new(folder / 'unit-launch-intent.json', {'supplement': reference(AUTH),
        'specification': reference(folder / 'spec.json'), 'command': command,
        'existing_model_units_restarted': False})
    answer = subprocess.run(command, env=resident.user_manager_environment(),
        capture_output=True, text=True, timeout=30)
    result = {'returncode': answer.returncode, 'stdout': answer.stdout, 'stderr': answer.stderr,
              'unit': spec['unit'], 'supplement': reference(AUTH)}
    write_new(folder / 'unit-launch-result.json', result)
    if answer.returncode != 0:
        raise RuntimeError('New owned model launch failed; preserve its consumed identity and inspect ownership')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare() if args.prepare else launch(), ensure_ascii=False))
