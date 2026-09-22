"""Compile actual calls into provenance-preserving SFT/RL interchange records."""

import copy
from pathlib import Path

from .kernel import World
from .storage import Store, atomic_write, json_bytes
from .validation import evaluate


def _jsonl(path, records):
    import json

    atomic_write(
        path,
        (
            "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in records)
        ).encode(),
    )


def _verified_intervals(state):
    intervals = []
    evals = {r["submission_id"]: r for r in state["evaluations"] if r["submission_id"]}
    action_times = {
        row["output"].get("result", {}).get("submission_id"): row["logical_time"]
        for row in state["interactions"]
        if row["action"] == "submit" and row["output"].get("ok")
    }
    for item in state["work_items"].values():
        lower = 0
        # A later requirement may use earlier work as context, but not duplicate its targets.
        if item["dependencies"]:
            previous = state["work_items"][item["dependencies"][-1]]
            lower = max((s.get("review") or {}).get("at", s["at"]) for s in previous["submissions"])
        for sub in item["submissions"]:
            evaluation = evals.get(sub["submission_id"])
            upper = action_times.get(sub["submission_id"], sub["at"])
            if (
                evaluation
                and evaluation["passed"]
                and evaluation["validity"] == "valid"
                and not sub["invalidated"]
                and (sub.get("review") or {}).get("decision") == "accepted"
            ):
                intervals.append((lower, upper, sub["submission_id"]))
            lower = max(upper, (sub.get("review") or {}).get("at", upper))
    return intervals


def compile_calls(state):
    actions = {row["action_id"]: row for row in state["interactions"]}
    intervals = _verified_intervals(state)
    sft, rl, candidates = [], [], []
    for call in state["calls"]:
        if call["actor_id"] != "analyst":
            continue
        times = [actions[aid]["logical_time"] for aid in call["action_ids"] if aid in actions]
        source = next(
            (
                sid
                for lower, upper, sid in intervals
                if times and all(lower < tick <= upper for tick in times)
            ),
            None,
        )
        eligible = bool(
            source
            and call["tools_complete"]
            and call["tool_results"]
            and all(row["ok"] for row in call["tool_results"])
            and call["branch_id"] == state["branch_id"]
            and call["provider"] not in ("rule_based", "fixture")
        )
        assistant = copy.deepcopy(call["response"]["choices"][0]["message"])
        messages = copy.deepcopy(call["request"]["messages"]) + [assistant]
        common = {
            "schema_version": state["schema_version"],
            "call_id": call["call_id"],
            "instance_id": state["instance_id"],
            "branch_id": call["branch_id"],
            "lineage_id": state["project"]["lineage_id"],
            "split": state["project"]["split"],
            "provider": call["provider"],
            "model": call["model_returned"] or call["model_requested"],
            "submission_id": source,
        }
        sample = {
            **common,
            "messages": messages,
            "tools": call["request"].get("tools", []),
            "message_loss_mask": [0] * (len(messages) - 1) + [int(eligible)],
            "eligible": eligible,
            "token_ids": call.get("token_ids"),
            "mask_granularity": "message; trainer must tokenize the original messages",
        }
        candidates.append(sample)
        if eligible:
            sft.append(sample)
        # Only target outputs are policy actions. Staff/tool contents remain observations.
        if call["branch_id"] == state["branch_id"]:
            rl.append(
                {
                    **common,
                    "observation": call["request"],
                    "action": assistant,
                    "tool_observations": call["tool_results"],
                    "policy_mask": 1,
                    "verified_segment_reward": float(bool(source)),
                    "token_ids": call.get("token_ids"),
                    "token_logprobs": call.get("token_logprobs"),
                    "usage": call["usage"],
                    "on_policy_training_ready": False,
                }
            )
    return sft, rl, candidates


def export_bundle(root, destination):
    destination = Path(destination).resolve()
    world_root = Path(root).resolve()
    if world_root == destination or world_root in destination.parents:
        raise ValueError("Export must be outside the live world")
    if destination.exists():
        raise ValueError("Export destination already exists")
    evaluate(root)
    state = Store(root).load()
    sft, rl, candidates = compile_calls(state)
    destination.mkdir(parents=True)
    _jsonl(destination / "calls.jsonl", state["calls"])
    _jsonl(destination / "interactions.jsonl", state["interactions"])
    _jsonl(destination / "evaluations.jsonl", state["evaluations"])
    _jsonl(destination / "sft.jsonl", sft)
    _jsonl(destination / "rl.jsonl", rl)
    _jsonl(destination / "candidates.jsonl", candidates)
    manifest = {
        "schema_version": state["schema_version"],
        "instance_id": state["instance_id"],
        "branch_id": state["branch_id"],
        "lineage_id": state["project"]["lineage_id"],
        "split": state["project"]["split"],
        "project": state["project"],
        "counts": {
            "model_calls": len(state["calls"]),
            "interactions": len(state["interactions"]),
            "sft": len(sft),
            "rl": len(rl),
            "candidates": len(candidates),
        },
        "limitations": [
            "Message masks require backend tokenization.",
            "Absent token IDs/log probabilities are null, never reconstructed as observations.",
            "SFT eligibility verifies outcomes, not every intermediate reasoning statement.",
            "Rule-based witnesses are not model-generated training demonstrations.",
        ],
    }
    atomic_write(destination / "manifest.json", json_bytes(manifest))
    World(root).snapshot(destination / "world")
    return manifest


def assert_disjoint(manifests):
    assignments = {}
    for manifest in manifests:
        lineage, split = manifest["lineage_id"], manifest["split"]
        if lineage in assignments and assignments[lineage] != split:
            raise ValueError(f"Lineage leakage across splits: {lineage}")
        assignments[lineage] = split
    return assignments
