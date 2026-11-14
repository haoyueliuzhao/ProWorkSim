"""Zero-network replay of actual paid responses through the real SDK.

Seven immutable historical responses include the real two-tool rejection and
subsequent legal recovery. Explicit programmed staff_wait responses only end the
diagnostic after the recorded tape; they are never called provider observations.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from .storage import digest, json_bytes
from .software_benchmark_deepseek_prefix_v055_r2 import count_incomplete_prefix

VERSION = "v203.2.3-recorded-provider-format-replay-r3"
TAPE_SHA256 = "c44737183545e22040990041377991a312020f519c2a929184f09f92dc691b2d"


class RecordedProviderReplay:
    def __init__(self, counter, folder, *, tape_path=None):
        path = Path(tape_path) if tape_path else Path(__file__).resolve().parents[2] / "config/v203-2-3-recorded-format-replay.json"
        raw = path.read_bytes()
        if digest(raw) != TAPE_SHA256:
            raise ValueError("Recorded provider response tape changed")
        self.tape = json.loads(raw)
        if self.tape.get("version") != "v203.2.3-recorded-provider-format-tape-r3":
            raise ValueError("Unexpected recorded provider tape")
        self.counter, self.folder = counter, Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.positions = {member: 0 for member in ("member_001", "member_002")}
        self.boundaries = dict.fromkeys(self.positions, 0)
        self.historical_prompt_bound = {}
        self.calls = []
        for member, rows in self.tape["members"].items():
            if member not in self.positions:
                raise ValueError("Tape member outside fixed REVIEW2")
            for row in rows:
                if digest(json_bytes(row["body"])) != row["source"]["sha256"]:
                    raise ValueError("A recorded provider body differs from its original retained source")
            self.historical_prompt_bound[member] = max(row["body"]["usage"]["prompt_tokens"] for row in rows)

    def measurement(self, wire, member):
        actual = self.counter.measure(wire)
        # Old immutable receipts describe a different historical prompt. A CPU
        # replay must reserve enough for those receipts without falsifying them
        # or pretending their token usage was measured on the current prompt.
        return {**actual,
            "prompt_tokens": max(actual["prompt_tokens"], self.historical_prompt_bound[member]),
            "method": "diagnostic_replay_max_current_recipe_and_historical_prompt_bound",
            "current_recipe_prompt_tokens": actual["prompt_tokens"],
            "historical_prompt_bound": self.historical_prompt_bound[member],
            "formal_provider_counter_changed": False, "current_provider_usage_measured": False}

    def post(self, route, payload):
        member, wire = payload["member_id"], payload["wire"]
        if member not in self.positions:
            raise ValueError("Cross-member replay request")
        if route == "/tokenize":
            return self.measurement(wire, member)
        if route == "/tokenize-prefix":
            folder = self.folder / member
            folder.mkdir(exist_ok=True)
            tokens = count_incomplete_prefix(SimpleNamespace(counter=self.counter, folder=folder),
                wire, tuple(payload["pending_ids"]))
            return {"prompt_tokens": tokens, "request_sha256": digest(json_bytes(wire)),
                "method": "official_original_member_incomplete_prefix", "count_only_not_dispatchable": True}
        if route != "/chat/completions" or payload.get("usage_id") != "agent":
            raise AssertionError("This bounded recorded-response diagnostic has no new model or summary backend")
        measured = self.measurement(wire, member)
        if payload["prompt_upper_bound"] != measured["prompt_tokens"]:
            raise AssertionError("Replay dispatch differs from its counted wire request")
        index = self.positions[member]
        rows = self.tape["members"][member]
        if index < len(rows):
            row = rows[index]
            body = copy.deepcopy(row["body"])
            self.positions[member] += 1
            kind = "unmodified_historical_provider_response"
            source = row["source"]
        else:
            self.boundaries[member] += 1
            if self.boundaries[member] > 2:
                raise AssertionError("Recorded diagnostic exceeded its explicit end-of-tape boundary")
            identity = "diagnostic-end-of-recorded-tape-" + member + "-" + str(self.boundaries[member])
            body = {"id": identity, "model": "deepseek-flash", "object": "chat.completion", "created": 0,
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                    "tool_calls": [{"id": identity, "type": "function", "function": {"name": "staff_wait",
                        "arguments": json.dumps({"reason": "Programmed diagnostic boundary after recorded provider tape"})}}]}}],
                "usage": {"prompt_tokens": measured["prompt_tokens"], "completion_tokens": 1,
                    "total_tokens": measured["prompt_tokens"] + 1, "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": measured["prompt_tokens"]}}
            kind, source = "programmed_diagnostic_boundary_not_provider_output", None
        receipt = {"member": member, "kind": kind, "historical_source": source,
            "response_id": body["id"], "response_sha256": digest(json_bytes(body)),
            "current_wire_sha256": digest(json_bytes(wire)), "current_count": measured,
            "new_provider_calls": 0, "new_cash_charge": 0,
            "usage_interpretation": "historical reported usage or programmed boundary; not current provider billing"}
        self.calls.append(receipt)
        with (self.folder / "response-replay.jsonl").open("a") as stream:
            stream.write(json.dumps(receipt, ensure_ascii=False) + "\n")
        return body

    def summary(self):
        return {"version": VERSION, "tape_sha256": TAPE_SHA256,
            "recorded_responses_replayed": dict(self.positions), "programmed_boundary_responses": dict(self.boundaries),
            "new_provider_calls": 0, "new_cash_charge": 0, "response_receipts": copy.deepcopy(self.calls)}


def run_sdk_replay(runtime, replay, *, max_opportunities=12):
    """Run actual bounded SDK opportunities through the failing recovery edge."""
    outcomes = []
    for _ in range(max_opportunities):
        runtime.sync_members()
        if runtime.select_next() is None:
            break
        outcome = runtime.step()
        outcomes.append(outcome)
        runtime.owner.save()
        runtime.note_population("recorded_provider_format_replay")
        if outcome["status"] in {"environment_error", "model_service_error", "model_budget_exhausted", "execution_integrity_error"}:
            break
        if all(value >= 1 for value in replay.boundaries.values()):
            break
    receipts = [row for worker in runtime.policies.values()
                for row in worker.transport._role_context_v203_2_3["receipts"]]
    recovery = [row for row in receipts if row.get("format_feedback_removed_indices")
                or row["proof"].get("format_feedback_removed_indices")]
    remapped = [row for row in recovery if any(item["projected_index"] != item["original_index"]
                for item in row.get("source_index_mapping", []))]
    passed = (len(outcomes) <= max_opportunities and all(value >= 1 for value in replay.boundaries.values())
              and not any(row["status"] == "environment_error" for row in outcomes) and bool(recovery))
    condition = runtime.policies["member_001"].transport._role_context_v203_2_3["condition"]
    if condition != "K0":
        passed = passed and bool(remapped) and not any(row["proof"].get("admitted") is False for row in receipts)
    else:
        passed = passed and all(row["baseline_request_sha256"] == row["selected_request_sha256"] for row in receipts)
    report = {"version": VERSION, "passed": passed, "condition": condition,
        "outcomes": outcomes, "recovery_projection_calls": len(recovery), "remapped_projection_calls": len(remapped),
        "recorded_two_tool_response_rejected": any(row["status"] == "model_format_feedback" for row in outcomes),
        "new_provider_calls": 0, "replay": replay.summary(),
        "interpretation": "Actual SDK replay of old provider outputs, not a new model run or benchmark score"}
    runtime._passive_boundary = "recorded_provider_replay_complete" if passed else "recorded_provider_replay_failed"
    runtime.owner.passive_sidecar.record("BOUNDARY", "boundary", {
        "status": runtime._passive_boundary, "opportunities": len(outcomes), "new_provider_calls": 0})
    return report
