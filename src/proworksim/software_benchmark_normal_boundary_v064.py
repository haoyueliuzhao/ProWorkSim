"""Typed, settled pre-dispatch boundaries for the two v064 model providers."""
from __future__ import annotations


def unwrap_normal_boundary(error):
    from .software_benchmark_normal_boundary_v054 import unwrap_normal_boundary as old
    original = old(error)
    if original is not None:
        return original
    from .software_benchmark_ref_budget_v064 import BeforeQwenDispatch
    from .software_benchmark_deepseek_adapter_v064 import RemoteEpisodeBoundary
    candidate = error
    # The SDK retains the original object and cause, so a message cannot forge a
    # pre-dispatch decision or hide a provider/network exception.
    from openhands.sdk.conversation.exceptions import ConversationRunError
    if type(error) is ConversationRunError:
        if error.__cause__ is not error.original_exception:
            return None
        candidate = error.original_exception
    if type(candidate) in {BeforeQwenDispatch, RemoteEpisodeBoundary}:
        return candidate
    return None


class GuardedModelAdapter:
    def __init__(self, adapter, gate, started):
        self.adapter, self.gate = adapter, gate
        self.adapter.started = started

    def __getattr__(self, name):
        return getattr(self.adapter, name)

    def count(self, request):
        with self.gate.request("REF"):
            return self.adapter.count(request)

    def complete(self, request, usage_id):
        with self.gate.request("REF"):
            return self.adapter.complete(request, usage_id)
