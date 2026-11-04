"""Object-order regression and strict negative argument controls, CPU only."""
from __future__ import annotations

import copy
import itertools
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_tooling_v117 as previous
from proworksim import software_benchmark_tooling_v120 as fixed


class Action:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
    def model_dump(self, **_):
        return copy.deepcopy(self.value)
    @classmethod
    def model_validate(cls, value):
        return cls(dict(reversed(list(value.items()))))


def test_actual_schema_six_tools_accept_object_order_with_or_without_explicit_null():
    schemas = {row['name']: row['parameters'] for row in fixed.tool_definitions({})}
    examples = {
        'list_files': {'path_prefix': 'pkg', 'cursor': None, 'patch_id': 'patch-1'},
        'read_file': {'max_lines': 30, 'path': 'pkg/file.py', 'cursor': None, 'start_line': 2},
        'search_file': {'text': 'needle', 'cursor': None, 'path': 'pkg/file.py'},
        'diff_workspace': {'cursor': None}, 'read_task': {'cursor': None},
        'search_repository': {'path_prefix': 'pkg', 'cursor': None, 'text': 'needle'},
    }
    for name, example in examples.items():
        for with_null in (False, True):
            original = {key: value for key, value in example.items() if with_null or key != 'cursor'}
            for order in itertools.permutations(original):
                pending = {key: original[key] for key in order}
                calls = []
                worker = SimpleNamespace(_pending={'name': name, 'arguments': pending, 'tool_call_id': 'real-id'},
                    _executions=0, _emit=lambda *_: None)
                def gateway(action, _conversation):
                    assert action.model_dump() == pending
                    calls.append(copy.deepcopy(pending))
                executor = fixed.NullableCursorExecutor(gateway, worker, name, schemas[name])
                # Match an SDK model's declared field order, dropping only null.
                projected = {key: original[key] for key in schemas[name]['properties']
                             if key in original and original[key] is not None}
                executor(Action(projected))
                assert calls == [pending]
                assert worker._pending['arguments'] == pending


def test_original_wrapper_reproduces_false_rejection_but_values_and_types_still_strict():
    schema = next(row['parameters'] for row in fixed.tool_definitions({}) if row['name'] == 'search_repository')
    raw = {'path_prefix': 'pylint/checkers/similar.py', 'text': 'min_lines'}
    projected = {'text': 'min_lines', 'path_prefix': 'pylint/checkers/similar.py'}
    calls = []
    worker = SimpleNamespace(_pending={'name': 'search_repository', 'arguments': raw, 'tool_call_id': 'original'},
        _executions=0, _emit=lambda *_: None)
    def callback(action, _):
        calls.append(action.model_dump())
    with pytest.raises(ValueError, match='SDK changed'):
        previous._NullableCursorExecutor(callback, worker, 'search_repository', schema)(Action(projected))
    assert not calls
    executor = fixed.NullableCursorExecutor(callback, worker, 'search_repository', schema)
    executor(Action(projected))
    assert len(calls) == 1
    for wrong in ({'text': 'different', 'path_prefix': raw['path_prefix']},
                  {**projected, 'cursor': None}, {**projected, 'arbitrary': True}, {'text': 'min_lines'}):
        with pytest.raises(ValueError, match='SDK changed'):
            executor(Action(wrong))
    worker._pending['arguments'] = {**raw, 'cursor': 'nonempty-cursor'}
    with pytest.raises(ValueError, match='SDK changed'):
        executor(Action(projected))
    assert len(calls) == 1
    assert fixed.canonical_arguments({'v': True}) != fixed.canonical_arguments({'v': 1})
    assert fixed.canonical_arguments({'v': 1}) != fixed.canonical_arguments({'v': '1'})
    assert fixed.canonical_arguments({'v': [1, 2]}) != fixed.canonical_arguments({'v': [2, 1]})


def test_equivalent_number_representation_reaches_gateway_with_original_raw_value():
    schema = next(row['parameters'] for row in fixed.tool_definitions({}) if row['name'] == 'read_file')
    raw = {'start_line': 1.0, 'path': 'pkg/file.py'}
    calls = []
    worker = SimpleNamespace(_pending={'name': 'read_file', 'arguments': raw, 'tool_call_id': 'original'},
        _executions=0, _emit=lambda *_: None)
    def gateway(action, _):
        assert action.model_dump() == worker._pending['arguments']
        calls.append(copy.deepcopy(worker._pending['arguments']))
    fixed.NullableCursorExecutor(gateway, worker, 'read_file', schema)(Action({'path': 'pkg/file.py', 'start_line': 1}))
    assert len(calls) == 1 and type(calls[0]['start_line']) is float
    assert fixed.canonical_arguments({'v': 1}) == fixed.canonical_arguments({'v': 1.0})
