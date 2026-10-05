"""CPU native-token upper bounds for four archived scripted legal routes.

Never sample or load weights. The archived reference requests remain immutable;
this is a conditional cost witness, not a model trajectory or policy support.
"""
import argparse
import copy
from collections import Counter
from importlib.metadata import version
import inspect
import json
from pathlib import Path

from proworksim.software_context_v034 import VERSION, project_software_request
from proworksim.storage import digest, json_bytes
from scripts.audit_software_presentation_v034 import ROOT, native_renderer, read, ref, write


DEFAULT_ROUTES = ROOT / "runs/v034-controls/world/development-2/sdk-routes"
DEFAULT_OUTPUT = ROOT / "runs/v034-controls/presentation/reference-route-budget.json"




def project_recorded_test_feedback(request):
    """Derive only run_tests message content using the final world pure helper."""
    from proworksim.software_tasks_v034 import project_public_test_feedback
    projected = copy.deepcopy(request)
    names, changes = {}, []
    for index, message in enumerate(projected["messages"]):
        for call in message.get("tool_calls", []):
            names[call["id"]] = call["function"]["name"]
        if message.get("role") != "tool" or names.get(message.get("tool_call_id")) != "run_tests":
            continue
        before = message["content"]
        envelope = json.loads(before)
        if envelope.get("ok") is not True or not isinstance(envelope.get("result"), dict):
            continue
        original_result = copy.deepcopy(envelope["result"])
        envelope["result"] = project_public_test_feedback(original_result)
        if original_result != json.loads(before)["result"]:
            raise ValueError("Pure public feedback helper mutated its raw input")
        after = json.dumps(envelope, ensure_ascii=False, allow_nan=False)
        if after != before:
            message["content"] = after
            changes.append({"message_index": index, "tool_call_id": message["tool_call_id"],
                            "original_content_sha256": digest(before.encode()),
                            "projected_content_sha256": digest(after.encode()),
                            "original_result_sha256": digest(json_bytes(original_result)),
                            "projected_result_sha256": digest(json_bytes(envelope["result"])),
                            "original_characters": len(before), "projected_characters": len(after)})
    restored = copy.deepcopy(projected)
    for record in changes:
        index = record["message_index"]
        restored["messages"][index]["content"] = request["messages"][index]["content"]
    if restored != request:
        raise ValueError("Public feedback derivation changed another request field")
    return projected, changes


def native_history_request(request, model):
    """Make fixture-only call IDs legal for Mistral, preserving all other bytes.

    The real Mistral parser already emits nine-character native IDs. This
    counterfactual alpha-renaming is explicitly archived and is not a codec fix.
    """
    measured = copy.deepcopy(request)
    renamed = []
    if model != "devstral-small-2507":
        return measured, renamed
    mapping = {}
    for index, message in enumerate(measured["messages"]):
        for call_index, call in enumerate(message.get("tool_calls", [])):
            previous = call["id"]
            if len(previous) == 9 and previous.isascii() and previous.isalnum():
                continue
            native = digest(previous.encode())[:9]
            if native in mapping.values() and mapping.get(previous) != native:
                raise ValueError("Reference ID alpha-renaming collision")
            mapping[previous] = native
            call["id"] = native
            renamed.append({"message_index": index, "call_index": call_index,
                            "field": "assistant.tool_calls.id", "original": previous, "native": native})
        if message.get("role") == "tool" and message.get("tool_call_id") in mapping:
            previous = message["tool_call_id"]
            message["tool_call_id"] = mapping[previous]
            renamed.append({"message_index": index, "field": "tool.tool_call_id",
                            "original": previous, "native": mapping[previous]})
    restored = copy.deepcopy(measured)
    for record in renamed:
        message = restored["messages"][record["message_index"]]
        if record["field"] == "tool.tool_call_id":
            message["tool_call_id"] = record["original"]
        else:
            message["tool_calls"][record["call_index"]]["id"] = record["original"]
    if restored != request:
        raise ValueError("Reference native ID mapping changed another request field")
    return measured, renamed


