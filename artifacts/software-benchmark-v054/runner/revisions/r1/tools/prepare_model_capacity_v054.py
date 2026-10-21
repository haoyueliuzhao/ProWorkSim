"""Wait for an eligible GPU, run bounded synthetic capacity checks, then release it.

No benchmark task, formal slot, training, proxy download or model configuration
search is performed. A failed admitted check is retained and never replayed.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import struct
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim.software_benchmark_capacity_guards_v054 import (  # noqa: E402
    SmokeLedger, check_seal, register_model, require_monitor, stop_registered, unit_state,
)
from proworksim.software_benchmark_match_v054 import CONTRACT  # noqa: E402
RUNTIME = Path('/data0/zhuxinrui/proworksim-runtime')
MODEL = ROOT / 'runs/assets/models/Qwen3.5-9B-c20223623576'
SOURCE = ROOT / 'artifacts/software-panel-v053/model-source-receipt.json'
REF_CONFIG = ROOT / 'config/v054-ref-service.json'
MATCH_CONFIG = ROOT / 'config/v054-match-seam.json'
CAPACITY_CONFIG = ROOT / 'config/v054-model-capacity-preparation-r5.json'
REVISION = 'c202236235762e1c871ad0ccb60c8ee5ba337b9a'
DEFAULT_MONITOR = 'proworksim-v054-model-capacity-preparation-r1.service'
SEAL_FILES = (
    'tools/prepare_model_capacity_v054.py', 'tools/run_model_capacity_service_v054.py',
    'tools/start_ref_capacity_server_v054.py', 'tools/run_ref_preparation_v054.sh',
    'tools/run_benchmark_runtime_v054.sh', 'tools/enter_benchmark_runtime_v054.sh',
    'tools/serve_benchmark_owner_v054.py', 'config/v054-ref-service.json',
    'config/v054-match-seam.json', 'config/v054-model-capacity-preparation.json',
    'config/v054-model-capacity-preparation-r2.json', 'scripts/run_ne_v021.py',
    'config/v054-model-capacity-preparation-r3.json',
    'config/v054-model-capacity-preparation-r4.json',
    'config/v054-model-capacity-preparation-r5.json',
    'artifacts/software-benchmark-v054/native-environment/ref-host-cuda-toolchain.json',
    'artifacts/software-benchmark-v054/manifests/native-interface.json',
    'artifacts/software-panel-v053/model-source-receipt.json',
    'runs/assets/models/Qwen3.5-9B-c20223623576/proworksim-manifest.json',
    'src/proworksim/software_benchmark_capacity_guards_v054.py',
    'src/proworksim/software_benchmark_gpu_lease_v054.py',
    'src/proworksim/software_benchmark_owner_ipc_v054.py',
    'src/proworksim/software_benchmark_match_v054.py',
    'src/proworksim/software_calibration_runtime_v051.py',
    'src/proworksim/candidate_runtime_v020.py',
    'src/proworksim/software_panel_resources_v053.py',
    'src/proworksim/storage.py',
    'artifacts/software-learning-v050/resume-r6-source/scripts/software_learning_resources_v050r3.py',
    'artifacts/software-learning-v050/resume-r6-source/scripts/software_learning_resources_v050r5.py',
)


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.writing')
    temp.write_bytes(encoded(value))
    temp.replace(path)


def reference(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def source_identity():
    receipt = json.loads(SOURCE.read_text())
    for name, item in receipt['files'].items():
        path = MODEL / name
        info = path.stat()
        actual = {'path': str(path), 'dev': info.st_dev, 'ino': info.st_ino,
                  'size': info.st_size, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}
        if actual != item['stat']:
            raise ValueError('Model file identity changed; no automatic rehash or reload: ' + name)
    if reference(MODEL / 'proworksim-manifest.json') != receipt['manifest']:
        raise ValueError('Model manifest changed')
    return {'source_receipt': reference(SOURCE), 'model_manifest': receipt['manifest'],
            'model_payload_rehashed': False, 'file_count': len(receipt['files'])}


def create_seal(output, monitor_unit, modes):
    output.mkdir(parents=True, exist_ok=True)
    contract = json.loads(MATCH_CONFIG.read_text())['contract']
    if contract != CONTRACT:
        raise ValueError('Capacity sealing cannot alter the original MATCH numerical contract')
    value = {'version': 'v054-model-capacity-source-seal-v1', 'sealed_utc': now(),
             'monitor_unit': monitor_unit, 'model_source': source_identity(),
             'files': [reference(ROOT / path) for path in SEAL_FILES],
             'match_contract': contract,
             'ref_config': json.loads(REF_CONFIG.read_text()),
             'maximum_preparation_residents': 1, 'maximum_requests_per_mode': 2,
             'modes_to_run': modes,
             'formal_execution_authorized': False}
    with (output / 'source-seal.json').open('xb') as stream:
        stream.write(encoded(value))
    return value


def gpu_rows():
    result = subprocess.run([
        'nvidia-smi', '--query-gpu=index,uuid,name,memory.total,memory.free,driver_version',
        '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=20)
    rows = []
    for line in result.stdout.splitlines():
        index, device, name, total, free, driver = map(str.strip, line.split(','))
        rows.append({'index': int(index), 'uuid': device, 'name': name,
                     'total_mib': int(total), 'free_mib': int(free), 'driver': driver})
    return rows


def eligible(rows, arm):
    minimum = 66560 if arm == 'REF' else 46080
    mode = 'REF' if arm == 'REF' else 'MATCH_PROJECT_shared_owner'
    physical_gpu = json.loads(CAPACITY_CONFIG.read_text())['modes'][mode]['physical_gpu']
    return sorted([row for row in rows if row['index'] == physical_gpu
                   and row['total_mib'] >= 81920 and row['free_mib'] >= minimum
                   and any(kind in row['name'] for kind in ('A100', 'A800'))],
                  key=lambda row: (-row['free_mib'], row['index']))


def ref_argv():
    config = json.loads(REF_CONFIG.read_text())
    options = config['server_options']
    return ['-m', 'vllm.entrypoints.cli.main', 'serve', str(MODEL),
            '--host', options['host'], '--port', str(options['port']),
            '--served-model-name', options['served_model_name'],
            '--tensor-parallel-size', '1', '--dtype', 'bfloat16',
            '--gpu-memory-utilization', '0.8', '--max-model-len', '131072',
            '--max-num-seqs', '1', '--no-enable-prefix-caching',
            '--generation-config', 'vllm', '--language-model-only',
            '--enable-auto-tool-choice', '--tool-call-parser', 'qwen3_coder',
            '--reasoning-parser', 'qwen3']


def http_json(path, body=None, timeout=1860, *, api_key):
    if not api_key:
        raise ValueError('REF requests require the private per-service API key')
    connection = http.client.HTTPConnection('127.0.0.1', 18054, timeout=timeout)
    try:
        connection.request('GET' if body is None else 'POST', path,
                           body=None if body is None else encoded(body),
                           headers={'Content-Type': 'application/json',
                                    'Authorization': 'Bearer ' + api_key})
        response = connection.getresponse()
        raw = response.read(32 * 1024**2 + 1)
        if response.status != 200 or len(raw) > 32 * 1024**2:
            raise ValueError(f'Local REF HTTP {response.status}; no retry/redirect; response bytes={len(raw)}')
        return json.loads(raw)
    finally:
        connection.close()


class OwnerRPC:
    def __init__(self, path, identity):
        self.path, self.identity = str(path), identity
        self.session, self.sequence = uuid.uuid4().hex, 0

    def call(self, operation, **arguments):
        self.sequence += 1
        request = {'version': 'software-benchmark-owner-ipc-v054', 'session': self.session,
                   'sequence': self.sequence, 'identity_sha256': hashlib.sha256(encoded(self.identity)).hexdigest(),
                   'operation': operation, 'arguments': arguments}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(660)
            stream.connect(self.path)
            pid, uid, _ = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if pid <= 0 or uid != os.getuid():
                raise ValueError('Owner socket identity changed')
            stream.sendall((json.dumps(request, ensure_ascii=False) + '\n').encode())
            with stream.makefile('rb') as reader:
                raw = reader.readline(32 * 1024**2 + 1)
        if len(raw) > 32 * 1024**2 or not raw.endswith(b'\n'):
            raise ValueError('Incomplete owner response; no replay')
        result = json.loads(raw)
        if (result.get('sequence') != self.sequence
                or result.get('identity_sha256') != request['identity_sha256'] or result.get('error')):
            raise ValueError('Owner response failed: ' + str(result.get('error')))
        return result['result']


def bounded_prompt(request, measure, target):
    """Find an actual counted prompt at the original maximum input, without generation."""
    base = copy.deepcopy(request)
    prefix = 'Synthetic capacity padding follows. Ignore it and finish with message ready.\n'
    low, high = 0, target
    for _ in range(20):
        count = (low + high) // 2
        trial = copy.deepcopy(base)
        trial['messages'][-1]['content'] = prefix + ' x' * count
        proof = measure(trial)
        tokens = proof['prompt_tokens']
        if tokens == target:
            return trial, proof
        if tokens < target:
            low = count + 1
        else:
            high = count - 1
    raise ValueError('Exact full input could not be constructed; no approximate capacity claim')


def check_transport(arm, folder, rpc=None, *, api_key=None):
    interface = json.loads((ROOT / 'artifacts/software-benchmark-v054/manifests/native-interface.json').read_text())
    tools = list(interface['tool_schemas'].values())
    request = {'model': 'raw-qwen3.5-9b-v054-' + arm.lower(),
               'messages': [{'role': 'system', 'content': interface['static_system_prompt']},
                            {'role': 'user', 'content': 'Synthetic preparation only; no repository. Call finish once with message ready.'}],
               'tools': tools, 'tool_choice': 'auto', 'stream': False,
               'max_tokens': 32768 if arm == 'REF' else 2048,
               'temperature': 0.6 if arm == 'REF' else 0.7,
               'top_p': 0.95 if arm == 'REF' else 1.0, 'top_k': 20 if arm == 'REF' else 0,
               'min_p': 0.0, 'presence_penalty': 0.0, 'repetition_penalty': 1.0,
               'seed': 202610210541, 'chat_template_kwargs': {'enable_thinking': arm == 'REF'},
               'add_generation_prompt': True, 'continue_final_message': False, 'add_special_tokens': False}
    def measure(body):
        if rpc is not None:
            return rpc.call('smoke_count', request=body)
        counted = http_json('/tokenize', {key: body[key] for key in (
            'model', 'messages', 'tools', 'chat_template_kwargs', 'add_generation_prompt',
            'continue_final_message', 'add_special_tokens')}, api_key=api_key)
        if (counted['count'] != len(counted['tokens']) or counted['max_model_len'] != 131072):
            raise ValueError('REF tokenizer count/window differs')
        return {'prompt_tokens': counted['count'], 'input_ids': counted['tokens']}
    ledger = SmokeLedger(folder / 'smoke-ledger.json')
    tool_observed = False
    for ordinal in (1, 2):
        if ordinal == 1:
            proof = measure(request)
        else:
            request, proof = bounded_prompt(request, measure, 98304 if arm == 'REF' else 16384)
        reservation = proof['prompt_tokens'] + request['max_tokens']
        ledger.prepare(ordinal, proof['prompt_tokens'], request['max_tokens'])
        write(folder / f'request-{ordinal}.json', {'request': request, 'exact_count': proof,
              'reserved_tokens': reservation, 'dispatch_evidence': 'smoke-ledger.json'})
        ledger.dispatched()
        response = (rpc.call('smoke_generate', request=request) if rpc else
                    http_json('/v1/chat/completions', request, api_key=api_key))
        write(folder / f'response-{ordinal}.json', response)
        usage = response['usage']
        if rpc and len(response['output_ids']) != usage['completion_tokens']:
            raise ValueError('Owner output IDs differ from accounting')
        ledger.settle(usage)
        tool_observed = tool_observed or any(
            choice.get('message', {}).get('tool_calls') for choice in response.get('choices', []))
    summary = ledger.summary()
    return {**summary,
            'maximum_full_input_exercised': summary['calls'][-1]['usage']['prompt_tokens'],
            'real_tool_calls_observed': bool(tool_observed),
            'tool_call_observation_scope': ('actual_REF_API_response' if rpc is None else
                                            'not_assessed_raw_owner_capacity_endpoint'),
            'tool_end_to_end_admission_claimed': False,
            'maximum_output_generated_not_required': True, 'formal_task_episodes': 0,
            'repository_task_material_used': False}


def execute(arm, card, root, *, monitor, seal_path):
    seal = check_seal(json.loads(seal_path.read_bytes()))
    require_monitor(monitor['unit'], pid=os.getpid(), invocation=monitor['invocation_id'])
    folder = root / arm.lower()
    folder.mkdir(exist_ok=False)
    source = source_identity()
    short = ROOT / 'runs/v054-gpu' / uuid.uuid4().hex[:8]
    short.mkdir(parents=True, exist_ok=False)
    cache = folder / 'cache'
    cache.mkdir()
    env = ['HF_HUB_OFFLINE=1', 'TRANSFORMERS_OFFLINE=1', 'HF_DATASETS_OFFLINE=1',
           'LITELLM_LOCAL_MODEL_COST_MAP=True', 'VLLM_NO_USAGE_STATS=1', 'DO_NOT_TRACK=1',
           'PYTORCH_CUDA_ALLOC_CONF=backend:native', 'NO_PROXY=*', 'no_proxy=*',
           'HTTP_PROXY=', 'HTTPS_PROXY=', 'ALL_PROXY=', 'http_proxy=', 'https_proxy=', 'all_proxy=',
           'PYTHONPATH=' + str(ROOT / 'src') + ':' + str(ROOT), 'TMPDIR=' + str(cache),
           'VLLM_CACHE_ROOT=' + str(cache), 'XDG_CACHE_HOME=' + str(cache),
           'TORCHINDUCTOR_CACHE_DIR=' + str(cache / 'inductor'), 'CUDA_CACHE_PATH=' + str(cache / 'cuda')]
    api_key = None
    if arm == 'REF':
        if len(str(short).encode()) + 1 + 36 > 107:
            raise ValueError('REF Unix IPC directory exceeds the actual kernel pathname limit')
        env += ['TRITON_LIBCUDA_PATH=/opt/host-nvidia', 'VLLM_RPC_BASE_PATH=' + str(short),
                'CUDA_HOME=/usr/local/cuda-13.0']
        api_key = secrets.token_urlsafe(48)
        key_path = folder / 'ref-api-key.private'
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(api_key + '\n')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 18054))  # Never connect to an unrelated resident service.
        command = ['/bin/bash', str(ROOT / 'tools/run_ref_preparation_v054.sh'), '--write-project',
                   '--gpu', str(card['index']), '/usr/bin/env', *env,
                   str(ROOT / 'runs/software-benchmark-v054/ref-venv/bin/python'),
                   str(ROOT / 'tools/start_ref_capacity_server_v054.py'),
                   '--api-key-file', str(key_path), '--', *ref_argv()[2:]]
    else:
        contract = json.loads(MATCH_CONFIG.read_text())['contract']
        if contract != seal['match_contract']:
            raise ValueError('MATCH contract differs from the sealed preparation configuration')
        binding = {'version': 'software-learning-resources-v0.50-r3',
                   'gpu_index': card['index'], 'gpu_uuid': card['uuid'],
                   'sampled_free_mib': card['free_mib'],
                   'target_mib': min(73728, card['free_mib'] - 1024)}
        env += ['PROWORKSIM_V053_GPU_BINDING=' + json.dumps(binding),
                'PYTORCH_ALLOC_CONF=backend:native']
        contract_path = folder / 'contract.json'
        write(contract_path, contract)
        permit = folder / 'load-admission.json'
        write(permit, {'model_loading_authorized': True, 'formal_execution_authorized': False,
                      'model_manifest': source['model_manifest'],
                      'contract_sha256': hashlib.sha256(encoded(contract)).hexdigest(),
                      'maximum_synthetic_requests': 2, 'card': card})
        command = [str(ROOT / 'tools/run_benchmark_runtime_v054.sh'), '--write-project', '--gpu', str(card['index']),
                   '/usr/bin/env', *env, str(ROOT / 'runs/v016-sdk/resident-venv/bin/python'),
                   str(ROOT / 'tools/serve_benchmark_owner_v054.py'),
                   '--socket', str(short / 'owner.sock'), '--model-local', str(MODEL),
                   '--model-manifest', str(MODEL / 'proworksim-manifest.json'),
                   '--contract', str(contract_path), '--output', str(folder / 'owner-service'),
                   '--identity-output', str(folder / 'owner-identity.json'),
                   '--verified-source-receipt', str(SOURCE), '--allow-gpu-load',
                   '--load-admission', str(permit), '--capacity-smoke-only', '--max-smoke-requests', '2']
    unit = 'proworksim-v054-model-preparation-' + uuid.uuid4().hex[:12] + '.service'
    record = {'arm': arm, 'status': 'starting', 'started_utc': now(), 'source': source,
              'card': card, 'unit': unit, 'argv': command, 'formal_execution_authorized': False,
              'monitor': monitor, 'source_seal': reference(seal_path),
              'formal_task_episodes': 0, 'numerical_configuration_changed': False}
    write(folder / 'receipt.json', record)
    process = registered = None
    try:
        launch = folder / 'service-launch.json'
        write(launch, {'unit': unit, 'monitor': monitor, 'seal': reference(seal_path),
                       'arm': arm, 'card': card, 'command': command,
                       'lease_receipt': str(folder / 'service-lease.json')})
        with (folder / 'server.log').open('xb') as log:
            process = subprocess.Popen(['systemd-run', '--user', '--quiet', '--pipe', '--wait',
                '--unit=' + unit, '--property=KillMode=control-group', '--property=TimeoutStopSec=30',
                '--property=SendSIGKILL=yes', '--property=RuntimeMaxSec=5400',
                '--property=BindsTo=' + monitor['unit'], '--property=After=' + monitor['unit'],
                '--', sys.executable, str(ROOT / 'tools/run_model_capacity_service_v054.py'),
                '--launch', str(launch), '--launch-sha256', reference(launch)['sha256']],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            registered = register_model(unit, process, monitor)
            record['registered_service'] = registered
            write(folder / 'receipt.json', record)
            deadline = time.monotonic() + 1800
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Model service exited before readiness; see retained log')
                if time.monotonic() >= deadline:
                    raise TimeoutError('Model service startup exceeded preparation bound')
                if arm == 'REF':
                    try:
                        models = http_json('/v1/models', timeout=2, api_key=api_key)
                    except (OSError, ValueError, http.client.HTTPException):
                        time.sleep(2)
                        continue
                    if not any(m['id'] == 'raw-qwen3.5-9b-v054-ref' and m['max_model_len'] == 131072
                               for m in models['data']):
                        raise ValueError('Actual REF service model or window differs')
                    record['service_models'] = models
                    rpc = None
                    break
                ready = folder / 'owner-service/service-ready.json'
                if ready.exists():
                    identity = json.loads((folder / 'owner-identity.json').read_text())
                    if not identity['actual_CalibrationActor'] or not identity['original_generate_native']:
                        raise ValueError('Expected the original actual owner numerical path')
                    if identity['contract'] != seal['match_contract']:
                        raise ValueError('Loaded owner contract differs from the sealed contract')
                    rpc = OwnerRPC(short / 'owner.sock', identity)
                    rpc.call('begin', slot={'slot_id': 'synthetic-v054-capacity-match', 'arm': 'MATCH',
                             'seed': 202610210541}, claim_id=uuid.uuid4().hex, started=time.monotonic())
                    record['owner_identity'] = identity
                    break
                time.sleep(2)
            record['transport'] = check_transport(arm, folder, rpc, api_key=api_key)
            if rpc:
                record['owner_close'] = rpc.call('finish', entries=[])
            record['status'] = 'capacity_and_synthetic_accounting_passed'
    except BaseException as error:
        record.update(status='technical_unknown_no_automatic_replay', error=repr(error),
                      incomplete_generation_usage_not_zeroed=True)
    finally:
        old_term = signal.signal(signal.SIGTERM, signal.SIG_IGN)
        old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
        ledger_path = folder / 'smoke-ledger.json'
        if ledger_path.exists():
            record['partial_or_complete_accounting'] = json.loads(ledger_path.read_bytes())
        if process is not None:
            try:
                if registered is None:
                    state = unit_state(unit)
                    if state.get('InvocationID') and state.get('ControlGroup'):
                        registered = {'unit': unit, 'invocation_id': state['InvocationID'],
                                      'main_pid': int(state['MainPID']), 'cgroup': state['ControlGroup']}
                if registered is None:
                    process.wait(timeout=35)
                    record['stopped_service'] = {'unit': unit, 'never_registered': True,
                                                 'outer_launcher_reaped': True}
                else:
                    record['stopped_service'] = stop_registered(registered, process)
            except Exception as error:
                record.update(status='cleanup_unknown', cleanup_error=repr(error))
        record['finished_utc'] = now()
        write(folder / 'receipt.json', record)
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--inspect-only', action='store_true')
    parser.add_argument('--seal-only', action='store_true')
    parser.add_argument('--modes', nargs='+', choices=('MATCH', 'REF'), default=['MATCH', 'REF'])
    parser.add_argument('--monitor-unit', default=DEFAULT_MONITOR)
    parser.add_argument('--maximum-wait-hours', type=float, default=96)
    args = parser.parse_args()
    if not 0 < args.maximum_wait_hours <= 96:
        raise ValueError('Preparation resource waiting is bounded by 96 hours')
    if args.seal_only:
        value = create_seal(args.output, args.monitor_unit, args.modes)
        print(json.dumps({'sealed': True, 'source_seal': reference(args.output / 'source-seal.json'),
                          'files': len(value['files']), 'model_loads': 0}))
        return 0
    if args.inspect_only:
        rows = gpu_rows()
        value = {'at_utc': now(), 'source': source_identity(), 'gpu_observation': rows,
                 'eligible_REF': eligible(rows, 'REF'), 'eligible_MATCH': eligible(rows, 'MATCH'),
                 'ref_argv': ref_argv(), 'model_loads': 0, 'generation_calls': 0,
                 'formal_execution_authorized': False}
        write(args.output / 'inspection.json', value)
        print(json.dumps({key: value[key] for key in ('at_utc', 'eligible_REF', 'eligible_MATCH', 'model_loads')}))
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    seal_path = args.output / 'source-seal.json'
    seal = check_seal(json.loads(seal_path.read_bytes()))
    if seal['monitor_unit'] != args.monitor_unit:
        raise ValueError('Capacity monitor differs from the sealed service name')
    if seal.get('modes_to_run') != args.modes or len(set(args.modes)) != len(args.modes):
        raise ValueError('Capacity modes differ from the sealed non-repeating preparation')
    owner = require_monitor(args.monitor_unit, pid=os.getpid())
    locks = ROOT / 'runs/v054-gpu/locks'
    locks.mkdir(parents=True, exist_ok=True)
    with ((args.output / 'monitor.lock').open('a+b') as monitor,
          (locks / 'capacity-preparation-monitor.lock').open('a+b') as global_monitor):
        for handle in (monitor, global_monitor):
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = args.output / 'state.json'
        if path.exists():
            state = json.loads(path.read_text())
            if state.get('active') or state.get('status') == 'technical_unknown':
                raise ValueError('Previous model startup cannot be automatically replayed')
        else:
            state = {'started_utc': now(), 'deadline_epoch': time.time() + args.maximum_wait_hours * 3600,
                     'results': {}, 'active': None, 'formal_task_episodes': 0,
                     'formal_execution_authorized': False, 'maximum_preparation_residents': 1,
                     'maximum_requests_per_mode': 2, 'model_payload_rehashed': False,
                     'source_seal': reference(seal_path)}
            state['modes_to_run'] = args.modes
        if state.get('source_seal') != reference(seal_path):
            raise ValueError('Previous preparation state belongs to another source seal')
        state['monitor'] = owner
        source_identity()
        def terminate(number, _frame):
            raise SystemExit(128 + number)
        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        try:
            while time.time() < state['deadline_epoch']:
                if all(arm in state['results'] for arm in args.modes):
                    state['status'] = 'preparation_capacity_complete_not_formal_execution'
                    write(path, state)
                    return 0
                rows = gpu_rows()
                state.update(status='waiting_for_eligible_gpu', last_observed_utc=now(), gpu_observation=rows)
                dispatched = False
                for arm in args.modes:
                    if arm in state['results']:
                        continue
                    for card in eligible(rows, arm):
                        # Probe only; the actual service owns all locks for its
                        # lifetime. No parent lease is held across startup.
                        from proworksim.software_benchmark_gpu_lease_v054 import GpuLease
                        try:
                            with (locks / 'capacity-preparation-single-resident.lock').open('a+b') as probe:
                                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                lease = GpuLease(card['uuid'])
                                lease.close()
                        except BlockingIOError:
                            continue
                        fresh = [row for row in gpu_rows() if row['uuid'] == card['uuid']]
                        if not eligible(fresh, arm):
                            continue
                        check_seal(seal)
                        state.update(active={'arm': arm, 'card': fresh[0]}, status='preparation_running')
                        write(path, state)
                        result = execute(arm, fresh[0], args.output, monitor=owner, seal_path=seal_path)
                        state['results'][arm], state['active'] = result, None
                        if result['status'] != 'capacity_and_synthetic_accounting_passed':
                            state['status'] = 'technical_unknown'
                            write(path, state)
                            return 1
                        dispatched = True
                        break
                    if dispatched:
                        break
                if all(arm in state['results'] for arm in args.modes):
                    state['status'] = 'preparation_capacity_complete_not_formal_execution'
                elif dispatched:
                    state['status'] = 'waiting_for_next_mode_gpu'
                write(path, state)
                if all(arm in state['results'] for arm in args.modes) or not args.watch:
                    return 0
                time.sleep(60)
            state['status'] = 'resource_wait_expired_no_formal_tasks_started'
            write(path, state)
            return 2
        except BaseException as error:
            state.update(status='technical_unknown' if state['active'] else 'monitor_stopped',
                         monitor_error_type=type(error).__name__, monitor_error=str(error))
            write(path, state)
            raise


if __name__ == '__main__':
    raise SystemExit(main())
