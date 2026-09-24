"""One explicitly bounded first-decision REINFORCE LoRA update.

The three episode names are fixed before viewing rewards. Only each first actual
local-base generation is differentiated; all later behavior is fixed continuation.
This is neither full multi-turn Agentic RL nor a learning-gain comparison.
GPU imports and computation occur only in main after immutable input admission.
"""

import argparse
import copy
import gc
import hashlib
import inspect
import json
import math
import os
import subprocess
import time
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import assess_historical_episode
from proworksim.rewards import episode_reward
from proworksim.storage import atomic_write, json_bytes, read_json

VERSION = "first-decision-reinforce-v0.11.2"
REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
EPISODE_NAMES = ["finance-direct-qwen-1", "finance-direct-qwen-2", "finance-direct-qwen-3"]
ROLE, NODE = "analyst", "FINANCE::reconcile"
BASELINE, TEMPERATURE = 0.5, 0.3
PROCESS = [
    {
        "requirement_id": "source-adoption",
        "kind": "required_source_adoption",
        "work_node": NODE,
        "aliases": ["ledger", "statement", "definitions"],
    }
]
REWARD = {
    "version": "reward-spec-v0.11",
    "reward_id": "first-decision-finance-v011",
    "objectives": [{"kind": "content", "work_node": NODE, "weight": 1}],
    "process_requirements": ["source-adoption"],
}


def sha_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def file_reference(path):
    path = Path(path)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha_file(path)}


