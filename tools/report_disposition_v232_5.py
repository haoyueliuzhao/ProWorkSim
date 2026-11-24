"""Reconcile a declared handoff disposition with the world event and the worker input."""

from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_inbox_preview_v232_4 as previous
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_disposition_v232_5 import has_full
from proworksim.storage import read_json, json_bytes, atomic_write
from run_disposition_v232_5 import PLAN, RUN, CASE, ARM
import json


def main():
    clone_function(
        previous.main,
        {**previous.main.__globals__, "PLAN": PLAN, "RUN": RUN, "CASE": CASE, "ARM": ARM},
    )()
    path = PLAN / "results.json"
    r = read_json(path)
    folder = RUN / CASE / ARM
    base = read_json(previous.PLAN / "results.json")
    r["v232_4_reference"] = {
        k: base[k]
        for k in (
            "physical",
            "effective_duties",
            "official",
            "termination",
            "qualifying_long_handoffs",
        )
    }
    with sqlite3.connect(
        "file:" + str(folder / "telemetry/events.sqlite") + "?mode=ro", uri=True
    ) as db:
        r["disposition_opportunities"] = [
            {k: d.get(k) for k in ("kind", "native_id", "agent_id", "request_id", "details")}
            for (raw,) in db.execute("select body from events order by rowid")
            if (d := json.loads(raw))["kind"]
            in (
                "disposition_credits_reserved",
                "disposition_unavailable",
                "disposition_released_blocked",
            )
            or (
                d["kind"] == "grant-dispatched"
                and d["native_id"][-1]
                in ("sender_disposition", "record_disposition", "receive_handoff")
            )
        ]
    rejection = []
    events = []
    for line in (folder / "runtime/experience.jsonl").open():
        e = json.loads(line)
        if e["kind"] == "tool_call":
            x = e["payload"]
            resp = x["response"]
            b = resp.get("result") or {}
            events.append(
                {
                    "op": x["opportunity_id"],
                    "actor": e.get("worker_id"),
                    "tool": x["action"],
                    "ok": resp["ok"],
                    "sequence": b.get("message_sequence"),
                    "source_reference": b.get("source_reference"),
                    "patch_id": b.get("patch_id"),
                    "counts": b.get("counts"),
                }
            )
            if not resp["ok"]:
                rejection.append(
                    {
                        "op": x["opportunity_id"],
                        "tool": x["action"],
                        "code": ((resp.get("error") or {}).get("rejection") or {}).get("code"),
                    }
                )
    r["executed_actions"] = events
    r["rejections"] = rejection
    w = read_json(folder / "prepared/world/control/state.json")
    by_seq = {e["sequence"]: e for e in w["software_events"]}
    duty = r["effective_duties"].get("work_root", {})
    for d in duty.get("sender_decisions", []):
        e = by_seq[d["sequence"]]
        if (
            e["actor_id"] != duty["owner"]
            or e["recipient"] != duty["recipient"]
            or e["body"] != d["body"]
        ):
            raise ValueError("Sender decision differs from world receipt")
    d = duty.get("recipient_disposition")
    if d:
        e = by_seq[d["response_sequence"]]
        if (
            e["actor_id"] != duty["recipient"]
            or e["recipient"] != duty["owner"]
            or not e["body"].startswith(f"{d['choice']} {d['message_sequence']} ")
        ):
            raise ValueError("Missing real addressed decision")
        if d["choice"] == "SKIP":
            cited = by_seq[d["own_evidence"]]
            if (
                cited["actor_id"] != duty["recipient"]
                or cited["source_reference"] != d["source_reference"]
            ):
                raise ValueError("Invalid SKIP citation")
        else:
            requests = [read_json(p)["payload"] for p in (folder / "api").glob("*/request.json")]
            (exposed,) = [q for q in requests if q["request_id"] == d["full_exposure_request"]]
            if exposed["member_id"] != duty["recipient"] or not has_full(
                exposed["wire"], by_seq[d["message_sequence"]]
            ):
                raise ValueError("No prior full exposure")
    r["processed_world_receipt"] = bool(d)
    r["unconditional_primary_success"] = bool(d and duty.get("status") == "handed_off")
    atomic_write(path, json_bytes(r))


if __name__ == "__main__":
    main()
