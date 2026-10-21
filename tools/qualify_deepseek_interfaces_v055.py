"""Execute one predeclared neutral two-request qualification condition.

No formal task is loaded. The actual original tool schemas are exposed, but
only the predetermined harmless fixture action can reach its real executor.
Any deviation fails this qualification without a replacement model request.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--condition", required=True)
    args = parser.parse_args()
    from proworksim.storage import digest
    from proworksim.software_benchmark_candidates_v054 import reference, write_new
    if digest(args.plan.read_bytes()) != args.plan_sha256:
        raise ValueError("Qualification plan changed")
    plan = json.loads(args.plan.read_text())
    if plan.get("version") != "v055-deepseek-neutral-qualification-plan-r1":
        raise ValueError("Unsupported qualification plan")
    matches = [row for row in plan["conditions"] if row["condition_id"] == args.condition]
    if len(matches) != 1 or plan.get("maximum_requests_per_condition") != 2:
        raise ValueError("One exact original two-request condition is required")
    row = matches[0]
    folder = Path(plan["output_root"]) / row["condition_id"]
    folder.mkdir(parents=True, exist_ok=False)
    write_new(folder / "intent.json", {"plan": reference(args.plan), "condition": row,
        "formal_task": False, "new_formal_slots_claimed": 0, "automatic_retry": False})
    os.environ["OH_PERSISTENCE_DIR"] = str(folder / "empty-user-config")
    receipt = {"version": "v055-deepseek-neutral-qualification-result-r1", "passed": False,
        "condition": row, "formal_task": False, "maximum_requests": 2,
        "official_grader_calls": 0, "GPU_loads": 0, "automatic_retry": False,
        "model_request_cap": "two_including_failed_or_uncertain_requests",
        "fixture_execution_allowlist": ["think", "finish"] if row["arm"] != "PROJECT" else ["read_file:fixture.py", "staff_done"]}
    adapter = runtime = conversation = None
    try:
        from proworksim.software_benchmark_deepseek_api_v055 import DeepSeekClient, load_api_key
        from proworksim.software_benchmark_deepseek_interfaces_v055 import DeepSeekAdapter, NATIVE_TOOLS, build_native_llm
        from proworksim.software_benchmark_deepseek_managed_v055 import RemoteProjectOwner, build_runtime
        from proworksim.software_benchmark_deepseek_tokenizer_v055 import build_counter
        from proworksim.software_benchmark_native_v054 import build_conversation
        from proworksim.software_benchmark_managed_v054 import managed_port
        from proworksim.software_benchmark_world_v054 import build_software_collaboration_case
        from proworksim.software_calibration_collector_v051 import DispatchDeadline, close_runtime, run_fragment
        from proworksim.repository_sources_v054 import RepositorySources, capture_repository
        from proworksim.model_policy import CONTROL_TOOLS

        class QualificationAdapter(DeepSeekAdapter):
            def complete(self, request, usage_id="agent"):
                if self.ledger.attempts >= 2:
                    raise RuntimeError("Neutral qualification two-request cap reached; no third request")
                if self.ledger.attempts == 1:
                    assistants = [m for m in request["messages"] if m["role"] == "assistant" and m.get("tool_calls")]
                    first = json.loads(Path(self.ledger.calls[0]["response"]["path"]).read_text())["choices"][0]["message"]
                    if len(assistants) != 1 or assistants[0].get("reasoning_content") != first.get("reasoning_content"):
                        raise ValueError("Original reasoning_content was not preserved before live continuation")
                body = super().complete(request, usage_id)
                calls = body["choices"][0]["message"].get("tool_calls") or []
                expected = (["read_file", "staff_done"] if self.arm == "PROJECT" else ["think", "finish"])[self.ledger.attempts - 1]
                if len(calls) != 1 or calls[0]["function"]["name"] != expected:
                    raise ValueError("Live qualification did not produce its one expected harmless fixture action")
                arguments = json.loads(calls[0]["function"]["arguments"])
                if expected == "read_file" and arguments != {"path": "fixture.py"}:
                    raise ValueError("Only the synthetic fixture.py may be read during qualification")
                return body

        if row["arm"] == "PROJECT":
            source = folder / "public"
            source.mkdir()
            (source / "fixture.py").write_text("value = 17\n")
            manifest = capture_repository(source, folder / "source", task_id="fixture__v055-qualification-1",
                problem_statement=plan["project_instruction"], source_identity={
                    "instance_id": "fixture__v055-qualification-1", "repo": "fixture/v055",
                    "base_commit": "a" * 40, "dataset_revision": "b" * 40})

            def never_test(**kwargs):
                raise ValueError("Neutral qualification never runs public or hidden tests")

            prepared = build_software_collaboration_case("fixture__v055-qualification-1", folder / "managed-world",
                provider=RepositorySources(manifest, runner=never_test))
            names = {tool["name"] for tool in managed_port(prepared).tools()} | {tool["name"] for tool in CONTROL_TOOLS}
        else:
            names = NATIVE_TOOLS
        client = DeepSeekClient(ledger_path=plan["ledger_path"], api_key=load_api_key(plan["api_key_file"]),
            allowed_tool_names=names, max_concurrency=plan["max_api_concurrency"],
            timeout_seconds=1800 if row["arm"] == "REF" else 600)
        adapter = QualificationAdapter(client=client, arm=row["arm"], thinking=row["thinking"],
            slot_id="neutral-qualification-r1-" + row["condition_id"], condition_id=row["condition_id"],
            folder=folder / "ledger", allowed_tool_names=names, counter=build_counter(plan["context_counter"]))
        if row["arm"] == "PROJECT":
            runtime, _, _ = build_runtime(RemoteProjectOwner(adapter, window_id=row["condition_id"]),
                prepared, folder / "runtime", deadline=DispatchDeadline())
            boundary = run_fragment(prepared, runtime)
            receipt["managed_boundary"] = boundary
            if (boundary["execution_integrity_failure"] is not None or runtime.actions != 1
                    or runtime.opportunities != 2 or boundary["closure_reason"] != "all_members_stopped_or_no_reachable_event"):
                raise ValueError("Managed neutral fixture did not close with exactly one read and one done")
            close_runtime(runtime)
            runtime = None
        else:
            workspace = folder / "workspace"
            workspace.mkdir()
            conversation = build_conversation(build_native_llm(adapter), workspace=workspace,
                                              persistence_dir=folder / "conversation")
            conversation.send_message(plan["native_instruction"])
            conversation.run()
            conversation.close()
            conversation = None
        if adapter.ledger.attempts != 2 or len(adapter.ledger.calls) != 2 or adapter.ledger.inflight is not None:
            raise ValueError("Two completely settled original API requests are required")
        comparisons = []
        for call in adapter.ledger.calls:
            request = json.loads(Path(call["request"]["path"]).read_text())
            measurement = request["measurement"]
            actual = call["usage"]["prompt_tokens"]
            if actual > measurement["prompt_tokens"]:
                raise ValueError("Provider actual prompt usage exceeds frozen local-plus-margin reservation")
            comparisons.append({"request": call["request"], "response": call["response"],
                "local_encoded_prompt_tokens": measurement["local_encoded_prompt_tokens"],
                "reservation_margin_tokens": measurement["reservation_margin_tokens"],
                "prompt_reservation": measurement["prompt_tokens"], "actual_provider_prompt_tokens": actual,
                "actual_completion_including_reasoning": call["usage"]["completion_tokens"],
                "provider_minus_local": actual - measurement["local_encoded_prompt_tokens"]})
        receipt.update(passed=True, comparisons=comparisons, actual_requests=2,
                       reasoning_content_original_continuation=True, selected_after_outcome=False)
    except BaseException as error:
        receipt.update(error={"type": type(error).__name__, "message": str(error)}, traceback=traceback.format_exc())
    finally:
        if conversation is not None:
            conversation.close()
        if runtime is not None:
            close_runtime(runtime)
        if adapter is not None:
            receipt["ledger"] = adapter.ledger.snapshot()
            receipt["actual_requests"] = adapter.ledger.attempts
        write_new(folder / "receipt.json", receipt)
    print(json.dumps({"condition": row["condition_id"], "passed": receipt["passed"],
                      "requests": receipt.get("actual_requests", 0), "error": receipt.get("error")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
