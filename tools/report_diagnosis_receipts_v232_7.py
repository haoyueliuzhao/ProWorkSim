"""Join search receipts to world events, physical inputs, and the final registered duty."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_disposition_v232_5 as prior
from run_diagnosis_receipts_v232_7 import PLAN, RUN, CASE, ARM
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_context_builder_v230 import object_text
from proworksim.storage import atomic_write, read_json, json_bytes


def main():
    clone_function(
        prior.main, {**prior.main.__globals__, "PLAN": PLAN, "RUN": RUN, "CASE": CASE, "ARM": ARM}
    )()
    path = PLAN / "results.json"
    result = read_json(path)
    folder = RUN / CASE / ARM
    world = read_json(folder / "prepared/world/control/state.json")
    events = {e["sequence"]: e for e in world["software_events"]}
    duty = result["effective_duties"]["work_root"]
    searches = []
    owner = duty["owner"]
    requests = [read_json(p)["payload"] for p in (folder / "api").glob("*/request.json")]
    block_intents = [m for m in result["message_attempts"] if m["header"][:1] == ["BLOCK"]]
    for line in (folder / "runtime/experience.jsonl").open():
        event = json.loads(line)
        if event["kind"] != "tool_call" or event.get("worker_id") != owner:
            continue
        action = event["payload"]
        reply = action["response"]
        if action["action"] != "search_repository" or not reply["ok"]:
            continue
        seq = reply["result"]["event_sequence"]
        assert (
            events[seq]["actor_id"] == owner
            and events[seq]["kind"] == "repository_search"
            and events[seq]["operation_id"] == reply["command_id"]
        )
        tool_receipts = []
        listings = []
        for q in requests:
            if q["member_id"] != owner or q["usage_id"] != "agent":
                continue
            for m in q["wire"]["messages"]:
                obj = object_text(m.get("content")) or {}
                if (
                    m.get("role") == "tool"
                    and m.get("tool_call_id") == action["model_tool_call_id"]
                    and (obj.get("result") or {}).get("event_sequence") == seq
                ):
                    tool_receipts.append(q["request_id"])
                if seq in obj.get("pending_diagnosis", {}).get("own_eligible_event_sequences", []):
                    listings.append(q["request_id"])
        searches.append(
            dict(
                sequence=seq,
                world_matches=len(events[seq]["matches"]),
                tool_receipt_requests=sorted(set(tool_receipts)),
                eligible_list_requests=sorted(set(listings)),
                cited_in_accepted_diagnosis=duty.get("evidence") == seq,
            )
        )
    result["repository_search_handoffs"] = searches
    result["block_intents"] = [
        {
            k: m.get(k)
            for k in (
                "opportunity",
                "actor",
                "world_accepted",
                "message_sequence",
                "later_recipient_worker_requests",
                "recipient_saw_body_at",
            )
        }
        for m in block_intents
    ]
    code = read_json(folder.with_name(ARM + "-code") / "receipt.json")
    if code["status"] == "official_report":
        instance, report = code["official_result"]
        observed = report[instance]
        result["official_code_tests"] = {
            "patch_applied": observed["patch_successfully_applied"],
            "infrastructure_failure": observed["infra_failure"],
            "target_failures": observed["tests_status"]["FAIL_TO_PASS"]["failure"],
            "regressions_passed": len(observed["tests_status"]["PASS_TO_PASS"]["success"]),
            "regressions_failed": observed["tests_status"]["PASS_TO_PASS"]["failure"],
        }
    atomic_write(path, json_bytes(result))


if __name__ == "__main__":
    main()
