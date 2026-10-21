"""Exactly two separately authorized synthetic owner sessions, one MATCH and one PROJECT."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402
from proworksim.software_benchmark_match_v054 import TOOL_NAMES, CONTRACT  # noqa: E402
from proworksim.software_benchmark_owner_ipc_v054 import OwnerClient  # noqa: E402
from proworksim.software_benchmark_supervision_v054 import process_identity  # noqa: E402


def sessions():
    return [{"slot_id": "synthetic-v054-resident-" + arm.lower() + "-r1", "arm": arm,
             "seed": 202610210560 + index, "instance_id": "synthetic-resident-handoff"}
            for index, arm in enumerate(("MATCH", "PROJECT"))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--make-authorization", type=Path)
    parser.add_argument("--declaration", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.make_authorization:
        print(json.dumps(write_new(args.make_authorization, {
            "version": "v054-resident-session-smoke-v1", "preparation_generation_authorized": True,
            "formal_execution_authorized": False, "maximum_generation_requests": 2,
            "maximum_requests_per_session": 1, "sessions": sessions(),
            "formal_slots_claimed": 0, "full_capacity_retested": False})))
        return 0
    if args.declaration is None or args.authorization is None or args.output is None:
        parser.error("Explicit resident declaration, synthetic permit and fresh output are required")
    declaration = json.loads(args.declaration.read_text())
    permit = json.loads(args.authorization.read_text())
    if declaration["mode"] != "MATCH_PROJECT" or permit.get("sessions") != sessions():
        raise ValueError("Wrong persistent mode or independently fixed two-session preparation permit")
    identity = json.loads(Path(declaration["identity_path"]).read_text())
    if (identity.get("resident") is not True or identity.get("actual_CalibrationActor") is not True
            or identity.get("original_generate_native") is not True or identity["contract"] != CONTRACT):
        raise ValueError("Only the actual unchanged raw resident may run this control")
    admin = OwnerClient(declaration["admin"]["socket_path"], identity)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    host = process_identity(os.getpid())
    completed, active, result = [], None, {"status": "running", "formal_slots_claimed": 0,
        "formal_task_content_used": False, "capacity_retested": False, "maximum_generation_requests": 2,
        "declaration": reference(args.declaration), "authorization": reference(args.authorization),
        "resident_identity": identity, "automatic_retry": False}
    try:
        for slot in permit["sessions"]:
            folder = root / slot["arm"]
            folder.mkdir()
            active = admin.call("acquire", slot=slot, claim_id=uuid.uuid4().hex,
                                authorization=reference(args.authorization), host_process=host)
            write_new(folder / "acquired.json", active)
            if not active.get("acquired"):
                raise RuntimeError("Resident busy; no synthetic request has been replayed")
            if active["resident_identity"] != identity:
                raise ValueError("Resident process/model identity changed between sessions")
            client = OwnerClient(active["session_socket"], active["session_identity"])
            begun = client.call("begin", slot=slot, claim_id=active["claim_id"],
                                authorization=reference(args.authorization), started=time.monotonic())
            write_new(folder / "begun.json", begun)
            tools = [{"type": "function", "function": {"name": name, "description": "Synthetic preparation only",
                "parameters": {"type": "object", "properties": {}}}}
                for name in (sorted(TOOL_NAMES) if slot["arm"] == "MATCH" else ["terminal"])]
            request = {"model": "raw-qwen3.5-9b-v054-match", "messages": [{"role": "user",
                "content": "Synthetic runtime check only. Reply with the single word OK. Do not call tools."}],
                "tools": tools, "temperature": .7, "max_tokens": 2048, "stream": False}
            write_new(folder / "request.json", request)
            if slot["arm"] == "MATCH":
                counted = client.call("match_count", request=request)
                write_new(folder / "count.json", counted)
                response = client.call("match_complete", request=request, usage_id="agent")
                body = response["body"]
                if response["ledger"]["attempts"] != 1 or response["ledger"]["inflight"] is not None:
                    raise ValueError("MATCH session did not use one new complete ledger attempt")
                if counted["prompt_tokens"] != body["usage"]["prompt_tokens"]:
                    raise ValueError("MATCH actual input differs from the same owner tokenizer")
            else:
                response = client.call("project_complete", request=request)
                if response["http_status"] != 200:
                    raise ValueError("Original PROJECT numerical request did not complete")
                body = response["body"]
                if (body["online_window_id"] != begun["window_id"]
                        or len(body["token_trace"]["input_ids"]) != body["usage"]["prompt_tokens"]
                        or len(body["token_trace"]["output_ids"]) != body["usage"]["completion_tokens"]):
                    raise ValueError("PROJECT fresh window or complete native token accounting differs")
            response_ref = write_new(folder / "response.json", response)
            usage = body["usage"]
            if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
                raise ValueError("Incomplete synthetic accounting")
            finished = client.call("finish", entries=[{"synthetic": True, "response": response_ref}])
            write_new(folder / "finish.json", finished)
            released = admin.call("release", claim_id=active["claim_id"], finish_receipt=finished["receipt"])
            write_new(folder / "released.json", released)
            quiet = released["quiescence"]
            if (not quiet["owner_idle"] or quiet["model_busy"] or not quiet["learning_unchanged"]
                    or not quiet["rng_restored_exactly"] or quiet["weights_reloaded"]
                    or not quiet["original_per_request_model_cache_absent"]
                    or quiet["allocator_reserved_bytes"] <= 0
                    or not quiet.get("per_session_resource_evidence")):
                raise ValueError("Resident was not independently closed and restored")
            completed.append({"slot": slot, "window_id": begun["window_id"], "usage": usage,
                              "response": response_ref, "release": released["receipt"]})
            active = None
        result.update(status="passed", sessions=completed,
            actual_model_generation_requests=2, known_actual_tokens=sum(row["usage"]["total_tokens"] for row in completed),
            unsettled_requests=0, resident_status=admin.call("status"), same_resident_PID_and_model=True,
            distinct_seeds_and_windows=True, weights_reloaded_between_sessions=False)
    except BaseException as error:
        result.update(status="technical_unknown", error={"type": type(error).__name__, "message": str(error)},
                      completed_sessions=completed, unfinished_usage_not_zeroed=True)
        if active and active.get("acquired"):
            try:
                result["poison"] = admin.call("poison", claim_id=active["claim_id"], reason="synthetic_control_failed")
            except BaseException as poison_error:
                result["poison_error"] = str(poison_error)
        raise
    finally:
        write_new(root / "receipt.json", result)
    print(json.dumps(reference(root / "receipt.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