def canonical_output(model, tokenizer, request, message):
    """Encode and parse a legal reference call, without sampling probabilities."""
    calls = message.get("tool_calls", [])
    if len(calls) != 1:
        raise ValueError("Each scripted reference decision must provide one call")
    call = calls[0]["function"]
    name, arguments = call["name"], json.loads(call["arguments"])
    if model == "qwen3.5-9b":
        from proworksim.candidate_runtime_v015 import parse_candidate_generated
        # Wrapper newlines are consumed by the native parameter parser; the
        # reference string's own leading/trailing newlines remain exact.
        parameters = []
        for key, value in arguments.items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
            parameters.append(f"<parameter={key}>\n{text}\n</parameter>")
        raw = "<tool_call>\n<function=" + name + ">\n" + "\n".join(parameters) + "\n</function>\n</tool_call><|im_end|>"
        output_ids = tokenizer(raw, add_special_tokens=False)["input_ids"]
        parsed, error = parse_candidate_generated(raw, request)
    else:
        from mistral_common.protocol.instruct.messages import AssistantMessage
        from mistral_common.protocol.instruct.tool_calls import FunctionCall, ToolCall
        from proworksim.native_codecs_v031 import parse_code_response
        assistant = AssistantMessage(tool_calls=[ToolCall(id="cpu000001",
            function=FunctionCall(name=name, arguments=arguments))])
        output_ids = tokenizer.native.instruct_tokenizer.encode_assistant_message(
            assistant, is_before_last_user_message=False, continue_message=False)
        raw = tokenizer.decode(output_ids)
        parsed, error = parse_code_response(raw, request, model)
    recovered = parsed.get("tool_calls", [])
    if (error is not None or len(recovered) != 1 or recovered[0]["function"]["name"] != name
            or json.loads(recovered[0]["function"]["arguments"]) != arguments):
        raise ValueError("Canonical native reference output did not roundtrip: " + str(error))
    return {"tool": name, "tokens_including_native_stop": len(output_ids),
            "output_ids_sha256": digest(json_bytes(list(output_ids))),
            "canonical_wire_sha256": digest(raw.encode()), "native_parser_roundtrip_equal": True,
            "within_2048": len(output_ids) <= 2048,
            "scope": "One constructed legal native encoding of the scripted action, not sampled output or a probability/support certificate."}


def load_routes(routes):
    witnesses = read(routes / "route-witnesses.json")["witnesses"]
    result = []
    for index in range(4):
        folder = routes / "window" / f"slot-{index}"
        events = [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines()]
        starts = [e for e in events if e["kind"] == "model_attempt" and e["payload"]["stage"] == "started"]
        steps = []
        for event in starts:
            payload = event["payload"]
            call = [e for e in events if e["kind"] == "model_call" and e["payload"]["stage"] == "started"
                    and e["payload"]["call_id"] == payload["call_id"]]
            finish = [e for e in events if e["kind"] == "model_attempt" and e["payload"]["stage"] == "finished"
                      and e["payload"]["attempt_id"] == payload["attempt_id"]]
            if (len(call) != 1 or len(finish) != 1 or finish[0]["payload"]["status"] != "success"
                    or call[0]["payload"]["request_sha256"] != digest(json_bytes(payload["request"]))
                    or finish[0]["payload"]["request"] != payload["request"]):
                raise ValueError("Scripted actual request/attempt binding mismatch")
            response = finish[0]["payload"]["response"]
            if response["http_status"] != 200 or payload["request"]["max_tokens"] != 2048:
                raise ValueError("Unexpected reference fixture response/output limit")
            steps.append({"sequence": event["sequence"], "member": event["worker_id"],
                          "decision_index": payload["decision_index"], "call_id": payload["call_id"],
                          "attempt_id": payload["attempt_id"], "request": payload["request"],
                          "message": response["body"]["choices"][0]["message"]})
        budget = read(folder / "team-budget.json")
        if len(steps) != budget["model"]["attempts"] or len(steps) != budget["model"]["decisions"]:
            raise ValueError("Reference decision/attempt margin differs from actual ledger")
        witness = next(w for w in witnesses if w["slot_id"] == budget["slot_id"])
        if witness["R"] != 1:
            raise ValueError("Only completed immutable legal route witnesses are in this control")
        result.append({"slot_index": index, "slot_id": budget["slot_id"], "route": witness["route"],
                       "case_id": witness["case_id"], "steps": steps, "test_runs": budget["tests"]["used"],
                       "opportunities": len((folder / "runtime-opportunities.jsonl").read_text().splitlines()),
                       "source_refs": {n: ref(folder / n) for n in
                                       ["experience.jsonl", "team-budget.json", "team-test-budget.json", "entry.json", "runtime-opportunities.jsonl"]}})
    if [len(route["steps"]) for route in result] != [9, 10, 14, 14]:
        raise ValueError("Final predeclared four-route inventory changed")
    return result


