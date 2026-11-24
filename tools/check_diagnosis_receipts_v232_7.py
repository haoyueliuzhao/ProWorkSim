"""Replay the archived search identity and exercise both fixed paths through the native SDK."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_disposition_v232_5 as fixture
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_evidence_v232_6 import EvidenceFollowupExecution, ReplyAwareWorld
from proworksim.software_context_builder_v230 import object_text
from proworksim.storage import atomic_write, json_bytes, read_json
from proworksim.tool_outcomes import ToolRejection

ROOT = fixture.ROOT
OUT = ROOT / "artifacts/software-benchmark-v232-7/diagnosis-receipts-r1"


class SearchProbe(EvidenceFollowupExecution):
    def __init__(self, backend, *args, **kwargs):
        def respond(route, payload):
            out = backend(route, payload)
            if route != "/chat/completions" or payload["member_id"] != "member_002":
                return out
            world = self.runtime.prepared.world
            duty = world.protocol().get("graph_control", {}).get("duties", {}).get("work_root", {})
            if duty.get("status") != "pending" or not duty.get("evidence_request"):
                return out
            call = out["choices"][0]["message"]["tool_calls"][0]
            if duty["awaiting_evidence"]:
                tool, arguments = (
                    "search_repository",
                    {"text": "value = 1", "path_prefix": "sample.py"},
                )
            else:
                event = next(
                    e
                    for e in reversed(world.state["software_events"])
                    if e["kind"] == "repository_search"
                )
                sequence = event["sequence"]
                assert event["actor_id"] == "member_002" and event["matches"]
                messages = payload["wire"]["messages"]
                snapshots = [
                    d["pending_diagnosis"]
                    for m in messages
                    if (d := object_text(m.get("content"))) and "pending_diagnosis" in d
                ]
                assert sequence in snapshots[-1]["own_eligible_event_sequences"]
                tool = "send_message"
                arguments = {
                    "recipient": "member_001",
                    "task_id": "work_root",
                    "body": f"DIAG {sequence} The search found the assignment in sample.py.",
                }
            call["function"] = {"name": tool, "arguments": json.dumps(arguments)}
            return out

        super().__init__(respond, *args, **kwargs)


class BlockProbe(EvidenceFollowupExecution):
    def __init__(self, backend, *args, **kwargs):
        def respond(route, payload):
            out = backend(route, payload)
            if route != "/chat/completions":
                return out
            fn = out["choices"][0]["message"]["tool_calls"][0]["function"]
            if not json.loads(fn["arguments"]).get("body", "").startswith("BLOCK "):
                return out
            w = self.runtime.prepared.world
            prior = w.runtime_availability

            def no_capacity():
                rows = prior()
                rows["member_001"] = {
                    **rows["member_001"],
                    "can_receive_work": False,
                    "remaining_decisions": 0,
                }
                return rows

            w.runtime_availability = no_capacity
            # A normal message still requires capacity. A blocker still requires a legal live peer.
            for recipient, task, body in [
                ("member_001", "work_root", "Please run another test"),
                ("member_001", "work_root", "NEED another test"),
                ("member_001", "other", "BLOCK budget insufficient"),
                ("member_002", "work_root", "BLOCK budget insufficient"),
                ("member_006", "work_root", "BLOCK budget insufficient"),
            ]:
                try:
                    w._check_message_recipient("member_002", recipient, task, body)
                except (ValueError, ToolRejection):
                    continue
                raise AssertionError((recipient, task, body))
            return out

        super().__init__(respond, *args, **kwargs)


def sdk(folder, mode, execution):
    folder.mkdir()
    os.environ["OH_PERSISTENCE_DIR"] = str(folder / "sdk-settings")
    result = clone_function(
        fixture.exercise, {**fixture.exercise.__globals__, "DispositionExecution": execution}
    )(folder, mode)
    calls = [
        json.loads(l)["payload"]
        for l in (folder / "runtime/experience.jsonl").read_text().splitlines()
        if json.loads(l)["kind"] == "tool_call"
    ]
    messages = [
        (c["arguments"]["body"].split()[0], c["response"]["result"]["message_sequence"])
        for c in calls
        if c["action"] == "send_message" and c["response"]["ok"]
    ]
    if mode == "need":
        (search,) = [
            c["response"]["result"]
            for c in calls
            if c["action"] == "search_repository" and c["response"]["ok"]
        ]
        (diag,) = [
            c["arguments"]["body"]
            for c in calls
            if c["action"] == "send_message"
            and c["arguments"]["body"].startswith("DIAG ")
            and c["response"]["ok"]
        ]
        assert (
            int(diag.split()[1]) == search["event_sequence"]
            and result["recipient"]["choice"] == "ADOPT"
        )
        return {
            "search_receipt": search["event_sequence"],
            "cited_sequence": int(diag.split()[1]),
            "shown_in_model_input": True,
            "accepted_messages": messages,
        }
    assert len(messages) == 1 and messages[0][0] == "BLOCK" and result["recipient"] is None
    return {
        "can_receive_new_work": False,
        "blocked_controls": 5,
        "accepted_messages": messages,
        "recipient_decision": None,
    }


def archived():
    folder = ROOT / "runs/software-benchmark-v232-6/need-followup-r1/Sphinx-9591/NEEDCHECK"
    w = object.__new__(ReplyAwareWorld)
    w.state = read_json(folder / "prepared/world/control/state.json")
    old = read_json(ROOT / "artifacts/software-benchmark-v232-6/need-followup-r1/results.json")[
        "posthoc_search_audit"
    ]
    seq = old["search_sequence"]
    rows = w.diagnosis_evidence("member_002")
    assert seq in rows and seq not in w.diagnosis_evidence("member_001") and 69 not in rows
    # Run the archived decision against the real native controller in memory.
    w.decision_task = "work_root"
    w.sender_due = True
    w._operation_context = {"operation_id": "offline-replay:Sphinx-9591:DIAG70"}
    w.full_exposures = {}
    w.scheduled_member = "member_002"
    w.fixed_candidates_closed = False
    duty = w.protocol()["graph_control"]["duties"]["work_root"]
    for cited in (69, seq):
        try:
            receipt = w._tool_project_action(
                "member_002",
                "SOFTWARE27",
                "send_message",
                {
                    "recipient": "member_001",
                    "task_id": "work_root",
                    "body": f"DIAG {cited} The test definition was located at line 1839.",
                },
            )
        except ToolRejection as exc:
            assert cited == 69 and exc.rejection["code"] == "graph_evidence_required"
        else:
            assert (
                cited == seq
                and duty["evidence"] == seq
                and receipt["message_sequence"] == duty["message_sequence"]
            )
    assert duty["status"] == "handed_off"
    return {
        "case": "Sphinx-9591",
        "sequence": seq,
        "old_guard": old["probe_citation_rejection"],
        "new_guard": "accepted",
        "peer_sequence_rejected": 69,
        "handoff_sequence_in_replay": duty["message_sequence"],
    }


def main():
    os.environ.update(
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        OPENHANDS_SUPPRESS_BANNER="1",
        HF_HUB_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
    )
    with tempfile.TemporaryDirectory(prefix="pws-diagnosis-receipts-") as tmp:
        folder = Path(tmp)
        results = {
            "archived": archived(),
            "sdk_search": sdk(folder / "search", "need", SearchProbe),
            "sdk_block": sdk(folder / "block", "block", BlockProbe),
            "provider_calls": 0,
        }
        OUT.mkdir(parents=True, exist_ok=True)
        atomic_write(OUT / "verification.json", json_bytes(results))
        print(json.dumps(results))


if __name__ == "__main__":
    main()
