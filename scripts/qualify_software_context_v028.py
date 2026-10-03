"""CPU-only regression for a recorded software context overflow.

Original transport records are immutable inputs. Reconstructed WorldCore and
reordered-message controls are labeled diagnostic inputs, never model trajectories.
Only the local tokenizer and native prompt renderer are loaded; no actor constructor,
model weights, sampling, network transport or optimizer is used.
"""

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim.audit import code_identity  # noqa: E402
from proworksim.deterministic_work_v024 import DeterministicCandidateActor  # noqa: E402
from proworksim.software_collaboration_v028 import (  # noqa: E402
    INTERFACE_REVISION, PROJECT, SoftwareCollaborationPort,
    build_software_collaboration_case, case_spec,
)
from proworksim.software_context_v028 import VERSION as CONTEXT_POLICY, project_software_request  # noqa: E402
from proworksim.storage import atomic_write, digest, json_bytes, read_json  # noqa: E402

VERSION = "software-context-regression-qualification-v0.28.1"
CONTEXT = 16384
OUTPUT = 2048


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def save(folder, name, value):
    path = folder / name
    atomic_write(path, json_bytes(value))
    return reference(path)


def actor_for(request):
    observations = [json.loads(message["content"])["observation"]
                    for message in request["messages"] if message["role"] == "user"]
    return observations[-1]["actor_id"]


def recorded_writes(failed_path, request):
    """Recover executed writes from this actor's preceding persisted requests.

    The failing request retains only four rounds: its fields.py overwrite has
    already aged out. Earlier requests provide its exact original arguments;
    matched successful tool receipts establish that each write really occurred.
    """
    actor = actor_for(request)
    calls = {}
    for path in sorted(failed_path.parent.glob("call-*.started.json")):
        if path.name > failed_path.name:
            continue
        record = read_json(path)
        current = record["request"]
        if actor_for(current) != actor:
            continue
        messages = current["messages"]
        for index, message in enumerate(messages[:-1]):
            tool_calls = message.get("tool_calls") or []
            if message["role"] != "assistant" or len(tool_calls) != 1:
                continue
            call = tool_calls[0]
            if call["function"]["name"] != "write_file":
                continue
            following = messages[index + 1]
            if following.get("role") != "tool" or following.get("tool_call_id") != call["id"]:
                raise ValueError("Recorded write has no exact corresponding tool receipt")
            receipt = json.loads(following["content"])
            if receipt.get("ok") is not True:
                continue
            entry = {"tool_call_id": call["id"], "source_record": reference(path),
                     "assistant_message_index": index, "actor_id": actor,
                     "arguments": json.loads(call["function"]["arguments"]),
                     "recorded_receipt": receipt}
            if call["id"] in calls:
                if calls[call["id"]]["arguments"] != entry["arguments"]:
                    raise ValueError("Repeated recorded write identity changed arguments")
            else:
                calls[call["id"]] = entry
    if not calls:
        raise ValueError("No recorded successful write_file action is available for reconstruction")
    return sorted(calls.values(), key=lambda item: item["recorded_receipt"]["logical_time"])


def full_diff_receipt(failed_path, request, model_visible_receipt):
    """Resolve the unchanged pre-SDK receipt by action ID and exact source.

    The old SDK clipped this result at 50000 message characters. Its model input
    is necessary to reproduce token counts, but cannot establish lossless pages.
    The corresponding durable public capture still contains the original bytes.
    """
    capture = failed_path.parent.parent / "slot-0/public-capture" / (actor_for(request) + ".jsonl")
    matches = []
    for line_index, line in enumerate(capture.read_text().splitlines(), 1):
        event = json.loads(line)
        payload = event["payload"]
        if (event["kind"] == "tool_call" and payload.get("action") == "diff_workspace"
                and payload["response"].get("action_id") == model_visible_receipt["action_id"]):
            matches.append({"capture": reference(capture), "line": line_index,
                            "event": event})
    if len(matches) != 1:
        raise ValueError("Expected exactly one original WorldCore diff receipt for the failed request")
    result = matches[0]["event"]["payload"]["response"]
    if result["result"]["source_reference"] != model_visible_receipt["result"]["source_reference"]:
        raise ValueError("Captured original diff refers to another source version")
    return result, matches[0]


