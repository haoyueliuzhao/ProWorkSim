#!/usr/bin/env python3
"""Read-only signal disaggregation of a frozen prior online run; no model load."""

import argparse
import copy
from pathlib import Path

from proworksim.online_signals import decision_stage, summarize_signals
from proworksim.online_training import reference
from proworksim.storage import atomic_write, json_bytes, read_json


def report_run(source):
    source = Path(source).resolve()
    online = source / "online"
    windows, references = [], []
    for directory in sorted(online.glob("window-*")):
        paths = [directory / "update" / (name + ".json") for name in
                 ("admission", "report", "losses", "gradient-probability-check")]
        admission, report, losses, checks = map(read_json, paths)
        references.extend(reference(path) for path in paths)
        rollouts = {}
        for slot in sorted((directory / "collection").glob("slot-*")):
            rollout_path = slot / "team-rollout.json"
            if rollout_path.exists():
                rollout = read_json(rollout_path)
                rollouts[rollout["rollout_id"]] = rollout
                references.append(reference(rollout_path))
        slot_rollouts = {item["slot_id"]: rollouts[item["reward"]["episode_id"]] for item in admission["slots"]
                         if item.get("reward", {}).get("episode_id") in rollouts}
        rows = copy.deepcopy(admission["decisions"])
        check_by_call = {item["call_id"]: item for item in checks}
        loss_by_call = {item["call_id"]: item for item in losses}
        for row, advantage in zip(rows, report["advantages"]):
            rollout = slot_rollouts[row["slot_id"]]
            reward = rollout["reward_eligibility"]
            starts = [event for event in rollout["events"] if event["kind"] == "model_call"
                      and event["payload"].get("stage") == "started" and event["payload"].get("call_id") == row["call_id"]]
            if len(starts) != 1:
                raise ValueError("Unique original start required for diagnostic stage")
            row["task"] = reward["scope"]
            row["stage"] = decision_stage(rollout["events"], starts[0]["sequence"], row["member_id"], reward["spec"]["work_id"])
            if row["call_id"] in check_by_call:
                import math
                ratios = [math.exp(value) for value in check_by_call[row["call_id"]]["signed_delta"]]
                loss = loss_by_call[row["call_id"]]
                clip = report["recipe"]["clip"]
                loss.update(clipped_objective_tokens=sum(r > 1 + clip and advantage > 0 or r < 1 - clip and advantage < 0 for r in ratios),
                            ratio_outside_interval_tokens=sum(r < 1 - clip or r > 1 + clip for r in ratios),
                            clipping_measured_tokens=len(ratios))
        summary = summarize_signals(rows, report["old_critic_values"], report["advantages"], losses)
        by_task_member = summarize_signals([{**row, "stage": {"label": "all_stages"}} for row in rows],
                                         report["old_critic_values"], report["advantages"], losses)
        windows.append({"window_id": report["window_id"], "reward_by_slot": [
            {"slot_id": slot["slot_id"], "reward": slot.get("reward", {}).get("reward")} for slot in admission["slots"]],
            "signal_by_stage": summary, "signal_by_task_member": by_task_member,
            "historical_shared_gradient_norms": report["gradient_norms"],
            "historical_group_gradients": None,
            "group_gradient_limitation": "Not recorded. Do not allocate the total norm to groups or infer nonzero group gradient from a nonzero scalar loss.",
            "post_update_policy_change": None,
            "post_update_limitation": "Frozen logs contain pre-update behavior recomputation only. No post-update forward or new work was executed in this read-only analysis."})
    return {"version": "historical-online-signal-analysis-v0.14", "source": str(source), "source_files": references,
            "original_files_changed": False, "model_forwards": 0, "windows": windows,
            "scope": "Retrospective disaggregation of saved real advantages/losses/tokens and public prior stages. No new gradient attribution or causal learning claim."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new output; historical diagnostic records are never overwritten")
    result = report_run(args.source)
    atomic_write(args.output, json_bytes(result))
    print({"output": str(args.output), "windows": len(result["windows"]), "model_forwards": 0})


if __name__ == "__main__":
    main()
