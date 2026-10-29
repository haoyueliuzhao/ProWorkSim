"""Use a common actual-capacity allocator for unchanged Qwen/API episodes."""
from __future__ import annotations

from types import ModuleType

from . import software_benchmark_api_parent_v076 as parent
from . import software_benchmark_episode_v066 as original_episode
from . import software_benchmark_resources_v076 as resources
from .software_benchmark_episodes_v075 import episode, provider
from .software_benchmark_expansion_episode_v069 import clone_namespace


def api_episode(policy):
    adapted = provider(policy)
    namespace = adapted.OwnedActorPair.create_container.__globals__
    original_options, original_validate = namespace["container_options"], namespace["validate_container"]

    def options(*args, **kwargs):
        return parent.container_options(original_options(*args, **kwargs))

    def validate(*args, **kwargs):
        attrs = original_validate(*args, **kwargs)
        parent.validate_container_parent(attrs)
        return attrs

    namespace.update(container_options=options, validate_container=validate)
    original_start = adapted.OwnedActorPair.start

    def start(self, role):
        attrs = original_start(self, role)
        parent.validate_container_parent(attrs, require_running=True)
        return attrs

    adapted.OwnedActorPair.start = start
    values = clone_namespace(original_episode, policy=policy,
        OwnedActorPair=adapted.OwnedActorPair, validate_actor_ready=adapted.validate_actor_ready)
    result = ModuleType(__name__ + ".private_parented_api_episode")
    result.__dict__.update(values)
    return result


class EpisodeBindings:
    def __init__(self, guard, *, watchdog_guard, capacity_probe=None, authorization_ref=None):
        self.primary_policy = resources.policy(guard, watchdog_guard=watchdog_guard,
            capacity_probe=capacity_probe, authorization_ref=authorization_ref)
        self.api_policy = self.primary_policy
        self.qwen, self.api = episode(self.primary_policy), api_episode(self.primary_policy)
        # Replace only the old pre-admission host check. The later atomic claim
        # rechecks actual capacity, pending-start budget and watchdog under lock.
        for delegate in (self.qwen, self.api):
            delegate.run_episode.__globals__["capacity"] = self.primary_policy.physical_capacity
            delegate.__dict__["capacity"] = self.primary_policy.physical_capacity

    def run_qwen(self, row, resident, *, stop_event=None, api_transport_factory=None):
        if row.get("model_key") != "QWEN":
            raise ValueError("The local binding accepts only original Qwen episodes")
        return self.qwen.run_episode(row, resident, stop_event=stop_event,
                                     api_transport_factory=api_transport_factory)

    def run_api(self, row, resident, *, stop_event=None, api_transport_factory=None):
        if row.get("model_key") != "DEEPSEEK" or row.get("input_plus_output_tokens") != 5_000_000:
            raise ValueError("The API binding accepts only original DeepSeek 5M episodes")
        parent.require_qualified()
        return self.api.run_episode(row, resident, stop_event=stop_event,
                                    api_transport_factory=api_transport_factory)
