"""Own one real REF model resident across independent, fenced task sessions."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))


def main():
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_gpu_lease_v054 import GpuLease
    from proworksim.software_benchmark_ref_deployment_v054 import RefPortReservation
    from proworksim.software_benchmark_supervision_v054 import process_identity
    from proworksim.software_benchmark_service_factory_v054 import (
        MODEL, capacity_admission, condition_reference, ref_arguments,
    )
    from tools.prepare_model_capacity_v054 import eligible, gpu_rows, source_identity
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--spec-sha256', required=True)
    args = parser.parse_args()
    spec_ref = reference(args.spec)
    if spec_ref['sha256'] != args.spec_sha256:
        raise ValueError('Immutable resident specification changed')
    spec = json.loads(args.spec.read_bytes())
    root, short = Path(spec['root']), Path(spec['short'])
    if (not root.resolve().is_relative_to(ROOT / 'runs/software-benchmark-v054')
            or not short.resolve().is_relative_to(ROOT / 'runs/v054-gpu')
            or len(str(short).encode()) + 37 > 107 or spec['arm'] != 'REF'
            or spec['condition'] != condition_reference('REF')
            or spec['model_manifest'] != reference(MODEL / 'proworksim-manifest.json')
            or spec['capacity_admission'] != capacity_admission('REF', spec['capacity_receipt'])
            or spec['REF_argv'] != ref_arguments()):
        raise ValueError('Resident differs from the frozen REF numerical deployment')
    capacity = json.loads(checked(spec['capacity_receipt']).read_bytes())
    if source_identity() != capacity['source']:
        raise ValueError('Original model identity changed')
    if any((root / name).exists() for name in ('ready.json', 'identity.json', 'session-state.json')):
        raise ValueError('An existing resident may not silently restart')
    cards = [row for row in eligible(gpu_rows(), 'REF') if row['uuid'] == spec['card']['uuid']]
    if len(cards) != 1 or cards[0]['index'] != 7:
        return 75  # no allocation; supervisor waits, without claiming a task
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    short.mkdir(mode=0o700, parents=True, exist_ok=True)
    key_path = Path(spec['api_key_file'])
    if key_path.parent != root or key_path.exists():
        raise ValueError('Each resident needs a fresh private API key in its own directory')
    gpu, port, process = None, None, None
    try:
        try:
            gpu = GpuLease(cards[0]['uuid'])
            port = RefPortReservation()
        except (BlockingIOError, OSError):
            return 75  # An unavailable lease allocates no GPU and consumes no slot.
        key = secrets.token_urlsafe(48)
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(key + '\n')
        cache = root / 'cache'
        cache.mkdir()
        descriptors = [handle.fileno() for handle in gpu.handles] + [port.lock.fileno()]
        env = ['HF_HUB_OFFLINE=1', 'TRANSFORMERS_OFFLINE=1', 'HF_DATASETS_OFFLINE=1',
               'LITELLM_LOCAL_MODEL_COST_MAP=True', 'VLLM_NO_USAGE_STATS=1', 'DO_NOT_TRACK=1',
               'PYTORCH_CUDA_ALLOC_CONF=backend:native', 'TRITON_LIBCUDA_PATH=/opt/host-nvidia',
               'CUDA_HOME=/usr/local/cuda-13.0', 'VLLM_RPC_BASE_PATH=' + str(short),
               'NO_PROXY=*', 'no_proxy=*', 'HTTP_PROXY=', 'HTTPS_PROXY=', 'ALL_PROXY=',
               'http_proxy=', 'https_proxy=', 'all_proxy=',
               'PYTHONPATH=' + str(ROOT / 'src') + ':' + str(ROOT),
               'TMPDIR=' + str(cache), 'VLLM_CACHE_ROOT=' + str(cache),
               'XDG_CACHE_HOME=' + str(cache), 'TORCHINDUCTOR_CACHE_DIR=' + str(cache / 'inductor'),
               'CUDA_CACHE_PATH=' + str(cache / 'cuda'),
               'PWS_REF_RESIDENT_SPEC=' + spec_ref['path'],
               'PWS_REF_RESIDENT_SPEC_SHA256=' + spec_ref['sha256']]
        command = ['/bin/bash', str(ROOT / 'tools/run_ref_preparation_v054.sh'), '--write-project',
                   '--gpu', '7', '/usr/bin/env', *env,
                   str(ROOT / 'runs/software-benchmark-v054/ref-venv/bin/python'),
                   str(ROOT / 'tools/start_ref_capacity_server_v054.py'),
                   '--api-key-file', str(key_path), '--', *ref_arguments(),
                   '--middleware', 'tools.ref_resident_middleware_v054.RefSessionGate']
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True,
                                   pass_fds=descriptors)
        def stopped(*_):
            raise SystemExit('Owned REF resident stopped')
        signal.signal(signal.SIGTERM, stopped)
        signal.signal(signal.SIGINT, stopped)
        until = time.monotonic() + 1800
        while time.monotonic() < until:
            if process.poll() is not None:
                raise RuntimeError('Owned resident exited; never attach to a different endpoint')
            connection = http.client.HTTPConnection('127.0.0.1', 18054, timeout=2)
            try:
                connection.request('GET', '/v1/models', headers={'Authorization': 'Bearer ' + key})
                response = connection.getresponse()
                models = json.loads(response.read(1024**2))
                if (response.status == 200 and any(row['id'] == 'raw-qwen3.5-9b-v054-ref'
                        and row['max_model_len'] == 131072 for row in models['data'])):
                    break
            except (OSError, ValueError, KeyError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(.2)
        else:
            raise TimeoutError('Resident startup did not reach readiness')
        identity = write_new(root / 'identity.json', {
            'model_revision': 'c202236235762e1c871ad0ccb60c8ee5ba337b9a', 'vllm_version': '0.32.0',
            'raw_release': True, 'adapter_sha256': None,
            'model_manifest_sha256': spec['model_manifest']['sha256'],
            'context_limit': 131072, 'max_output_tokens': 32768, 'service_admission_complete': True,
            'endpoint': 'http://127.0.0.1:18054', 'models_response': models,
            'capacity_receipt': spec['capacity_receipt'], 'condition': spec['condition'],
            'deployment_version': 'v054-persistent-ref-session-v1', 'resident_spec': spec_ref})
        write_new(root / 'ready.json', {
            'ready': True, 'resident': True, 'source_spec': spec_ref,
            'host_process': process_identity(os.getpid()), 'gpu_index': 7,
            'identity': identity, 'gpu_uuid': cards[0]['uuid'],
            'gpu_lease_held': True, 'endpoint_lease_held': True,
            'resident_child_pid': process.pid,
            'model_resident': True, 'formal_generation_requests': 0,
            'admin_endpoint': 'http://127.0.0.1:18054', 'api_key_file': str(key_path)})
        return process.wait()
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
            # systemd KillMode=control-group additionally owns escaped descendants;
            # every inherited lock FD stays held until those processes also exit.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if port:
            port.close()
        if gpu:
            gpu.close()


if __name__ == '__main__':
    raise SystemExit(main())
