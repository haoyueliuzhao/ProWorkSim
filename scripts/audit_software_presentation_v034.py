"""One narrow, preselected CPU native-token presentation audit; never load weights."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from proworksim.software_context_v034 import (
    VERSION,
    deduplicate_contracts,
    observation_messages,
    project_software_request,
)
from proworksim.storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["contract", "tool_schema", "task_board", "version_metadata", "code",
         "latest_feedback", "historical_observations"]


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def ref(path):
    path = Path(path)
    return {"path": str(path.relative_to(ROOT)),
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def select(output):
    plan = read(output / "selection-plan.json")
    samples, stages = [], []
    for model in plan["models"]:
        for slot in plan["slot_ids"]:
            base = ROOT / plan["origins"][slot] / model / "actual/diagnostics"
            folder = base / ("slot-1" if "ledger" in slot else "slot-3")
            events = [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines()]
            attempts = [e for e in events if e["kind"] == "model_attempt"
                        and e["payload"]["stage"] == "started"]
            mapped = []
            for index, event in enumerate(attempts, 1):
                request_folder = folder / "raw-transport/context-projections" / f"request-{index:05d}"
                if read(request_folder / "original-request.json") != event["payload"]["request"]:
                    raise ValueError("Actual event/request order mismatch")
                mapped.append((event, request_folder))
            edits = [e for e in events if e["kind"] == "tool_call"
                     and e["payload"]["action"] in {"write_file", "replace_file"}
                     and e["payload"]["response"].get("ok") is True
                     and e["payload"]["response"].get("command_committed") is True]
            tests = [e for e in events if e["kind"] == "tool_call"
                     and e["payload"]["action"] == "run_tests"
                     and e["payload"]["response"].get("ok") is True
                     and e["payload"]["response"].get("result", {}).get("executed") is True]
            selections = [mapped[0] if mapped else None,
                          next((x for x in mapped if edits and x[0]["sequence"] > edits[0]["sequence"]), None),
                          next((x for x in mapped if tests and x[0]["sequence"] > tests[0]["sequence"]), None),
                          mapped[-1] if mapped else None]
            for stage, choice in zip(plan["stage_order"], selections):
                record = {"model": model, "slot_id": slot, "stage": stage, "selected": choice is not None}
                stages.append(record)
                if choice is None:
                    record["missing_reason"] = "No qualifying event or no subsequent actual call"
                    continue
                event, request_folder = choice
                payload = event["payload"]
                key = f"{model}/{slot}/{payload['attempt_id']}"
                record["sample_id"] = key
                existing = next((x for x in samples if x["sample_id"] == key), None)
                if existing:
                    existing["stages"].append(stage)
                    continue
                response = read(request_folder / "response.json")
                finished = [e for e in events if e["kind"] == "model_attempt"
                            and e["payload"]["stage"] == "finished"
                            and e["payload"]["attempt_id"] == payload["attempt_id"]]
                if (len(finished) != 1 or finished[0]["payload"]["status"] != "success"
                        or finished[0]["payload"]["response"] != response):
                    raise ValueError("Actual attempt finished/archived response binding mismatch")
                if response["http_status"] != 200 or not isinstance(response["body"]["token_trace"]["input_ids"], list):
                    raise ValueError("Selected call lacks actual native input IDs")
                samples.append({"sample_id": key, "model": model, "slot_id": slot,
                                "member": event["worker_id"], "sequence": event["sequence"],
                                "call_id": payload["call_id"], "attempt_id": payload["attempt_id"],
                                "finished_sequence": finished[0]["sequence"], "finished_response_equal": True,
                                "stages": [stage], "folder": str(request_folder.relative_to(ROOT)),
                                "files": {n: ref(request_folder / n) for n in
                                          ["original-request.json", "selected-request.json", "projection.json", "response.json"]},
                                "events": ref(folder / "experience.jsonl"),
                                "first_successful_edit_sequence": edits[0]["sequence"] if edits else None,
                                "first_executed_test_sequence": tests[0]["sequence"] if tests else None})
    manifest = {"version": plan["version"], "plan": ref(output / "selection-plan.json"),
                "selection_completed_before_token_measurement": True, "stage_assignments": stages,
                "samples": samples, "selected_unique_calls": len(samples),
                "missing_stages": sum(not row["selected"] for row in stages), "model_calls": 0, "gpu_used": False}
    write(output / "sample-manifest.json", manifest)
    return {"selected_unique_calls": len(samples), "missing_stages": manifest["missing_stages"]}


def native_renderer(model):
    from proworksim.candidate_runtime_v015 import prepare_candidate_prompt
    from proworksim.candidate_runtime_v030 import MistralNativeTokenizer
    from proworksim.native_codecs_v031 import prepare_code_request
    historical = "v030" if model == "qwen3.5-9b" else "v031"
    owner_path = ROOT / f"runs/software-model-selection-{historical}" / model / "actual/resident/owner.json"
    owner = read(owner_path)
    model_path = Path(owner["base_identity"]["path"])
    if model == "qwen3.5-9b":
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
        def render(request):
            return prepare_candidate_prompt(request, tokenizer, owner["inference_profile"])
        names = ["tokenizer.json", "tokenizer_config.json", "chat_template.jinja"]
    else:
        tokenizer = MistralNativeTokenizer(model_path)
        def render(request):
            return prepare_code_request(request, tokenizer, model)
        names = ["tekken.json", "config.json"]
    provenance = {"owner": ref(owner_path), "tokenizer_path": str(model_path),
                  "files": [{"path": str(model_path / name), "file_sha256": digest((model_path / name).read_bytes())}
                            for name in names if (model_path / name).exists()],
                  "weights_loaded": False}
    return tokenizer, render, provenance


def _rewrite_json(message, function):
    try:
        value = json.loads(message.get("content", ""))
    except (ValueError, TypeError):
        return
    before = copy.deepcopy(value)
    function(value)
    if value != before:
        message["content"] = json.dumps(value, ensure_ascii=False, allow_nan=False)


def eliminate(request, category):
    """Counterfactual diagnostics only: masks content, retaining native envelopes.

    These category removals are NOT runtime projection policies. In particular,
    legitimate tools and code are removed only for explicit cost measurements.
    """
    result = copy.deepcopy(request)
    observations = list(observation_messages(result))
    if category == "tool_schema":
        result.pop("tools", None)
        result.pop("tool_choice", None)
    elif category in {"contract", "task_board"}:
        for index, payload in observations:
            observation = payload["observation"]
            if category == "contract":
                observation.pop("contract", None)
                if isinstance(observation.get("root_goal"), dict):
                    observation["root_goal"].pop("description", None)
            else:
                for key in ["tasks", "task_event_sequences", "task_formation"]:
                    observation.pop(key, None)
            result["messages"][index]["content"] = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    elif category == "version_metadata":
        keys = {"workspace_reference", "source_reference", "base_source_reference", "version_id",
                "object_id", "files_sha256", "sha256", "committed_revision", "command_id", "action_id",
                "logical_time", "world_id", "instance_id", "branch_id", "project_id", "interface_revision",
                "included_patch_ids", "patches", "all_fixed_patches", "deliveries", "handoffs",
                "older_handoff_sequences", "current_version_test_coverage"}
        def remove(value):
            if isinstance(value, dict):
                for key in list(value):
                    if key in keys:
                        del value[key]
                    else:
                        remove(value[key])
            elif isinstance(value, list):
                for item in value:
                    remove(item)
        for message in result["messages"]:
            if message.get("role") in {"user", "tool"}:
                _rewrite_json(message, remove)
    elif category == "code":
        # Exact tool payload fields for file reads/diffs/searches and edits.
        # Contract read_file text is classified as contract, not source code.
        names = {}
        for message in result["messages"]:
            for call in message.get("tool_calls", []):
                function = call["function"]
                names[call["id"]] = function["name"]
                if function["name"] in {"write_file", "replace_file"}:
                    args = json.loads(function["arguments"])
                    for key in ("text", "old", "new"):
                        if key in args:
                            args[key] = ""
                    function["arguments"] = json.dumps(args, ensure_ascii=False, allow_nan=False)
            if message.get("role") == "tool" and names.get(message.get("tool_call_id")) in {
                    "read_file", "search_file", "diff_workspace"}:
                def remove_code(value):
                    payload = value.get("result", {}) if isinstance(value, dict) else {}
                    if payload.get("path") == "contract.md":
                        return
                    for key in ("text", "diff", "matches"):
                        payload.pop(key, None)
                _rewrite_json(message, remove_code)
    elif category == "latest_feedback":
        latest_tool = max((i for i, m in enumerate(result["messages"]) if m.get("role") == "tool"), default=-1)
        if latest_tool >= 0:
            result["messages"][latest_tool]["content"] = ""
        # Initial public baseline feedback and subsequent latest observable state
        # are not automatically latest actual tool feedback.
    elif category == "historical_observations":
        for index, _ in observations[:-1]:
            def remove_observation(payload):
                payload.pop("observation", None)
            _rewrite_json(result["messages"][index], remove_observation)
    else:
        raise ValueError(category)
    return result


def measure(output):
    manifest = read(output / "sample-manifest.json")
    if manifest["plan"] != ref(output / "selection-plan.json"):
        raise ValueError("Selection plan changed after manifest")
    rows, provenance = [], {}
    for model in ["qwen3.5-9b", "devstral-small-2507"]:
        tokenizer, render, provenance[model] = native_renderer(model)
        def ids(request):
            rendered, _, _ = render(request)
            return tokenizer(rendered, add_special_tokens=False)["input_ids"]
        for sample in [s for s in manifest["samples"] if s["model"] == model]:
            folder = ROOT / sample["folder"]
            for name, expected in sample["files"].items():
                if ref(folder / name) != expected:
                    raise ValueError("Frozen selected artifact changed")
            actual = read(folder / "selected-request.json")
            original = read(folder / "original-request.json")
            response = read(folder / "response.json")["body"]
            actual_ids = ids(actual)
            old_projection = read(folder / "projection.json")
            actual_rendered, _, _ = render(actual)
            if (digest(actual_rendered.encode()) != old_projection["rendered_prompt_sha256"]
                    or digest(json_bytes(actual_ids)) != old_projection["input_ids_sha256"]
                    or len(actual_ids) != old_projection["selected_prompt_tokens"]):
                raise ValueError("Original projection render/IDs/count binding mismatch")
            if actual_ids != response["token_trace"]["input_ids"] or len(actual_ids) != response["usage"]["prompt_tokens"]:
                raise ValueError("Native input reconstruction mismatch: " + sample["sample_id"])
            total = len(actual_ids)
            current, previous, deltas, independent = actual, total, [], []
            for category in ORDER:
                current = eliminate(current, category)
                count = len(ids(current))
                deltas.append({"category": category, "tokens_removed_given_previous_categories": previous - count,
                               "remaining_prompt_tokens": count})
                previous = count
                independent.append({"category": category,
                                    "tokens_removed_alone": total - len(ids(eliminate(actual, category)))})
            projected_actual, duplicate_evidence = deduplicate_contracts(actual)
            dedup_count = len(ids(projected_actual))
            new_selected, new_audit = project_software_request(original, render=render, tokenizer=tokenizer,
                                                              context_limit=16384)
            rows.append({**{k: sample[k] for k in ["sample_id", "model", "slot_id", "stages", "member", "sequence"]},
                         "actual_prompt_tokens": total, "exact_input_ids_equal": True,
                         "input_ids_sha256": digest(json_bytes(actual_ids)),
                         "original_rendered_prompt_sha256": old_projection["rendered_prompt_sha256"],
                         "original_projection_count_equal": True,
                         "ordered_elimination": deltas, "residual_tokens": previous,
                         "telescoping_identity_holds": sum(x["tokens_removed_given_previous_categories"] for x in deltas) + previous == total,
                         "independent_elimination": independent,
                         "nonadditivity_tokens": sum(x["tokens_removed_alone"] for x in independent) + previous - total,
                         "duplicate_evidence": duplicate_evidence,
                         "same_retained_rounds_after_dedup_tokens": dedup_count,
                         "same_retained_rounds_tokens_removed": total - dedup_count,
                         "full_original_request_tokens": new_audit["original_prompt_tokens"],
                         "new_gamma_from_original_tokens": new_audit["selected_prompt_tokens"],
                         "new_gamma_actual_difference_tokens": total - new_audit["selected_prompt_tokens"],
                         "new_gamma_projection": new_audit,
                         "complete_tools_equal": new_selected.get("tools") == original.get("tools")})
    totals = {"unique_calls": len(rows), "stage_assignments": len(manifest["stage_assignments"]),
              "missing_stages": manifest["missing_stages"],
              "actual_prompt_tokens": sum(r["actual_prompt_tokens"] for r in rows),
              "same_retained_rounds_after_dedup_tokens": sum(r["same_retained_rounds_after_dedup_tokens"] for r in rows),
              "same_retained_rounds_tokens_removed": sum(r["same_retained_rounds_tokens_removed"] for r in rows),
              "new_gamma_from_original_tokens": sum(r["new_gamma_from_original_tokens"] for r in rows),
              "new_gamma_actual_difference_tokens": sum(r["new_gamma_actual_difference_tokens"] for r in rows),
              "ordered_elimination": {c: sum(next(x["tokens_removed_given_previous_categories"] for x in r["ordered_elimination"] if x["category"] == c) for r in rows) for c in ORDER},
              "residual_tokens": sum(r["residual_tokens"] for r in rows),
              "nonadditivity_tokens": sum(r["nonadditivity_tokens"] for r in rows)}
    report = {"version": VERSION, "passed": True, "selection_manifest": ref(output / "sample-manifest.json"),
              "selection_plan": ref(output / "selection-plan.json"), "native_provenance": provenance,
              "category_order": ORDER,
              "definitions": {"ordered_elimination": "Exact native token differences after each declared category removal; order dependent, not unique token ownership. Masked requests are cost counterfactuals, never model calls or runtime policy.",
                              "independent_elimination": "Each category removed alone from the actual request. Overlap and BPE/template boundaries make deltas nonadditive.",
                              "residual": "Native envelope, instructions, assistant prose, initial public feedback, historical format-feedback messages, remaining current state, legal tool-call structure and all unclassified text. Not assigned to a misleading category.",
                              "contract": "observation.contract and root_goal.description; explicit tool-return reads of contract.md remain residual unless latest-feedback masking covers them.",
                              "task_board": "Observation tasks, task_event_sequences and task_formation.",
                              "code": "Declared file edit arguments and read/search/diff tool-result fields only; prose or code quoted elsewhere stays residual.",
                              "latest_feedback": "Most recent actual tool message content after previous category removal; initial baseline feedback stays residual.",
                              "historical_observations": "Earlier SDK observation objects after previous category removal; latest complete observation remains.",
                              "new_gamma_comparison": "Same archived requests re-rendered without generation. New Gamma may retain additional older complete rounds, so compare fixed retained rounds separately from actual new selector output. This is not realized episode saving or behavior equivalence."},
              "totals": totals, "samples": rows, "model_calls": 0, "gpu_used": False,
              "weights_loaded": False, "qualification_repeated": False,
              "limitations": ["Four predeclared seed1 T episodes; no population estimate over 575 calls.",
                              "No behavior-distribution-invariance or task success claim.",
                              "No model memory, summaries, planning or legal schema reduction."]}
    write(output / "report.json", report)
    lines = ["# v0.34 P0 输入呈现窄核查", "", "固定两模型×两个根目标×seed1 的 T 槽，各四阶段；先保存选择规则和样本清单，再计 token。阶段按全槽事件顺序，可能跨成员。缺失阶段和重复调用单列。", "",
             f"{totals['unique_calls']} 个不同实际调用；{totals['missing_stages']} 个阶段缺失。全部 native input IDs 与原响应逐项相等。CPU tokenizer；模型调用 0，GPU 使用 false，未加载权重，未重做资格。", "",
             "| 类别（按此消除顺序） | 条件消除 token 差 |", "|---|---:|"]
    lines += [f"| {c} | {totals['ordered_elimination'][c]} |" for c in ORDER]
    lines += [f"| 未分摊残余 | {totals['residual_tokens']} |", f"| 原实际 prompt 总量 | {totals['actual_prompt_tokens']} |", "",
              "这些数值是按声明顺序逐项消除后的精确差值，可与残余相加复原总量；并非唯一的 BPE 归属或比例。单独消除各类别存在交叠及模板/BPE 边界效应，JSON 同时保留非可加性差。", "",
              f"同一已保留历史轮次仅去重复合同后：{totals['same_retained_rounds_after_dedup_tokens']} token，差值 {totals['same_retained_rounds_tokens_removed']}。从完整原请求执行新 Γ 后：{totals['new_gamma_from_original_tokens']} token，相对旧实际输入差值 {totals['new_gamma_actual_difference_tokens']}；新投影可因此保留更多旧轮，两种差值须分开。", "",
              "运行时仅删除完全相等的 root_goal.description 和早期观察重复 contract，最新完整合同、其余当前状态、最新真实工具反馈及全部合法工具 schema 保留。容量规则沿用整轮删除；最新 user 中合同锚点不会被删除。完整原请求与投影请求均归档。", "",
              "这是新 Γ，后续 B/G/I 一致采用。没有宣称行为分布不变，也没有将反事实请求的 token 差外推为未来完整经历节约或成功率提升。原 575 调用及旧业务结果不变。", "",
              "| 模型/根目标/阶段 | 原实际 | 固定历史去重后 | 新 Γ |", "|---|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['model']} / {row['slot_id']} / {', '.join(row['stages'])} | {row['actual_prompt_tokens']} | {row['same_retained_rounds_after_dedup_tokens']} | {row['new_gamma_from_original_tokens']} |")
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return totals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "runs/v034-controls/presentation")
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()
    if args.select == args.measure:
        raise ValueError("Choose exactly one of --select or --measure; freeze selection first")
    print(json.dumps(select(args.output) if args.select else measure(args.output)))


if __name__ == "__main__":
    main()
