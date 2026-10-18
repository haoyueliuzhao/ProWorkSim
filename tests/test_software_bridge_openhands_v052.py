"""Only new synthetic OH/reference seams; no model weights or real task content."""
import copy
import json
from pathlib import Path

import pytest

from proworksim import software_bridge_openhands_v052 as oh
from proworksim.software_bridge_sources_v052 import run_repository_tests
from proworksim.storage import digest, json_bytes

PROJECT = Path(__file__).resolve().parents[1]
RUNTIME = PROJECT / 'artifacts/software-bridge-v052/source-qualification/runtime.json'


class SyntheticProvider:
    def __init__(self):
        self.files = {'parse.py': 'def answer():\n    return 0\n',
                      'tests/test_bridge.py': 'from parse import answer\n\ndef test_answer():\n    assert answer() == 1\n'}
        self.runtime = json.loads(RUNTIME.read_bytes())
        self.authoritative_receipts = []
        self._backend = run_repository_tests

    def build_case(self, task_id):
        return {'task_id': task_id, 'files': copy.deepcopy(self.files), 'editable_paths': ['parse.py'],
                'root_goal': 'Fix the synthetic answer function to return one.',
                'source_contract': {'fixture_only': True}}

    def runner_spec(self, task_id):
        return {'task_id': task_id, 'module': 'parse', 'nodeids': ['tests/test_bridge.py::test_answer'],
                'config_relative_path': None, 'cpu_python': self.runtime['python_invocation'],
                'loopback_fixture': None, 'source_roots': ['parse.py'],
                'readonly_paths': ['tests/test_bridge.py'],
                'frozen_test_hashes': {'tests/test_bridge.py': digest(self.files['tests/test_bridge.py'].encode())},
                'initial_production_hashes': {'parse.py': digest(self.files['parse.py'].encode())},
                'initial_file_paths': sorted(self.files), 'accepted_new_production_paths': [],
                'bridge_runtime_ref': oh.ref(RUNTIME)}


class ProgrammedOwner:
    path = 'project'
    contract = {**oh.EXPECTED}

    def __init__(self, replies=(), *, fits=True):
        self.replies = list(replies)
        self.fits = fits
        self.phase = 'idle'
        self.window_id = None
        self.generated = 0
        self.prepared = []
        self.guard_calls = 0
        self.identity = {'raw_release': True, 'checkpoint': None, 'adapter_sha256': None,
                         'policy_version': 'synthetic-only', 'inference_profile_sha256': 'synthetic-only'}

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def prepare_request(self, request):
        self.prepared.append(copy.deepcopy(request))
        native = {'version': 'CPU-only', 'prompt_tokens': 100, 'fits': self.fits,
                  'input_ids': [1] * 100, 'rendered_prompt': json.dumps(request),
                  'actual_prompt_messages': copy.deepcopy(request['messages']),
                  'request_sha256': digest(json_bytes(request)), 'sha256': digest(json_bytes(request))}
        return native['rendered_prompt'], native['actual_prompt_messages'], native

    def generate_native(self, native):
        text = self.replies.pop(0)
        self.generated += 1
        return {'attempt_id': 'synthetic-' + str(self.generated), 'actor_identity': self.freeze_identity(),
                'input': copy.deepcopy(native), 'output_ids': [2], 'raw_generated_text': text,
                'finish_reason': 'stop', 'usage': {'prompt_tokens': 100, 'completion_tokens': 1, 'total_tokens': 101}}

    def capture_evaluation_state(self):
        self.guard_calls += 1
        return {'synthetic': True}

    def begin_window(self, window):
        self.phase, self.window_id = 'collecting', window

    def reseed(self, seed, *, label):
        return {'seed': seed, 'label': label}

    def finish_evaluation(self, entries, output):
        Path(output).mkdir()
        self.phase = 'idle'

    def finish_evaluation_guard(self, before):
        return {'learning_unchanged': True, 'rng_restored_exactly': True, 'fixture_only': True}


def tool(name, **params):
    return '<tool_call><function=' + name + '>' + ''.join(
        '<parameter=' + key + '>' + str(value) + '</parameter>' for key, value in params.items()
    ) + '</function></tool_call>'


def setup(tmp_path):
    provider = SyntheticProvider()
    case = provider.build_case('synthetic-bridge')
    case['runner_spec'] = provider.runner_spec(case['task_id'])
    manifest = tmp_path / 'reference-runtime.json'
    manifest.write_bytes(json_bytes(oh.sdk_provenance()))
    case['reference_runtime'] = oh.ref(manifest)
    worktree = tmp_path / 'worktree'
    worktree.mkdir()
    for name, value in case['files'].items():
        path = worktree / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(value.encode())
    return provider, case, worktree


def collect(tmp_path, owner, **kwargs):
    provider, case, worktree = setup(tmp_path)
    return oh.collect_episode(owner=owner, task_source=case, provider=provider,
        slot_id='v052-synthetic-OH_ref', sampling_seed=202610180521, worktree=worktree,
        episode_folder=tmp_path / 'episode', allow_cpu_fixture=True, **kwargs)


