"""No provider/container calls: finish intent, shared guards and original step."""
from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.harness_runtime import SDKStaffRuntime
from proworksim.software_benchmark_finish_review_v110 import (
    FINISH_REVIEW, FinishReviewPolicy, policy_manifest,
)
from proworksim.software_benchmark_native_control_v062 import FINISH_REVIEW as ORIGINAL_REVIEW
from proworksim.software_benchmark_review_runtime_v110 import FinishReviewWorkerMixin, decorate_runtime

STARTED = {'started': 1., 'soft_at': 21601., 'hard_at': 23401.}
LIMITS = {'input_plus_output_tokens': 5_000_000, 'all_model_attempts': 512,
          'agent_decisions': 512, 'soft_seconds': 21600, 'hard_seconds': 23400}


def snapshot(**changes):
    value = {'complete_actual_tokens': 100, 'known_actual_tokens': 100,
             'inflight': None, 'uncertain_reserved_tokens': 0,
             'token_limit': 5_000_000, 'all_model_attempt_limit': 512,
             'agent_decision_limit': 512, 'attempts': 1, 'decisions': 1}
    return {**value, **changes}


def test_shared_policy_is_once_and_does_not_spend_or_reset():
    ledger = snapshot()
    original = copy.deepcopy(ledger)
    policy = FinishReviewPolicy(started=STARTED, limits=LIMITS, clock=lambda: 2.)
    first = policy.offer(ledger, intent_id='real-call:tool-1', reason='finished')
    second = policy.offer(ledger, intent_id='real-call:tool-2', reason='reviewed')
    assert first['permitted'] and not first['accepted_finish']
    assert second['reason'] == 'opportunity_limit' and second['accepted_finish']
    assert ledger == original and policy.used == 1
    assert FINISH_REVIEW == ORIGINAL_REVIEW == policy_manifest()['message']
    with pytest.raises(ValueError, match='new actual'):
        policy.offer(ledger, intent_id='real-call:tool-1', reason='duplicate')


def test_no_review_for_exhaustion_deadline_or_uncertain_accounting():
    for current, clock, reason in (
        (snapshot(known_actual_tokens=4_980_000, complete_actual_tokens=4_980_000),
         2., 'no_room_for_complete_output_reservation'),
        (snapshot(attempts=512), 2., 'model_attempt_limit'),
        (snapshot(decisions=512), 2., 'agent_decision_limit'),
        (snapshot(), 21601., 'episode_deadline'),
    ):
        policy = FinishReviewPolicy(started=STARTED, limits=LIMITS, clock=lambda: clock)
        assert policy.offer(current, intent_id='real:1', reason='done')['reason'] == reason
        assert policy.used == 0
    policy = FinishReviewPolicy(started=STARTED, limits=LIMITS, clock=lambda: 2.)
    with pytest.raises(RuntimeError, match='uncertain'):
        policy.offer(snapshot(complete_actual_tokens=None), intent_id='real:1', reason='done')
    assert policy.used == 0


class Recorder:
    def __init__(self): self.events = []
    def record(self, kind, payload, **kwargs):
        self.events.append({'kind': kind, 'payload': copy.deepcopy(payload), **kwargs})


class Team:
    def __init__(self): self.decisions = 0
    def consume_decision(self, *_): self.decisions += 1
    def cleanup(self, *_): pass
    def snapshot(self):
        return {'remaining_decisions': 512-self.decisions, 'remaining_attempts': 512-self.decisions,
                'available_tokens': 5_000_000-100*self.decisions, 'integrity_failure': None,
                'decisions': self.decisions}


class ScriptedWorker(FinishReviewWorkerMixin):
    def __init__(self, team, ledger):
        self.role_id, self.team_budget, self.ledger = 'member_001', team, ledger
        self._done, self._in_step, self._identity, self._identity_epoch = None, False, {}, 0
        self.meter = {'decisions': 0}
        self.config = {'budget': {'max_decisions': 512}, 'model': 'scripted-no-provider',
            'backend_id': 'cpu-only', 'model_revision': 'fixture', 'weight_identity': {}, 'task': 'repair'}
        self._observation_texts, self._sdk_events = [], []
        self.format_errors = {'consecutive': 0}
        self.definitions = [{'name': 'staff_done', 'description': 'original'}]
        self.agent = None
        self.messages, self.events, self._result = [], [], None
        self.conversation = SimpleNamespace(state=SimpleNamespace(execution_status='idle'),
            send_message=self.send_message, run=self.run)

    def snapshot(self): return {'meter': copy.deepcopy(self.meter), 'done': self._done}
    def _emit(self, kind, value): self.events.append((kind, copy.deepcopy(value)))
    def _fail(self, *args, **kwargs): raise RuntimeError(str(args))
    def send_message(self, text, **kwargs):
        self.messages.append((text, kwargs))
        self.conversation.state.execution_status = 'idle'

    def run(self):
        self.ledger['attempts'] += 1
        self.ledger['decisions'] += 1
        self.ledger['known_actual_tokens'] += 100
        self.ledger['complete_actual_tokens'] += 100
        self._completions = self._executions = 1
        tool_id = 'tool-' + str(self.meter['decisions'])
        self._pending = {'name': 'staff_done', 'arguments': {'reason': 'finished'}, 'tool_call_id': tool_id}
        association = {**self._association, 'model_call_id': self._association['call_id'],
                       'model_tool_call_id': tool_id}
        self._result = self.execute('staff_done', {'reason': 'finished'}, association)
        self.conversation.state.execution_status = 'paused'