def measure(request, folder, renderer):
    folder.mkdir(parents=True, exist_ok=False)
    rendered, normalized, projection = renderer.prepare_request(request)
    ids = renderer.tokenizer(rendered, add_special_tokens=False)["input_ids"]
    maximum = request["max_tokens"]
    result = {"prompt_tokens": len(ids), "reserved_output_tokens": maximum,
              "context_limit": CONTEXT, "fits_context": len(ids) + maximum <= CONTEXT,
              "remaining_context_after_output_reservation": CONTEXT - maximum - len(ids),
              "request": save(folder, "request.json", request),
              "normalized_messages": save(folder, "normalized-messages.json", normalized),
              "native_projection": save(folder, "native-projection.json", projection),
              "actual_tokenizer_input_ids": save(folder, "input-ids.json", ids)}
    atomic_write(folder / "rendered-prompt.txt", rendered.encode())
    result["rendered_prompt"] = reference(folder / "rendered-prompt.txt")
    save(folder, "measurement.json", result)
    return result


def check_projection(request, selected, audit):
    messages = request["messages"]
    retained = audit["selected_indices"]
    removed = set(audit["removed_indices"])
    pairs = audit["complete_tool_rounds"]
    return (selected["messages"] == [messages[index] for index in retained]
            and {key: value for key, value in selected.items() if key != "messages"}
            == {key: value for key, value in request.items() if key != "messages"}
            and all(index in retained for index, message in enumerate(messages)
                    if message["role"] in {"system", "user"})
            and all(not (set(pair) & removed) or set(pair) <= removed for pair in pairs)
            and (not pairs or all(index in retained for index in pairs[-1])))


def projection_control(request, folder, renderer):
    selected, audit = project_software_request(
        request, render=renderer.prepare_request, tokenizer=renderer.tokenizer, context_limit=CONTEXT)
    original = measure(request, folder / "original", renderer)
    measured = measure(selected, folder / "selected", renderer)
    result = {"original": original, "selected": measured, "audit": audit,
              "original_content_and_complete_pairs_preserved": check_projection(request, selected, audit)}
    save(folder, "projection-control.json", result)
    return result


