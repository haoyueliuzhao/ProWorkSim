"""Explicit PROJECT finish-intent hook, before an accepted done transition.

No world event, member revival, test or submission is synthesized.  The new
worker step retains the original one-action/meter/exception path, and changes
only interpretation and presentation of a trusted deferred finish control.
"""
from __future__ import annotations

import copy
import json
from types import MethodType

from .software_benchmark_finish_review_v110 import (
    DONE_DESCRIPTION, FINISH_REVIEW, FinishReviewPolicy, SENDER, VERSION, require_known_usage,
)
from .storage import digest, json_bytes

ORIGINAL_HARNESS_VERSION = 'openhands-managed-worker-v0.33'


def _execution_status(conversation):
    value = conversation.state.execution_status
    return getattr(value, 'value', str(value))


class FinishReviewWorkerMixin:
    """Compose before the existing managed/history worker in the MRO."""

    def _deliver_finish_review(self, action):
        pending = getattr(self, '_v110_pending_finish_review', None)
        if (not isinstance(pending, dict) or action['name'] != 'staff_done'
                or pending['model_call_id'] != self._association['call_id']
                or pending['model_tool_call_id'] != action['tool_call_id']
                or pending['reason'] != action['arguments']['reason']
                or self._result.get('worker_state') != 'finish_review_pending'
                or self._done is not None or _execution_status(self.conversation) not in {'paused', 'idle'}):
            raise RuntimeError('Only the matched unaccepted finish intent may receive a final review')
        policy = self._v110_finish_review_policy
        provider_before = self._v110_finish_review_adapter.ledger.snapshot()
        team_before = self.team_budget.snapshot()
        meter_before = copy.deepcopy(self.meter)
        conversation, identity = self.conversation, copy.deepcopy(self._identity)
        self.conversation.send_message(FINISH_REVIEW, sender=SENDER)
        if (self.conversation is not conversation or self._identity != identity
                or self._done is not None or _execution_status(self.conversation) not in {'paused', 'idle'}
                or self._v110_finish_review_adapter.ledger.snapshot() != provider_before
                or self.team_budget.snapshot() != team_before or self.meter != meter_before):
            raise RuntimeError('Final-review delivery changed identity, accounting or accepted termination')
        self._v110_pending_finish_review = None
        event = policy._emit('finish_review_sent', intent_id=pending['intent_id'],
            review_index=pending['review_index'], message_sha256=digest(FINISH_REVIEW.encode()),
            same_conversation=True, charged_in_next_request=True, accepted_finish=False,
            world_event_created=False, member_retired_or_revived=False)
        self._emit('execution_policy_message', event)

    def step(self, public_observation, opportunity, model_identity=None):
        # Explicit copy of HarnessWorker.step. Only the trusted finish-review
        # interpretation block below differs. Retain its v056 pre-step guard;
        # no function-global cloning is used.
        failure = getattr(self, '_execution_failure_v056', None)
        if failure is not None:
            self._fail('execution_integrity_error',
                'Prior managed execution outcome is unresolved; worker reuse is forbidden',
                managed_execution_failure=copy.deepcopy(failure))
        if self._in_step:
            raise RuntimeError("SDK worker is already in an opportunity")
        if self._done:
            return {"kind": "done", "reason": self._done, "memory": self.snapshot()}
        if self.meter["decisions"] >= self.config["budget"]["max_decisions"]:
            self._fail("model_budget_exhausted", "SDK worker decision budget reached")
        if model_identity is not None and model_identity != self._identity:
            self.refresh_transport(self.transport, model_identity)
        self._in_step = True
        self._pending = self._result = self._boundary_error = self._last_body = None
        self._executions = self._completions = 0
        self.meter["decisions"] += 1
        call_id = "model-" + digest(json_bytes([
            opportunity.get("run_id"), self.role_id, self.meter["decisions"]]))[:24]
        self._association = {
            "call_id": call_id, "decision_id": call_id, "worker_id": self.role_id,
            "opportunity_id": opportunity.get("opportunity_id"),
            "decision_index": self.meter["decisions"], "requested_model": self.config["model"],
            "backend_id": self.config["backend_id"], "action_protocol": "native_tools",
            "model_revision": self.config["model_revision"],
            "weight_identity": copy.deepcopy(self._identity),
            "harness_version": self._v110_original_harness_version,
            "identity_epoch": self._identity_epoch,
        }
        before = len(self._sdk_events)
        try:
            if self.team_budget is not None:
                self.team_budget.consume_decision(self.role_id, call_id)
            observation_text = json.dumps(
                {"role_task": self.config["task"], "observation": public_observation},
                ensure_ascii=False, allow_nan=False)
            self._observation_texts.append(observation_text)
            self.conversation.send_message(observation_text)
            self.conversation.run()
            if self._pending and self._pending.get("native_tool_call") is False:
                from openhands.sdk.conversation.state import ConversationExecutionStatus
                tool = self.agent.tools_map[self._pending["name"]]
                action = tool.action_from_arguments(self._pending["arguments"])
                self.conversation.execute_tool(self._pending["name"], action)
                with self.conversation.state:
                    self.conversation.state.execution_status = ConversationExecutionStatus.PAUSED
            if self._completions != 1 or self._executions != 1:
                raise RuntimeError("SDK step did not execute exactly the admitted action")
            self.format_errors["consecutive"] = 0
            action = self._pending
            kind = {"staff_wait": "wait", "staff_done": "done"}.get(action["name"], "act")
            if getattr(self, '_v110_pending_finish_review', None) is not None:
                self._deliver_finish_review(action)
                kind = 'act'
                self._emit('finish_intent_deferred', {
                    **self._association, 'reason': action['arguments']['reason'],
                    'accepted_finish': False, 'world_action_executed': False})
            elif kind == "done":
                self._done = action["arguments"]["reason"]
            if kind != "act":
                self._emit("model_control", {
                    **self._association, "kind": kind,
                    "reason": action["arguments"]["reason"], "world_action_executed": False})
            return {
                "kind": kind, "action": action["name"],
                "arguments": action["arguments"], "result": self._result, "executed": True,
                "model_call_id": call_id, "decision_id": call_id,
                "model_tool_call_id": action["tool_call_id"],
                "reason": action["arguments"].get("reason") if kind != "act" else None,
                "sdk_events_added": len(self._sdk_events) - before, "memory": self.snapshot(),
            }
        except Exception:
            if self._boundary_error is not None:
                if self._boundary_error.status == "model_format_error":
                    return self._format_rejection(self._boundary_error)
                raise self._boundary_error from None
            raise
        finally:
            if self.team_budget is not None:
                self.team_budget.cleanup(self.role_id, call_id)
            self._in_step = False


