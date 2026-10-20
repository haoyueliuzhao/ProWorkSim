"""Real-tokenizer and SDK/condenser control with programmed CPU responses only."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-local", type=Path, required=True)
    parser.add_argument("--interface-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {
        "version": "software-benchmark-v054-match-seam-control-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "passed": False,
        "model_calls": 0, "programmed_responses": 0, "network_attempts": 0,
        "weight_file_opens": 0, "gpu_device_opens": 0, "official_parser_executions": 0,
        "formal_execution_authorized": False,
    }

    def audit(event, values):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            receipt["network_attempts"] += 1
            raise RuntimeError("Network forbidden in the synthetic MATCH control")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                receipt["weight_file_opens"] += 1
                raise RuntimeError("Weight access forbidden in the synthetic control")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                receipt["gpu_device_opens"] += 1
                raise RuntimeError("GPU access forbidden in the synthetic control")

    sys.addaudithook(audit)
    try:
        assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
        assert os.environ.get("NVIDIA_VISIBLE_DEVICES") == "void"
        assert os.environ.get("HF_HUB_OFFLINE") == "1"
        from transformers import AutoTokenizer
        from openhands.sdk import Message, TextContent
        from openhands.sdk.event import MessageEvent
        from proworksim import software_benchmark_match_v054 as seam
        from proworksim.software_benchmark_native_v054 import build_agent
        from proworksim.software_calibration_runtime_v051 import validate_native_input

        tokenizer = AutoTokenizer.from_pretrained(
            str(args.model_local), local_files_only=True, trust_remote_code=False)
        declared = json.loads((args.model_local / "proworksim-manifest.json").read_bytes())
        assert declared["declared_hf_revision"] == "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
        interface = json.loads(args.interface_manifest.read_bytes())
        response_ids = tokenizer.encode("synthetic control response", add_special_tokens=False) + [248044]

        class Owner:
            programmed_fixture = True
            path = "project"
            contract = seam.CONTRACT

            def __init__(self):
                self.tokenizer = tokenizer

            def freeze_identity(self):
                return {"raw_release": True, "checkpoint": None, "adapter_sha256": None,
                        "programmed_fixture_only": True}

            def generate_native(self, native):
                assert validate_native_input(native, self.contract)
                receipt["programmed_responses"] += 1
                return {
                    "attempt_id": "programmed-" + str(receipt["programmed_responses"]),
                    "actor_identity": self.freeze_identity(),
                    "input": copy.deepcopy(native), "output_ids": response_ids,
                    "raw_generated_text": tokenizer.decode(response_ids, skip_special_tokens=False),
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": native["prompt_tokens"],
                              "completion_tokens": len(response_ids),
                              "total_tokens": native["prompt_tokens"] + len(response_ids)},
                }

        class Codec:
            def decode(self, **kwargs):
                return {"message": {"role": "assistant", "content": "synthetic control response"},
                        "codec_identity": {"programmed_fixture_only": True}}

        class ToolView:
            def __init__(self, schema):
                self.schema = schema

            def to_openai_tool(self, **kwargs):
                return copy.deepcopy(self.schema)

        bridge = seam.MatchBridge(
            Owner(), codec=Codec(), folder=args.output / "episode",
            slot_id="synthetic-tokenizer-sdk-condenser", allow_programmed_fixture=True)
        llm = seam.build_llm(bridge)
        agent = build_agent(llm)
        assert agent.llm._bridge is agent.condenser.llm._bridge is bridge
        tools = [ToolView(value) for _, value in sorted(interface["tool_schemas"].items())]
        messages = [
            Message(role="system", content=[TextContent(text=interface["static_system_prompt"])]),
            Message(role="user", content=[TextContent(text="Synthetic CPU request; no repository task.")]),
        ]
        request = seam.serialize_sdk_request(
            messages, tools, add_security_risk_prediction=True,
            formatted_messages=llm.format_messages_for_llm(messages))
        native = bridge.prepare(request)
        expected = tokenizer.apply_chat_template(
            seam.normalize_native_messages(request["messages"]), tools=request["tools"],
            tokenize=False, add_generation_prompt=True,
            enable_thinking=False, preserve_thinking=False)
        assert native["rendered_prompt"] == expected
        assert native["input_ids"] == tokenizer(expected, add_special_tokens=False)["input_ids"]
        assert not native["single_call_hint_applied"]
        assert llm.get_token_count(messages, tools, add_security_risk_prediction=True) == native["prompt_tokens"]
        assert bridge.ledger.attempts == 0
        response = agent.llm.generate(
            messages=messages, tools=tools, store=False, add_security_risk_prediction=True)
        assert response.raw_response.usage.total_tokens == bridge.ledger.actual
        event = MessageEvent(
            source="user", llm_message=Message(
                role="user", content=[TextContent(text="Earlier synthetic event.")]))
        condensed = agent.condenser._generate_condensation(
            forgotten_events=[event], summary_offset=0)
        assert condensed.summary == "synthetic control response"
        assert bridge.ledger.attempts == 2 and bridge.ledger.decisions == 1
        state = bridge.ledger.snapshot()
        assert set(state["per_usage_id"]) == {"agent", "condenser"}
        assert state["complete_actual_tokens"] == sum(
            item["usage"]["total_tokens"] for item in state["calls"])
        receipt.update({
            "passed": True,
            "actual_tokenizer_class": f"{type(tokenizer).__module__}.{type(tokenizer).__name__}",
            "tokenizer_revision": declared["declared_hf_revision"],
            "actual_prompt_tokens": native["prompt_tokens"],
            "actual_prompt_sha256": native["rendered_prompt_sha256"],
            "actual_input_ids_sha256": native["input_ids_sha256"],
            "template_exactly_equal_without_project_hint": True,
            "owner_native_input_validator_passed": True,
            "native_interface_manifest_sha256": hashlib.sha256(args.interface_manifest.read_bytes()).hexdigest(),
            "official_sdk_generate_and_condenser_called": True,
            "agent_condenser_share_one_bridge": True,
            "ledger": state,
            "formal_numerical_generation_executed": False,
            "official_output_parser_tested": False,
        })
    except Exception as error:
        receipt["error"] = {"type": type(error).__name__, "message": str(error)}
        receipt["traceback"] = traceback.format_exc()
    receipt["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    (args.output / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