def measure(routes, output, *, feedback_projection=False, baseline_report=None):
    baseline_report = Path(baseline_report).resolve() if baseline_report else None
    inventory = load_routes(routes)
    helper_source = ref(ROOT / "src/proworksim/software_tasks_v034.py") if feedback_projection else None
    if feedback_projection:
        from proworksim.software_tasks_v034 import project_public_test_feedback
        helper_function_sha256 = digest(inspect.getsource(project_public_test_feedback).encode())
    else:
        helper_function_sha256 = None
    baseline = read(baseline_report) if baseline_report else None
    baseline_rows = {(row["model"], row["slot_id"]): row for row in baseline["rows"]} if baseline else {}
    if baseline:
        if not feedback_projection or not baseline["passed"] or not baseline["public_feedback_projection_applied"]:
            raise ValueError("Delta reuse requires the saved successful preceding feedback measurement")
        if baseline["source_route_witnesses"] != ref(routes / "route-witnesses.json"):
            raise ValueError("Cannot reuse a changed route inventory")
        for name, expected in baseline["source_refs"].items():
            if name not in {"scripts/measure_software_reference_routes_v034.py", "src/proworksim/software_tasks_v034.py"}:
                if ref(ROOT / name) != expected:
                    raise ValueError("A reused native renderer/projection source changed: " + name)
    rows, provenance = [], {}
    recomputed, reused = 0, 0
    for model in ["qwen3.5-9b", "devstral-small-2507"]:
        tokenizer, render, provenance[model] = native_renderer(model)
        if baseline and provenance[model] != baseline["native_provenance"][model]:
            raise ValueError("A reused tokenizer or native owner provenance changed")
        for route in inventory:
            steps = []
            cumulative = 0
            before_row = baseline_rows.get((model, route["slot_id"]))
            if before_row and before_row["source_refs"] != route["source_refs"]:
                raise ValueError("A reused archived route changed")
            before_steps = {step["call_id"]: step for step in before_row["steps"]} if before_row else {}
            for step in route["steps"]:
                original_request = step["request"]
                feedback_request, feedback_changes = (project_recorded_test_feedback(original_request)
                    if feedback_projection else (original_request, []))
                request, renamed_ids = native_history_request(feedback_request, model)
                request_hash = digest(json_bytes(request))
                before = before_steps.get(step["call_id"])
                if before and before["original_request_sha256"] != digest(json_bytes(original_request)):
                    raise ValueError("A reused original request changed")
                if before and before["native_legal_reference_request_sha256"] == request_hash:
                    measured = copy.deepcopy(before)
                    measured["measurement_origin"] = "reused_unchanged_exact_derived_request"
                    reused += 1
                else:
                    selected, projection = project_software_request(request, render=render, tokenizer=tokenizer,
                                                                    context_limit=16384)
                    # The feedback-only derivation cannot change output tool
                    # schemas or the reference action. Reuse its prior exact
                    # native output encoding proof, not sampled probabilities.
                    encoded_output = (copy.deepcopy(before["canonical_reference_output"]) if before else
                                      canonical_output(model, tokenizer, selected, step["message"]))
                    reservation = projection["selected_prompt_tokens"] + 2048
                    measured = {k: step[k] for k in ["sequence", "member", "decision_index", "call_id", "attempt_id"]} | {
                        "original_request_sha256": digest(json_bytes(original_request)),
                        "native_legal_reference_request_sha256": request_hash,
                        "fixture_id_alpha_renaming": renamed_ids,
                        "public_feedback_derivation": feedback_changes,
                        "all_fields_except_declared_feedback_and_ids_unchanged": True,
                        "selected_request_sha256": projection["selected_request_sha256"],
                        "native_input_ids_sha256": projection["input_ids_sha256"],
                        "rendered_prompt_sha256": projection["rendered_prompt_sha256"],
                        "prompt_tokens": projection["selected_prompt_tokens"],
                        "reserved_output_tokens": 2048, "context_upper_bound_tokens": reservation,
                        "context_margin_tokens": 16384 - reservation,
                        "context_fits": projection["fits"],
                        "removed_complete_round_indices": projection["removed_indices"],
                        "duplicate_values_removed": len(projection["deduplication"]["removed_values"]),
                        "canonical_reference_output": encoded_output,
                        "measurement_origin": "recomputed_changed_derived_request" if before else "full_measurement"}
                    recomputed += 1
                if before:
                    measured["preceding_native_request_sha256"] = before["native_legal_reference_request_sha256"]
                    measured["preceding_prompt_tokens"] = before["prompt_tokens"]
                    measured["prompt_token_delta_from_preceding"] = measured["prompt_tokens"] - before["prompt_tokens"]
                    measured["canonical_output_encoding_reused_unchanged_action_and_tools"] = True
                cumulative += measured["context_upper_bound_tokens"]
                measured["episode_cumulative_upper_bound_tokens"] = cumulative
                measured["episode_budget_margin_tokens"] = 500000 - cumulative
                steps.append(measured)
            count = len(steps)
            rows.append({k: route[k] for k in ["slot_index", "slot_id", "route", "case_id", "source_refs", "opportunities", "test_runs"]} | {
                "model": model, "scripted_calls": count, "member_calls": dict(Counter(s["member"] for s in steps)),
                "decision_margin": 128 - count, "attempt_margin": 128 - count,
                "test_margin": 32 - route["test_runs"], "prompt_tokens_sum": sum(s["prompt_tokens"] for s in steps),
                "maximum_output_reservations": 2048 * count, "episode_token_upper_bound": cumulative,
                "episode_token_margin": 500000 - cumulative,
                "peak_prompt_tokens": max(s["prompt_tokens"] for s in steps),
                "minimum_context_margin": min(s["context_margin_tokens"] for s in steps),
                "peak_canonical_output_tokens": max(s["canonical_reference_output"]["tokens_including_native_stop"] for s in steps),
                "canonical_output_tokens_sum": sum(s["canonical_reference_output"]["tokens_including_native_stop"] for s in steps),
                "all_steps_fit_context": all(s["context_fits"] for s in steps),
                "all_constructed_outputs_fit_output_limit": all(s["canonical_reference_output"]["within_2048"] for s in steps),
                "episode_budget_fits": cumulative <= 500000, "steps": steps})
    passed = all(r["all_steps_fit_context"] and r["all_constructed_outputs_fit_output_limit"]
                 and r["episode_budget_fits"] and r["decision_margin"] >= 0 and r["test_margin"] >= 0 for r in rows)
    if feedback_projection and helper_source != ref(ROOT / "src/proworksim/software_tasks_v034.py"):
        raise ValueError("Public feedback helper source changed during measurement")
    report = {"version": "reference-route-native-budget-v0.34", "presentation_version": VERSION,
              "passed": passed, "public_feedback_projection_applied": feedback_projection,
              "public_feedback_projection_source": helper_source,
              "public_feedback_projection_function_sha256": helper_function_sha256,
              "initial_capacity_failure_archive": ref(ROOT / "runs/v034-controls/presentation/reference-route-initial/provenance.json"),
              "model_calls": 0, "gpu_used": False, "weights_loaded": False,
              "reference_routes": 4, "unique_scripted_calls": 47, "native_request_measurements": 94,
              "new_native_request_measurements": recomputed, "reused_native_request_measurements": reused,
              "preceding_feedback_measurement": ref(baseline_report) if baseline_report else None,
              "preceding_feedback_receipt": ref(Path(baseline_report).parent / "measurement-checks.json") if baseline_report else None,
              "source_route_witnesses": ref(routes / "route-witnesses.json"),
              "native_provenance": provenance,
              "library_versions": {name: version(name) for name in ["transformers", "tokenizers", "mistral_common"]},
              "source_refs": {name: ref(ROOT / name) for name in [
                  "scripts/measure_software_reference_routes_v034.py", "scripts/audit_software_presentation_v034.py",
                  "src/proworksim/software_context_v034.py", "src/proworksim/software_context_v028.py",
                  "src/proworksim/candidate_runtime_v015.py", "src/proworksim/candidate_runtime_v030.py",
                  "src/proworksim/native_codecs_v031.py"]},
              "limits": {"context": 16384, "max_output_per_call": 2048, "episode_tokens": 500000,
                         "decisions": 128, "attempts": 128, "test_runs": 32},
              "rows": rows,
              "interpretation": "Conditional native cost witness for archived scripted legal requests, preserving member/session sequence. Where explicitly enabled, only run_tests message result payloads are derived with the final world public-feedback pure function and every replacement is hashed. Devstral additionally requires fixture-only call-ID alpha-renaming to legal nine-character native IDs. All fields except these declared derivations are unchanged. Sum of measured native projected input lengths plus 2048 for EVERY call is a conservative output-reservation upper bound for these explicitly defined reference requests. No budget credit is removed and no old charge is replaced.",
              "limitations": [
                  "Reference scripts and constructed native outputs are not model behavior, model support, teacher labels, inference qualification, gradient evidence or action probabilities.",
                  "Archived observations retain their original synthetic budget counters and fixture identities. Public feedback projection, when enabled, is a declared new world presentation contract, not mere exact duplicate removal; Devstral call IDs are additionally alpha-renamed. A fresh native runtime would expose different cumulative counters/identities, so this is not a byte-exact replay of fresh native requests or a guarantee for all executions.",
                  "Reference development-2 requests predate integer-comparator tightening. That change alters generated test_visible.py/bundle hashes, but these four scripts did not read that file; exact final-world request bytes are not claimed. Independent world controls establish unchanged reference answers under the stricter comparator.",
                  "Original Devstral synthetic fixture history IDs are not legal native IDs. The first encoding attempt stopped at the native validator; only the independent control script was corrected with deterministic reversible ID mapping, not production code or archived requests.",
                  "Real policies may take more decisions, produce longer thoughts, make mistakes or consume more resources. The legal route witness does not estimate that exploration cost.",
                  "Canonical tool-call outputs are constructed and roundtrip parsed. Existence below 2048 proves representability only, without claiming the model chooses them.",
                  "No original 16-sample presentation audit, model qualification, near-16K stress, world driver or old route was rerun."]}
    if feedback_projection:
        report["source_refs"]["src/proworksim/software_tasks_v034.py"] = ref(ROOT / "src/proworksim/software_tasks_v034.py")
    write(output, report)
    lines = ["# v0.34 合法参考路线的原生预算旁证", "", f"仅对已归档四条脚本合法路线作 CPU 原生编码：47 个原请求、两个固定 tokenizer，覆盖 94 次输入计量；本次新增重编码 {recomputed}，按完全相等的派生请求和不变的原生来源复用 {reused}。模型调用 0，GPU false，未加载权重。按真实成员与调用顺序保存每步 SHA；前置计量及回执独立保留。", "",
             "| 模型 | 根目标/路线 | 调用 | 峰值输入 | 输入+每步2048上界 | 距50万余量 | 最小16K余量 | 参考输出峰值 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['model']} | {row['case_id']}/{row['route']} | {row['scripted_calls']} | {row['peak_prompt_tokens']} | {row['episode_token_upper_bound']} | {row['episode_token_margin']} | {row['minimum_context_margin']} | {row['peak_canonical_output_tokens']} |")
    lines += ["", "每条路线实际有 1 次测试，32 次上限尚余 31 次；9/10/14/14 次实际脚本决定分别剩 119/118/114/114 次。" + ("全部逐步输入加2048不超过16384，整条路线保守上界不超过500000。" if passed else "容量或输出边界存在未通过步骤，详见JSON及表中真实差值；不得作为通过门。") + "", "",
              "同时构造同一工具动作的合法原生输出，编码含结束 token，并用原生解析器核对工具名称和参数完全还原；这只证明这些参考动作可以在2048内表达，不是模型采样、概率或策略支持证据。", "",
              "开启feedback-projection时，仅对历史run_tests消息的result字段调用最终world纯函数，其余封套与当前状态不变，逐项记录原/新内容SHA。这是明确的新world呈现，不称为纯字节去重。Devstral另将fixture长调用ID可逆重命名为原生9位ID。原件和初次失败旁证保留。观察里的预算数字和身份仍是fixture原值；整数比较器收紧后生成的test_visible.py及bundle字节亦可能不同。本报告不是新执行请求逐字节重演或任意探索保证，真实模型可用更多资源。", "",
              "旧16样本审计、旧收费与业务结果保持不变；没有重跑资格、近16K压力或世界路线。"]
    output.with_suffix(".md").write_text("\n".join(lines) + "\n")
    if not passed:
        raise ValueError("At least one declared native route budget bound failed; see saved report")
    return [{k: row[k] for k in ["model", "slot_id", "scripted_calls", "peak_prompt_tokens", "episode_token_upper_bound", "episode_token_margin", "minimum_context_margin", "peak_canonical_output_tokens"]} for row in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", type=Path, default=DEFAULT_ROUTES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--feedback-projection", action="store_true")
    parser.add_argument("--baseline-report", type=Path)
    args = parser.parse_args()
    print(json.dumps(measure(args.routes, args.output, feedback_projection=args.feedback_projection, baseline_report=args.baseline_report)))


if __name__ == "__main__":
    main()
