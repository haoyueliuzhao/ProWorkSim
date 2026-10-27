"""Two owned, capacity-gated REF residents using ordinary-user host Python.

Transient user units provide CPU/RAM bounds. No shared service, driver, mount,
user-manager setting or linger setting is changed. Only exact owned units stop.
"""
from __future__ import annotations

import fcntl
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_dispatch_v064 import BATCH_ROOT, CONSTRAINTS, cpu_set, require_v064_allowed
from .software_benchmark_dispatch_v064 import reserve_model, release_model, ResourceBusy
from .software_benchmark_gpu_lease_v054 import GpuLease
from .software_benchmark_ref_host_v061 import ROOT, RUNTIME, launch_spec, prepare_runtime
from .software_benchmark_ref_service_v056 import (MANIFEST_SHA, MODEL, VLLM_METADATA,
    MODEL_REVISION, models_response, server_arguments as original_server_arguments)
from .software_benchmark_supervision_v054 import process_identity

VERSION = 'v064-owned-user-ref-resident-r1'
RUNS = BATCH_ROOT / 'residents'
PORTS = tuple(range(18210, 18216))
GPU_UUID = re.compile(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z')
GIB = 1024**3
MINIMUM_FREE_MIB = 50176
GPU_MEMORY_UTILIZATION = '0.6'
RPC_ROOT = ROOT / 'runs/g64c1'


def existing_runtime():
    """Refuse to recreate or revise the previously prepared private Python."""
    if not (RUNTIME / 'manifest.json').is_file():
        raise ValueError('The existing private Python r3 runtime must already be prepared')
    return prepare_runtime()


def model_launch_spec(arguments, *, index, gpu_uuid, cache):
    """Reuse the frozen private Python/headers; scope every new cache to v064."""
    unit_name(index)
    cache = Path(cache).resolve()
    if cache != (RUNS / f'model-{index}' / 'cache').resolve():
        raise ValueError('New model caches must remain in this exact v064 resident')
    existing_runtime()
    command, environment = launch_spec(arguments, gpu_uuid=gpu_uuid, cache=None)
    environment.update(TMPDIR=str(cache), VLLM_CACHE_ROOT=str(cache), XDG_CACHE_HOME=str(cache),
                       TORCHINDUCTOR_CACHE_DIR=str(cache / 'inductor'), CUDA_CACHE_PATH=str(cache / 'cuda'))
    return command, environment


def server_arguments(port):
    """Only the explicitly approved cache reservation changes from v056."""
    result = original_server_arguments(port)
    position = result.index('--gpu-memory-utilization') + 1
    if result[position] != '0.8':
        raise ValueError('The original GPU memory reservation differs from the reviewed baseline')
    result[position] = GPU_MEMORY_UTILIZATION
    return result


def user_manager_environment():
    """Address only this existing user bus; do not change manager settings."""
    uid = os.getuid()
    runtime = Path('/run/user') / str(uid)
    if uid == 0 or not runtime.is_dir() or runtime.stat().st_uid != uid or not (runtime / 'bus').is_socket():
        raise RuntimeError('The existing ordinary-user manager socket is unavailable')
    env = {key: os.environ[key] for key in ('HOME', 'USER', 'LOGNAME') if key in os.environ}
    env.update(PATH='/usr/bin:/bin', LANG='C.UTF-8', LC_ALL='C.UTF-8',
               XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'bus'))
    return env


def shared_capacity_for(new_models):
    if type(new_models) is not int or not 0 <= new_models <= 6:
        raise ValueError('At most six newly reserved model residents')
    available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines()
                     if line.startswith('MemAvailable:'))
    # Reserve the new residents at their full hard ceiling, plus both task and
    # grader lanes; preserve the project's 128-GiB shared-host memory floor.
    needed = (128 + 96 * new_models + 40 + 32 + 16) * GIB
    return available >= needed and shutil.disk_usage(ROOT).free >= 384 * GIB


def gpu_capacity():
    answer = subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,name,memory.total,memory.free',
        '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=15, check=True)
    cards = []
    for line in answer.stdout.splitlines():
        index, uuid, name, total, free = [p.strip() for p in line.split(',')]
        if int(index) not in range(8) or not GPU_UUID.fullmatch(uuid):
            raise ValueError('Unexpected GPU index/UUID')
        if 'A800' in name and int(total) >= 81920 and int(free) >= MINIMUM_FREE_MIB:
            cards.append({'gpu_index': int(index), 'gpu_uuid': uuid, 'free_mib': int(free)})
    return sorted(cards, key=lambda x: (-x['free_mib'], x['gpu_index']))


