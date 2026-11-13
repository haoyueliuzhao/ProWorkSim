"""Audit retained v174 response outputs only; no model/world/scoring operation."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from proworksim.software_collaboration_observation_v141 import load_official_content_counter

DIRECT = {"send_message": "body", "handoff_patch": "message"}
COORDINATION = {
    "org_review_patch", "offer_transfer", "accept_transfer", "decline_transfer",
    "declare_dependency", "clear_dependency", "create_task", "claim_task",
    "revise_task", "return_task", "org_declare_role", "org_status",
    "delivery_status", "submit_integration", "staff_wait", "staff_done",
}
AUDIT = ROOT / "artifacts/software-benchmark-v174/final-report-r1/evidence-audit.json"
PANEL = ROOT / "artifacts/software-benchmark-v174/final-report-r1/summary.json"
INPUT_SUMMARY = ROOT / "artifacts/software-benchmark-v175/p0-corpus-r1/summary.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": digest(raw), "bytes": len(raw)}


def checked_json(ref):
    raw = Path(ref["path"]).read_bytes()
    if len(raw) != ref["bytes"] or digest(raw) != ref["sha256"]:
        raise ValueError("Retained response/receipt reference changed: " + ref["path"])
    return json.loads(raw)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Ambiguous duplicate argument key")
        value[key] = item
    return value


def nonempty(value):
    return value not in (None, "", [], {})


def inspect_response(item):
    receipt = checked_json(item["receipt"])
    ledger = receipt["ledger_record"]
    metadata = checked_json(receipt["response_metadata_ref"])
    body = checked_json(receipt["response_original_ref"])
    usage = body["usage"]
    charged = json.loads(ledger["usage_json"])
    if (receipt["request_id"] != item["request_id"] or ledger["request_id"] != item["request_id"]
            or ledger["status"] != "settled" or ledger["response_id"] != body["id"]
            or metadata != receipt["response_metadata"] or metadata["outcome"] != "success"
            or metadata["episode_id"] != ledger["slot_id"] or metadata["member_id"] != ledger["member_id"]
            or ledger["usage_id"] != item["purpose"] or usage != charged or receipt.get("observer_errors")):
        raise ValueError("Response identity or settled usage is inconsistent")
    for actual, normalized in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens"),
                               ("total_tokens", "total_tokens")):
        if type(usage.get(actual)) is not int or usage[actual] < 0 or usage[actual] != metadata["usage"][normalized]:
            raise ValueError("Provider usage differs from independently retained metadata")
    if usage["prompt_tokens"] + usage["completion_tokens"] != usage["total_tokens"]:
        raise ValueError("Provider token accounting does not add up")
    choices = body.get("choices", [])
    calls, other_content = [], []
    for ci, choice in enumerate(choices):
        message = choice.get("message", {})
        if message.get("role") != "assistant":
            other_content.append("unexpected_role")
        if nonempty(message.get("content")):
            other_content.append("assistant_content")
        for key in ("reasoning", "reasoning_content", "refusal", "audio"):
            if nonempty(message.get(key)):
                other_content.append(key)
        native = message.get("tool_calls") or []
        if not isinstance(native, list):
            raise ValueError("Malformed original tool_calls container")
        for ti, call in enumerate(native):
            function = call.get("function", {})
            calls.append({"choice_index": ci, "tool_index": ti, "tool_call_id": call.get("id"),
                          "tool": function.get("name"), "arguments": function.get("arguments"),
                          "finish_reason": choice.get("finish_reason"), "protocol": "tool_calls"})
        legacy = message.get("function_call")
        if legacy:
            calls.append({"choice_index": ci, "tool_index": None, "tool_call_id": None,
                          "tool": legacy.get("name"), "arguments": legacy.get("arguments"),
                          "finish_reason": choice.get("finish_reason"), "protocol": "function_call"})
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if isinstance(reasoning, int) and reasoning > 0:
        other_content.append("reported_reasoning_tokens")
    direct = [call for call in calls if call["tool"] in DIRECT]
    kind = "not_direct_communication"
    if item["purpose"] == "agent" and direct:
        pure = (len(choices) == 1 and len(calls) == 1 and not other_content
                and direct[0]["finish_reason"] in {"tool_calls", "function_call"})
        kind = "single_communication_action_without_other_visible_content" if pure else "mixed_communication_response"
    fields = []
    if item["purpose"] == "agent":
        for call in direct:
            field = DIRECT[call["tool"]]
            entry = {key: call[key] for key in ("choice_index", "tool_index", "tool_call_id", "tool", "protocol")}
            entry["field"] = field
            try:
                arguments = json.loads(call["arguments"], object_pairs_hook=unique_object)
                text = arguments[field]
                if not isinstance(text, str):
                    raise ValueError("Communication body is not a complete string")
                entry.update(text=text, text_sha256=digest(text.encode()), characters=len(text),
                             complete_field_available=True)
            except (ValueError, TypeError, KeyError) as error:
                entry.update(complete_field_available=False, error=type(error).__name__ + ": " + str(error))
            fields.append(entry)
    return {
        "request_id": item["request_id"], "logical_id": ledger["logical_id"], "episode_id": ledger["slot_id"],
        "member_id": ledger["member_id"], "purpose": ledger["usage_id"], "response_id": body["id"],
        "receipt": item["receipt"], "response_original": receipt["response_original_ref"],
        "response_metadata": receipt["response_metadata_ref"],
        "actual_usage": {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
        "response_class": kind, "choices": len(choices), "tool_names": [call["tool"] for call in calls],
        "other_visible_output_components": sorted(set(other_content)),
        "direct_communication_fields": fields,
        "other_coordination_tool_names": sorted({call["tool"] for call in calls if call["tool"] in COORDINATION}),
        "world_acceptance_not_required_or_inferred": True,
    }


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def main():
    if (OUT / "summary.json").exists():
        raise ValueError("Use a new revision directory instead of replacing this audit")
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    audit, panel, inputs = [json.loads(path.read_bytes()) for path in (AUDIT, PANEL, INPUT_SUMMARY)]
    episodes = {row["slot_id"]: row for row in panel["rows"]}
    assert len(episodes) == 72 and len(audit["physical_capture_index"]) == 5523
    manifest = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    count, tokenizer = load_official_content_counter(manifest, manifest_sha256=reference(manifest)["sha256"])
    all_usage, purposes, groups, output_classes = Counter(), defaultdict(Counter), {}, defaultdict(Counter)
    coordination = defaultdict(Counter)
    index_path = OUT / "verified-response-index.jsonl.gz"
    seen, selected, compressor_requests = set(), [], []
    for group in ("C0", "C1", "C2"):
        groups[group] = {"actual_usage": Counter(), "purpose_usage": defaultdict(Counter),
            "response_classes": defaultdict(Counter), "direct_tools": defaultdict(Counter),
            "agent_direct_communication_body_output_local_estimated_tokens": 0,
            "communication_fields_without_complete_text": 0, "agent_without_tool_calls": 0}
    with index_path.open("xb") as raw_out, gzip.GzipFile(fileobj=raw_out, mode="wb", mtime=0) as archive:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for row in pool.map(inspect_response, audit["physical_capture_index"]):
                if row["request_id"] in seen or row["episode_id"] not in episodes:
                    raise ValueError("Duplicate physical response or noncanonical episode")
                seen.add(row["request_id"])
                row["group"] = group = episodes[row["episode_id"]]["group_id"]
                target = groups[group]
                usage = row["actual_usage"]
                target["actual_usage"].update(usage)
                all_usage.update(usage)
                for value in (purposes[row["purpose"]], target["purpose_usage"][row["purpose"]]):
                    value.update(usage)
                    value["requests"] += 1
                if row["purpose"] == "compressor":
                    compressor_requests.append(row)
                for entry in row["direct_communication_fields"]:
                    tool = target["direct_tools"][entry["tool"]]
                    tool["emitted_tool_calls"] += 1
                    if entry["complete_field_available"]:
                        tokens = count(entry.pop("text"))
                        entry["body_output_local_estimated_tokens"] = tokens
                        tool["body_output_local_estimated_tokens"] += tokens
                        tool["body_characters"] += entry["characters"]
                        target["agent_direct_communication_body_output_local_estimated_tokens"] += tokens
                    else:
                        target["communication_fields_without_complete_text"] += 1
                if row["purpose"] == "agent":
                    values = target["response_classes"][row["response_class"]]
                    values["physical_responses"] += 1
                    values["provider_completion_tokens_reference_only"] += usage["completion_tokens"]
                    output_classes[row["response_class"]].update({"physical_responses": 1,
                        "provider_completion_tokens_reference_only": usage["completion_tokens"]})
                    if not row["tool_names"]:
                        target["agent_without_tool_calls"] += 1
                    for tool in row["other_coordination_tool_names"]:
                        coordination[tool].update({"response_occurrences": 1,
                            "whole_response_completion_tokens_reference_only_not_additive": usage["completion_tokens"]})
                if row["direct_communication_fields"] or row["other_coordination_tool_names"]:
                    selected.append(row)
                archive.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    expected = Counter()
    for row in panel["rows"]:
        expected.update({key: row["usage"][key] for key in all_usage})
    if all_usage != expected or len(seen) != 5523:
        raise ValueError("Actual response totals differ from the canonical 72-episode table")
    compressor_peer, lookup_records = Counter(), []
    dataset = Path(inputs["dataset"]["path"])
    with sqlite3.connect(dataset.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        for row in compressor_requests:
            found = db.execute("SELECT slot_id,metadata FROM requests WHERE request_id=?", (row["request_id"],)).fetchone()
            if not found or found[0] != row["episode_id"]:
                raise ValueError("Five-request source lookup identity differs")
            metadata = json.loads(found[1])
            peer = metadata["source_estimates"]["Peer-message"]
            compressor_peer[row["group"]] += peer
            lookup_records.append({"request_id": row["request_id"], "group": row["group"],
                "peer_input_local_estimated_tokens": peer, "dataset_metadata_sha256": digest(found[1].encode())})
    assert len(lookup_records) == 5 and sum(compressor_peer.values()) == 1006
    assert purposes["compressor"]["completion_tokens"] == 636 and purposes["compressor"]["total_tokens"] == 3985
    for group, target in groups.items():
        target["compressor_peer_input_local_estimated_tokens_excluded_from_agent"] = compressor_peer[group]
        agent_peer = inputs["source_estimates_by_condition"][group]["Peer-message"] - compressor_peer[group]
        target["agent_peer_input_local_estimated_tokens"] = agent_peer
        target["identified_communication_tokens_mixed_accounting_approximation"] = (
            agent_peer + target["agent_direct_communication_body_output_local_estimated_tokens"]
            + target["purpose_usage"]["compressor"]["total_tokens"])
        assert target["actual_usage"] == Counter({key: sum(row["usage"][key] for row in panel["rows"] if row["group_id"] == group) for key in all_usage})
    body_total = sum(value["agent_direct_communication_body_output_local_estimated_tokens"] for value in groups.values())
    agent_peer_total = sum(value["agent_peer_input_local_estimated_tokens"] for value in groups.values())
    assert agent_peer_total == 4918361
    save(OUT / "targeted-response-records.json", selected)
    save(OUT / "compressor-five-source-lookups.json", {
        "dataset_reference_from_original_seal": inputs["dataset"], "database_full_hash_rechecked": False,
        "lookup_method": "5 SELECT metadata FROM requests WHERE request_id=? primary-key lookups only",
        "rows": lookup_records, "group_peer_input_local_estimated_tokens": dict(compressor_peer)})
    summary = {
        "schema": "communication-output-accounting-20261113-r2", "canonical_episodes": 72,
        "verified_physical_responses": len(seen), "superseded_attempts_excluded": 27,
        "sources": {name: reference(path) for name, path in (("canonical_audit", AUDIT), ("canonical_panel", PANEL), ("prior_input_estimates", INPUT_SUMMARY))},
        "actual_usage_matches_original_panel": True, "actual_usage": dict(all_usage),
        "actual_usage_by_purpose": {key: dict(value) for key, value in purposes.items()},
        "groups": groups, "agent_response_classes": dict(output_classes),
        "other_coordination_output_reference_only": dict(coordination),
        "agent_peer_input_local_estimated_tokens": agent_peer_total,
        "agent_direct_communication_body_output_local_estimated_tokens": body_total,
        "identified_communication_tokens_mixed_accounting_approximation": agent_peer_total + body_total + purposes["compressor"]["total_tokens"],
        "tokenizer": tokenizer, "verified_response_index": reference(index_path),
        "targeted_records": reference(OUT / "targeted-response-records.json"),
        "compressor_source_lookups": reference(OUT / "compressor-five-source-lookups.json"),
        "analysis_source": reference(Path(__file__).resolve()),
        "definitions": {
            "body_output": "Only complete decoded send_message.body and handoff_patch.message strings from agent responses; each physical occurrence counted, regardless of later execution/rejection.",
            "excluded_body_output_parts": "assistant.content/reasoning, routing arguments, field names, JSON escapes, tool names/protocol wrapper and other tool outputs; outputs are not provider-exact per-field billing.",
            "pure_completion_reference": "One communication tool and no other visible output; entire completion includes routing/protocol, so still not equal to message body tokens.",
            "mixed_completion_reference": "Contains direct communication plus explanatory text, other output, multiple calls or choices; whole completion is a reference amount only and is not attributed to communication body.",
            "identified_sum": "agent Peer input estimate + agent body output estimate + compressor actual input/output; excludes compressor Peer input estimate already covered by compressor actual input.",
            "not_additive": "Do not add whole-response completion reference totals or per-tool coordination reference totals to the identified sum.",
            "collaboration_scope": "Excludes peer rereads, peer contents inside historical summaries, indexes/wrappers and collaboration-induced code reading, testing and rework. Not complete collaboration cost.",
        },
        "new_model_calls": 0, "new_world_actions": 0, "new_grading_calls": 0,
        "full_input_corpus_reprocessed": False, "request_input_payloads_read": 0,
    }
    save(OUT / "summary.json", summary)
    print(json.dumps({"responses": len(seen), "actual_output": all_usage["completion_tokens"],
        "body_output_local_estimate": body_total, "response_classes": output_classes,
        "groups": {key: {"body_output": value["agent_direct_communication_body_output_local_estimated_tokens"],
                         "direct_tools": value["direct_tools"], "classes": value["response_classes"],
                         "compressor_usage": value["purpose_usage"]["compressor"]} for key, value in groups.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
