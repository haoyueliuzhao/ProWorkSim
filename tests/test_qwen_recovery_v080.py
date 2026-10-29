import importlib.util
import json
from pathlib import Path
import threading

import pytest

from proworksim import software_benchmark_resources_v076 as original
from proworksim import software_benchmark_resources_v080 as revised
from proworksim.software_benchmark_episodes_v080 import EpisodeBindings
from proworksim.software_benchmark_candidates_v054 import write_new

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def actor(index=1):
    return {'key': 'actor-'+str(index), 'spec': {'role': 'actor', 'slot_id': 'slot-'+str(index)},
            'reserved_cpu': 6, 'reserved_memory_bytes': 32*original.GIB}


def ready():
    return {'version': 'v064-private-native-controller-r1',
            'trusted_SDK_imports_complete': True, 'model_calls': 0}


@pytest.mark.parametrize('payload', [b'', b'{"version":', b'\xff', b'[]'])
def test_partial_status_stays_pending_then_complete_is_admitted(tmp_path, payload):
    path = tmp_path/'episodes/1/controller-ready.json'
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    cache = set()
    observed = revised.safe_pending_pairs([actor()], batch_root=tmp_path, materialized=cache)
    assert observed == ['actor-1'] and not cache
    assert observed.observation_issues[0]['global_stop_required'] is False
    path.write_text(json.dumps(ready()))
    assert revised.safe_pending_pairs([actor()], batch_root=tmp_path, materialized=cache) == []
    assert cache == {('actor-1', 'slot-1')}


def test_unqualified_or_entered_marker_never_becomes_ready(tmp_path):
    path = tmp_path/'episodes/1/controller-ready.json'
    path.parent.mkdir(parents=True)
    for patch in ({'version': 'other'}, {'trusted_SDK_imports_complete': False}, {'model_calls': 1}):
        path.write_text(json.dumps({**ready(), **patch}))
        assert revised.safe_pending_pairs([actor()], batch_root=tmp_path) == ['actor-1']
    with pytest.raises(ValueError, match='identity'):
        revised.safe_pending_pairs([{'key': 'actor-../1', 'spec': actor()['spec']}], batch_root=tmp_path)


def test_private_binding_preserves_frozen_reader_and_inputs():
    old_reader = original.pending_pairs
    bindings = EpisodeBindings(lambda *a, **kw: {}, watchdog_guard=lambda: {'fresh': True, 'admit': True})
    assert original.pending_pairs is old_reader
    assert original.MAX_STARTING_PAIRS == 4
    assert bindings.primary_policy.admission_snapshot.__closure__
    assert bindings.qwen.run_episode.__globals__['policy'] is bindings.primary_policy
    assert bindings.primary_policy.CONSTRAINTS['generation_pair_reserved_memory_bytes'] == 32*original.GIB


def test_qwen_policy_refuses_API_creation_identity_before_writing(tmp_path):
    policy = revised.policy(lambda *a, **kw: {}, watchdog_guard=lambda: {'fresh': True, 'admit': True})
    with pytest.raises(PermissionError, match='only Qwen'):
        policy._write_claim(tmp_path/'foreign.json', {'spec': {'role': 'actor',
            'slot_id': 'v064:task:DEEPSEEK_REF_B5000K:1'}})
    assert not (tmp_path/'foreign.json').exists()


def test_recovered_terminal_result_requires_original_identity_and_cleanup(tmp_path):
    prep = module('v080_prepare_fixture', 'prepare_qwen_recovery_v080.py')
    row = {'slot_id': 'slot', 'configuration': {'config': 1}, 'condition_id': 'condition'}
    quiet = write_new(tmp_path/'quiet.json', {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False})
    result = {**row, 'model_key': 'QWEN', 'status': 'technical_unknown', 'quiescence': quiet, 'retained_objects': []}
    ref = write_new(tmp_path/'result.json', result)
    assert prep.terminal_result(row, ref)['status'] == 'technical_unknown'
    with pytest.raises(ValueError, match='identity'):
        prep.terminal_result({**row, 'slot_id': 'another'}, ref)


def test_one_score_worker_and_four_generation_workers_are_enforced():
    runner = module('v080_runner_fixture', 'run_qwen_recovery_v080.py')
    stop = threading.Event()
    with runner.executors(stop) as (generation, scoring):
        assert generation._max_workers == 4 and scoring._max_workers == 1
    assert stop.is_set()
    bound = runner.binding()
    assert bound.__globals__['scope'].MEMORY_BYTES == 32*original.GIB
    assert bound.__globals__['executors'] is runner.executors
    assert 'proworksim.software_benchmark_episodes_v080' in bound.__code__.co_names
