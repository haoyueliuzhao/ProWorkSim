"""Exercise the deployed admission binding, not only its standalone reader."""
import importlib.util
import json
from pathlib import Path
import threading

import pytest

from proworksim import software_benchmark_resources_v076 as frozen
from proworksim import software_benchmark_resources_v079 as api_old
from proworksim import software_benchmark_resources_v080 as qwen_old
from proworksim import software_benchmark_resources_v084 as revised
from proworksim.software_benchmark_episodes_v084 import EpisodeBindings

ROOT = Path(__file__).resolve().parents[1]


def physical():
    return {'memory_available_bytes': 1024*frozen.GIB, 'disk_free_bytes': 2048*frozen.GIB,
            'cpu_sample_fresh': True, 'host_cpu_utilization_percent': 20}


def actor(index=1):
    return {'key': f'actor-{index}', 'spec': {'role': 'actor',
        'slot_id': f'v064:task:QWEN_REF_B5000K:{index}'},
        'reserved_cpu': 6, 'reserved_memory_bytes': 32*frozen.GIB}


def binding():
    return EpisodeBindings(lambda *a, **kw: {},
        watchdog_guard=lambda: {'fresh': True, 'admit': True}, capacity_probe=physical)


@pytest.mark.parametrize('payload', [b'', b'{"version":', b'\xff', b'[]'])
def test_real_admission_does_not_abort_on_partial_marker(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(revised.safe_pending_pairs, '__kwdefaults__',
                        {'batch_root': tmp_path, 'materialized': None})
    path = tmp_path/'episodes/1/controller-ready.json'
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    b = binding()
    actual = b.primary_policy.admission_snapshot.__globals__
    assert actual['pending_pairs'] is revised.safe_pending_pairs
    assert actual['evaluate'] is revised.evaluate
    assert b.qwen.run_episode.__globals__['policy'] is b.primary_policy
    state = b.primary_policy.admission_snapshot([actor()])
    assert state['pending_pair_keys'] == ['actor-1']
    assert state['pending_status_observation_issues'][0]['global_stop_required'] is False
    assert state['maximum_starting_pairs'] == 8
    path.write_text(json.dumps({'version': 'v064-private-native-controller-r1',
        'trusted_SDK_imports_complete': True, 'model_calls': 0}))
    ready = b.primary_policy.admission_snapshot([actor()])
    assert ready['pending_pair_keys'] == []
    assert ready['pending_status_observation_issues'] == []
    # Once fully validated, the materialized cache must survive disappearance.
    path.unlink()
    assert b.primary_policy.admission_snapshot([actor()])['pending_pair_keys'] == []


def test_frozen_bindings_preserved_and_regression_witness():
    # Document the exact old fault while proving this adapter never mutates it.
    before = frozen.pending_pairs
    for old in (api_old, qwen_old):
        policy = old.policy(lambda *a, **kw: {}, watchdog_guard=lambda: {}, capacity_probe=physical)
        assert policy.admission_snapshot.__globals__['pending_pairs'].__code__ is before.__code__
    b = binding()
    assert frozen.pending_pairs is before
    assert frozen.MAX_STARTING_PAIRS == 4
    assert b.primary_policy.admission_snapshot.__globals__['pending_pairs'] is revised.safe_pending_pairs


def test_qwen_scope_still_refuses_api_identity(tmp_path):
    with pytest.raises(PermissionError, match='only Qwen'):
        binding().primary_policy._write_claim(tmp_path/'claim.json',
            {'spec': {'role': 'actor', 'slot_id': 'v064:task:DEEPSEEK_REF_B5000K:1'}})
    assert not (tmp_path/'claim.json').exists()


def test_new_owner_keeps_four_generation_one_grader_and_frozen_models():
    spec = importlib.util.spec_from_file_location('v084_test_runner', ROOT/'tools/run_qwen_recovery_v084.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    stop = threading.Event()
    with runner.executors(stop) as (generation, grading):
        assert generation._max_workers == 4 and grading._max_workers == 1
    bound = runner.binding()
    assert bound.__globals__['scope'].OLD_UNIT == 'proworksim-v080-primary.service'
    assert bound.__globals__['scope'].MEMORY_BYTES == 32*frozen.GIB
    assert 'proworksim.software_benchmark_episodes_v084' in bound.__code__.co_names