def unit_name(index):
    if type(index) is not int or index not in range(6):
        raise ValueError('Only six named model units are allowed')
    return f'proworksim-v064-model-{index}.service'


def make_spec(index, card):
    require_v064_allowed('v064.model.start')
    unit_name(index)
    folder = RUNS / f'model-{index}'
    if folder.exists():
        raise ValueError('Never restart or replace an entered resident identity')
    model_ref = reference(MODEL / 'proworksim-manifest.json')
    if model_ref['sha256'] != MANIFEST_SHA:
        raise ValueError('Original model checkpoint identity changed')
    if 'Version: 0.32.0\n' not in VLLM_METADATA.read_text():
        raise ValueError('The pinned vLLM version changed')
    reservation = reserve_model(index)
    body = {'version': VERSION, 'index': index, 'root': str(folder), 'unit': unit_name(index),
        'resource_reservation': reservation,
        'ownership_token': secrets.token_hex(16),
        'gpu_index': card['gpu_index'], 'gpu_uuid': card['gpu_uuid'], 'port': PORTS[index],
        'endpoint': f'http://127.0.0.1:{PORTS[index]}', 'api_key_file': str(folder / 'api-key.private'),
        'model_manifest': model_ref, 'model_revision': MODEL_REVISION,
        'vllm_metadata': reference(VLLM_METADATA),
        'server_arguments': server_arguments(PORTS[index]), 'runtime': existing_runtime(),
        'minimum_free_mib': MINIMUM_FREE_MIB, 'automatic_restart': False,
        'gpu_memory_utilization': float(GPU_MEMORY_UTILIZATION),
        'deployment_revision': 'v064-model-memory-06',
        'rpc_base_path': str(RPC_ROOT / f'model-{index}'),
        'requires_real_full_context_capacity_admission': True,
        'cpu_quota_percent': 1200, 'memory_max_bytes': 96 * 1024**3,
        'cpu_affinity': [int(n) for n in cpu_set('model', index).split(',')],
        'memory_swap_max_bytes': 0, 'maximum_tasks': 2048,
        'adapter': reference(__file__), 'host_configuration_changed': False}
    folder.mkdir(parents=True, mode=0o700)
    write_new(folder / 'spec.json', body)
    return body


def validate_spec(spec):
    index = spec.get('index')
    if (spec.get('version') != VERSION or type(index) is not int or index not in range(6)
            or spec.get('root') != str(RUNS / f'model-{index}') or spec.get('unit') != unit_name(index)
            or spec.get('port') != PORTS[index] or spec.get('server_arguments') != server_arguments(PORTS[index])
            or spec.get('endpoint') != f'http://127.0.0.1:{PORTS[index]}'
            or spec.get('api_key_file') != str(RUNS / f'model-{index}' / 'api-key.private')
            or spec.get('model_revision') != MODEL_REVISION or spec.get('model_manifest', {}).get('sha256') != MANIFEST_SHA
            or not GPU_UUID.fullmatch(spec.get('gpu_uuid', '')) or spec.get('gpu_index') not in range(8)
            or spec.get('automatic_restart') is not False or checked(spec['adapter']) != Path(__file__).resolve()
            or spec.get('minimum_free_mib') != MINIMUM_FREE_MIB
            or spec.get('rpc_base_path') != str(RPC_ROOT / f'model-{index}')
            or spec.get('cpu_quota_percent') != CONSTRAINTS['model_resident_cpu_quota_percent']
            or spec.get('memory_max_bytes') != CONSTRAINTS['model_resident_memory_bytes']
            or spec.get('memory_swap_max_bytes') != CONSTRAINTS['model_resident_swap_bytes']
            or spec.get('maximum_tasks') != CONSTRAINTS['model_resident_tasks_max']
            or spec.get('gpu_memory_utilization') != float(GPU_MEMORY_UTILIZATION)
            or spec.get('requires_real_full_context_capacity_admission') is not True
            or re.fullmatch(r'[0-9a-f]{32}', spec.get('ownership_token', '')) is None
            or spec.get('runtime') != existing_runtime()):
        raise ValueError('Resident differs from the fixed model/runtime/resource scope')
    checked(spec['model_manifest'])
    reservation = json.loads(checked(spec['resource_reservation']).read_bytes())
    if (reservation.get('key') != f'model-{index}'
            or reservation.get('spec', {}).get('role') != 'model'
            or reservation.get('lane') != index):
        raise ValueError('Model residency lacks its exact aggregate resource reservation')
    if spec.get('cpu_affinity') != [int(n) for n in cpu_set('model', index).split(',')]:
        raise ValueError('Model CPU affinity differs from the fixed host CPU pool')
    if checked(spec['vllm_metadata']) != VLLM_METADATA or 'Version: 0.32.0\n' not in VLLM_METADATA.read_text():
        raise ValueError('Pinned vLLM package metadata differs')
    return spec


