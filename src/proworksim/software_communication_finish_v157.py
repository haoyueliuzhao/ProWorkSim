"""Same single finish self-review with conservative auxiliary-unknown admission.

Unknown compressor reservations remain in the real ledger. They may decline an
extra self-review but cannot turn an otherwise lawful finish into a system error.
Agent/condenser uncertainty and any integrity conflict remain non-finishable.
"""
from __future__ import annotations
import copy
from types import MethodType
from .software_benchmark_finish_review_v117 import FinishReviewPolicy as OriginalPolicy
from .software_benchmark_finish_review_v117 import require_known_usage as original_require_known
from .software_role_baseline_runtime_v141 import specialize_worker_controls, MAX_OUTPUT_TOKENS
from .storage import digest, json_bytes

VERSION = 'v157-finish-with-retained-auxiliary-accounting-r1'


def require_known_usage(snapshot):
    if not snapshot.get('uncertain_reserved_tokens'):
        return original_require_known(snapshot)
    provider = snapshot.get('authoritative_provider_snapshot') or {}
    held = provider.get('uncertain_reserved_tokens')
    compressor = provider.get('per_usage_id', {}).get('compressor', {}).get('uncertain_reserved_tokens', 0)
    if (provider.get('source') != 'one_shared_physical_provider_sqlite'
            or provider.get('inflight_count') != 0 or snapshot.get('inflight') is not None
            or type(held) is not int or held <= 0 or compressor != held
            or held != snapshot['uncertain_reserved_tokens']
            or provider.get('known_actual_tokens') != snapshot.get('known_actual_tokens')
            or provider.get('available_tokens') != max(0, 5_000_000-held-provider['known_actual_tokens'])
            or provider.get('token_limit') != 5_000_000):
        raise RuntimeError('Only fully retained auxiliary unknown reservations may close normally')


class FinishReviewPolicy(OriginalPolicy):
    def offer(self, snapshot, *, intent_id, reason):
        require_known_usage(snapshot)
        held = snapshot.get('uncertain_reserved_tokens', 0)
        if not held:
            return super().offer(snapshot, intent_id=intent_id, reason=reason)
        # This temporary value is only a conservative admission bound. Never
        # publish it as actual usage or write it into the provider/native ledger.
        admission = copy.deepcopy(snapshot)
        upper = snapshot['known_actual_tokens']+held
        admission.update(known_actual_tokens=upper, complete_actual_tokens=upper,
                         uncertain_reserved_tokens=0)
        self._emit('auxiliary_unknown_finish_admission',
            intent_id=intent_id, known_actual_tokens=snapshot['known_actual_tokens'],
            uncertain_reserved_tokens=held, conservative_admission_upper=upper,
            actual_usage_complete=False, reservation_released=False)
        return super().offer(admission, intent_id=intent_id, reason=reason)


def decorate_reviews(runtime, owner, deadline):
    from .software_benchmark_review_runtime_v117 import ORIGINAL_HARNESS_VERSION
    runtime.finish_review_policies = {}
    started = {key: getattr(deadline, key) for key in ('started', 'soft_at', 'hard_at')}
    limits = {'agent_decisions': 512, 'all_model_attempts': 512, 'input_plus_output_tokens': 5_000_000,
        'output_limit': MAX_OUTPUT_TOKENS, 'soft_seconds': 21600, 'hard_seconds': 23400}
    for member, worker in runtime.policies.items():
        policy = FinishReviewPolicy(started=started, limits=limits, clock=deadline.clock,
            event_sink=lambda event, member=member: runtime.recorder.record('member_finish_review', event, worker_id=member))
        runtime.finish_review_policies[member] = policy
        worker._v117_original_harness_version = ORIGINAL_HARNESS_VERSION
        worker._v117_finish_review_policy = policy
        worker._v117_finish_review_adapter = owner.adapter
        worker._v117_pending_finish_review = None
        specialize_worker_controls(worker)
    original_execute = runtime.execute
    def execute(self, label, name, arguments, association):
        if name != 'staff_done':
            return original_execute(label, name, arguments, association)
        self.deadline.check_hard('settle_returned_legal_action')
        self._check_active(label, association)
        worker, policy = self.policies[label], self.finish_review_policies[label]
        if (label not in owner.adapters or label in self.stopped or label in self.waiting
                or label in self.work_ended or self._active['executed'] or worker._done is not None
                or worker._v117_pending_finish_review is not None or set(arguments) != {'reason'}
                or not isinstance(arguments['reason'], str) or not arguments['reason']):
            raise RuntimeError('Only a live scheduled member may request its private review')
        team, provider = self.team_budget.snapshot(), owner.adapter.ledger.snapshot()
        require_known_usage(provider)
        if team.get('integrity_failure'):
            raise RuntimeError('Review cannot hide shared accounting uncertainty')
        if any(team[key] <= 0 for key in ('remaining_decisions', 'remaining_attempts', 'available_tokens')):
            return original_execute(label, name, arguments, association)
        intent = association['model_call_id']+':'+association['model_tool_call_id']
        offered = policy.offer(provider, intent_id=intent, reason=arguments['reason'])
        if not offered['permitted']:
            return original_execute(label, name, arguments, association)
        worker._v117_pending_finish_review = {'intent_id': intent,
            'model_call_id': association['model_call_id'], 'model_tool_call_id': association['model_tool_call_id'],
            'reason': arguments['reason'], 'review_index': offered['review_index']}
        interpreted = {'kind': 'act', 'requested_control_kind': 'done', 'action': name,
            'arguments': copy.deepcopy(arguments), **self._association(association)}
        response = {'ok': True, 'worker_state': 'finish_review_pending', 'reason': arguments['reason'],
            'world_effect': False, 'accepted_finish': False, 'review_index': offered['review_index'],
            'policy_version': VERSION, 'message_follows': True, 'team_finished': False}
        self._active['executed'] = True
        self.recorder.record('policy_decision', {'decision': interpreted,
            'memory_before_sha256': digest(json_bytes(self.roles[label]['memory'])), 'harness': VERSION}, worker_id=label)
        self.record_harness_call(label, {'action': name, 'arguments': arguments,
            'response': response, 'request_key': None}, association)
        self.roles[label]['last_action'] = {'action': name, 'arguments': copy.deepcopy(arguments)}
        self.roles[label]['last_result'] = copy.deepcopy(response)
        self._active.update(decision=interpreted, response=copy.deepcopy(response))
        return response
    runtime.execute = MethodType(execute, runtime)