def test_official_conversation_terminal_shared_runner_finish_and_ledger(tmp_path):
    owner = ProgrammedOwner([
        tool('terminal', command='echo SHOULD_NOT_RUN', is_input='true'),
        tool('terminal', command="python -c \"from pathlib import Path; Path('parse.py').write_text('def answer():\\n    return 1\\n')\""),
        tool('terminal', command='bridge_run_tests'),
        tool('finish', message='Synthetic change completed.'),
    ])
    result = collect(tmp_path, owner)
    assert owner.generated == 4
    assert_closed_synthetic_result(result)


def assert_closed_synthetic_result(result):
    assert result['status'] == 'closed' and result['sdk_execution_status'] == 'finished'
    assert result['ledger']['attempts'] == result['ledger']['complete_responses'] == 4
    assert result['ledger']['known_actual_tokens'] == 404
    assert result['ledger']['inflight'] is None
    assert result['fixture_only'] is True and result['formal_native_provider'] is False
    commands = [json.loads(oh.checked(x).read_bytes()) for x in result['tool_commands']]
    assert len(commands) == 3
    assert commands[0]['result']['side_effect'] is False
    assert commands[0]['result']['execution_kind'] == 'unsupported_interactive_request'
    execution = commands[2]['result']['execution']
    assert execution['executed'] is True and execution['returncode'] == 0
    assert execution['tests'][0]['nodeid'] == 'tests/test_bridge.py::test_answer'
    assert execution['tests'][0]['outcome'] == 'passed'
    assert execution['bridge_binding']['sha256']
    requests = [json.loads(oh.checked(call['request']).read_bytes())['request'] for call in result['ledger']['calls']]
    # The second real SDK request contains the previous native action/observation;
    # no external managed worker reconstructs the history.
    assert any(m['role'] == 'tool' for m in requests[1]['messages'])
    assert {t['function']['name'] for t in requests[0]['tools']} == {'terminal', 'finish'}
    description = next(t['function']['description'] for t in requests[0]['tools'] if t['function']['name'] == 'terminal')
    assert 'fresh noninteractive bash' in description and 'no interactive continuation' in description
    assert 'OpenHands' in requests[0]['messages'][0]['content']
    assert json.loads(oh.checked(result['candidate_files']).read_bytes())['parse.py'].endswith('return 1\n')
    assessment = oh.measure_closed(result, row={'condition': 'OH_ref', 'slot_id': result['slot_id'],
        'task_id': result['task_id'], 'seed': result['sampling_seed']}, owner_identity=result['actor_identity'],
        accounting={'started_generations': 4, 'complete_generations': 4, 'known_actual_tokens': 404,
                    'uncertain_reservation_tokens': 0, 'integrity_errors': []})
    assert assessment['decision'] == 'pending'
    assert assessment['issues'] == []
    assert assessment['unresolved'] == ['CPU_fixture_is_not_formal_native_evidence']


def test_initial_capture_actual_official_request_has_no_guard_attempt_or_tool(tmp_path):
    captured = []
    owner = ProgrammedOwner()
    result = collect(tmp_path, owner, initial_capture=lambda request, native: captured.append((request, native)))
    assert result['status'] == 'initial_request_captured' and len(captured) == 1
    assert owner.generated == owner.guard_calls == 0 and owner.phase == 'idle'
    counters = result['capture_counters']
    assert counters['harness_decisions'] is counters['team_decisions'] is None
    assert counters['native_SDK_LLM_entries'] == 1
    assert all(counters[k] == 0 for k in ('adapter_decisions', 'attempts', 'reservation_tokens', 'responses', 'tool_actions', 'model_generations'))
    assert captured[0][0] == json.loads(oh.checked(result['original_request']).read_bytes())
    assert 'candidate_files' not in result


def test_context_preexecution_closes_unique_tree_without_model_or_tool(tmp_path):
    owner = ProgrammedOwner(fits=False)
    result = collect(tmp_path, owner)
    assert result['status'] == 'safe_local_stop'
    assert result['stop_reason'] == 'full_native_context_preexecution_rejection'
    assert result['ledger']['decisions'] == 1 and result['ledger']['attempts'] == owner.generated == 0
    assert result['tool_commands'] == []
    assert result['ledger']['known_actual_tokens'] == 0
    assert result['candidate_lock'] and result['episode_guard']['rng_restored_exactly']
    rejected = json.loads(oh.checked(result['ledger']['preexecution_rejections'][0]).read_bytes())
    assert rejected['generation_started'] is rejected['new_tool_side_effect'] is False


def test_programmed_owner_cannot_claim_formal_raw_reference():
    with pytest.raises(ValueError, match='cannot enter a formal'):
        oh.validate_owner(ProgrammedOwner(), metadata_only=False, allow_cpu_fixture=False)
    owner = ProgrammedOwner()
    owner.identity['checkpoint'] = {'path': '/not/a/raw/model'}
    with pytest.raises(ValueError, match='raw/no-adapter'):
        oh.validate_owner(owner, metadata_only=False, allow_cpu_fixture=True)
