"""Six real SDK/interface constructions with programmed HTTP only, no network."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arms", nargs="+", choices=["REF", "MATCH", "PROJECT"], default=["REF", "MATCH", "PROJECT"])
    parser.add_argument("--modes", nargs="+", choices=["thinking", "nonthinking"], default=["nonthinking", "thinking"])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"version": "v055-deepseek-sdk-control-r1", "passed": False,
               "paid_model_calls": 0, "network_attempts": 0, "GPU_access": 0, "conditions": []}

    def audit(event, values):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            receipt["network_attempts"] += 1
            raise RuntimeError("No network in programmed SDK control")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.startswith(("/dev/nvidia", "/dev/dri/")) or path.endswith(".safetensors"):
                receipt["GPU_access"] += 1
                raise RuntimeError("No GPU or model weights in programmed SDK control")

    sys.addaudithook(audit)
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "empty-user-config")
    runtime = conversation = None
    try:
        from proworksim.software_benchmark_deepseek_api_v055 import DeepSeekClient, MODEL
        from proworksim.software_benchmark_deepseek_interfaces_v055 import DeepSeekAdapter, NATIVE_TOOLS, build_native_llm
        from proworksim.software_benchmark_deepseek_managed_v055 import RemoteProjectOwner, build_runtime
        from proworksim.software_benchmark_native_v054 import build_conversation
        from proworksim.software_benchmark_managed_v054 import managed_port
        from proworksim.software_benchmark_world_v054 import build_software_collaboration_case
        from proworksim.software_calibration_collector_v051 import DispatchDeadline, close_runtime, run_fragment
        from proworksim.repository_sources_v054 import RepositorySources, capture_repository
        from proworksim.model_policy import CONTROL_TOOLS
        from proworksim.storage import digest, json_bytes

        def fixture_counter(request):
            return {"prompt_tokens": 1000, "method": "programmed_CPU_count_not_formal_tokenizer",
                    "request_sha256": digest(json_bytes(request)), "count_kind": "programmed_fixture"}

        for arm in args.arms:
            for thinking in (mode == "thinking" for mode in args.modes):
                condition = arm + ("-thinking" if thinking else "-nonthinking")
                folder = output / condition
                folder.mkdir()
                prepared = None
                if arm == "PROJECT":
                    source = folder / "public"
                    source.mkdir()
                    (source / "fixture.py").write_text("value = 1\n")
                    manifest = capture_repository(source, folder / "source", task_id="fixture__v055-1",
                        problem_statement="Synthetic SDK interface check only.",
                        source_identity={"instance_id": "fixture__v055-1", "repo": "fixture/v055",
                                         "base_commit": "a" * 40, "dataset_revision": "b" * 40})

                    def never_test(**kwargs):
                        raise RuntimeError("Fixture does not request public tests")

                    provider = RepositorySources(manifest, runner=never_test)
                    prepared = build_software_collaboration_case("fixture__v055-1", folder / "managed-world", provider=provider)
                    names = {row["name"] for row in managed_port(prepared).tools()} | {row["name"] for row in CONTROL_TOOLS}
                    steps = [("read_file", {"path": "fixture.py"}), ("staff_done", {"reason": "CPU fixture ended"})]
                else:
                    names = NATIVE_TOOLS
                    steps = [("think", {"thought": "Neutral synthetic SDK check."}),
                             ("finish", {"message": "CPU fixture ended"})]

                class FixtureHTTP:
                    def __init__(self):
                        self.requests = []

                    def request(self, method, path, payload):
                        index = len(self.requests)
                        if index >= 2:
                            raise ValueError("Fixture permits exactly two original SDK requests")
                        assert (method, path) == ("POST", "/chat/completions")
                        if index:
                            assistants = [m for m in payload["messages"] if m["role"] == "assistant"]
                            assert len(assistants) == 1
                            assert assistants[0]["reasoning_content"] == ("Preserved fixture reasoning" if thinking else "")
                        self.requests.append(copy.deepcopy(payload))
                        name, arguments = steps[index]
                        return {"id": condition + f"-response-{index}", "model": MODEL,
                            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                                "role": "assistant", "content": "", "reasoning_content": "Preserved fixture reasoning" if thinking else "",
                                "tool_calls": [{"id": condition + f"-call-{index}", "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)}}]}}],
                            "usage": {"prompt_tokens": 1000, "completion_tokens": 30, "total_tokens": 1030,
                                "prompt_cache_hit_tokens": 500, "prompt_cache_miss_tokens": 500,
                                "completion_tokens_details": {"reasoning_tokens": 10 if thinking else 0}}}

                fixture = FixtureHTTP()
                client = DeepSeekClient(ledger_path=folder / "fixture-only.sqlite3", api_key="fixture-no-secret",
                                        allowed_tool_names=names, transport=fixture)
                adapter = DeepSeekAdapter(client=client, arm=arm, thinking=thinking,
                    slot_id="synthetic-" + condition, condition_id=condition, folder=folder / "ledger",
                    allowed_tool_names=names, counter=fixture_counter)
                if arm != "PROJECT":
                    workspace = folder / "workspace"
                    workspace.mkdir()
                    conversation = build_conversation(build_native_llm(adapter), workspace=workspace,
                                                      persistence_dir=folder / "conversation")
                    conversation.send_message("Synthetic check only. Think once and finish.")
                    conversation.run()
                    assert set(conversation.agent.tools_map) == NATIVE_TOOLS
                    conversation.close()
                    conversation = None
                    evidence = {"native_original_five_tools": True}
                else:
                    runtime, _, _ = build_runtime(RemoteProjectOwner(adapter, window_id=condition),
                                                 prepared, folder / "runtime", deadline=DispatchDeadline())
                    boundary = run_fragment(prepared, runtime)
                    assert boundary["execution_integrity_failure"] is None
                    assert runtime.actions == 1  # staff_done is lifecycle control, not a business action.
                    assert runtime.opportunities == 2
                    charges = list(runtime.team_budget.snapshot()["records"].values())
                    assert len(charges) == 2
                    assert all(r["charge"]["usage_status"] == "reported_api_usage" for r in charges)
                    ledger = runtime.policies["member_001"].transport.feedback_ledger
                    assert len(ledger.generations) == 2
                    evidence = {"real_managed_actions": runtime.actions, "closure_reason": boundary["closure_reason"],
                                "actual_api_usage_evidence_without_token_ids": True}
                    close_runtime(runtime)
                    runtime = None
                assert len(fixture.requests) == 2
                assert adapter.ledger.snapshot()["known_actual_tokens"] == 2060
                assert all(request["model"] == MODEL and "seed" not in request for request in fixture.requests)
                assert all(not ({"web_search", "browser"} & {tool["function"]["name"] for tool in request.get("tools", [])})
                           for request in fixture.requests)
                receipt["conditions"].append({"condition": condition, "programmed_requests": 2,
                    "reasoning_continuation_preserved": True, "actual_tokens_from_fixture_usage": 2060,
                    "provider_seed_sent": False, **evidence})
        receipt["passed"] = len(receipt["conditions"]) == len(args.modes) * len(args.arms)
    except BaseException as error:
        receipt["error"] = {"type": type(error).__name__, "message": str(error)}
        receipt["traceback"] = traceback.format_exc()
    finally:
        if conversation is not None:
            conversation.close()
        if runtime is not None:
            close_runtime(runtime)
        (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
