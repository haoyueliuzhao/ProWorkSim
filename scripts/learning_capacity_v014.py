"""CPU counterfactual model-input capacity of explicit public rule paths.

No model forward, sampling, behavior probability, learner, or training export.
A program chooses valid actions. Actual ModelPolicy builds requests and the
same local-service prepare_prompt and pinned tokenizer render their input.
"""

import argparse
import copy
import json
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.local_model_service import prepare_prompt
from proworksim.model_policy import ModelPolicy
from proworksim.online_collection import run_fragment
from proworksim.staff_runtime import StaffRuntime
from proworksim.storage import digest, json_bytes
from proworksim.templates.learning_work import build_learning_case
from proworksim.work_interface import WorkInterface
from scripts.learning_work_experiment_v014 import PublicWitnessPolicy


class ProgramTransport:
    def __init__(self, tokenizer, output, role):
        self.tokenizer, self.output, self.role = tokenizer, output, role
        self.output.mkdir(parents=True, exist_ok=False)
        self.decision = None
        self.rows = []

    def complete(self, request, *, timeout_seconds):
        rendered, messages, projection = prepare_prompt(request, self.tokenizer, "single_call")
        ids = self.tokenizer(rendered, add_special_tokens=False)["input_ids"]
        index = len(self.rows)
        decision = self.decision
        action = decision.get("action") if decision["kind"] == "act" else "staff_" + decision["kind"]
        arguments = decision.get("arguments", {"reason": decision.get("reason", "program witness")})
        folder = self.output / f"request-{index:02d}"
        folder.mkdir()
        (folder / "request.json").write_bytes(json_bytes(request))
        (folder / "prompt.txt").write_text(rendered)
        (folder / "render.json").write_bytes(json_bytes({"actual_prompt_messages": messages, "prompt_projection": projection,
                                                         "input_ids": ids, "input_origin": "actual_modelpolicy_request_program_path"}))
        row = {"role": self.role, "local_index": index, "program_action": action,
               "input_tokens": len(ids), "requested_output": request["max_tokens"],
               "prompt_plus_reserved_output": len(ids) + request["max_tokens"],
               "exceeds_8192": len(ids) + request["max_tokens"] > 8192,
               "exceeds_12288": len(ids) + request["max_tokens"] > 12288,
               "prompt_sha256": digest(rendered.encode()), "request_sha256": digest(json_bytes(request)),
               "actual_decision_source": "program_witness", "behavior_logprobs": None}
        self.rows.append(row)
        body = {"id": f"program-{self.role}-{index}", "model": "program_witness_no_model",
                "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": f"program-tool-{index}", "type": "function",
                     "function": {"name": action, "arguments": json.dumps(arguments)}}]}, "finish_reason": "tool_calls"}],
                # Adapter-only synthetic completion accounting, not sampled tokens.
                "usage": {"prompt_tokens": len(ids), "completion_tokens": 1, "total_tokens": len(ids) + 1},
                "origin": "program_witness", "real_model_execution": False}
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


class CounterfactualInputPolicy:
    def __init__(self, task, role, limit, tokenizer, output, role_task):
        self.reference = PublicWitnessPolicy(role=role, task=task, limit=limit)
        self.rule_memory = {}
        self.transport = ProgramTransport(tokenizer, output, role)
        self.policy = ModelPolicy({
            "backend_id": "program_witness", "model": "program_witness_no_model",
            "base_url": "http://127.0.0.1:1/v1", "api_key_env": None,
            "task": role_task, "action_protocol": "native_tools", "context_policy": "latest_observation",
            "format_error_policy": "format_feedback_continue", "format_limits": {"max_total": 4, "max_consecutive": 2},
            "temperature": 0.7, "max_output_tokens": 512, "max_context_tokens": 32768,
            "pricing": {"input_miss_per_million": 0, "input_hit_per_million": 0, "output_per_million": 0},
            "budget": {"max_decisions": limit, "max_http_attempts": limit, "max_total_tokens": 500000,
                       "max_cost_usd": 0, "max_context_bytes": 240000},
        }, transport=self.transport)
        self.config = {"origin": "program_witness_counterfactual_input", "reference": self.reference.config,
                       "model_policy": self.policy.config, "training_eligible": False}

    def bind_event_sink(self, sink):
        self.policy.bind_event_sink(sink)

    def decide(self, context):
        scripted_context = {**context, "memory": self.rule_memory}
        decision = self.reference.decide(scripted_context)
        self.rule_memory = copy.deepcopy(decision["memory"])
        self.transport.decision = decision
        return self.policy.decide(context)


def run_case(case_id, presentation, tokenizer, root):
    prepared = build_learning_case(case_id, root)
    captures, ports, policies = {}, {}, {}
    for role_spec in prepared.scenario["roles"]:
        role = role_spec["role_id"]
        port = WorkInterface(prepared.world.session(role, "TEAM"), role, variant="v14", presentation=presentation,
                             audit_dir=root / "public-projections" / role)
        ports[role] = capture_port(port, captures.setdefault(role, []))
        policies[role] = CounterfactualInputPolicy(prepared.case["task"], role, prepared.case["role_decision_limits"][role],
                                                  tokenizer, root / "requests" / role, role_spec["config"]["task"])
    runtime = StaffRuntime(ports, policies, recorder=ExperienceRecorder())
    boundary = run_fragment(prepared, runtime)
    rows = [row for policy in policies.values() for row in policy.transport.rows]
    # No episode/TeamRollout is produced or exported: not actor data.
    result = {"case_id": case_id, "presentation": presentation, "boundary": boundary,
              "origin": "program_witness_counterfactual_input", "model_execution": False, "training_eligible": False,
              "max_prompt_tokens": max((row["input_tokens"] for row in rows), default=None),
              "max_prompt_plus_reserved_output": max((row["prompt_plus_reserved_output"] for row in rows), default=None),
              "exceeds_8192": [row for row in rows if row["exceeds_8192"]],
              "exceeds_12288": [row for row in rows if row["exceeds_12288"]], "steps": rows,
              "decision_counts": {role: len(policy.transport.rows) for role, policy in policies.items()},
              "declaration": "32k render-only adapter allowance is used to observe the full scripted path. 8k/12k exceedance is measured counterfactually, not bypassed in a real actor run."}
    (root / "runtime.json").write_bytes(json_bytes(runtime.snapshot()))
    (root / "public-capture.json").write_bytes(json_bytes(captures))
    (root / "capacity.json").write_bytes(json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    source_before = code_identity()
    rows = []
    for task in ("implement", "review", "chain"):
        for presentation in ("full_v14", "compact_v14"):
            rows.append(run_case("development-v14-f0-" + task, presentation, tokenizer, args.output / (task + "-" + presentation)))
    report = {"version": "learning-capacity-v0.14", "model": str(args.model.resolve()),
              "source_before": source_before, "source_after": code_identity(),
              "tokenizer_fingerprint": digest(tokenizer.backend_tokenizer.to_str().encode()),
              "native_tool_prompt": "single_call", "source_origin": "program_witness", "real_model_execution": False,
              "real_network_http_calls": 0, "real_behavior_logprobs": False, "training_eligible": False,
              "cases": rows}
    (args.output / "report.json").write_bytes(json_bytes(report))
    print([{key: row[key] for key in ("case_id", "presentation", "max_prompt_tokens", "max_prompt_plus_reserved_output", "decision_counts")} for row in rows])


if __name__ == "__main__":
    main()
