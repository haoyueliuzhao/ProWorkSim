"""P0-A: exact archived-request recovery and native-tokenizer CPU replay.

All 32 original v040 capacity rejections are retained. Historical requests are
recovered only when every SDK-selected message hash and the whole request hash
match original records. Replayed measurements never become model trajectories.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import time

from proworksim.software_context_replay_v041 import load_native_measurement, measure_request, reference
from proworksim.storage import atomic_write, digest, json_bytes, read_json

VERSION = "software-context-replay-v0.41"
SOURCE = Path(__file__).resolve().parents[1]
CONTROL_SOURCES = ("src/proworksim/software_context_v041.py", "src/proworksim/software_context_replay_v041.py",
    "scripts/software_context_replay_v041.py", "src/proworksim/software_context_v034.py",
    "src/proworksim/software_context_v028.py", "src/proworksim/candidate_runtime_v015.py",
    "src/proworksim/training.py", "src/proworksim/harness_sdk.py")


def _events(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def archived_requests(episode):
    """Yield each original rejected request with strict recorded hash witnesses."""
    episode = Path(episode)
    events_path = episode / "experience.jsonl"
    events = _events(events_path)
    budget = read_json(episode / "team-budget.json")["model"]
    bank, templates, tool_names = {}, {}, {}

    def add(message, witness):
        checksum = digest(json_bytes(message))
        bank.setdefault(checksum, {"message": copy.deepcopy(message), "witness": witness})

    for path in sorted((episode / "raw-transport").glob("request-*/original-request.json")):
        request = read_json(path)
        observations = [json.loads(m["content"])["observation"] for m in request["messages"]
            if m.get("role") == "user" and isinstance(m.get("content"), str) and '"observation"' in m["content"]]
        if observations:
            templates.setdefault(observations[-1]["actor_id"], request)
        for index, message in enumerate(request["messages"]):
            add(message, {"path": str(path), "message_index": index})
    for event in events:
        payload = event["payload"]
        witness = {"path": str(events_path), "experience_sequence": event["sequence"], "kind": event["kind"]}
        if event["kind"] == "model_response":
            for choice in payload["response"]["choices"]:
                message = choice["message"]
                add(message, witness)
                for call in message.get("tool_calls", []):
                    tool_names[call["id"]] = call["function"]["name"]
        elif event["kind"] == "harness_sdk_event":
            sdk = payload["event"]
            if sdk.get("kind") == "MessageEvent":
                message = sdk["llm_message"]
                for block in message["content"]:
                    if block.get("type") != "text":
                        raise ValueError("Archived managed SDK message has non-text content")
                    add({"content": block["text"], "role": message["role"]}, witness)
            elif sdk.get("kind") == "ObservationEvent":
                blocks = sdk["observation"]["content"]
                if len(blocks) != 1 or blocks[0].get("type") != "text":
                    raise ValueError("Archived visible tool feedback has an unexpected SDK structure")
                add({"content": blocks[0]["text"], "role": "tool", "tool_call_id": sdk["tool_call_id"],
                     "name": sdk["tool_name"]}, witness)
        elif event["kind"] == "model_tool_result":
            original = payload["message"]
            add({"content": original["content"], "role": "tool", "tool_call_id": original["tool_call_id"],
                 "name": tool_names[original["tool_call_id"]]}, witness)

    for event in events:
        payload = event["payload"]
        if event["kind"] != "model_call" or payload.get("stage") != "started":
            continue
        record = budget["records"][payload["call_id"]]
        if record["status"] != "admission_rejected" or record.get("budget_kind") != "context_capacity":
            continue
        if record["attempt_started"] is not False:
            raise ValueError("Historical capacity rejection unexpectedly began generation")
        selection = payload["context_selection"]
        request = copy.deepcopy(templates[event["worker_id"]])
        witnesses, messages = [], []
        for index in selection["selected_indices"]:
            expected = selection["messages"][index]
            actual = bank.get(expected["sha256"])
            if actual is None:
                raise ValueError(f"Original SDK-selected message {index} has no exact archived witness")
            messages.append(copy.deepcopy(actual["message"]))
            witnesses.append({"original_message_index": index, "sha256": expected["sha256"], **actual["witness"]})
        request["messages"] = messages
        preparation = record["rejected_reservation"]["preparation"]
        if (digest(json_bytes(request)) != payload["request_sha256"]
                or digest(json_bytes(request)) != preparation["original_request_sha256"]
                or digest(json_bytes(messages)) != selection["selected_messages_sha256"]):
            raise ValueError("Recovered request does not equal the recorded rejected request")
        yield request, {"slot_id": episode.name, "member": event["worker_id"], "call_id": payload["call_id"],
            "original_request_hash_verified": True, "selected_message_hashes_verified": True,
            "recorded_preparation": copy.deepcopy(preparation), "model_call_experience_sequence": event["sequence"],
            "message_witnesses": witnesses, "sources": [reference(events_path), reference(episode / "team-budget.json")],
            "reconstruction_scope": "Original JSON envelope only, selected by recorded per-message and whole-request hashes; no model sampling, new messages, altered tool return or token-trace reconstruction"}


def _save_measurement(folder, measured):
    folder.mkdir(parents=True, exist_ok=False)
    files = {}
    for name in ("original", "old", "new"):
        value = measured[name]
        request = value.get("request", value.get("selected"))
        encoding = value["encoding"]
        artifacts = {name + "-request.json": json_bytes(request),
            name + "-native-prompt.txt": encoding["rendered_prompt"].encode(),
            name + "-input-ids.json": json_bytes(encoding["input_ids"]),
            name + "-encoding.json": json_bytes({k: v for k, v in encoding.items()
                if k not in {"rendered_prompt", "input_ids", "native_messages"}})}
        if "projection" in value:
            artifacts[name + "-projection.json"] = json_bytes(value["projection"])
        for filename, content in artifacts.items():
            path = folder / filename
            atomic_write(path, content)
            files[filename] = reference(path)
    return files


def replay(run_root, output):
    run_root, output = Path(run_root).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan = read_json(run_root / "plan.json")
    measurement = load_native_measurement(run_root / "plan.json")
    started, rows = time.time(), []
    for worker, assignments in plan["assignments"].items():
        for unit in assignments:
            episode = run_root / worker / "actual/episodes" / unit["slot_id"]
            for request, witness in archived_requests(episode):
                measured = measure_request(request, measurement)
                old, new = measured["old"], measured["new"]
                preparation = witness["recorded_preparation"]
                reproduction = {"selected_request": old["projection"]["selected_request_sha256"] == preparation["selected_request_sha256"],
                    "prompt_tokens": old["encoding"]["prompt_tokens"] == preparation["prompt_tokens"],
                    "rendered_prompt": old["encoding"]["rendered_prompt_sha256"] == preparation["rendered_prompt_sha256"],
                    "input_ids": old["encoding"]["input_ids_sha256"] == preparation["input_ids_sha256"],
                    "context_limit": old["encoding"]["context_limit"] == preparation["context_limit"],
                    "output_reservation": old["encoding"]["reserved_output_tokens"] == preparation["reserved_output_tokens"]}
                folder = output / witness["slot_id"] / witness["member"]
                files = _save_measurement(folder, measured)
                row = {**witness, "old_record_reproduced": all(reproduction.values()), "old_reproduction_checks": reproduction,
                    "old_selected_prompt_tokens": old["encoding"]["prompt_tokens"],
                    "new_selected_prompt_tokens": new["encoding"]["prompt_tokens"],
                    "new_headroom_tokens": new["encoding"]["headroom_tokens"], "new_fits": new["encoding"]["fits"],
                    "reserved_output_tokens": 2048, "context_limit": 16384,
                    "new_selected_request_sha256": new["projection"]["selected_request_sha256"],
                    "new_input_ids_sha256": new["encoding"]["input_ids_sha256"],
                    "deleted_fields": new["projection"]["deduplication"]["removed_values"], "artifacts": files}
                atomic_write(folder / "record.json", json_bytes(row))
                rows.append(row)
    value = {"version": VERSION, "kind": "P0-A-original-32-context-prefixes", "checked_prefixes": len(rows),
        "fit_prefixes": sum(row["new_fits"] for row in rows),
        "old_records_reproduced": sum(row["old_record_reproduced"] for row in rows),
        "passed": len(rows) == 32 and all(row["old_record_reproduced"] and row["new_fits"] for row in rows),
        "min_headroom_tokens": min(row["new_headroom_tokens"] for row in rows) if rows else None,
        "maximum_new_prompt_tokens": max(row["new_selected_prompt_tokens"] for row in rows) if rows else None,
        "source_files": {name: digest((SOURCE / name).read_bytes()) for name in CONTROL_SOURCES},
        "native_measurement_identity": measurement.identity, "rows": rows,
        "new_model_calls": 0, "new_backward_calls": 0, "model_weights_loaded": False,
        "started_at": started, "ended_at": time.time(),
        "scope": "Historical-prefix capacity under new presentation only. Does not claim the model would choose the same actions, reach these prefixes or succeed. Any non-fit blocks admission; no lossy fallback or output/context change."}
    atomic_write(output / "qualification.json", json_bytes(value))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", default=str(SOURCE / "runs/software-organization-v040"))
    parser.add_argument("--output", default=str(SOURCE / "runs/v041-controls/context-replay"))
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    result = replay(args.run_root, args.output)
    print(json.dumps({key: result[key] for key in ("passed", "checked_prefixes", "fit_prefixes", "old_records_reproduced", "min_headroom_tokens", "maximum_new_prompt_tokens")}))


if __name__ == "__main__":
    main()
