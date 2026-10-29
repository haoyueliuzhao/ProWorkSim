"""Concise public guidance with the original bounded conversation lifecycle."""
from __future__ import annotations

from types import FunctionType

from . import software_benchmark_native_control_v062 as original

VERSION = 'v090-concise-native-verification-guidance-r1'
WORKFLOW_GUIDANCE = '''Use the issue and public API contract to determine expected behavior. Select focused reproductions and regression checks from public repository files and the supplied execution context. A missing module, collection error, zero tests or timeout is not a passing test. Reuse sufficient recorded evidence; repeat work when a change, uncertainty or nondeterminism warrants it. Before finishing, report what ran and what remains unverified. Public test success does not establish the complete repair, and no entire-repository pass is required. All work shares the original limits.'''
STUCK_CORRECTION = '''The native SDK detected repeated or non-actionable behavior. Continue in the same workspace and budget: inspect the last result, then choose a useful action or an honest finish report. Reuse existing evidence; repeat only for a concrete reason. If the last reply contained only reasoning, keep the next reasoning brief and emit a valid tool action or finish. No budget or deadline is reset.'''
FINISH_REVIEW = '''One final review is available within the remaining original budget. Compare the repair with the issue and public contract. Address any concrete uncovered behavior with a focused check; cite sufficient existing evidence without rerunning it. Report actual results and remaining limitations, then finish. No extra agent, budget or deadline is added.'''

_namespace = {**vars(original), 'VERSION': VERSION, 'WORKFLOW_GUIDANCE': WORKFLOW_GUIDANCE,
              'STUCK_CORRECTION': STUCK_CORRECTION, 'FINISH_REVIEW': FINISH_REVIEW}


def _clone(function):
    result = FunctionType(function.__code__, _namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


initial_message = _clone(original.initial_message)
run_controlled_conversation = _clone(original.run_controlled_conversation)
create_conversation = original.create_conversation
MAX_STUCK_CORRECTIONS = original.MAX_STUCK_CORRECTIONS
MAX_FINISH_REVIEWS = original.MAX_FINISH_REVIEWS