def run_controls(output, failed_path, prior_path, report):
    from transformers import AutoTokenizer

    source_record = read_json(failed_path)
    request = source_record["request"]
    prior = read_json(prior_path)
    profile = prior["runtime_profile"]
    if (profile["max_context_tokens"] != CONTEXT or profile["max_output_tokens"] != OUTPUT
            or profile["chat_template_kwargs"].get("enable_thinking") is not False
            or request["max_tokens"] != OUTPUT):
        raise ValueError("This regression fixes the original non-thinking 16384/2048 profile")
    model_path = Path(prior["model"])
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    renderer = object.__new__(DeterministicCandidateActor)
    renderer.tokenizer = tokenizer
    renderer.inference_profile = copy.deepcopy(profile)
    report.update(runtime_profile=profile, tokenizer_files={
        name: reference(model_path / name) for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")})
    inputs = output / "inputs"
    inputs.mkdir()
    atomic_write(inputs / failed_path.name, failed_path.read_bytes())
    atomic_write(inputs / "prior-model-plan.json", prior_path.read_bytes())
    report["original_failed_request"] = measure(request, output / "original-failed-request", renderer)

    diff_indices = [index for index, message in enumerate(request["messages"])
                    if message.get("role") == "tool" and message.get("name") == "diff_workspace"]
    if not diff_indices:
        raise ValueError("Expected the recorded diff_workspace tool result")
    diff_index = diff_indices[-1]
    old_receipt = json.loads(request["messages"][diff_index]["content"])
    world_receipt, capture_provenance = full_diff_receipt(failed_path, request, old_receipt)
    original_diff = world_receipt["result"]["diff"]
    capture_path = Path(capture_provenance["capture"]["path"])
    atomic_write(inputs / "original-public-capture.jsonl", capture_path.read_bytes())
    save(inputs, "original-full-diff-receipt.json", capture_provenance)
    report["input_files_before"].append(capture_provenance["capture"])
    report["original_world_tool_receipt"] = {
        "capture": capture_provenance["capture"], "line": capture_provenance["line"],
        "action_id": world_receipt["action_id"],
        "world_diff_chars": len(original_diff),
        "model_visible_diff_chars": len(old_receipt["result"]["diff"]),
        "model_visible_message_chars": len(request["messages"][diff_index]["content"]),
        "sdk_clipping_marker_present": "<response clipped>" in old_receipt["result"]["diff"],
        "world_and_model_visible_diffs_equal": original_diff == old_receipt["result"]["diff"],
        "comparison_scope": "Pagination is compared to the full WorldCore receipt. Token counts use the preserved SDK model-visible request, including its original clipping marker.",
    }
    writes = recorded_writes(failed_path, request)
    report["reconstruction_writes"] = save(inputs, "recorded-successful-writes.json", writes)
    for item in writes:
        source = Path(item["source_record"]["path"])
        atomic_write(inputs / source.name, source.read_bytes())
        report["input_files_before"].append(item["source_record"])

    case = case_spec("marshmallow-integration-dev")
    prepared = build_software_collaboration_case(case, output / "reconstructed-world")
    actor = actor_for(request)
    port = SoftwareCollaborationPort(prepared.world.session(actor, PROJECT), actor)
    action_folder = output / "reconstructed-world-actions"
    action_folder.mkdir()
    for index, item in enumerate(writes, 1):
        receipt = port.call("write_file", **item["arguments"])
        save(action_folder, f"write-{index:03d}.json", {"recorded_action": item, "actual_receipt": receipt})
        if receipt.get("ok") is not True:
            raise ValueError("Actual WorldCore rejected a reconstructed recorded write")

    pages, fragments = [], []
    arguments = {}
    while True:
        receipt = port.call("diff_workspace", **arguments)
        save(action_folder, f"diff-page-{len(pages) + 1:03d}.json",
             {"arguments": arguments, "actual_receipt": receipt})
        if receipt.get("ok") is not True:
            raise ValueError("Actual WorldCore rejected a pinned diff page")
        page = receipt["result"]
        if not pages:
            first_receipt = copy.deepcopy(receipt)
            fixed_reference = copy.deepcopy(page["source_reference"])
        pages.append(page)
        fragments.append(page["diff"])
        if not page["has_more"]:
            break
        if page["next_offset"] <= page["offset"]:
            raise ValueError("Diff pagination did not advance")
        arguments = {"offset": page["next_offset"], "source_reference": fixed_reference}
    reconstructed_diff = "".join(fragments)
    atomic_write(action_folder / "concatenated-diff.txt", reconstructed_diff.encode())
    report["diff_reconstruction"] = {
        "case": case, "actor_id": actor, "interface_revision": INTERFACE_REVISION,
        "page_count": len(pages), "first_page_chars": len(pages[0]["diff"]),
        "original_diff_chars": len(original_diff), "original_diff_sha256": digest(original_diff.encode()),
        "reconstructed_diff_chars": len(reconstructed_diff),
        "reconstructed_diff_sha256": digest(reconstructed_diff.encode()),
        "reconstructed_full_diff_equals_original": reconstructed_diff == original_diff,
        "all_pages_pin_same_source": all(page["source_reference"] == fixed_reference for page in pages),
        "all_pages_declare_full_hash": all(page["diff_sha256"] == digest(reconstructed_diff.encode()) for page in pages),
        "all_pages_declare_full_length": all(page["total_chars"] == len(reconstructed_diff) for page in pages),
        "all_pages_contiguous": [page["offset"] for page in pages]
        == [sum(len(fragment) for fragment in fragments[:index]) for index in range(len(pages))],
        "concatenated_diff": reference(action_folder / "concatenated-diff.txt"),
    }

    # Change only the old tool result's result field and current world schemas.
    # Surrounding old action metadata is retained for a controlled tokenization
    # comparison, not represented as a real new execution/model trajectory.
    paged = copy.deepcopy(request)
    replacement = copy.deepcopy(old_receipt)
    replacement["result"] = copy.deepcopy(first_receipt["result"])
    paged["messages"][diff_index]["content"] = json.dumps(replacement, ensure_ascii=False, allow_nan=False)
    world_tools = {definition["name"]: definition for definition in port.tools()}
    original_names = {tool["function"]["name"] for tool in request["tools"]}
    if not set(world_tools) <= original_names:
        raise ValueError("Current world introduced a tool absent from the recorded contract")
    for tool in paged["tools"]:
        name = tool["function"]["name"]
        if name in world_tools:
            tool["function"] = copy.deepcopy(world_tools[name])
    save(action_folder, "request-reconstruction.json", {
        "kind": "reconstructed_CPU_control_not_model_trajectory",
        "replaced_result_message_index": diff_index,
        "changed_request_fields": [f"messages[{diff_index}].content JSON result", "tools matching current WorldCore names"],
        "world_tool_names": sorted(world_tools),
        "preserved_original_control_tool_names": sorted(original_names - set(world_tools)),
        "actual_new_world_first_page_receipt": first_receipt,
        "legacy_receipt_with_reconstructed_result": replacement,
    })
    report["paged_failed_path"] = projection_control(paged, output / "paged-failed-path", renderer)

    # Move the unchanged large diff round ahead of the earlier small rounds.
    # This explicitly synthetic ordering isolates eviction of an OLD full pair.
    reordered = copy.deepcopy(request)
    large_pair = copy.deepcopy(request["messages"][diff_index - 1:diff_index + 1])
    del reordered["messages"][diff_index - 1:diff_index + 1]
    insert_at = next(index for index, message in enumerate(reordered["messages"])
                     if message["role"] == "assistant")
    reordered["messages"][insert_at:insert_at] = large_pair
    report["older_large_diff"] = projection_control(reordered, output / "older-large-diff", renderer)
    save(output / "older-large-diff", "construction.json", {
        "kind": "reordered_CPU_control_not_model_trajectory", "moved_original_indices": [diff_index - 1, diff_index],
        "inserted_at": insert_at, "message_text_changes": False,
    })
    report["latest_large_diff"] = projection_control(request, output / "latest-large-diff", renderer)
    old = report["original_failed_request"]
    repaired = report["paged_failed_path"]
    older = report["older_large_diff"]
    latest = report["latest_large_diff"]
    diff = report["diff_reconstruction"]
    report["gates"] = {
        "recorded_19439_prompt_tokens_reproduced": old["prompt_tokens"] == 19439,
        "recorded_16k_overflow_reproduced": not old["fits_context"],
        "full_diff_reconstructed_exactly": diff["reconstructed_full_diff_equals_original"],
        "all_diff_pages_complete_and_bound": all(diff[key] for key in (
            "all_pages_pin_same_source", "all_pages_declare_full_hash", "all_pages_declare_full_length", "all_pages_contiguous")),
        "new_diff_path_fits_without_eviction": repaired["original"]["fits_context"] and not repaired["audit"]["removed_indices"],
        "new_diff_path_fits_after_projection": repaired["audit"]["fits"],
        "older_large_diff_initially_overflows": not older["original"]["fits_context"],
        "older_large_diff_pair_is_removed": set([insert_at, insert_at + 1]) <= set(older["audit"]["removed_indices"]),
        "older_large_diff_then_fits": older["audit"]["fits"],
        "latest_large_diff_remains_explicit_overflow": not latest["audit"]["fits"],
        "latest_large_diff_pair_not_removed": not set([diff_index - 1, diff_index]) & set(latest["audit"]["removed_indices"]),
        "all_projection_controls_preserve_retained_text_and_pairs": all(
            control["original_content_and_complete_pairs_preserved"] for control in (repaired, older, latest)),
    }


def qualify(output, failed_request, prior_model_plan):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    failed_path, prior_path = Path(failed_request).resolve(), Path(prior_model_plan).resolve()
    report = {
        "version": VERSION, "passed": False, "source": code_identity(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model_calls": 0, "model_weights_loaded": False, "gpu_used": False, "optimizer_updates": 0,
        "interface_revision": INTERFACE_REVISION, "context_policy": CONTEXT_POLICY,
        "max_context_tokens": CONTEXT, "max_output_tokens": OUTPUT,
        "failed_request": reference(failed_path), "prior_model_plan": reference(prior_path),
        "input_files_before": [reference(failed_path), reference(prior_path)],
        "qualification_implementation": {str(path.relative_to(ROOT)): reference(path) for path in (
            Path(__file__).resolve(), ROOT / "src/proworksim/software_collaboration_v028.py",
            ROOT / "src/proworksim/software_context_v028.py")},
        "scope": "CPU actual-tokenizer regression only. Recorded failed request is preserved; reconstructed WorldCore pages and reordered messages are controls, never model trajectories or success/learning evidence.",
    }
    save(output, "context-qualification.json", report)
    try:
        run_controls(output, failed_path, prior_path, report)
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["source_after"] = code_identity()
        report["input_files_after"] = [reference(row["path"]) for row in report["input_files_before"]]
        gates = report.setdefault("gates", {})
        gates["source_unchanged_during_qualification"] = report["source"] == report["source_after"]
        gates["original_input_files_unchanged"] = report["input_files_before"] == report["input_files_after"]
        report["passed"] = "error" not in report and all(gates.values())
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(output, "context-qualification.json", report)
        summary = {key: report[key] for key in ("version", "passed", "source", "source_after", "model_calls", "gpu_used", "gates")}
        summary["report"] = reference(output / "context-qualification.json")
        if "error" in report:
            summary["error"] = report["error"]
        save(output, "summary.json", summary)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--failed-request", required=True)
    parser.add_argument("--prior-model-plan", required=True)
    args = parser.parse_args()
    report = qualify(args.output, args.failed_request, args.prior_model_plan)
    print(json.dumps({"passed": report["passed"], "output": str(Path(args.output).resolve()),
                      "error": report.get("error"), "gates": report["gates"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
