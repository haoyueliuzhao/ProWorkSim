"""Affected v062 model scope boundaries; no services, network or GPU access."""
from collections import deque
import copy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_dispatch_v062 as policy
from proworksim import software_benchmark_model_capacity_v062 as capacity
from proworksim import software_benchmark_model_fifo_v062 as fifo
from proworksim import software_benchmark_ref_resident_v062 as resident
from proworksim.software_benchmark_ref_budget_v062 import CapabilityBudgetRefAdapter
from proworksim.software_benchmark_candidates_v054 import write_new


def test_frozen_inference_changes_only_owned_port_and_retains_admitted_reservation():
    original = resident.original_server_arguments(18171)
    actual = resident.server_arguments(18171)
    assert [(a, b) for a, b in zip(original, actual, strict=True) if a != b] == [('0.8', '0.6')]
    assert resident.PORTS == fifo.PORTS == capacity.PORTS == (18171, 18172)
    assert resident.RUNS == policy.BATCH_ROOT / 'residents'
    assert resident.MINIMUM_FREE_MIB == policy.CONSTRAINTS['minimum_free_gpu_mib'] == 50176
    assert capacity.NEUTRAL_TOTAL_TOKENS * 2 == policy.CONSTRAINTS['neutral_model_preparation_total_tokens']
    assert [resident.unit_name(i) for i in range(2)] == policy.CONSTRAINTS['new_owned_user_units'][:2]
    for index in (-1, 2, True):
        with pytest.raises(ValueError):
            resident.unit_name(index)


def test_private_python_is_reused_without_old_cache_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(resident, 'RUNS', tmp_path)
    monkeypatch.setattr(resident, 'existing_runtime', lambda: {'reused': True})
    calls = []
    def launch(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return ['existing-loader', *arguments], {'CPATH': 'existing-private-headers', 'CUDA_VISIBLE_DEVICES': 'GPU-fixture'}
    monkeypatch.setattr(resident, 'launch_spec', launch)
    cache = tmp_path / 'model-0/cache'
    command, env = resident.model_launch_spec(['fixed-script'], index=0, gpu_uuid='GPU-fixture', cache=cache)
    assert calls == [(['fixed-script'], {'gpu_uuid': 'GPU-fixture', 'cache': None})]
    assert command == ['existing-loader', 'fixed-script'] and env['CPATH'] == 'existing-private-headers'
    assert all(Path(env[key]).is_relative_to(cache) for key in (
        'TMPDIR', 'VLLM_CACHE_ROOT', 'XDG_CACHE_HOME', 'TORCHINDUCTOR_CACHE_DIR', 'CUDA_CACHE_PATH'))
    with pytest.raises(ValueError, match='exact v062 resident'):
        resident.model_launch_spec(['fixed-script'], index=0, gpu_uuid='GPU-fixture', cache=tmp_path / 'model-1/cache')
    assert len(calls) == 1 and not cache.exists()


def test_pending_authorization_blocks_service_creation_before_side_effects(monkeypatch):
    from proworksim.software_benchmark_shared_server_hold_v057 import SharedServerHold
    def denied(*args, **kwargs):
        raise SharedServerHold('pending fixture authorization')
    monkeypatch.setattr(resident, 'require_v062_allowed', denied)
    monkeypatch.setattr(resident, 'gpu_capacity', lambda: pytest.fail('Never inspect GPU when authorization is pending'))
    monkeypatch.setattr(resident, 'prepare_runtime', lambda: pytest.fail('Never alter or prepare runtime'))
    for operation in (resident.start_residents, resident.ready_residents,
                      lambda: resident.make_spec(0, {}), lambda: resident.run_service('missing')):
        with pytest.raises(SharedServerHold, match='pending'):
            operation()


def test_fixed_owned_unit_command_keeps_bounds_and_no_restart(monkeypatch):
    monkeypatch.setattr(resident, 'validate_spec', lambda value: value)
    spec = {'unit': resident.unit_name(1), 'ownership_token': 'b' * 32,
            'cpu_affinity': list(range(36, 48)), 'root': str(resident.RUNS / 'model-1')}
    command = resident.unit_command(spec)
    assert '--description=ProWorkSim v062 ' + 'b' * 32 in command
    assert '--property=Restart=no' in command and '--property=MemoryMax=96G' in command
    assert '--property=CPUQuota=1200%' in command and '--property=TasksMax=2048' in command
    assert str(resident.ROOT / 'tools/serve_ref_capability_v062.py') in command
    assert not any('v061-model' in value or 'serve_ref_recovery_v061' in value for value in command)
    actual = {'memory.max': str(96 * resident.GIB), 'memory.swap.max': '0', 'pids.max': '2048', 'cpu.max': None}
    assert not resident.validate_cpu_memory_limits(actual, range(36, 48), range(36, 48))['cpu_cgroup_controller_available']


@pytest.mark.parametrize('description', ['ProWorkSim v061 ' + 'b' * 32, 'ProWorkSim v062 ' + 'a' * 32])
def test_stop_rejects_old_version_or_wrong_current_nonce(tmp_path, monkeypatch, description):
    monkeypatch.setattr(resident, 'RUNS', tmp_path)
    root = tmp_path / 'model-0'
    root.mkdir()
    (root / 'spec.json').write_text('{}')
    monkeypatch.setattr(resident, 'validate_spec', lambda _: {'unit': resident.unit_name(0), 'ownership_token': 'b' * 32})
    monkeypatch.setattr(resident, 'user_manager_environment', lambda: {})
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=f'Description={description}\nLoadState=loaded\nActiveState=active\n')
    monkeypatch.setattr(resident.subprocess, 'run', run)
    assert not resident.stop_residents()[0]['owned_unit_stopped']
    assert len(calls) == 1 and 'stop' not in calls[0]


