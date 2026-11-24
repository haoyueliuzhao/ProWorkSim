"""Separate the natural task outcome from coverage of the NEED-specific rule."""

import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_disposition_v232_5 as previous
from run_evidence_followup_v232_6 import PLAN, RUN, CASE, ARM
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_evidence_v232_6 import VERIFICATION_TOOLS
from proworksim.software_graph_controller_v228 import ControlledWorld, NaturalWorld
from proworksim.tool_outcomes import ToolRejection
from proworksim.software_context_builder_v230 import object_text
from proworksim.storage import read_json, json_bytes, atomic_write


def audit_search(folder, world, chain, duty):
    """Probe the real citation guard without executing a message or modifying a world."""
    owner = duty["owner"]
    evidence = next(
        e
        for e in world["software_events"]
        if e["kind"] == "repository_search"
        and e["actor_id"] == owner
        and any(
            e["sequence"] in row["world_events"]
            for row in chain
            if row["action"] == "search_repository" and row["accepted"]
        )
    )
    sequence = evidence["sequence"]
    (project,) = world["projects"]
    protocol = world["projects"][project]["software"]["protocol_v216"]
    assert sequence > protocol["graph_control"]["versions"][-1]["after_event"]
    probe = object.__new__(ControlledWorld)
    probe.state = world
    probe.protocol = lambda: protocol
    with patch.object(
        NaturalWorld, "_tool_project_action", side_effect=AssertionError("passed guard")
    ):
        try:
            probe._tool_project_action(
                owner,
                project,
                "send_message",
                {
                    "recipient": duty["recipient"],
                    "task_id": "work_root",
                    "body": f"DIAG {sequence} The repository search located the test definition.",
                },
            )
        except ToolRejection as exc:
            rejection = exc.rejection["code"]
        else:
            raise ValueError("Probe did not reach the citation guard")
    assert rejection == "graph_evidence_required"
    block = next(r for r in chain if r.get("header", [])[:1] == ["BLOCK"])
    for f in (folder / "api").glob("*/request.json"):
        response = read_json(f.with_name("response.json"))
        if not any(
            c["id"] == block["tool_call_id"]
            for c in response["choices"][0]["message"].get("tool_calls") or []
        ):
            continue
        q = read_json(f)["payload"]
        assert q["member_id"] == owner
        for m in reversed(q["wire"]["messages"]):
            data = object_text(m.get("content")) or {}
            if "pending_diagnosis" in data:
                shown = data["pending_diagnosis"]["own_eligible_event_sequences"]
                return dict(
                    search_sequence=sequence,
                    actual_kind=evidence["kind"],
                    returned_matches=len(evidence["matches"]),
                    block_request_eligible=shown,
                    probe_citation_rejection=rejection,
                    probe_provider_calls=0,
                )
    raise ValueError("Missing pending diagnosis on BLOCK request")


def main():
    clone_function(
        previous.main,
        {**previous.main.__globals__, "PLAN": PLAN, "RUN": RUN, "CASE": CASE, "ARM": ARM},
    )()
    path = PLAN / "results.json"
    result = read_json(path)
    folder = RUN / CASE / ARM
    base = read_json(previous.PLAN / "results.json")
    result["v232_5_baseline"] = {
        k: base[k]
        for k in (
            "effective_duties",
            "termination",
            "physical",
            "official",
            "anomaly_endpoint",
            "rejections",
        )
    }
    duty = result["effective_duties"]["work_root"]
    need = duty.get("evidence_request")
    read = duty.get("need_reply_read")
    chain = []
    read_op = None
    verified = []
    disposition_closed = False
    world = read_json(folder / "prepared/world/control/state.json")
    events = {e["sequence"]: e for e in world["software_events"]}
    for line in (folder / "runtime/experience.jsonl").open():
        e = json.loads(line)
        if e["kind"] != "tool_call":
            continue
        d = e["payload"]
        actor = e.get("worker_id")
        tool = d["action"]
        rsp = d["response"]
        val = rsp.get("result") or {}
        op = d["opportunity_id"]
        ordinal = int(op.rsplit("-", 1)[1])
        args = d["arguments"]
        sequences = [
            v["sequence"]
            for v in events.values()
            if v["actor_id"] == actor and v.get("operation_id") == rsp.get("command_id")
        ]
        row = {
            "actor": actor,
            "action": tool,
            "opportunity": ordinal,
            "accepted": rsp["ok"],
            "tool_call_id": d["model_tool_call_id"],
            "world_events": sequences,
        }
        if tool == "send_message":
            text = args.get("body", "")
            row.update(
                header=text.split()[:2],
                message_sequence=val.get("message_sequence"),
                recipient=args.get("recipient"),
            )
        if not rsp["ok"]:
            row["reason"] = ((rsp.get("error") or {}).get("rejection") or {}).get("code")
        if (
            read is not None
            and actor == duty["owner"]
            and tool == "read_work_event"
            and args.get("sequence") == read
            and rsp["ok"]
            and val.get("diagnosis_followup")
        ):
            if (
                not need
                or events[read]["actor_id"] != duty["recipient"]
                or events[read]["recipient"] != actor
                or events[read]["task_id"] != "work_root"
                or read <= need["sequence"]
            ):
                raise ValueError("Reply identity mismatch")
            read_op = ordinal
        if (
            read_op is not None
            and actor == duty["owner"]
            and rsp["ok"]
            and row.get("header", [])[:1] in (["DIAG"], ["BLOCK"])
        ):
            disposition_closed = True
        elif (
            not disposition_closed
            and read_op is not None
            and ordinal > read_op
            and actor == duty["owner"]
            and tool in VERIFICATION_TOOLS
            and rsp["ok"]
        ):
            verified.extend(
                s
                for s in sequences
                if events[s]["kind"] in ("read", "search", "repository_search", "test")
                or "review" in events[s]["kind"]
            )
        chain.append(row)
    if read is not None and read_op is None:
        raise ValueError("State claims read without matching receipt")
    result["need_path"] = {
        "need_sequence": need["sequence"] if need else None,
        "qualifying_reply_read_sequence": read,
        "qualifying_read_opportunity": read_op,
        "verified_after_reply": bool(verified) if read_op is not None else None,
        "independent_events": verified,
        "accepted_diagnosis_cites_followup": (
            duty.get("status") == "handed_off" and duty.get("evidence") in verified
        )
        if read_op is not None
        else None,
    }
    result["native_action_chain"] = chain
    result["posthoc_search_audit"] = audit_search(folder, world, chain, duty)
    atomic_write(path, json_bytes(result))


if __name__ == "__main__":
    main()
