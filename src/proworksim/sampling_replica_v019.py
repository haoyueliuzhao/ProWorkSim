"""Readonly same-policy samplers, never a second learner.

The parent exports only adapter tensors at a declared collection boundary. A
child independently loads the exact base/profile, installs those tensors, and
verifies the full actor identity and source before sampling. Each replica owns
its private model/cache/RNG; seeds remain the collector's predeclared slot seeds.
No critic, optimizer, learning checkpoint or training forward exists here.
"""

import copy
from pathlib import Path

from .audit import code_identity
from .candidate_runtime_v019 import CandidateActor, candidate_profile
from .online_training import recipe_config, reference, sha_file, tensor_tree_digest
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "readonly-sampling-replica-v0.19"


def _runtime_profile(profile):
    expected = candidate_profile(
        profile["candidate_id"], dtype=profile["dtype"], devices=profile["devices"]
    )
    if any(profile.get(key) != value for key, value in expected.items()):
        raise ValueError("Snapshot has an undeclared candidate v0.19 execution profile")
    return expected


def _checked_recipe(recipe, runtime):
    if recipe != recipe_config(recipe) or any(
        recipe[key] != runtime[field]
        for key, field in (("max_length", "max_context_tokens"),
                           ("max_output_tokens", "max_output_tokens"),
                           ("temperature", "temperature"))
    ):
        raise ValueError("Snapshot recipe differs from the declared runtime input/output/sampling contract")


def _source_refs():
    root = Path(__file__).resolve().parent
    return {
        name: reference(root / name)
        for name in ("sampling_replica_v019.py", "online_training.py", "candidate_runtime_v019.py", "prefix_cache_v019.py")
    }


def export_sampling_snapshot(owner, directory):
    if getattr(owner, "sampling_only", False) or owner.phase != "collecting" or owner.busy:
        raise ValueError("Only the idle current-window parent learner may export a sampling snapshot")
    declared = owner.freeze_identity()
    actual = owner._make_identity()
    if actual != declared or not owner.window_id:
        raise ValueError("Parent parameters/window differ from the declared current actor")
    runtime = _runtime_profile(owner.inference_profile)
    _checked_recipe(owner.recipe, runtime)
    source = code_identity()
    tensors = owner.actor_state()
    if any("lora_" not in name for name in tensors):
        raise ValueError("Sampling snapshots contain only actual LoRA tensors")
    if tensor_tree_digest(tensors, owner.torch) != declared["adapter_sha256"]:
        raise ValueError("Parent adapter changed during export")
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "snapshot.pt"
    owner.torch.save(tensors, path)
    metadata = {
        "version": VERSION,
        "window_id": owner.window_id,
        "actor_identity": declared,
        "policy_revision": owner.policy_revision,
        "parent_update_counts": {"actor": owner.actor_steps, "critic": owner.critic_steps},
        "base_identity": copy.deepcopy(owner.base_identity),
        "inference_profile": copy.deepcopy(owner.inference_profile),
        "runtime_profile": runtime,
        "recipe": copy.deepcopy(owner.recipe),
        "source_identity": source,
        "source_refs": _source_refs(),
        "snapshot": reference(path),
        "adapter_tensor_sha256": declared["adapter_sha256"],
        "tensor_schema": {name: {"shape": list(value.shape), "dtype": str(value.dtype)} for name, value in tensors.items()},
        "snapshot_contains": "LoRA actor tensors only; no critic, optimizer, RNG or learner checkpoint",
    }
    if owner._make_identity() != declared or code_identity() != source:
        raise ValueError("Parent actor or source changed during sampling snapshot export")
    atomic_write(directory / "manifest.json", json_bytes(metadata))
    return {**metadata, "manifest": reference(directory / "manifest.json")}


def _read_snapshot(directory):
    """Check immutable metadata/source before loading candidate dependencies or weights."""
    directory = Path(directory).resolve()
    manifest = read_json(directory / "manifest.json")
    if manifest.get("version") != VERSION or not manifest.get("window_id"):
        raise ValueError("An actual fixed-window sampling snapshot is required")
    if manifest.get("source_identity") != code_identity() or manifest.get("source_refs") != _source_refs():
        raise ValueError("Sampling replica source differs from the parent snapshot")
    runtime = _runtime_profile(manifest["inference_profile"])
    if runtime != manifest.get("runtime_profile"):
        raise ValueError("Snapshot runtime profile changed")
    _checked_recipe(manifest["recipe"], runtime)
    actor = manifest["actor_identity"]
    if (
        actor.get("inference_profile_sha256") != digest(json_bytes(manifest["inference_profile"]))
        or actor.get("adapter_sha256") != manifest.get("adapter_tensor_sha256")
        or type(manifest.get("policy_revision")) is not int
        or manifest["policy_revision"] < 0
        or actor.get("policy_version") != "online-actor-" + str(manifest["policy_revision"]) + ":" + actor["adapter_sha256"]
    ):
        raise ValueError("Sampling snapshot actor identity is inconsistent")
    base = manifest["base_identity"]
    base_manifest = Path(base["manifest"]["path"]).resolve()
    if sha_file(base_manifest) != base["manifest"]["sha256"] or actor.get("base_manifest_sha256") != base["manifest"]["sha256"]:
        raise ValueError("Parent base-weight manifest changed")
    path = directory / "snapshot.pt"
    if Path(manifest["snapshot"]["path"]).resolve() != path or reference(path) != manifest["snapshot"]:
        raise ValueError("Sampling adapter snapshot bytes changed")
    return manifest, path