def test_fifo_bridge_admits_only_new_slot_and_retains_single_request_accounting(monkeypatch):
    admitted = []
    monkeypatch.setattr(policy, 'require_v062_allowed', lambda *args, **kwargs: admitted.append((args, kwargs)))
    stop = threading.Event()
    frames = deque([fifo.encoded_frame({'type': 'model_bridge_ready', 'version': fifo.VERSION}),
                    fifo.encoded_frame({'id': 1, 'path': '/tokenize', 'payload': {}})])
    sent = []
    class Channel:
        def readline(self, deadline):
            return frames.popleft()
        def write(self, value):
            sent.append(fifo.decode_frame(value))
    def post(*args):
        stop.set()
        return {'tokens': [1], 'count': 1}
    slot = 'v062:synthetic:FIX5M:1'
    client = SimpleNamespace(port=18171, timeout_seconds=1800, post=post)
    result = fifo.serve_model_channel(Channel(), endpoint='unused', key_file='unused',
        deadline=time.monotonic() + 10, stop_event=stop, slot_id=slot, transport=client)
    assert admitted == [(('v062.model.bridge',), {'slot_id': slot})]
    assert result['requests'] == 1 and result['status'] == 'stopped_after_controller'
    assert sent[-1] == {'op': 'stop'}
    client.port = 18161
    with pytest.raises(ValueError, match='admitted port'):
        fifo.serve_model_channel(Channel(), endpoint='unused', key_file='unused',
            deadline=time.monotonic() + 10, stop_event=stop, slot_id=slot, transport=client)