review_worker_mixin = FinishReviewWorkerMixin


def decorate_runtime(runtime, *, adapter, started, limits, clock=None):
    """Attach one explicit finish-intent handler to a newly assembled S1 runtime."""
    if (runtime.labels != ['member_001'] or runtime.initial_members != ['member_001']
            or runtime.actions or runtime.opportunities or hasattr(runtime, 'finish_review_policy_v110')):
        raise ValueError('Final-review policy binds only a fresh original single-member runtime')
    worker = runtime.policies['member_001']
    if not isinstance(worker, FinishReviewWorkerMixin) or worker._done is not None:
        raise ValueError('The PROJECT worker must have its explicit pre-done review step')
    worker._v110_original_harness_version = ORIGINAL_HARNESS_VERSION
    policy = FinishReviewPolicy(started=started, limits=limits,
        **({'clock': clock} if clock is not None else {}),
        event_sink=lambda event: runtime.recorder.record('finish_review_policy_v110', event,
                                                       worker_id='member_001'))
    worker._v110_finish_review_policy = runtime.finish_review_policy_v110 = policy
    worker._v110_finish_review_adapter = adapter
    worker._v110_pending_finish_review = None
    for definition in worker.definitions:
        if definition['name'] == 'staff_done':
            definition['description'] = DONE_DESCRIPTION
    if getattr(worker, 'agent', None) is not None:
        from .harness_sdk import HARNESS_VERSION, HarnessWorker
        from .software_benchmark_managed_worker_v056 import _ExecutionFailureBoundaryMixin
        steps = [cls.__dict__['step'] for cls in type(worker).__mro__ if 'step' in cls.__dict__]
        if (steps != [FinishReviewWorkerMixin.step, _ExecutionFailureBoundaryMixin.step, HarnessWorker.step]
                or HARNESS_VERSION != ORIGINAL_HARNESS_VERSION):
            raise ValueError('The managed step chain gained an unreviewed boundary wrapper')
        from openhands.sdk.tool import register_tool, resolve_tool
        for specification in worker.agent.tools:
            for tool in resolve_tool(specification, worker.conversation.state):
                if tool.name == 'staff_done':
                    register_tool(specification.name, tool.model_copy(update={'description': DONE_DESCRIPTION}))

    original_execute = runtime.execute

    def execute(self, label, name, arguments, association):
        if name != 'staff_done':
            return original_execute(label, name, arguments, association)
        self.deadline.check_hard('settle_returned_legal_action')
        self._check_active(label, association)
        registry = self.prepared.world._software()['registry']
        if (label != 'member_001' or registry.get(label, {}).get('status') != 'live'
                or label in self.stopped or label in self.waiting or label in self.work_ended
                or self._active['executed'] or worker._done is not None
                or worker._v110_pending_finish_review is not None
                or set(arguments) != {'reason'} or not isinstance(arguments['reason'], str)
                or not arguments['reason']):
            raise RuntimeError('No accepted, stopped or retired member can request a review')
        team = self.team_budget.snapshot()
        if team.get('integrity_failure'):
            raise RuntimeError('A final review cannot conceal managed accounting uncertainty')
        provider = adapter.ledger.snapshot()
        require_known_usage(provider)
        intent_id = association['model_call_id'] + ':' + association['model_tool_call_id']
        if any(team.get(key, 0) <= 0 for key in (
                'remaining_decisions', 'remaining_attempts', 'available_tokens')):
            policy._emit('finish_review_not_offered', intent_id=intent_id,
                permitted=False, reason='managed_budget_boundary', accepted_finish=True,
                opportunities_used=policy.used)
            return original_execute(label, name, arguments, association)
        decision = policy.offer(provider, intent_id=intent_id,
                                reason=arguments['reason'])
        if not decision['permitted']:
            return original_execute(label, name, arguments, association)
        pending = {'intent_id': intent_id, 'model_call_id': association['model_call_id'],
                   'model_tool_call_id': association['model_tool_call_id'],
                   'reason': arguments['reason'], 'review_index': decision['review_index']}
        worker._v110_pending_finish_review = pending
        # The proposal is recorded as a nonterminal harness operation. It never
        # claims a world event, test result, legal submission or work completion.
        interpreted = {'kind': 'act', 'requested_control_kind': 'done', 'action': name,
                       'arguments': copy.deepcopy(arguments), **self._association(association)}
        response = {'ok': True, 'worker_state': 'finish_review_pending',
                    'reason': arguments['reason'], 'world_effect': False,
                    'accepted_finish': False, 'review_index': decision['review_index'],
                    'policy_version': VERSION, 'message_follows': True}
        self._active['executed'] = True
        self.recorder.record('policy_decision', {'decision': interpreted,
            'memory_before_sha256': digest(json_bytes(self.roles[label]['memory'])),
            'harness': VERSION}, worker_id=label)
        self.record_harness_call(label, {'action': name, 'arguments': arguments,
            'response': response, 'request_key': None}, association)
        self.roles[label]['last_action'] = {'action': name, 'arguments': copy.deepcopy(arguments)}
        self.roles[label]['last_result'] = copy.deepcopy(response)
        self._active.update(decision=interpreted, response=copy.deepcopy(response))
        return response

    runtime.execute = MethodType(execute, runtime)
    return runtime