class SamplingReplica(CandidateActor):
    def __init__(self, *args, **kwargs):
        if "sampling_only" in kwargs and kwargs["sampling_only"] is not True:
            raise ValueError("A sampling replica cannot construct a learner")
        kwargs["sampling_only"] = True
        super().__init__(*args, **kwargs)
        self._replica_manifest = None

    def verify_sampling_identity(self):
        expected = self._replica_manifest
        if expected is None:
            raise ValueError("Replica has not installed its declared snapshot")
        actual = self._make_identity()
        optimizer_absent = not any(hasattr(self, name) for name in ("critic", "actor_optimizer", "critic_optimizer"))
        if (
            not optimizer_absent or any(p.requires_grad for p in self.model.parameters())
            or self.actor_steps != 0 or self.critic_steps != 0
            or actual != expected["actor_identity"] or self.freeze_identity() != actual
            or self.window_id != expected["window_id"] or self.phase != "collecting"
            or code_identity() != expected["source_identity"]
        ):
            raise ValueError("Readonly replica identity, source, window or no-optimizer guard failed")
        return {
            "version": VERSION, "passed": True,
            "actor_identity": copy.deepcopy(expected["actor_identity"]),
            "actual_actor_identity": actual,
            "window_id": self.window_id,
            "optimizer_absent": True, "critic_absent": True,
            "local_optimizer_updates": 0,
            "parent_update_counts": copy.deepcopy(expected["parent_update_counts"]),
            "policy_revision_scope": "Parent policy version copied as identity metadata; no local update",
            "source_identity": copy.deepcopy(expected["source_identity"]),
        }

    def begin_window(self, window_id):
        raise ValueError("Readonly replica is bound to exactly its exported parent window")


def load_replica(snapshot_path, output):
    """Return a verified CandidateActor-compatible sampler already in collecting."""
    manifest, path = _read_snapshot(snapshot_path)
    import torch

    tensors = torch.load(path, map_location="cpu", weights_only=True)
    if (
        not isinstance(tensors, dict) or not tensors
        or any(not isinstance(name, str) or "lora_" not in name or not torch.is_tensor(value)
               for name, value in tensors.items())
        or tensor_tree_digest(tensors, torch) != manifest["adapter_tensor_sha256"]
        or {name: {"shape": list(value.shape), "dtype": str(value.dtype)} for name, value in tensors.items()} != manifest["tensor_schema"]
    ):
        raise ValueError("Snapshot does not contain the exact declared LoRA tensor dictionary")
    base = manifest["base_identity"]
    replica = SamplingReplica.from_candidate(
        base["path"], manifest=base["manifest"]["path"],
        profile=manifest["runtime_profile"], recipe=manifest["recipe"], output=output,
    )
    if (
        replica.inference_profile != manifest["inference_profile"]
        or replica.base_identity != base or replica.recipe != manifest["recipe"]
        or set(replica.actor_parameters) != set(tensors)
    ):
        raise ValueError("Loaded replica base/profile/recipe/adapter names differ from parent")
    with torch.no_grad():
        for name, parameter in replica.actor_parameters.items():
            tensor = tensors[name]
            if tensor.shape != parameter.shape or tensor.dtype != parameter.dtype:
                raise ValueError("Replica adapter tensor shape or dtype differs from snapshot")
            parameter.copy_(tensor.to(parameter.device))
    replica.policy_revision = manifest["policy_revision"]
    # These counters describe this process only. Parent counts remain metadata.
    replica.actor_steps = replica.critic_steps = 0
    replica.window_id, replica.phase = manifest["window_id"], "collecting"
    replica.used_window_ids = [replica.window_id]
    replica._identity = replica._make_identity()
    replica._replica_manifest = copy.deepcopy(manifest)
    replica.prefix_cache.clear(reason="installed_parent_actor_snapshot")
    checked = replica.verify_sampling_identity()
    owner_path = replica.output / "owner.json"
    owner_record = read_json(owner_path)
    fresh_identity = owner_record["initial_actor_identity"]
    owner_record.update(
        initial_actor_identity=replica.freeze_identity(),
        initialization="readonly_current_window_parent_adapter_snapshot",
        fresh_base_adapter_before_snapshot=fresh_identity,
        sampling_snapshot=reference(Path(snapshot_path).resolve() / "manifest.json"),
        parent_update_counts=manifest["parent_update_counts"],
        local_optimizer_updates=0,
    )
    atomic_write(owner_path, json_bytes(owner_record))
    atomic_write(replica.output / "replica-verification.json", json_bytes(checked))
    return replica
