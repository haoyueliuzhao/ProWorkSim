"""API-only episode binding for eight startup slots; reuse the qualified parent."""
from __future__ import annotations

from . import software_benchmark_api_parent_v076 as parent
from . import software_benchmark_resources_v079 as resources
from .software_benchmark_episodes_v076 import api_episode


class EpisodeBindings:
    def __init__(self, guard, *, watchdog_guard, capacity_probe=None,
                 authorization_ref=None, qwen_target=None):
        self.primary_policy = resources.policy(guard, watchdog_guard=watchdog_guard,
            capacity_probe=capacity_probe, authorization_ref=authorization_ref,
            qwen_target=qwen_target)
        self.api_policy = self.primary_policy
        self.api = api_episode(self.api_policy)
        self.api.run_episode.__globals__["capacity"] = self.api_policy.physical_capacity
        self.api.__dict__["capacity"] = self.api_policy.physical_capacity

    def run_api(self, row, resident, *, stop_event=None, api_transport_factory=None):
        if row.get("model_key") != "DEEPSEEK" or row.get("input_plus_output_tokens") != 5_000_000:
            raise ValueError("Only original DeepSeek 5M episodes may use the API startup expansion")
        parent.require_qualified()
        return self.api.run_episode(row, resident, stop_event=stop_event,
            api_transport_factory=api_transport_factory)

    def run_qwen(self, *args, **kwargs):
        raise PermissionError("The live Qwen coordinator and its resource policy remain unchanged")
