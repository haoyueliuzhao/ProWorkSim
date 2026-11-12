"""Host-only Qwen/API episode bindings for the shared v075 resource policy."""
from __future__ import annotations

from types import FunctionType, ModuleType

from . import software_benchmark_docker_actor_v066 as original_provider
from . import software_benchmark_episode_v066 as original_episode
from . import software_benchmark_resources_v075 as resources
from .software_benchmark_expansion_episode_v069 import clone_function, clone_namespace

VERSION = "v075-private-consistent-resource-episodes-r1"


def provider(policy):
    namespace = clone_namespace(original_provider, policy=policy)
    methods = {name: clone_function(value, namespace) if isinstance(value, FunctionType) else value
               for name, value in vars(original_provider.OwnedActorPair).items()
               if name not in {"__dict__", "__weakref__"}}
    namespace["OwnedActorPair"] = type("V075OwnedActorPair", (object,), methods)
    value = ModuleType(__name__ + ".provider")
    value.__dict__.update(namespace)
    return value


def episode(policy):
    adapted = provider(policy)
    namespace = clone_namespace(original_episode, policy=policy,
        OwnedActorPair=adapted.OwnedActorPair,
        validate_actor_ready=adapted.validate_actor_ready)
    value = ModuleType(__name__ + ".episode")
    value.__dict__.update(namespace)
    return value


class EpisodeBindings:
    """Create once per coordinator; never alter old function dictionaries."""

    def __init__(self, guard, *, authorization_ref=None):
        self.primary_policy = resources.policy(guard, authorization_ref=authorization_ref)
        self.api_policy = resources.api_policy(guard, authorization_ref=authorization_ref,
                                               primary=self.primary_policy)
        self.qwen = episode(self.primary_policy)
        self.api = episode(self.api_policy)

    def run_qwen(self, row, resident, *, stop_event=None, api_transport_factory=None):
        if row.get("model_key") != "QWEN":
            raise ValueError("The local binding accepts only original Qwen episodes")
        return self.qwen.run_episode(row, resident, stop_event=stop_event,
                                     api_transport_factory=api_transport_factory)

    def run_api(self, row, resident, *, stop_event=None, api_transport_factory=None):
        if row.get("model_key") != "DEEPSEEK" or row.get("input_plus_output_tokens") != 5_000_000:
            raise ValueError("The API binding accepts only original DeepSeek 5M episodes")
        return self.api.run_episode(row, resident, stop_event=stop_event,
                                    api_transport_factory=api_transport_factory)
