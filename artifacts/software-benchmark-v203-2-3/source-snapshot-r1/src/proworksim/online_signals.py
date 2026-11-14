"""Finite, measured online learning diagnostics and joint reward-to-go targets.

Stage labels are descriptive metadata derived only from the recorded public
prefix. They never enter a worker prompt or select an action/reward.
"""

import math
from collections import defaultdict

VERSION = "online-signal-diagnostics-v0.14"


def decision_stage(events, before_sequence, member_id, work_id=None):
    latest, observation_sequence, delivered = {}, None, False
    for event in events:
        if event["sequence"] >= before_sequence:
            break
        payload = event["payload"]
        if event["kind"] == "public_observation" and event.get("worker_id") == member_id:
            latest, observation_sequence = payload.get("work_items", {}), event["sequence"]
        if event["kind"] == "environment_event" and payload.get("kind") == "manual_handoff":
            detail = payload.get("payload", {})
            if (detail.get("route_id") == "basis" and payload.get("outcome") == "applied"
                    and (work_id is None or detail.get("work_item_id") == work_id)):
                delivered = True
    work = latest.get(work_id, {}) if work_id else (next(iter(latest.values())) if len(latest) == 1 else {})
    status = work.get("status", "unobserved")
    return {
        "label": status + ("/after_basis_delivery" if delivered else "/no_episode_basis_delivery"),
        "before_sequence": before_sequence, "own_observation_sequence": observation_sequence,
        "work_id": work_id, "basis_delivery_in_current_episode": delivered,
        "scope": "Past public status and actually applied basis delivery; preparation may already establish work state",
    }


def joint_return(reward, sequence, mode, events):
    if mode == "terminal_mc":
        return float(reward["reward"]), {"mode": mode, "terminal_reward": reward["reward"]}
    if mode != "joint_reward_to_go":
        raise ValueError("Unknown credit assignment recipe")
    ledger = reward.get("ledger")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("events"), list):
        raise ValueError("Joint reward-to-go requires an explicit historical reward ledger")
    actual_sequences = {e["sequence"] for e in events}
    terminal = ledger.get("terminal_sequence")
    if type(terminal) is not int or terminal != max(actual_sequences):
        raise ValueError("Reward ledger terminal sequence must match the original episode")
    values, future = [], []
    for index, entry in enumerate(ledger["events"]):
        amount, at = entry.get("amount"), entry.get("sequence")
        if (type(amount) not in (int, float) or not math.isfinite(amount)
                or type(at) is not int or at not in actual_sequences
                or entry.get("settlement") not in {"event", "terminal"}
                or not isinstance(entry.get("term_id"), str) or not entry["term_id"]):
            raise ValueError("Finite, located historical reward settlements required")
        if entry["settlement"] == "terminal" and at != terminal:
            raise ValueError("Terminal credit must be settled at episode terminal sequence")
        values.append(float(amount))
        if at >= sequence:
            future.append(index)
    if not math.isclose(math.fsum(values), reward["reward"], abs_tol=1e-10, rel_tol=1e-10):
        raise ValueError("Reward ledger total differs from the terminal task contract")
    target = math.fsum(values[index] for index in future)
    return target, {"mode": mode, "terminal_reward": reward["reward"], "decision_sequence": sequence,
                    "included_ledger_event_indices": future, "past_reward_excluded": math.fsum(values) - target,
                    "ledger_version": ledger.get("version"), "terminal_sequence": terminal}


def group_key(row):
    return (row.get("task", "unspecified"), row["member_id"], row.get("stage", {}).get("label", "unspecified"))


def summarize_signals(rows, values, advantages, losses):
    loss_by_call = {item["call_id"]: item for item in losses}
    grouped = {}
    for row, value, advantage in zip(rows, values, advantages):
        key = group_key(row)
        group = grouped.setdefault(key, {
            "task": key[0], "member_id": key[1], "stage": key[2], "decisions": 0,
            "output_tokens": 0, "advantages": {"positive": 0, "negative": 0, "zero": 0},
            "advantage_range": [advantage, advantage], "critic_value_range": [value, value],
            "return_target_range": [row["reward"], row["reward"]], "actor_loss_sum": 0.0,
            "critic_loss_sum": 0.0, "call_ids": [], "clipped_objective_tokens": 0,
            "ratio_outside_interval_tokens": 0, "clipping_measured_tokens": 0,
        })
        group["decisions"] += 1
        group["output_tokens"] += len(row["tokens"]["output_ids"])
        group["advantages"]["positive" if advantage > 0 else "negative" if advantage < 0 else "zero"] += 1
        for field, item in (("advantage_range", advantage), ("critic_value_range", value), ("return_target_range", row["reward"])):
            group[field] = [min(group[field][0], item), max(group[field][1], item)]
        group["call_ids"].append(row["call_id"])
        loss = loss_by_call.get(row["call_id"])
        if loss:
            group["actor_loss_sum"] += loss["actor_loss"]
            group["critic_loss_sum"] += loss["critic_loss"]
            for field in ("clipped_objective_tokens", "ratio_outside_interval_tokens", "clipping_measured_tokens"):
                group[field] += loss.get(field, 0)
    for group in grouped.values():
        n = group["clipping_measured_tokens"]
        group["clipped_objective_fraction"] = group["clipped_objective_tokens"] / n if n else None
        group["ratio_outside_interval_fraction"] = group["ratio_outside_interval_tokens"] / n if n else None
        group["own_gradient_record"] = ("mathematically_zero_advantage_term" if group["advantages"]["zero"] == group["decisions"]
                                        else "not_measured_by_this_summary")
    return {"version": VERSION, "groups": list(grouped.values()),
            "scope": "Actual admitted own-token terms. Retention, nonzero signal, gradient size and work improvement are distinct."}