def resources():
    result = {
        "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
        "recorded_at": time.time(),
        "shared_gpu_authorized": True,
    }
    for key, command in {
        "gpu": [
            "nvidia-smi",
            "--query-gpu=index,name,memory.used,memory.free,utilization.gpu",
            "--format=csv",
        ],
        "compute_processes": [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv",
        ],
    }.items():
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=20, check=False
            )
            result[key] = {
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except (OSError, subprocess.TimeoutExpired) as error:
            result[key] = {"error_type": type(error).__name__, "message": str(error)}
    return result


def extract_first_decision(manifest, history, reward, *, capture_matches, max_length=8192):
    """Pure admission of saved actual token records; never tokenize report text."""
    record = {
        "episode_id": manifest.get("episode_id"),
        "eligible": False,
        "exclusions": [],
        "reward_result": copy.deepcopy(reward),
        "reward": reward.get("reward"),
        "role": ROLE,
    }
    if (
        not isinstance(capture_matches, dict)
        or not capture_matches
        or any(value is not True for value in capture_matches.values())
    ):
        record["exclusions"].append(
            {"kind": "public_capture_unverified", "actual_matches": copy.deepcopy(capture_matches)}
        )
        return record
    if not reward.get("eligible"):
        record["exclusions"].append(
            {"kind": "reward_ineligible", "reasons": copy.deepcopy(reward.get("exclusions", []))}
        )
        return record
    if (
        type(reward.get("reward")) not in (int, float)
        or not math.isfinite(reward["reward"])
        or not 0 <= reward["reward"] <= 1
    ):
        raise ValueError("Eligible reward must preserve an actual finite result")
    policy = manifest.get("policies", {}).get(ROLE, {})
    config = policy.get("config", {})
    if (
        policy.get("implementation") != "proworksim.model_policy.ModelPolicy"
        or config.get("backend_id") != "local-qwen-http"
        or config.get("model") != "Qwen2.5-7B-Instruct"
        or config.get("model_revision") != REVISION
        or config.get("temperature") != TEMPERATURE
        or config.get("action_protocol") != "single_decision_json"
        or not isinstance(config.get("weight_identity"), dict)
    ):
        raise ValueError("Trajectory is not the declared unmodified local Qwen behavior policy")
    identity = config["weight_identity"]
    if (
        set(identity) - {"path", "manifest", "manifest_sha256"}
        or not {"path", "manifest"} <= set(identity)
        or any(not isinstance(value, str) or not value for value in identity.values())
    ):
        raise ValueError(
            "Behavior identity must identify only immutable base files, without an updated adapter"
        )
    if NODE not in manifest.get("responsibility", {}).get("work_nodes", []):
        raise ValueError("Episode did not predeclare this financial work-node responsibility")
    if manifest.get("status") != "closed" or reward.get("episode_id") != manifest["episode_id"]:
        raise ValueError("Reward does not bind this closed episode")
    interval = manifest["experience"]
    events = history["events"][interval["start"] : interval["end"]]
    starts = [
        event
        for event in events
        if event.get("worker_id") == ROLE
        and event.get("kind") == "model_call"
        and event["payload"].get("stage") == "started"
    ]
    if not starts:
        record["exclusions"].append({"kind": "no_actual_first_model_decision"})
        return record
    first = starts[0]["payload"]
    if first.get("decision_index") != 1 or first.get("model_revision") != REVISION:
        raise ValueError("Episode prefix is not the first draw from the declared base policy")
    call_id = first["call_id"]
    attempts = [
        event["payload"]
        for event in events
        if event.get("worker_id") == ROLE
        and event.get("kind") == "model_attempt"
        and event["payload"].get("call_id") == call_id
        and event["payload"].get("stage") == "finished"
    ]
    if len(attempts) != 1 or attempts[0].get("status") != "success":
        record["exclusions"].append(
            {
                "kind": "first_decision_service_retry_or_unavailable",
                "attempt_statuses": [a.get("status") for a in attempts],
            }
        )
        return record
    responses = [
        event
        for event in events
        if event.get("worker_id") == ROLE
        and event.get("kind") == "model_response"
        and event["payload"].get("call_id") == call_id
    ]
    if len(responses) != 1:
        record["exclusions"].append({"kind": "first_actual_model_response_unavailable"})
        return record
    response = responses[0]["payload"]["response"]
    if response != attempts[0]["response"]["body"]:
        raise ValueError("Recorded completion differs from its actual transport response")
    if response.get("model") != config["model"] or response.get("system_fingerprint") != REVISION:
        raise ValueError("Actual backend identity differs from declared base weights")
    trace = response.get("token_trace")
    if not isinstance(trace, dict):
        record["exclusions"].append({"kind": "actual_token_trace_missing"})
        return record
    for key in ("input_ids", "output_ids"):
        if (
            not isinstance(trace.get(key), list)
            or not trace[key]
            or any(type(value) is not int or value < 0 for value in trace[key])
        ):
            raise ValueError("Actual token IDs are missing or malformed; never reconstructed")
    n, m = len(trace["input_ids"]), len(trace["output_ids"])
    if trace.get("input_mask") != [0] * n or trace.get("output_mask") != [1] * m:
        raise ValueError("Only full real input-zero/output-one token masks are admitted")
    logs = trace.get("behavior_logprobs")
    if (
        not isinstance(logs, list)
        or len(logs) != m
        or any(type(x) not in (int, float) or not math.isfinite(x) or x > 1e-6 for x in logs)
    ):
        record["exclusions"].append({"kind": "actual_behavior_logprobs_missing_or_invalid"})
        return record
    if (
        trace.get("sampling_temperature") != TEMPERATURE
        or trace.get("sampling_top_p") != 1.0
        or trace.get("sampling_top_k") != 0
    ):
        raise ValueError("Behavior sampling distribution differs from the frozen REINFORCE policy")
    effective = response.get("effective_generation", {})
    if any(
        effective.get(key) != value
        for key, value in {
            "do_sample": True,
            "temperature": 1.0,
            "top_p": 1.0,
            "top_k": 0,
            "repetition_penalty": 1.0,
        }.items()
    ):
        raise ValueError("Service sampling included an unsupported extra transform")
    if (
        trace.get("source")
        != "actual generation token IDs and sampling logits, not retokenized text"
    ):
        raise ValueError("Token trace lacks the declared actual generation provenance")
    usage = response.get("usage", {})
    if (
        usage.get("prompt_tokens") != n
        or usage.get("completion_tokens") != m
        or usage.get("total_tokens") != n + m
    ):
        raise ValueError("Actual recorded token IDs disagree with observed usage")
    record.update(
        model_call_id=call_id,
        service_completion_id=response["id"],
        model_response_sequence=responses[0]["sequence"],
        policy_identity=copy.deepcopy(policy),
        first_response=copy.deepcopy(response),
        token_trace=copy.deepcopy(trace),
        input_tokens=n,
        output_tokens=m,
        sequence_tokens=n + m,
        labels=[-100] * n + list(trace["output_ids"]),
        loss_mask=[0] * n + [1] * m,
        advantage=reward["reward"] - BASELINE,
        continuation="All subsequent target/model/world/colleague actions are fixed recorded behavior; no gradient through them",
    )
    if n + m > max_length:
        record["exclusions"].append(
            {"kind": "length_limit", "actual": n + m, "maximum": max_length, "truncated": False}
        )
        return record
    record["eligible"] = True
    return record


def compare_logprobs(recomputed, behavior, max_atol, mean_atol):
    if len(recomputed) != len(behavior) or not recomputed:
        raise ValueError("Probability records require equal nonempty token sequences")
    if any(not math.isfinite(value) for value in [*recomputed, *behavior]):
        raise ValueError("Nonfinite token log probability")
    signed = [float(a) - float(b) for a, b in zip(recomputed, behavior)]
    absolute = [abs(value) for value in signed]
    return {
        "recomputed_logprobs": recomputed,
        "actual_behavior_logprobs": behavior,
        "signed_delta": signed,
        "max_abs_delta": max(absolute),
        "mean_abs_delta": sum(absolute) / len(absolute),
        "sequence_sum_delta": sum(signed),
        "max_atol": max_atol,
        "mean_atol": mean_atol,
        "passed": max(absolute) <= max_atol and sum(absolute) / len(absolute) <= mean_atol,
    }


def prepare(episodes, output, max_length):
    if len(episodes) != 3 or [Path(p).resolve().parent.name for p in episodes] != EPISODE_NAMES:
        raise ValueError(
            "Use the three predeclared finance-direct-qwen-1/2/3 episode directories in order"
        )
    rows, source_records = [], []
    for path in episodes:
        path = Path(path).resolve()
        manifest = read_json(path / "manifest.json")
        assessment = assess_historical_episode(path, process_requirements=PROCESS)
        reward = episode_reward(assessment, REWARD)
        case_path = path.parent / "record.json"
        case_record = read_json(case_path) if case_path.is_file() else {}
        capture_matches = case_record.get("public_capture_matches")
        if manifest.get("status") != "closed":
            row = {
                "episode_id": manifest.get("episode_id"),
                "eligible": False,
                "exclusions": [{"kind": "episode_not_closed"}],
                "reward_result": reward,
            }
        else:
            history_path = (path / manifest["experience"]["path"]).resolve()
            if (
                not history_path.is_relative_to(path)
                or sha_file(history_path) != manifest["experience"]["sha256"]
            ):
                raise ValueError("Episode experience differs from its fixed manifest")
            history = read_json(history_path)
            row = extract_first_decision(
                manifest, history, reward, capture_matches=capture_matches, max_length=max_length
            )
            if row["eligible"]:
                before, after = manifest["source_start"], manifest["source_end"]
                if before != after or before.get("code_dirty") is not False:
                    raise ValueError(
                        "Training input is not a frozen unchanged model-development execution"
                    )
            source_records.append(
                {
                    "episode": str(path),
                    "manifest": file_reference(path / "manifest.json"),
                    "experience": file_reference(history_path),
                    "case_record": file_reference(case_path) if case_path.is_file() else None,
                    "public_capture_matches": capture_matches,
                }
            )
        row["case_record"] = file_reference(case_path) if case_path.is_file() else None
        row["public_capture_matches"] = copy.deepcopy(capture_matches)
        row["episode_path"] = str(path)
        row["episode_name"] = path.parent.name
        rows.append(row)
        atomic_write(output / (path.parent.name + "-assessment.json"), json_bytes(assessment))
        atomic_write(output / (path.parent.name + "-reward.json"), json_bytes(reward))
    identities = [row["policy_identity"] for row in rows if row["eligible"]]
    if identities and any(identity != identities[0] for identity in identities):
        raise ValueError("Selected first decisions did not share one unchanged behavior policy")
    result = {
        "predeclared": EPISODE_NAMES,
        "selection": "Not conditioned on success/reward; no replacement episodes",
        "records": rows,
        "source_files": source_records,
        "eligible": sum(row["eligible"] for row in rows),
        "excluded": sum(not row["eligible"] for row in rows),
    }
    atomic_write(output / "targets.json", json_bytes(result))
    return result


def verify_weights(model_path, row):
    model_path = Path(model_path).resolve()
    if (model_path / "adapter_config.json").exists() or any(model_path.glob("adapter_model.*")):
        raise ValueError(
            "Training requires the unmodified base directory, not a pre-updated adapter"
        )
    identity = row["policy_identity"]["config"]["weight_identity"]
    manifest_path = Path(identity["manifest"]).resolve()
    manifest = read_json(manifest_path)
    if (
        identity.get("manifest_sha256") is not None
        and sha_file(manifest_path) != identity["manifest_sha256"]
    ):
        raise ValueError(
            "Behavior weight manifest differs from the hash frozen in model configuration"
        )
    if manifest.get("declared_hf_revision") != REVISION:
        raise ValueError("Weight hash manifest revision differs from behavior")
    files = manifest.get("files", {})
    if not files or not any(name.endswith(".safetensors") for name in files):
        raise ValueError("Full base weight hashes are required")
    checked = {}
    for name, expected in files.items():
        file = (model_path / name).resolve()
        if (
            not file.is_relative_to(model_path)
            or file.stat().st_size != expected["bytes"]
            or sha_file(file) != expected["sha256"]
        ):
            raise ValueError("Base file differs from recorded behavior identity: " + name)
        checked[name] = {"bytes": expected["bytes"], "sha256": expected["sha256"]}
    return {
        "model": str(model_path),
        "revision": REVISION,
        "behavior_weight_manifest": file_reference(manifest_path),
        "checked_files": checked,
        "claim": "Matches declared frozen local service base files; behavior trace has real scores. This is trusted-service provenance, not cryptographic attestation of remote memory.",
    }


def replay_tensors(rows, *, torch, device, pad_token_id):
    width = max(row["input_tokens"] for row in rows)
    ids = [
        [pad_token_id] * (width - row["input_tokens"]) + row["token_trace"]["input_ids"]
        for row in rows
    ]
    masks = [[0] * (width - row["input_tokens"]) + [1] * row["input_tokens"] for row in rows]
    return torch.tensor(ids, dtype=torch.long, device=device), torch.tensor(
        masks, dtype=torch.long, device=device
    )


def cached_batch_logprobs(network, rows, *, torch, device, temperature=0.3):
    """Full recorded output log probabilities with differentiable past KV states.

    Uses installed HF preparation/update helpers to preserve cache positions and
    the same attention-mask cumsum position IDs as generation. Every past remains
    on its computation graph; finished peer rows stay in the batch with real pad.
    """
    pad = rows[0]["first_response"]["effective_generation"]["pad_token_id"]
    ids, mask = replay_tensors(rows, torch=torch, device=device, pad_token_id=pad)
    width = ids.shape[1]
    kwargs = {
        "attention_mask": mask,
        "use_cache": True,
        "logits_to_keep": 1,
        "cache_position": torch.arange(width, device=device),
        "past_key_values": None,
    }
    values = []
    maximum = max(row["output_tokens"] for row in rows)
    for index in range(maximum):
        inputs = network.prepare_inputs_for_generation(ids, **kwargs)
        outputs = network(**inputs, return_dict=True)
        chosen = torch.tensor(
            [
                row["token_trace"]["output_ids"][index] if index < row["output_tokens"] else pad
                for row in rows
            ],
            dtype=torch.long,
            device=device,
        )
        logits = outputs.logits[:, -1, :].float() / temperature
        values.append(torch.log_softmax(logits, dim=-1).gather(1, chosen[:, None]).squeeze(1))
        kwargs = network._update_model_kwargs_for_generation(
            outputs, kwargs, is_encoder_decoder=False
        )
        ids = torch.cat((ids, chosen[:, None]), dim=1)
    return torch.stack(values, dim=1)


def original_batch_groups(rows, service_root):
    """Verify complete historical batch membership against original service files.

    Original v0.11 records did not include row indices. Replays use predeclared
    episode order and verify token likelihoods; no historical row order is invented.
    """
    root = Path(service_root).resolve()

    def key(response):
        meta = response.get("service_record", {})
        if (
            type(meta.get("batch_index")) is not int
            or type(meta.get("batch_size")) is not int
            or meta["batch_size"] < 1
        ):
            raise ValueError("Original service batch identity is unavailable")
        value = {
            "model": response.get("model"),
            "fingerprint": response.get("system_fingerprint"),
            "batch_index": meta["batch_index"],
            "batch_size": meta["batch_size"],
            "generation": response.get("effective_generation"),
            "temperature": response.get("token_trace", {}).get("sampling_temperature"),
            "recorded_group_id": meta.get("group_id"),
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    selected = {}
    for index, row in enumerate(rows):
        response = row["first_response"]
        identity = response.get("id")
        if not isinstance(identity, str) or not identity or Path(identity).name != identity:
            raise ValueError("Original service completion identity is not a safe local record name")
        path = root / (identity + ".json")
        original = read_json(path)
        if json_bytes(original.get("response")) != json_bytes(response):
            raise ValueError("Saved episode response differs from its original service ledger")
        identity_key = key(response)
        selected.setdefault(identity_key, []).append((index, row, path))
    peers = {identity: [] for identity in selected}
    for path in sorted(root.glob("*.json")):
        value = read_json(path)
        response = value.get("response")
        if (
            not isinstance(response, dict)
            or not response.get("token_trace")
            or not response.get("service_record")
        ):
            continue
        identity_key = key(response)
        if identity_key in peers:
            peers[identity_key].append((response["id"], path))
    groups = []
    for identity_key, members in selected.items():
        first = members[0][1]["first_response"]
        expected_size = first["service_record"]["batch_size"]
        selected_ids = [member[1]["first_response"]["id"] for member in members]
        peer_ids = [identity for identity, _ in peers[identity_key]]
        if (
            len(peer_ids) != expected_size
            or len(set(peer_ids)) != expected_size
            or set(peer_ids) != set(selected_ids)
        ):
            raise ValueError(
                "Original batch peers are not all covered by the admitted preselected episodes; do not silently shrink or replace it"
            )
        groups.append(
            {
                "derived_group_key": identity_key,
                "service_root": str(root),
                "batch_index": first["service_record"]["batch_index"],
                "batch_size": expected_size,
                "indices": [member[0] for member in members],
                "episode_names": [member[1]["episode_name"] for member in members],
                "actual_completion_ids": selected_ids,
                "original_service_files": [file_reference(member[2]) for member in members],
                "original_recorded_row_indices": [
                    member[1]["first_response"]["service_record"].get("batch_row_index")
                    for member in members
                ],
                "replay_row_order": "Predeclared selected episode order; original missing row indices are not backfilled",
                "prefix_width": max(member[1]["input_tokens"] for member in members),
                "pad_token_id": first["effective_generation"]["pad_token_id"],
                "original_effective_generation": copy.deepcopy(first["effective_generation"]),
            }
        )
    return groups


class TrainingResourceLimit(RuntimeError):
    def __init__(self, details):
        super().__init__("Predeclared process RSS limit prevents continuing activation storage")
        self.details = details


def process_rss_bytes():
    fields = Path("/proc/self/statm").read_text().split()
    return int(fields[1]) * os.sysconf("SC_PAGE_SIZE")


class _SavedTensorPayload:
    def __init__(self, owner, data, device, shape, stride, repeat_heads=1, cpu_bytes=0):
        self.owner, self.data, self.device = owner, data, device
        self.shape, self.stride, self.repeat_heads = shape, stride, repeat_heads
        self.cpu_bytes = cpu_bytes

    def __del__(self):
        if self.cpu_bytes:
            self.owner.stats["packed_cpu_live_bytes"] -= self.cpu_bytes


class ParameterResidentSavedTensors:
    """Keep parameter/view storages resident; copy only saved activation data.

    Hook detachment stores autograd's saved *data*, not a detached computational
    cache. Graph edges and all original past KV tensors remain untouched.
    Exact repeated attention heads may be stored once, then restored byte-exactly.
    """

    def __init__(self, network, *, torch, max_rss_bytes, progress=None):
        self.torch, self.max_rss_bytes, self.progress = torch, max_rss_bytes, progress
        self.parameters = {}
        for parameter in network.parameters():
            key = self.storage_key(parameter)
            self.parameters[key] = parameter.untyped_storage().nbytes()
        config = getattr(network, "config", None)
        self.heads = getattr(config, "num_attention_heads", None)
        self.kv_heads = getattr(config, "num_key_value_heads", None)
        self.last_progress = 0.0
        self.stats = {
            "version": "parameter-resident-saved-data-v0.11.2",
            "parameter_storages": len(self.parameters),
            "resident_parameter_storage_bytes": sum(self.parameters.values()),
            "retained_parameter_refs": 0,
            "retained_parameter_bytes_not_copied": 0,
            "offloaded_activation_refs": 0,
            "raw_activation_bytes": 0,
            "offloaded_activation_bytes": 0,
            "packed_cpu_live_bytes": 0,
            "packed_cpu_peak_bytes": 0,
            "exact_repeated_head_refs": 0,
            "unpack_calls": 0,
            "rss_peak_bytes": process_rss_bytes(),
            "max_rss_bytes": max_rss_bytes,
            "cpu_pin_memory": False,
            "parameter_identity": "untyped_storage.data_ptr plus device, includes transposed views",
            "cache_graph_detached": False,
        }
        self.context = None

    @staticmethod
    def storage_key(tensor):
        return str(tensor.device), tensor.untyped_storage().data_ptr()

    def sample(self, extra_bytes=0):
        rss = process_rss_bytes()
        self.stats["rss_current_bytes"] = rss
        self.stats["rss_peak_bytes"] = max(rss, self.stats["rss_peak_bytes"])
        if rss + extra_bytes > self.max_rss_bytes:
            details = {**self.stats, "next_cpu_copy_bytes": extra_bytes, "observed_rss_bytes": rss}
            if self.progress:
                self.progress(details)
            raise TrainingResourceLimit(details)
        if self.progress and time.monotonic() - self.last_progress >= 2:
            self.progress(copy.deepcopy(self.stats))
            self.last_progress = time.monotonic()

    def pack(self, tensor):
        self.sample()
        shape, stride, device = tuple(tensor.shape), tuple(tensor.stride()), tensor.device
        size = tensor.numel() * tensor.element_size()
        if self.storage_key(tensor) in self.parameters:
            self.stats["retained_parameter_refs"] += 1
            self.stats["retained_parameter_bytes_not_copied"] += size
            return _SavedTensorPayload(self, tensor.detach(), device, shape, stride)
        data = tensor.detach()
        repeat = 1
        if (
            data.ndim == 4
            and data.stride(-1) == 1
            and type(self.heads) is int
            and type(self.kv_heads) is int
            and self.kv_heads > 0
            and self.heads > self.kv_heads
            and self.heads % self.kv_heads == 0
            and data.shape[1] == self.heads
        ):
            count = self.heads // self.kv_heads
            grouped = data.unflatten(1, (self.kv_heads, count))
            first = grouped[:, :, 0]
            if all(
                self.torch.equal(
                    first.view(self.torch.uint8), grouped[:, :, index].view(self.torch.uint8)
                )
                for index in range(1, count)
            ):
                data = first
                repeat = count
                self.stats["exact_repeated_head_refs"] += 1
        cpu_bytes = data.numel() * data.element_size()
        self.sample(cpu_bytes)
        # A dense, non-pinned CPU copy avoids retaining an oversized view storage
        # and avoids the pinned allocator retaining every old episode's blocks.
        saved = data.contiguous().to("cpu", copy=True)
        self.stats["offloaded_activation_refs"] += 1
        self.stats["raw_activation_bytes"] += size
        self.stats["offloaded_activation_bytes"] += cpu_bytes
        self.stats["packed_cpu_live_bytes"] += cpu_bytes
        self.stats["packed_cpu_peak_bytes"] = max(
            self.stats["packed_cpu_peak_bytes"], self.stats["packed_cpu_live_bytes"]
        )
        packet = _SavedTensorPayload(self, saved, device, shape, stride, repeat, cpu_bytes)
        self.sample()
        return packet

    def unpack(self, packet):
        self.sample()
        self.stats["unpack_calls"] += 1
        if not packet.cpu_bytes:
            return packet.data
        value = packet.data.to(packet.device)
        if packet.repeat_heads != 1:
            value = value.repeat_interleave(packet.repeat_heads, dim=1)
        if tuple(value.shape) != packet.shape:
            raise ValueError("Saved activation shape changed during exact storage restoration")
        if tuple(value.stride()) != packet.stride:
            # Broadcast zero strides need one stored element along that dimension.
            compact_shape = tuple(
                1 if stride == 0 else size for size, stride in zip(packet.shape, packet.stride)
            )
            slices = tuple(slice(0, 1) if stride == 0 else slice(None) for stride in packet.stride)
            restored = self.torch.empty_strided(
                compact_shape, packet.stride, device=packet.device, dtype=value.dtype
            )
            restored.copy_(value[slices])
            value = restored.as_strided(packet.shape, packet.stride)
        return value

    def __enter__(self):
        self.context = self.torch.autograd.graph.saved_tensors_hooks(self.pack, self.unpack)
        self.context.__enter__()
        return self

    def __exit__(self, *arguments):
        return self.context.__exit__(*arguments)

    def snapshot(self):
        self.sample()
        return copy.deepcopy(self.stats)


def protocol(args):
    return {
        "version": VERSION,
        "episodes": EPISODE_NAMES,
        "reward_spec": REWARD,
        "process_requirements": PROCESS,
        "baseline": BASELINE,
        "loss": "mean admitted episodes [-(reward - 0.5) * sum output-token log p_theta(token|prefix; temperature=0.3)]",
        "sample_scope": "First real target-model generation only; remaining behavior fixed; real failures retained, infrastructure/unknown reward excluded and reported",
        "optimizer": {
            "kind": "AdamW",
            "steps": 1,
            "learning_rate": 1e-6,
            "weight_decay": 0,
            "betas": [0.9, 0.999],
            "epsilon": 1e-8,
            "gradient_clip_norm": 1.0,
        },
        "lora": {
            "r": 8,
            "alpha": 16,
            "dropout": 0,
            "target_modules": ["q_proj", "v_proj"],
            "bias": "none",
        },
        "seed": 20260924,
        "max_length": args.max_length,
        "context_truncation": False,
        "sequence_logprob_normalization": "sum, not mean-token CE",
        "logprob_tolerance": {
            "max_absolute_nats": args.logprob_max_atol,
            "mean_absolute_nats": args.logprob_mean_atol,
            "applied_before_any_update": True,
        },
        "execution": "model.eval with gradients enabled; complete original batch/cache trajectory; past KV remains differentiable; parameter/view saved data stays GPU resident; nonparameter activation data copied nonpinned to CPU; byte-exact repeated KV heads losslessly stored once; no new sampling",
        "max_rss_gib": args.max_rss_gib,
        "resource_stop": "Observed current RSS plus next saved activation allocation checked before/after each pack; no change to reward or original operator stop",
        "replay_mode": args.replay_mode,
        "service_records": str(args.service_records),
        "teacher_forcing_control": "Explicit legacy mode retained; it failed the original likelihood gate on two recorded batched episodes; no tolerance or data change",
        "not_claimed": [
            "Full multi-turn Agentic RL",
            "Three-arm training comparison",
            "Held-out performance improvement",
            "API provider parameter training",
            "Exact BF16 sampling-probability bitwise equivalence",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", nargs=3, required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--logprob-max-atol", type=float, default=0.2)
    parser.add_argument("--logprob-mean-atol", type=float, default=0.03)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--max-rss-gib", type=float, default=64)
    parser.add_argument(
        "--replay-mode", choices=("cached_replay", "teacher_forcing"), default="cached_replay"
    )
    parser.add_argument("--service-records", type=Path, default=Path("runs/qwen-service-v11"))
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output requires a new independent destination")
    if (
        args.max_length < 1
        or not math.isfinite(args.max_rss_gib)
        or args.max_rss_gib <= 0
        or any(
            not math.isfinite(x) or x < 0 for x in (args.logprob_max_atol, args.logprob_mean_atol)
        )
    ):
        parser.error("Invalid fixed length or probability tolerance")
    model_path, output = args.model.resolve(), args.output.resolve()
    protected = [model_path, *[p.resolve() for p in args.episode]]
    if any(output == path or output.is_relative_to(path) for path in protected):
        parser.error("Output must be outside source model and episode archives")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "protocol": protocol(args),
        "source_before": code_identity(),
        "started_at": time.time(),
        "resources_before": resources(),
        "training_happened": False,
        "optimizer_steps": 0,
        "learning_gain_measured": False,
    }
    atomic_write(output / "protocol.json", json_bytes(report["protocol"]))

    def save(stage):
        report["stage"] = stage
        atomic_write(output / "progress.json", json_bytes(report))

    try:
        prepared = prepare(args.episode, output, args.max_length)
        admitted = [row for row in prepared["records"] if row["eligible"]]
        report.update(
            selected_episodes=3,
            eligible_episodes=len(admitted),
            excluded_episodes=3 - len(admitted),
            exclusions=[
                {"episode_name": row["episode_name"], "reasons": row["exclusions"]}
                for row in prepared["records"]
                if not row["eligible"]
            ],
        )
        if not admitted:
            report["status"] = "no_eligible_episodes"
            save("admission")
            return 1
        original_groups = original_batch_groups(admitted, args.service_records)
        report["original_replay_groups"] = original_groups
        groups = (
            original_groups
            if args.replay_mode == "cached_replay"
            else [{"indices": [index], "mode": "teacher_forcing"} for index in range(len(admitted))]
        )
        report["base_identity"] = verify_weights(model_path, admitted[0])
        save("validated_inputs")
        if args.prepare_only:
            report["status"] = "prepared_no_training"
            return 0

        import torch
        import transformers
        import peft
        from peft import LoraConfig, PeftModel, get_peft_model, get_peft_model_state_dict
        from safetensors.torch import save_file
        from transformers import AutoModelForCausalLM

        if not torch.cuda.is_available():
            raise ValueError(
                "This fixed experiment requires an available CUDA device; no silent CPU fallback"
            )
        torch.manual_seed(20260924)
        torch.set_num_threads(8)
        report["libraries"] = {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "peft": peft.__version__,
        }
        report["device"] = torch.cuda.get_device_name()
        torch.cuda.reset_peak_memory_stats()

        def load_base():
            network = AutoModelForCausalLM.from_pretrained(
                model_path, local_files_only=True, dtype=torch.bfloat16, attn_implementation="sdpa"
            ).to("cuda")
            if "logits_to_keep" not in inspect.signature(network.forward).parameters:
                raise ValueError(
                    "Declared model implementation must support output-only logits without cropping context"
                )
            network.config.use_cache = False
            return network

        base = load_base()
        model = get_peft_model(
            base,
            LoraConfig(
                r=8,
                lora_alpha=16,
                lora_dropout=0,
                target_modules=["q_proj", "v_proj"],
                bias="none",
                task_type="CAUSAL_LM",
            ),
        )
        model.eval()  # Evaluation mode controls dropout, NOT autograd.
        parameters = [
            (name, value) for name, value in model.named_parameters() if value.requires_grad
        ]
        if not parameters or any("lora_" not in name for name, _ in parameters):
            raise ValueError("Only the declared LoRA adapter may be trainable")

        def adapter_state(network):
            return {
                name: tensor.detach().cpu().contiguous().clone()
                for name, tensor in get_peft_model_state_dict(network).items()
            }

        def tensor_digest(values):
            hashed = hashlib.sha256()
            for name, tensor in sorted(values.items()):
                hashed.update(json_bytes([name, str(tensor.dtype), list(tensor.shape)]))
                hashed.update(tensor.contiguous().view(torch.uint8).numpy().tobytes())
            return hashed.hexdigest()

        def selected_logprobs(network, row):
            trace = row["token_trace"]
            ids = trace["input_ids"] + trace["output_ids"]
            if max(ids) >= network.config.vocab_size:
                raise ValueError("Recorded token is outside this exact base vocabulary")
            inputs = torch.tensor([ids], device="cuda", dtype=torch.long)
            targets = torch.tensor(trace["output_ids"], device="cuda", dtype=torch.long)
            # m+1 logits: final real input -> output1, ... output(m-1) -> outputm.
            logits = (
                network(
                    input_ids=inputs,
                    attention_mask=torch.ones_like(inputs),
                    use_cache=False,
                    logits_to_keep=len(targets) + 1,
                )
                .logits[0, :-1]
                .float()
                / TEMPERATURE
            )
            if logits.shape[0] != len(targets):
                raise ValueError("Output logit selection did not preserve every target")
            return torch.log_softmax(logits, dim=-1).gather(1, targets[:, None]).squeeze(1)

        def grouped_logprobs(network, group_rows):
            if args.replay_mode == "cached_replay":
                return cached_batch_logprobs(
                    network, group_rows, torch=torch, device="cuda", temperature=TEMPERATURE
                )
            if len(group_rows) != 1:
                raise ValueError("Legacy teacher-forcing control expects one episode per forward")
            return selected_logprobs(network, group_rows[0])[None, :]

        before = adapter_state(model)
        save_file(before, output / "adapter-before.safetensors")
        report["before_adapter_sha256"] = tensor_digest(before)
        comparisons = []
        for group in groups:
            group_rows = [admitted[index] for index in group["indices"]]
            with torch.no_grad():
                values = grouped_logprobs(model, group_rows)
                actual = [
                    values[index, : row["output_tokens"]].cpu().tolist()
                    for index, row in enumerate(group_rows)
                ]
            for row, observed in zip(group_rows, actual):
                comparison = {
                    "episode_name": row["episode_name"],
                    "replay_mode": args.replay_mode,
                    "batch_size": len(group_rows),
                    **compare_logprobs(
                        observed,
                        row["token_trace"]["behavior_logprobs"],
                        args.logprob_max_atol,
                        args.logprob_mean_atol,
                    ),
                }
                comparisons.append(comparison)
            del values
        atomic_write(output / "behavior-probability-check.json", json_bytes(comparisons))
        if not all(row["passed"] for row in comparisons):
            report["status"] = "behavior_probability_mismatch"
            save("probability_check_failed_no_update")
            return 1
        report["behavior_probability_checks"] = [
            {
                key: row[key]
                for key in (
                    "episode_name",
                    "max_abs_delta",
                    "mean_abs_delta",
                    "sequence_sum_delta",
                    "passed",
                )
            }
            for row in comparisons
        ]
        optimizer = torch.optim.AdamW(
            [value for _, value in parameters],
            lr=1e-6,
            betas=(0.9, 0.999),
            eps=1e-8,
            weight_decay=0,
        )
        optimizer.zero_grad(set_to_none=True)
        storage_phase = "gradient_forward"

        def storage_progress(stats):
            report["saved_tensor_storage"] = stats
            save(storage_phase)

        saved_storage = ParameterResidentSavedTensors(
            model,
            torch=torch,
            max_rss_bytes=int(args.max_rss_gib * 1024**3),
            progress=storage_progress,
        )
        losses, gradient_probability_checks = [], []
        report["backward_groups_completed"] = 0
        with torch.enable_grad():
            for group_index, group in enumerate(groups):
                group_rows = [admitted[index] for index in group["indices"]]
                report["active_replay_group"] = group_index
                storage_phase = "gradient_forward"
                save(storage_phase)
                with saved_storage:
                    logp = grouped_logprobs(model, group_rows)
                    terms = []
                    for index, row in enumerate(group_rows):
                        selected = logp[index, : row["output_tokens"]]
                        measured = compare_logprobs(
                            selected.detach().cpu().tolist(),
                            row["token_trace"]["behavior_logprobs"],
                            args.logprob_max_atol,
                            args.logprob_mean_atol,
                        )
                        gradient_probability_checks.append(
                            {
                                "episode_name": row["episode_name"],
                                "grad_enabled": selected.requires_grad,
                                "batch_size": len(group_rows),
                                **measured,
                            }
                        )
                        if not selected.requires_grad or not measured["passed"]:
                            atomic_write(
                                output / "gradient-probability-check.json",
                                json_bytes(gradient_probability_checks),
                            )
                            report["status"] = "gradient_probability_mismatch"
                            save("gradient_probability_check_failed_no_update")
                            return 1
                        term = -row["advantage"] * selected.sum() / len(admitted)
                        terms.append(term)
                        losses.append(
                            {
                                "episode_name": row["episode_name"],
                                "reward": row["reward"],
                                "advantage": row["advantage"],
                                "output_tokens": len(selected),
                                "logprob_sum": float(selected.detach().sum()),
                                "loss_contribution": float(term.detach()),
                            }
                        )
                    loss = torch.stack(terms).sum()
                    if not torch.isfinite(loss):
                        raise ValueError("Nonfinite actual REINFORCE loss")
                    storage_phase = "backward"
                    save(storage_phase)
                    loss.backward()
                    report["backward_groups_completed"] += 1
                del logp, loss, selected, term, terms
                gc.collect()
                report["saved_tensor_storage"] = saved_storage.snapshot()
                save("group_backward_complete")
        atomic_write(
            output / "gradient-probability-check.json", json_bytes(gradient_probability_checks)
        )
        gradients = {
            "pre_clip." + name: value.grad.detach().cpu().contiguous().clone()
            for name, value in parameters
            if value.grad is not None
        }
        norm = torch.nn.utils.clip_grad_norm_([value for _, value in parameters], 1.0)
        if not torch.isfinite(norm) or float(norm) == 0:
            raise ValueError("Expected a finite nonzero gradient from the admitted real outcomes")
        gradients.update(
            {
                "post_clip." + name: value.grad.detach().cpu().contiguous().clone()
                for name, value in parameters
                if value.grad is not None
            }
        )
        save_file(gradients, output / "actual-gradients.safetensors")
        atomic_write(output / "losses.json", json_bytes(losses))
        optimizer.step()
        report.update(
            training_happened=True,
            optimizer_steps=1,
            losses=losses,
            total_loss=sum(row["loss_contribution"] for row in losses),
            gradient_norm_before_clip=float(norm),
            gradient_clip_limit=1.0,
            gradient_file=file_reference(output / "actual-gradients.safetensors"),
        )
        after = adapter_state(model)
        report["after_adapter_sha256"] = tensor_digest(after)
        report["changed_adapter_elements"] = sum(
            int((after[name] != before[name]).sum()) for name in after
        )
        if (
            report["before_adapter_sha256"] == report["after_adapter_sha256"]
            or not report["changed_adapter_elements"]
        ):
            raise ValueError("Optimizer step did not change actual adapter parameters")
        checkpoint_path = output / "adapter"
        model.save_pretrained(checkpoint_path, safe_serialization=True, save_embedding_layers=False)
        with torch.no_grad():
            probe_rows = [admitted[index] for index in groups[0]["indices"]]
            updated_probabilities = (
                grouped_logprobs(model, probe_rows)[0, : probe_rows[0]["output_tokens"]]
                .cpu()
                .tolist()
            )
        save("adapter_saved")
        del optimizer, model, base, parameters, norm
        gc.collect()
        torch.cuda.empty_cache()
        base = load_base()
        restored = PeftModel.from_pretrained(base, checkpoint_path, is_trainable=False)
        restored.eval()
        restored_state = adapter_state(restored)
        report["reloaded_adapter_sha256"] = tensor_digest(restored_state)
        with torch.no_grad():
            restored_probabilities = (
                grouped_logprobs(restored, probe_rows)[0, : probe_rows[0]["output_tokens"]]
                .cpu()
                .tolist()
            )
        functional = compare_logprobs(
            restored_probabilities,
            updated_probabilities,
            args.logprob_max_atol,
            args.logprob_mean_atol,
        )
        atomic_write(output / "reload-probability-check.json", json_bytes(functional))
        report["reload_parameter_match"] = (
            report["reloaded_adapter_sha256"] == report["after_adapter_sha256"]
        )
        report["reload_functional_check"] = {
            key: functional[key] for key in ("max_abs_delta", "mean_abs_delta", "passed")
        }
        report["peak_gpu_bytes"] = torch.cuda.max_memory_allocated()
        if not report["reload_parameter_match"] or not functional["passed"]:
            raise ValueError("Adapter reload verification failed; measured differences preserved")
        report["status"] = "one_update_saved_and_reloaded"
        save("complete")
        return 0
    except TrainingResourceLimit as error:
        report.update(status="resource_limit", resource_stop=error.details)
        save("resource_limit_no_further_compute")
        return 1
    except Exception as error:
        report.update(
            status="experiment_error", error={"type": type(error).__name__, "message": str(error)}
        )
        save("error")
        return 1
    finally:
        report.update(
            ended_at=time.time(), source_after=code_identity(), resources_after=resources()
        )
        atomic_write(output / "report.json", json_bytes(report))
        print(
            json.dumps(
                {
                    key: report.get(key)
                    for key in (
                        "status",
                        "eligible_episodes",
                        "excluded_episodes",
                        "training_happened",
                        "optimizer_steps",
                        "learning_gain_measured",
                    )
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