def fixture_runtime():
    ledger = snapshot(known_actual_tokens=0, complete_actual_tokens=0, decisions=0, attempts=0)
    team = Team()
    worker = ScriptedWorker(team, ledger)
    runtime = SDKStaffRuntime.__new__(SDKStaffRuntime)
    runtime.labels = runtime.initial_members = ['member_001']
    runtime.actions = runtime.opportunities = runtime.cursor = 0
    runtime._in_step = False
    runtime._active = None
    runtime.run_id = 'cpu-fixture'
    runtime.roles = {'member_001': {'memory': {}, 'opportunities': 0, 'actions': 0,
                                  'identity': None, 'status': 'ready'}}
    runtime.policies = {'member_001': worker}
    runtime.recorder = Recorder()
    runtime.team_budget = team
    runtime.waiting, runtime.stopped, runtime.work_ended = {}, {}, {}
    registry = {'member_001': {'status': 'live'}}
    runtime.prepared = SimpleNamespace(world=SimpleNamespace(_software=lambda: {'registry': registry}))
    runtime.deadline = SimpleNamespace(check_hard=lambda *_: None)
    runtime.ports = {'member_001': SimpleNamespace(tools=lambda: [], observe=lambda: {
        'world_id': 'w', 'instance_id': 'i', 'branch_id': 'b', 'actor_id': 'member_001', 'projects': {}})}
    worker.execute = lambda name, arguments, association: runtime.execute('member_001', name, arguments, association)
    adapter = SimpleNamespace(ledger=SimpleNamespace(snapshot=lambda: copy.deepcopy(ledger)))
    decorate_runtime(runtime, adapter=adapter, started=STARTED, limits=LIMITS, clock=lambda: 2.)
    return runtime, worker, ledger, registry


def test_actual_staff_step_keeps_first_finish_nonterminal_then_accepts_second():
    runtime, worker, ledger, registry = fixture_runtime()
    first = runtime.step()
    assert first['status'] == 'running' and worker._done is None
    assert worker._result['worker_state'] == 'finish_review_pending'
    assert worker.messages[-1][0] == FINISH_REVIEW
    assert runtime.work_ended == runtime.waiting == runtime.stopped == {}
    assert registry == {'member_001': {'status': 'live'}}
    assert ledger['attempts'] == 1 and runtime.opportunities == 1 and runtime.actions == 0
    second = runtime.step()
    assert second['status'] == 'completed' and worker._done == 'finished'
    assert sum(text == FINISH_REVIEW for text, _ in worker.messages) == 1
    assert ledger['attempts'] == 2 and runtime.opportunities == 2 and runtime.actions == 0
    # An accepted finish is never cleared or revived by this hook.
    third = runtime.step()
    assert third['status'] == 'completed' and ledger['attempts'] == 2 and worker._done == 'finished'


def test_retired_member_cannot_be_reviewed_and_no_world_action_is_invented():
    runtime, worker, ledger, registry = fixture_runtime()
    registry['member_001']['status'] = 'retired'
    result = runtime.step()
    assert result['status'] == 'environment_error'
    assert worker._done is None and not any(text == FINISH_REVIEW for text, _ in worker.messages)
    assert ledger['attempts'] == 1 and runtime.actions == 0
    assert not any(row['kind'] == 'tool_call' for row in runtime.recorder.events)


def test_prior_unresolved_tool_execution_cannot_be_reentered():
    runtime, worker, ledger, _ = fixture_runtime()
    worker._execution_failure_v056 = {'matches_admitted_action': True, 'world_result_known': False}
    result = runtime.step()
    assert result['status'] == 'environment_error'
    assert ledger['attempts'] == 0 and runtime.actions == 0 and worker._done is None


def test_empty_managed_budget_does_not_hide_provider_uncertainty():
    runtime, worker, ledger, _ = fixture_runtime()
    original_snapshot = runtime.team_budget.snapshot
    runtime.team_budget.snapshot = lambda: {**original_snapshot(), 'available_tokens': 0}
    # A previous unsettled request must not be converted to an accepted finish.
    ledger['uncertain_reserved_tokens'] = 100
    result = runtime.step()
    assert result['status'] == 'environment_error' and worker._done is None
    assert runtime.finish_review_policy_v110.used == 0


def test_new_step_preserves_the_original_accounting_and_execution_ast():
    root = Path(__file__).resolve().parents[1] / 'src/proworksim'
    def method(path, name):
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
        return copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'step'))
    old = method(root/'harness_sdk.py', 'HarnessWorker')
    new = method(root/'software_benchmark_review_runtime_v110.py', 'FinishReviewWorkerMixin')
    # The outer legacy v056 wrapper remains as the exact pre-step guard.
    legacy = method(root/'software_benchmark_managed_worker_v056.py', '_ExecutionFailureBoundaryMixin')
    assert ast.dump(ast.Module(body=new.body[:2], type_ignores=[]), include_attributes=False) == ast.dump(
        ast.Module(body=legacy.body[:2], type_ignores=[]), include_attributes=False)
    new.body = new.body[2:]
    class Normalize(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None if node.module == 'openhands.sdk.conversation.state' else node
        def visit_Attribute(self, node):
            if node.attr == '_v110_original_harness_version':
                return ast.Name(id='HARNESS_VERSION', ctx=ast.Load())
            return self.generic_visit(node)
        def visit_If(self, node):
            if isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Call):
                call = node.test.left
                if isinstance(call.func, ast.Name) and call.func.id == 'getattr' and any(
                        isinstance(a, ast.Constant) and a.value == '_v110_pending_finish_review' for a in call.args):
                    return self.visit(node.orelse[0])
            return self.generic_visit(node)
    new = Normalize().visit(new)
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)