class GroupGradientCapture:
    """Capture actual leaf gradient contributions during existing backwards.

    Hooks only observe gradients; they return None and never alter accumulation.
    A fixed group cap bounds CPU storage. Missing groups remain explicit.
    """

    def __init__(self, parameters, torch, maximum):
        self.parameters, self.torch, self.maximum = parameters, torch, maximum
        self.current = None
        self.buffers, self.counts, self.omitted = {}, defaultdict(int), set()
        self.handles = [parameter.register_hook(self._hook(name)) for name, parameter in parameters.items()] if maximum else []

    def _hook(self, name):
        def capture(gradient):
            if self.current not in self.buffers:
                return
            data = gradient.detach().cpu()
            target = self.buffers[self.current]
            if name not in target:
                target[name] = data.clone()
            else:
                target[name].add_(data)
        return capture

    def select(self, row):
        key = group_key(row)
        self.current = key
        self.counts[key] += 1
        if key not in self.buffers:
            if len(self.buffers) < self.maximum:
                self.buffers[key] = {}
            else:
                self.omitted.add(key)

    def finish(self):
        for handle in self.handles:
            handle.remove()
        self.handles.clear()
        total = {name: p.grad.detach().cpu() for name, p in self.parameters.items() if p.grad is not None}
        total_norm_squared = sum(float(g.double().square().sum()) for g in total.values())
        groups, reconstructed = [], {}
        for key, parameters in self.buffers.items():
            norm_squared = sum(float(g.double().square().sum()) for g in parameters.values())
            dot = sum(float((g.double() * total[name].double()).sum()) for name, g in parameters.items())
            groups.append({"task": key[0], "member_id": key[1], "stage": key[2], "decisions": self.counts[key],
                           "gradient_l2_norm": math.sqrt(norm_squared), "dot_with_total_gradient": dot,
                           "cosine_with_total_gradient": dot / math.sqrt(norm_squared * total_norm_squared)
                           if norm_squared and total_norm_squared else None,
                           "record": "direct leaf-gradient hooks, summed before shared clipping"})
            for name, gradient in parameters.items():
                if name not in reconstructed:
                    reconstructed[name] = gradient.clone()
                else:
                    reconstructed[name].add_(gradient)
        residual = math.sqrt(sum(float((g.double() - reconstructed.get(name, self.torch.zeros_like(g)).double()).square().sum())
                                 for name, g in total.items())) if not self.omitted and self.maximum else None
        return {"version": VERSION, "maximum_groups": self.maximum, "groups": groups,
                "omitted_groups": [list(key) for key in sorted(self.omitted)],
                "total_gradient_l2_norm": math.sqrt(total_norm_squared), "all_groups_reconstruction_l2_residual": residual,
                "additional_actor_forwards": 0,
                "scope": "Norms are not additive. Dot/cosine show alignment in this update, not causal work benefit; finite precision accumulation may leave residual."}


def sampled_change(before, after, clip):
    if not before or len(before) != len(after):
        raise ValueError("Aligned actual sampled token probabilities required")
    delta = [new - old for old, new in zip(before, after)]
    if any(not math.isfinite(value) for value in delta):
        raise ValueError("Nonfinite post-update sampled probability")
    ratios = [math.exp(value) for value in delta]
    return {
        "sampled_output_tokens": len(delta), "old_logprobs": before, "new_logprobs": after,
        "new_minus_old_logprob": delta, "sampled_ratio_range": [min(ratios), max(ratios)],
        "mean_new_minus_old_logprob": math.fsum(delta) / len(delta),
        "mean_abs_logprob_delta": math.fsum(abs(value) for value in delta) / len(delta),
        "sampled_old_to_new_logratio_mean": -math.fsum(delta) / len(delta),
        "sampled_k3_ratio_minus_logratio_minus_one": math.fsum(math.expm1(value) - value for value in delta) / len(delta),
        "sampled_ratio_outside_clip_fraction": sum(r < 1 - clip or r > 1 + clip for r in ratios) / len(ratios),
        "scope": "Selected behavior-token estimates at their original contexts; not full-distribution KL, trajectory KL, or fresh work success. Logratio sample mean can be negative.",
    }


def select_post_update_rows(rows, maximum):
    """Predeclared, outcome-blind first decision per encountered diagnostic group."""
    selected, seen = [], set()
    for index, row in enumerate(rows):
        key = group_key(row)
        if key not in seen and len(selected) < maximum:
            selected.append(index)
        seen.add(key)
    return selected