def test_new_capacity_root_and_one_neutral_call_per_resident(tmp_path, monkeypatch):
    monkeypatch.setattr(capacity, 'BATCH_ROOT', tmp_path)
    monkeypatch.setattr(policy, 'require_v062_allowed', lambda *args, **kwargs: {})
    root = tmp_path / 'residents/model-0'
    root.mkdir(parents=True)
    args = resident.server_arguments(18171)
    spec = {'index': 0, 'root': str(root), 'port': 18171, 'endpoint': 'http://127.0.0.1:18171',
            'api_key_file': str(root / 'api-key.private'), 'model_revision': capacity.MODEL_REVISION,
            'model_manifest': {'sha256': capacity.MANIFEST_SHA}, 'server_arguments': args}
    line = b'GPU KV cache size: 850,000 tokens, Maximum concurrency for 131,072 tokens per request: 6.49x\n'
    (root / 'service.stdout.log').write_bytes(line)
    (root / 'service.stderr.log').write_bytes(b'')
    qualified = capacity.qualify_capacity(spec)
    calls = []
    def post(path, body):
        calls.append(path)
        if path == '/tokenize':
            return {'tokens': [1, 2], 'count': 2, 'max_model_len': 131072}
        return {'model': capacity.MODEL_NAME, 'choices': [{'message': {'content': 'READY'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}
    client = SimpleNamespace(port=18171, timeout_seconds=1800, post=post)
    receipt = capacity.run_neutral_probe(spec, qualified, transport=client)
    assert json.loads(Path(receipt['path']).read_bytes())['known_actual_tokens'] == 3
    with pytest.raises(FileExistsError):
        capacity.run_neutral_probe(spec, qualified, root / 'other-probe', transport=client)
    assert calls == ['/tokenize', '/v1/chat/completions']
    assert capacity.neutral_request()['seed'] == 20261026062
    with pytest.raises(ValueError, match='exact raw'):
        capacity.validate_spec(spec | {'root': str(tmp_path / 'residents-compiler-r4/model-0')})


def test_adapter_reuses_budget_algorithm_with_only_admitted_new_identities(tmp_path):
    condition = json.loads((resident.ROOT / 'config/v056-condition-REF_B5000K.json').read_bytes())
    identity = {'model_revision': capacity.MODEL_REVISION, 'vllm_version': '0.32.0', 'raw_release': True,
                'adapter_sha256': None, 'model_manifest_sha256': capacity.MANIFEST_SHA,
                'context_limit': 131072, 'max_output_tokens': 32768, 'service_admission_complete': True,
                'deployment_version': resident.VERSION, 'port': 18171}
    transport = SimpleNamespace(port=18171)
    adapter = CapabilityBudgetRefAdapter(transport=transport, folder=tmp_path / 'ledger',
        slot_id='v062:synthetic:FIX5M:7', seed=7, service_identity=identity, condition=condition)
    assert adapter.ledger.token_limit == 5_000_000 and adapter.ledger.attempt_limit == 512
    assert adapter.request_defaults['max_tokens'] == 32768
    assert adapter.request_defaults['chat_template_kwargs'] == {'enable_thinking': True}
    for changes in ({'slot_id': 'old:synthetic'}, {'seed': 8},
                    {'service_identity': identity | {'deployment_version': 'v061-owned-user-ref-resident-r4-private-compiler'}},
                    {'service_identity': identity | {'port': 18161}}):
        kwargs = {'transport': transport, 'folder': tmp_path / 'forbidden', 'slot_id': 'v062:synthetic:FIX5M:7',
                  'seed': 7, 'service_identity': identity, 'condition': copy.deepcopy(condition)} | changes
        with pytest.raises(ValueError):
            CapabilityBudgetRefAdapter(**kwargs)
    assert not (tmp_path / 'forbidden').exists()


def test_spec_validation_binds_new_runtime_scope_before_any_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(resident, 'RUNS', tmp_path / 'residents')
    monkeypatch.setattr(resident, 'RPC_ROOT', tmp_path / 'short')
    monkeypatch.setattr(resident, 'require_v062_allowed', lambda *args, **kwargs: {})
    monkeypatch.setattr(resident, 'cpu_set', lambda role, index: ','.join(map(str, range(24 + index * 12, 36 + index * 12))))
    model = tmp_path / 'model'
    model.mkdir()
    model_ref = write_new(model / 'proworksim-manifest.json', {'synthetic': True})
    monkeypatch.setattr(resident, 'MODEL', model)
    monkeypatch.setattr(resident, 'MANIFEST_SHA', model_ref['sha256'])
    metadata = tmp_path / 'METADATA'
    metadata.write_text('Version: 0.32.0\n')
    monkeypatch.setattr(resident, 'VLLM_METADATA', metadata)
    monkeypatch.setattr(resident, 'existing_runtime', lambda: {'reused_private_runtime': True})
    card = {'gpu_index': 3, 'gpu_uuid': 'GPU-12345678-1234-1234-1234-123456789abc'}
    spec = resident.make_spec(0, card)
    assert resident.validate_spec(spec) == spec
    for change in ({'port': 18161}, {'unit': 'proworksim-v061-model-0.service'},
                   {'memory_max_bytes': 97 * resident.GIB}, {'cpu_affinity': list(range(13))},
                   {'rpc_base_path': str(tmp_path / 'old-v061')}, {'automatic_restart': True}):
        with pytest.raises(ValueError):
            resident.validate_spec(spec | change)
    with pytest.raises(ValueError, match='Never restart'):
        resident.make_spec(0, card)
