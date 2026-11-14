"""Private host-only episode/provider adaptation for API5M expanded capacity."""
from __future__ import annotations

from functools import lru_cache, wraps
from types import FunctionType, ModuleType

from . import software_benchmark_expansion_resources_v069 as resources
from . import software_benchmark_docker_actor_v066 as original_provider
from . import software_benchmark_episode_v066 as original_episode

VERSION = "v069-private-api5m-expansion-episode-r1"


def clone_function(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    value.__annotations__ = dict(function.__annotations__)
    return value


def clone_namespace(module, **overrides):
    namespace = {**vars(module), **overrides}
    for name, value in vars(module).items():
        if isinstance(value, FunctionType) and value.__module__ == module.__name__:
            namespace[name] = clone_function(value, namespace)
    return namespace


def guarded_pair_method(function, *, cleanup=False):
    @wraps(function)
    def call(self, *args, **kwargs):
        if cleanup:
            resources.authorize_cleanup(self.claims, slot_id=self.slot_id, instance_id=self.instance_id)
        else:
            resources.require_v066_allowed("v066.run", slot_id=self.slot_id, instance_id=self.instance_id)
            for ref in self.claims.values():
                resources.validate_owned_claim(ref, slot_id=self.slot_id, instance_id=self.instance_id)
        return function(self, *args, **kwargs)
    return call


@lru_cache(maxsize=1)
def provider():
    namespace = clone_namespace(original_provider, policy=resources)
    methods = {name: clone_function(value, namespace) if isinstance(value, FunctionType) else value
               for name, value in vars(original_provider.OwnedActorPair).items()
               if name not in {"__dict__", "__weakref__"}}
    for name in ("create_volume", "create_container", "upload_archive", "upload_file", "attach", "start",
                 "download_archive", "download_compressed_archive"):
        methods[name] = guarded_pair_method(methods[name])
    for name in ("stop_writers", "cleanup"):
        methods[name] = guarded_pair_method(methods[name], cleanup=True)
    namespace["OwnedActorPair"] = type("ExpandedOwnedActorPair", (object,), methods)
    module = ModuleType(__name__ + ".private_provider")
    module.__dict__.update(namespace)
    return module


@lru_cache(maxsize=1)
def episode():
    adapted = provider()
    namespace = clone_namespace(original_episode, policy=resources,
        OwnedActorPair=adapted.OwnedActorPair, validate_actor_ready=adapted.validate_actor_ready)
    module = ModuleType(__name__ + ".private_episode")
    module.__dict__.update(namespace)
    return module


def run_episode(row, resident, *, stop_event=None, api_transport_factory=None):
    if row.get("model_key") != "DEEPSEEK" or row.get("input_plus_output_tokens") != 5_000_000:
        raise ValueError("This host adapter accepts only original API5M slots")
    resources.require_v066_allowed("v066.run", slot_id=row["slot_id"], instance_id=row["instance_id"])
    output = resources.BATCH_ROOT / "episodes" / str(row["slot_index"])
    if output.exists():
        raise ValueError("An existing physical episode directory cannot be re-entered")
    return episode().run_episode(row, resident, stop_event=stop_event, api_transport_factory=api_transport_factory)
