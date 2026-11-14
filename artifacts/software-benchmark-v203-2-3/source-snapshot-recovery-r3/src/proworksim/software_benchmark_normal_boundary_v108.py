"""Recognize only the observed, pre-dispatch v105 token-budget boundary.

The caller retains the established complete-usage and response-projection
guards before normal shutdown and the original host-side candidate lock.
"""
from __future__ import annotations

from .software_benchmark_normal_boundary_v064 import GuardedModelAdapter  # noqa: F401
from .software_benchmark_normal_boundary_v064 import unwrap_normal_boundary as previous
from .software_benchmark_deepseek_adapter_v105 import RemoteEpisodeBoundary

VERSION = 'v108-exact-v105-predispatch-budget-closure-r1'
NORMAL_REASON = 'episode_token_reservation_exhausted'


def unwrap_normal_boundary(error):
    established = previous(error)
    if established is not None:
        return established
    from openhands.sdk.conversation.exceptions import ConversationRunError
    candidate = error
    if type(error) is ConversationRunError:
        if error.__cause__ is not error.original_exception:
            return None
        candidate = error.original_exception
    if (type(candidate) is RemoteEpisodeBoundary
            and candidate.before_dispatch_proven is True
            and candidate.classification == NORMAL_REASON
            and str(candidate) == NORMAL_REASON):
        return candidate
    return None
