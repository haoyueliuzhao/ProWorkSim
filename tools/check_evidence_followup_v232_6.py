"""Use actual SDK/world actions to exercise NEED -> addressed reply -> source check -> DIAG."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_disposition_v232_5 as base
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_evidence_v232_6 import EvidenceFollowupExecution
from proworksim.storage import atomic_write, json_bytes


class Probe(EvidenceFollowupExecution):
    def __init__(self, backend, *args, **kwargs):
        def scripted(route, payload):
            out = backend(route, payload)
            if route != "/chat/completions":
                return out
            w = self.runtime.prepared.world
            d = w.protocol().get("graph_control", {}).get("duties", {}).get("work_root", {})
            if not d.get("evidence_request") or d["status"] != "pending":
                return out
            actor = payload["member_id"]
            records = w.state["software_events"]
            reply = next(
                (
                    e
                    for e in records
                    if e["kind"] == "work_message"
                    and e["actor_id"] == d["recipient"]
                    and e.get("recipient") == d["owner"]
                    and e["sequence"] > d["evidence_request"]["sequence"]
                ),
                None,
            )
            if actor == d["recipient"] and not reply:
                tool, arguments = (
                    "send_message",
                    {
                        "recipient": d["owner"],
                        "task_id": "work_root",
                        "body": "The public file to inspect is sample.py.",
                    },
                )
            elif (
                actor == d["owner"] and d.get("awaiting_evidence") and not d.get("need_reply_read")
            ):
                if reply:
                    tool, arguments = "read_work_event", {"sequence": reply["sequence"]}
                else:
                    tool, arguments = (
                        "staff_wait",
                        {"reason": "Waiting for the addressed evidence reply"},
                    )
            else:
                return out
            out["choices"][0]["message"]["tool_calls"][0]["function"] = {
                "name": tool,
                "arguments": json.dumps(arguments),
            }
            return out

        super().__init__(scripted, *args, **kwargs)


def main():
    os.environ.update(
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        OPENHANDS_SUPPRESS_BANNER="1",
        HF_HUB_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
    )
    with tempfile.TemporaryDirectory(prefix="pws-v232-6") as tmp:
        folder = Path(tmp)
        os.environ["OH_PERSISTENCE_DIR"] = str(folder / "sdk-settings")
        row = clone_function(
            base.exercise, {**base.exercise.__globals__, "DispositionExecution": Probe}
        )(folder, "need")
        sequence = []
        with (folder / "runtime/experience.jsonl").open() as f:
            for line in f:
                e = json.loads(line)
                if (
                    e["kind"] == "tool_call"
                    and e.get("worker_id") == "member_002"
                    and e["payload"]["response"]["ok"]
                ):
                    d = e["payload"]
                    sequence.append(
                        d["action"]
                        if d["action"] != "send_message"
                        else d["arguments"]["body"].split()[0]
                    )
        assert sequence[-4:] == ["NEED", "read_work_event", "read_file", "DIAG"], sequence
        assert row["recipient"]["choice"] == "ADOPT"
        row.update(accepted_sender_sequence=sequence)
        atomic_write(
            base.ROOT / "artifacts/software-benchmark-v232-6/need-followup-r1/sdk-control.json",
            json_bytes(row),
        )


if __name__ == "__main__":
    main()
