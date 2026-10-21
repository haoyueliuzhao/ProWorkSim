"""Six explicitly authorized short raw-model requests; no formal slot or retry."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new  # noqa: E402
from proworksim.software_benchmark_match_v054 import CONTRACT, TOOL_NAMES  # noqa: E402
from proworksim.software_benchmark_owner_ipc_v054 import OwnerClient  # noqa: E402
from proworksim.software_benchmark_supervision_v054 import process_identity  # noqa: E402

VERSION = "v054-mp-interleave-control-r1"
PERMIT_VERSION = "v054-resident-interleave-control-v1"
PROTOCOL = "mp-interleave-v1"


def plan():
    requests = {}
    for label, word in (("A1", "ALPHA"), ("A2", "BETA"), ("B1", "GAMMA")):
        names = sorted(TOOL_NAMES) if label == "A1" else [] if label == "A2" else ["terminal"]
        requests[label] = {
            "model": "raw-qwen3.5-9b-v054-match", "messages": [{"role": "user", "content":
                f"Synthetic isolation check {label}. Reply only with {word}. Do not call tools."}],
            "tools": [{"type": "function", "function": {"name": name,
                "description": "Synthetic preparation only", "parameters": {
                    "type": "object", "properties": {}}}} for name in names],
            "temperature": .7, "max_tokens": 2048, "stream": False}
    sessions, session_requests = [], {}
    for phase in ("baseline", "interleaved"):
        for name, arm, seed, labels in (("A", "MATCH", 202610210561, ["A1", "A2"]),
                                        ("B", "PROJECT", 202610210562, ["B1"])):
            slot = {"slot_id": f"synthetic-v054-interleave-{phase}-{name.lower()}-r1",
                    "instance_id": "synthetic-interleaving-control", "arm": arm, "seed": seed,
                    "maximum_generation_requests": len(labels)}
            sessions.append(slot)
            session_requests[slot["slot_id"]] = labels
    return {"sessions": sessions, "requests": requests, "session_requests": session_requests,
            "usage_ids": {"A1": "agent", "A2": "condenser", "B1": None},
            "execution_plan": [{"phase": "baseline", "order": ["A1", "A2", "B1"]},
                               {"phase": "interleaved", "order": ["A1", "B1", "A2"]}]}


def make_permit(*, resident_id, gpu_index, gpu_uuid, source_manifest):
    if (not re.fullmatch(r"[a-z0-9-]+", resident_id) or type(gpu_index) is not int
            or gpu_index not in range(8) or not re.fullmatch(
                r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", gpu_uuid)):
        raise ValueError("Bind the preparation to an exact deployment and GPU UUID")
    return {"version": PERMIT_VERSION, "preparation_generation_authorized": True,
            "formal_execution_authorized": False, "formal_slots_claimed": 0,
            "session_protocol": PROTOCOL, "maximum_sessions": 2,
            "maximum_generation_requests": 6, "maximum_prompt_tokens": 8192,
            "maximum_output_tokens": 2048, "maximum_total_tokens": 61440,
            "full_capacity_retested": False, "automatic_retry": False,
            "deployment": {"resident_id": resident_id, "gpu_index": gpu_index,
                           "gpu_uuid": gpu_uuid, "source_manifest": source_manifest}, **plan()}


def preparation_permit(*, resident_id, gpu_index, gpu_uuid, source_manifest):
    """One shared permit builder for the provisioner and this explicit control CLI."""
    return make_permit(resident_id=resident_id, gpu_index=gpu_index, gpu_uuid=gpu_uuid,
                       source_manifest=source_manifest)


def validate_permit(value):
    deployment = value["deployment"]
    checked(deployment["source_manifest"])
    if value != make_permit(**deployment):
        raise ValueError("Only the fixed six short requests and four synthetic sessions are authorized")


def read_ref(value):
    return json.loads(checked(value).read_text())


def comparisons(projections):
    return {label: {key: projections[("baseline", label)][key]
                   == projections[("interleaved", label)][key]
                   for key in ("output", "token_trace", "rng")}
            for label in ("A1", "A2", "B1")}


def serialized_turns(records):
    turns = [row["turn"] for row in records]
    return (all(turn["started_monotonic"] <= turn["finished_monotonic"] for turn in turns)
            and all(a["ordinal"] < b["ordinal"]
                    and a["finished_monotonic"] <= b["started_monotonic"]
                    for a, b in zip(turns, turns[1:])))


def projection(response, arm):
    body = response["body"]
    if arm == "MATCH":
        ledger = response["ledger"]
        if ledger.get("inflight") is not None or ledger.get("complete_actual_tokens") is None:
            raise ValueError("MATCH response has unsettled usage")
        native_ref = ledger["calls"][-1]["response"]
        native = read_ref(native_ref)
        trace = {"input_ids": native["input"]["input_ids"], "output_ids": native["output_ids"],
                 "behavior_logprobs": native["behavior_logprobs"]}
        raw = native["raw_generated_text"]
    else:
        if response.get("http_status") != 200:
            raise ValueError("PROJECT original response did not complete")
        native_ref = None
        trace = {key: body["token_trace"][key] for key in (
            "input_ids", "output_ids", "behavior_logprobs")}
        raw = body["raw_generated_text"]
    usage = body["usage"]
    if (len(trace["input_ids"]) != usage["prompt_tokens"]
            or len(trace["output_ids"]) != usage["completion_tokens"]
            or len(trace["behavior_logprobs"]) != usage["completion_tokens"]
            or not 0 < usage["prompt_tokens"] <= 8192
            or not 0 < usage["completion_tokens"] <= 2048
            or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
        raise ValueError("Full original trace and bounded synthetic accounting do not agree")
    choices = copy.deepcopy(body["choices"])
    for choice in choices:
        for index, tool_call in enumerate(choice["message"].get("tool_calls") or []):
            if "id" in tool_call:
                tool_call["id"] = "<transport-tool-call-id-" + str(index) + ">"
    return {"output": {"raw_generated_text": raw, "choices": choices,
                       "usage": usage, "native_finish_reason": body["native_finish_reason"]},
            "token_trace": trace, "native_response": native_ref}


def execute(declaration_path, authorization_path, output):
    from proworksim.software_benchmark_interleaved_owner_v054 import InterleavedOwnerClient
    declaration, permit = read_ref(reference(declaration_path)), read_ref(reference(authorization_path))
    validate_permit(permit)
    authorized = reference(authorization_path)
    spec = read_ref(declaration["source_spec"])
    identity = json.loads(Path(declaration["identity_path"]).read_text())
    deployment = permit["deployment"]
    binding = identity["resource_binding"]
    if (declaration["mode"] != "MATCH_PROJECT"
            or declaration.get("session_protocol") != PROTOCOL or declaration.get("maximum_sessions") != 2
            or spec.get("version") != "v054-match-resident-spec-v3"
            or spec.get("session_protocol") != PROTOCOL or spec.get("maximum_sessions") != 2
            or spec["preparation_permit"] != authorized
            or any(declaration[key] != deployment[key] for key in ("resident_id", "gpu_index", "gpu_uuid"))
            or binding["gpu_index"] != deployment["gpu_index"] or binding["gpu_uuid"] != deployment["gpu_uuid"]
            or identity.get("session_protocol") != PROTOCOL or identity.get("maximum_sessions") != 2
            or identity.get("actual_CalibrationActor") is not True
            or identity.get("original_generate_native") is not True
            or identity["contract"] != CONTRACT or identity.get("model_loads_at_initialization") != 1):
        raise ValueError("A separately bound real two-session resident is required")
    # Preserve the exact source identity that authorized this synthetic deployment.
    if spec.get("source_manifest") != deployment["source_manifest"]:
        raise ValueError("Control permit and deployment source revision differ")
    admin = OwnerClient(declaration["admin"]["socket_path"], identity)
    root = output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    host, active, completed, records, accounted = process_identity(os.getpid()), {}, [], [], []
    original_owner = identity["resident_owner_process"]
    if process_identity(original_owner["pid"]) != original_owner:
        raise ValueError("Resident process identity is no longer live")
    projections, begun_windows, attempted, pending = {}, [], 0, None
    summary = {"version": VERSION, "status": "running", "session_protocol": PROTOCOL,
        "maximum_sessions": 2, "maximum_generation_requests": 6, "formal_slots_claimed": 0,
        "formal_task_content_used": False, "full_capacity_retested": False,
        "declaration": reference(declaration_path), "authorization": authorized,
        "resident_identity": identity, "automatic_retry": False}

    def acquire(slot):
        folder = root / slot["slot_id"]
        folder.mkdir()
        value = admin.call("acquire", slot=slot, claim_id=uuid.uuid4().hex,
                           authorization=authorized, host_process=host, session_slot=0 if slot["arm"] == "MATCH" else 1)
        write_new(folder / "acquired.json", value)
        if not value.get("acquired") or value["resident_identity"] != identity:
            raise ValueError("Resident is busy or changed identity; no control replay")
        active[slot["slot_id"]] = {"slot": slot, "acquired": value, "folder": folder,
            "client": InterleavedOwnerClient(value["session_socket"], value["session_identity"]),
            "responses": []}
        begun = active[slot["slot_id"]]["client"].call("begin", slot=slot,
            claim_id=value["claim_id"], authorization=authorized, started=time.monotonic())
        write_new(folder / "begun.json", begun)
        begun_windows.append(begun["window_id"])
        return active[slot["slot_id"]]

    def finish(session):
        value, folder, slot = session["acquired"], session["folder"], session["slot"]
        finished = session["client"].call("finish", entries=[{"synthetic": True, "response": r}
                                                           for r in session["responses"]])
        write_new(folder / "finish.json", finished)
        if (finished["guard"].get("learning_unchanged") is not True
                or finished["guard"].get("rng_restored_exactly") is not True):
            raise ValueError("Original per-session learning/RNG closure failed")
        released = admin.call("release", claim_id=value["claim_id"], finish_receipt=finished["receipt"])
        release_ref = write_new(folder / "released.json", released)
        if released.get("state") != "released" or released.get("claim_id") != value["claim_id"]:
            raise ValueError("A different or unfinished session was released")
        completed.append({"slot": slot, "claim_id": value["claim_id"], "release": release_ref,
                          "responses": session["responses"]})
        del active[slot["slot_id"]]
        # A retired socket must not accept another session operation.
        try:
            OwnerClient(value["session_socket"], value["session_identity"], timeout=2).call(
                "match_count", request=permit["requests"]["A1"])
        except (OSError, RuntimeError):
            pass
        else:
            raise ValueError("Released socket still accepts requests")

    def generate(session, phase, label):
        nonlocal attempted, pending
        if attempted >= 6:
            raise ValueError("The independent synthetic generation cap was exhausted")
        slot, client, folder = session["slot"], session["client"], session["folder"]
        request = copy.deepcopy(permit["requests"][label])
        call = {"phase": phase, "label": label, "claim_id": session["acquired"]["claim_id"],
                "slot_id": slot["slot_id"], "request": request}
        write_new(folder / (label + "-request.json"), call)
        counted = None
        if slot["arm"] == "MATCH":
            counted = client.call("match_count", request=request)
            write_new(folder / (label + "-count.json"), counted)
        attempted += 1
        pending = {**call, "attempt": attempted, "actual_usage": None}
        write_new(root / (f"attempt-{attempted:02d}.json"), pending)
        response = (client.call("match_complete", request=request, usage_id=permit["usage_ids"][label])
                    if slot["arm"] == "MATCH" else client.call("project_complete", request=request))
        response_ref = write_new(folder / (label + "-response.json"), response)
        value = projection(response, slot["arm"])
        accounted.append({"response": response_ref, "usage": value["output"]["usage"]})
        pending.update(response=response_ref, verified_actual_usage=value["output"]["usage"])
        if counted is not None and counted["prompt_tokens"] != value["output"]["usage"]["prompt_tokens"]:
            raise ValueError("The exact MATCH counter differs from complete native usage")
        evidence = response["interleave_evidence"]
        turn = read_ref(evidence["turn"])
        if (evidence.get("shared_parked_rng_restored") is not True
                or evidence.get("cache_absent") is not True
                or evidence.get("generator_replaced") is not False
                or turn["claim_id"] != session["acquired"]["claim_id"]
                or evidence["owner_model_object_id"] != identity["resident_model_object_id"]):
            raise ValueError("Original model identity or shared parked RNG changed")
        value["rng"] = {key: evidence[key] for key in ("rng_before_sha256", "rng_after_sha256")}
        projections[(phase, label)] = value
        row = {"phase": phase, "label": label, "claim_id": session["acquired"]["claim_id"],
               "response": response_ref, "interleave_evidence": evidence,
               "usage": value["output"]["usage"], "turn": turn}
        records.append(row)
        session["responses"].append(response_ref)
        pending = None
        if sum(r["usage"]["total_tokens"] for r in records) > 61440:
            raise ValueError("Synthetic total token authorization exceeded")

    try:
        baseline_a, baseline_b, inter_a, inter_b = permit["sessions"]
        a = acquire(baseline_a)
        generate(a, "baseline", "A1")
        generate(a, "baseline", "A2")
        finish(a)
        b = acquire(baseline_b)
        generate(b, "baseline", "B1")
        finish(b)
        a, b = acquire(inter_a), acquire(inter_b)
        live = admin.call("status")
        claims = [a["acquired"]["claim_id"], b["acquired"]["claim_id"]]
        if set(live.get("active_claims", [])) != set(claims) or live.get("available_session_slots") != []:
            raise ValueError("The control did not establish two simultaneous independent sessions")
        write_new(root / "two-live-sessions.json", {"claims": claims, "resident_status": live})
        generate(a, "interleaved", "A1")
        generate(b, "interleaved", "B1")
        finish(b)  # B closure must not invalidate the still-open A window/RNG.
        generate(a, "interleaved", "A2")
        finish(a)
        comparison = comparisons(projections)
        write_new(root / "comparisons.json", comparison)
        serialized = serialized_turns(records)
        final_status = admin.call("status")
        if process_identity(original_owner["pid"]) != original_owner:
            raise ValueError("Control ended in a different resident process")
        summary.update(completed_sessions=len(completed), sessions=completed, calls=records,
            actual_model_generation_requests=len(records), unsettled_requests=0,
            known_actual_tokens=sum(r["usage"]["total_tokens"] for r in records),
            same_resident_PID_and_model=True, isolated_sessions=len(set(begun_windows)) == 4,
            per_request_FIFO_serialization=serialized,
            serialization_control_scope="six observed generation turns plus separate manager CPU contention control",
            all_three_outputs_equal=all(v["output"] for v in comparison.values()),
            all_three_token_traces_equal=all(v["token_trace"] for v in comparison.values()),
            all_three_rng_transitions_equal=all(v["rng"] for v in comparison.values()),
            weights_reloaded_between_sessions=False, model_loads=final_status["model_loads"],
            resident_status=final_status)
        passed = (len(records) == 6 and len(completed) == 4 and summary["isolated_sessions"]
                  and serialized and summary["all_three_outputs_equal"]
                  and summary["all_three_token_traces_equal"] and summary["all_three_rng_transitions_equal"]
                  and final_status["model_loads"] == 1 and final_status.get("poisoned") is None
                  and final_status.get("active_claims") == [] and final_status.get("inflight") is None)
        summary["status"] = "passed" if passed else "failed_control"
        if not passed:
            raise ValueError("Interleaved output/token/RNG identity or request serialization control failed")
    except BaseException as error:
        if summary["status"] != "failed_control":
            summary["status"] = "technical_unknown"
        summary.update(error={"type": type(error).__name__, "message": str(error)},
            completed_sessions=len(completed), completed_generation_requests=len(records),
            known_actual_tokens=sum(r["usage"]["total_tokens"] for r in accounted),
            accounted_responses=accounted, pending_request=pending,
            client_generation_operations_sent=attempted, unsettled_requests=attempted-len(accounted),
            unfinished_usage_not_zeroed=True, calls=records)
        # A failed admission cannot silently leave an apparently reusable service.
        try:
            summary["poison"] = OwnerClient(declaration["admin"]["socket_path"], identity, timeout=5).call(
                "poison_shared", reason="interleaving_control_failed")
        except BaseException as poison_error:
            summary["poison_error"] = str(poison_error)
        raise
    finally:
        write_new(root / "receipt.json", summary)
    return reference(root / "receipt.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--make-authorization", type=Path)
    parser.add_argument("--resident-id")
    parser.add_argument("--gpu-index", type=int)
    parser.add_argument("--gpu-uuid")
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--declaration", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.make_authorization:
        if any(value is None for value in (args.resident_id, args.gpu_index, args.gpu_uuid, args.source_manifest)):
            parser.error("Preparation needs resident ID, physical GPU UUID/index and sealed source manifest")
        result = write_new(args.make_authorization, make_permit(resident_id=args.resident_id,
            gpu_index=args.gpu_index, gpu_uuid=args.gpu_uuid, source_manifest=reference(args.source_manifest)))
    else:
        if args.declaration is None or args.authorization is None or args.output is None:
            parser.error("Explicit declaration, independent permit and fresh output are required")
        result = execute(args.declaration, args.authorization, args.output)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