def unit_command(spec):
    validate_spec(spec)
    return ['systemd-run', '--user', '--collect', '--no-block', '--unit=' + spec['unit'],
        '--description=ProWorkSim v064 ' + spec['ownership_token'],
        '--setenv=PYTHONHOME=', '--setenv=PYTHONPATH=', '--setenv=LD_LIBRARY_PATH=', '--setenv=LD_PRELOAD=',
        '--property=Restart=no', '--property=KillMode=control-group', '--property=CPUQuota=1200%',
        '--property=CPUAffinity=' + ' '.join(map(str, spec['cpu_affinity'])),
        '--property=MemoryMax=96G', '--property=MemorySwapMax=0', '--property=TasksMax=2048',
        '--property=OOMPolicy=stop', '--property=TimeoutStopSec=90',
        '--property=WorkingDirectory=' + str(ROOT),
        '--property=StandardOutput=append:' + str(Path(spec['root']) / 'service.stdout.log'),
        '--property=StandardError=append:' + str(Path(spec['root']) / 'service.stderr.log'),
        str(ROOT / '.venv/bin/python'), '-B', str(ROOT / 'tools/serve_ref_capability_v064.py'),
        '--spec', str(Path(spec['root']) / 'spec.json')]


def start_residents():
    require_v064_allowed('v064.model.start')
    RUNS.mkdir(parents=True, exist_ok=True)
    with (RUNS / 'allocation.lock').open('a+b') as allocation:
        fcntl.flock(allocation, fcntl.LOCK_EX)
        existing = [json.loads(p.read_bytes()) for p in sorted(RUNS.glob('model-*/spec.json'))]
        used = {s['gpu_uuid'] for s in existing}
        cards = [c for c in gpu_capacity() if c['gpu_uuid'] not in used] if len(existing) < 6 else []
        if cards and not shared_capacity_for(min(len(cards), 6 - len(existing))):
            return ready_residents()
        for index in range(6):
            if (RUNS / f'model-{index}').exists() or not cards:
                continue
            try:
                spec = make_spec(index, cards.pop(0))
            except ResourceBusy:
                break
            command = unit_command(spec)
            write_new(Path(spec['root']) / 'unit-launch-intent.json', {'specification': reference(Path(spec['root']) / 'spec.json'), 'command': command})
            result = subprocess.run(command, env=user_manager_environment(), capture_output=True, text=True, timeout=30)
            write_new(Path(spec['root']) / 'unit-launch-result.json', {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
            if result.returncode != 0:
                raise RuntimeError('Owned model unit did not start: ' + result.stderr[-1000:])
    return ready_residents()


def ready_residents():
    require_v064_allowed('v064.model.start')
    result = []
    for path in sorted(RUNS.glob('model-*/ready.json')):
        if (path.parent / 'closed.json').exists():
            continue
        value = json.loads(path.read_bytes())
        spec = validate_spec(json.loads((path.parent / 'spec.json').read_bytes()))
        owner = value.get('host_process', {})
        try:
            if process_identity(owner['pid']) != owner:
                continue
        except (OSError, KeyError, ValueError, ProcessLookupError):
            continue
        key = Path(spec['api_key_file']).read_text().strip()
        try:
            alive = models_response(spec, key)
        except (OSError, ValueError, http.client.HTTPException):
            alive = None
        if alive is not None:
            result.append(value)
    return result


def validate_cpu_memory_limits(actual, affinity, expected_affinity):
    if (actual.get('memory.max') != str(96 * 1024**3) or actual.get('memory.swap.max') != '0'
            or actual.get('pids.max') != '2048' or sorted(affinity) != sorted(expected_affinity)
            or len(set(affinity)) != 12):
        raise ValueError('Owned resident CPU affinity/RAM/PID/swap bounds differ')
    cpu_max = actual.get('cpu.max')
    if cpu_max is not None:
        parts = cpu_max.split()
        if (len(parts) != 2 or not all(part.isdigit() for part in parts)
                or int(parts[1]) <= 0 or not 0 < int(parts[0]) <= 12 * int(parts[1])):
            raise ValueError('Available resident CPU cgroup ceiling is invalid')
    return {**actual, 'cpu_affinity': sorted(affinity), 'cpu_limit_enforced_by': 'inherited_process_affinity',
            'cpu_cgroup_controller_available': cpu_max is not None}


def actual_unit_limits(spec):
    group = Path('/proc/self/cgroup').read_text().strip()
    prefix, _, cgroup_path = group.partition('::')
    if prefix != '0' or not cgroup_path.endswith('/' + spec['unit']):
        raise ValueError('Model must execute inside its exact bounded owned user unit')
    own_cgroup = Path('/sys/fs/cgroup') / cgroup_path.lstrip('/')
    actual = {key: (own_cgroup / key).read_text().strip()
              for key in ('memory.max', 'memory.swap.max', 'pids.max')}
    actual['cpu.max'] = (own_cgroup / 'cpu.max').read_text().strip() if (own_cgroup / 'cpu.max').exists() else None
    return validate_cpu_memory_limits(actual, os.sched_getaffinity(0), spec['cpu_affinity'])


def run_service(spec_path):
    require_v064_allowed('v064.model.start')
    spec = validate_spec(json.loads(Path(spec_path).read_bytes()))
    folder = Path(spec['root'])
    if any((folder / p).exists() for p in ('launch.json', 'ready.json', 'closed.json', 'api-key.private')):
        raise ValueError('A used resident identity cannot restart')
    requested = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda *_: requested.set())
    lease = endpoint_lock = process = None
    outcome = {'version': VERSION, 'model': 'Qwen/Qwen3.5-9B', 'unit': spec['unit'],
               'other_processes_signalled': False}
    try:
        outcome['actual_resource_limits'] = actual_unit_limits(spec)
        if not shared_capacity_for(1):
            raise RuntimeError('Shared-host memory/disk reserve is no longer sufficient')
        if (spec['gpu_index'], spec['gpu_uuid']) not in {(c['gpu_index'], c['gpu_uuid']) for c in gpu_capacity()}:
            raise RuntimeError('GPU no longer meets the frozen free-memory threshold')
        lease = GpuLease(spec['gpu_uuid'])
        endpoint_lock = (RUNS / f'port-{spec["port"]}.lock').open('a+b')
        fcntl.flock(endpoint_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', spec['port']))
        key = secrets.token_urlsafe(48)
        fd = os.open(spec['api_key_file'], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(key + '\n')
        cache = folder / 'cache'
        cache.mkdir(mode=0o700)
        short = Path(spec['rpc_base_path'])
        short.mkdir(parents=True, mode=0o700, exist_ok=False)
        args = [str(ROOT / 'tools/start_ref_capacity_server_v054.py'), '--api-key-file', spec['api_key_file'], '--', *spec['server_arguments']]
        command, environment = model_launch_spec(args, index=spec['index'], gpu_uuid=spec['gpu_uuid'], cache=cache)
        environment.update(VLLM_RPC_BASE_PATH=str(short), VLLM_HOST_IP='127.0.0.1',
                           GLOO_SOCKET_IFNAME='lo', NCCL_SOCKET_IFNAME='lo',
                           OMP_NUM_THREADS='12', MAX_JOBS='12')
        write_new(folder / 'launch.json', {'specification': reference(spec_path), 'command': command,
            'gpu_lease': lease.receipt, 'owner': process_identity(os.getpid()), 'runtime': spec['runtime']})
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, start_new_session=True)
        until, models = time.monotonic() + 1800, None
        while time.monotonic() < until and not requested.is_set():
            if process.poll() is not None:
                raise RuntimeError('Owned REF engine exited before readiness')
            try:
                models = models_response(spec, key)
            except (OSError, ValueError, http.client.HTTPException):
                models = None
            if models is not None:
                break
            requested.wait(.5)
        if models is None:
            raise RuntimeError('REF engine readiness interrupted or timed out')
        from .software_benchmark_model_capacity_v064 import qualify_capacity, run_neutral_probe
        capacity = qualify_capacity(spec, folder / 'capacity-admission')
        probe = run_neutral_probe(spec, capacity, folder / 'neutral-admission')
        probe_value = json.loads(checked(probe).read_bytes())
        if probe_value.get('passed') is not True:
            raise RuntimeError('Neutral model admission did not pass; no formal request may enter')
        identity = {'model_revision': MODEL_REVISION, 'vllm_version': '0.32.0', 'raw_release': True,
            'adapter_sha256': None, 'model_manifest_sha256': MANIFEST_SHA, 'context_limit': 131072,
            'max_output_tokens': 32768, 'service_admission_complete': True, 'endpoint': spec['endpoint'],
            'gpu_index': spec['gpu_index'], 'gpu_uuid': spec['gpu_uuid'], 'port': spec['port'],
            'deployment_version': VERSION, 'models_response': models, 'resident_spec': reference(spec_path),
            'gpu_memory_utilization': float(GPU_MEMORY_UTILIZATION), 'capacity_admission': capacity,
            'neutral_admission': probe, 'context_and_sampling_limits_changed': False}
        ready = {k: spec[k] for k in ('root', 'unit', 'endpoint', 'api_key_file', 'gpu_index', 'gpu_uuid')}
        ready.update(identity=write_new(folder / 'identity.json', identity), identity_value=identity,
                     model_identity_value=identity, host_process=process_identity(os.getpid()),
                     resident_child_pid=process.pid)
        write_new(folder / 'ready.json', ready)
        outcome['ready'] = True
        while not requested.wait(1):
            if process.poll() is not None:
                raise RuntimeError('Owned REF engine exited during residency')
        outcome['status'] = 'requested_stop'
    except Exception as error:
        outcome.update(status='technical_unknown', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
        outcome['child_returncode'] = process.returncode if process is not None else None
        outcome['child_exited'] = process is None or process.poll() is not None
        if endpoint_lock is not None:
            endpoint_lock.close()
        if lease is not None:
            lease.close()
        write_new(folder / 'closed.json', outcome)
    return 0 if outcome.get('status') == 'requested_stop' else 1


def _stop_resident(path):
    """One owned unit's failure cannot prevent cleanup of the other residents."""
    try:
        spec = validate_spec(json.loads(path.read_bytes()))
        shown = subprocess.run(['systemctl', '--user', 'show', spec['unit'],
            '--property=Description,ActiveState,LoadState'], env=user_manager_environment(), capture_output=True, text=True, timeout=15)
        props = dict(line.split('=', 1) for line in shown.stdout.splitlines() if '=' in line)
        known_absent = shown.returncode == 0 and props.get('LoadState') == 'not-found'
        owned = shown.returncode == 0 and props.get('Description') == 'ProWorkSim v064 ' + spec['ownership_token']
        if not owned and not known_absent:
            return {'unit': spec['unit'], 'owned_unit_stopped': False,
                    'error': 'Cannot establish ownership/absence; no stop issued'}
        stopped = None
        if owned:
            stopped = subprocess.run(['systemctl', '--user', 'stop', spec['unit']], env=user_manager_environment(), capture_output=True, text=True, timeout=100)
            shown = subprocess.run(['systemctl', '--user', 'show', spec['unit'],
                '--property=ActiveState,LoadState'], env=user_manager_environment(), capture_output=True, text=True, timeout=15)
            props = dict(line.split('=', 1) for line in shown.stdout.splitlines() if '=' in line)
        inactive = shown.returncode == 0 and props.get('ActiveState') in ('inactive', 'failed')
        inactive = inactive or (shown.returncode == 0 and props.get('LoadState') == 'not-found')
        record = {'unit': spec['unit'], 'stop_returncode': stopped.returncode if stopped is not None else None,
            'active_state': props.get('ActiveState'), 'owned_unit_stopped': inactive,
            'closed': reference(path.parent / 'closed.json') if (path.parent / 'closed.json').exists() else None}
        if inactive:
            record['resource_reservation_released'] = release_model(spec['resource_reservation'], quiescent=True)
        return record
    except Exception as error:
        return {'specification_path': str(path), 'owned_unit_stopped': False,
                'error': {'type': type(error).__name__, 'message': str(error)}}


def stop_residents():
    from concurrent.futures import ThreadPoolExecutor
    paths = sorted(RUNS.glob('model-*/spec.json'))
    if len(paths) > 6:
        raise ValueError('Unexpected number of owned model specifications')
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(_stop_resident, paths))
