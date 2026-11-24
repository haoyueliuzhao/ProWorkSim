"""Summarize live v231 receipts, without equating unknowns with failure or zeros."""

import json
from collections import Counter
import sqlite3

from proworksim.software_context_panel_v231 import DESIGN, ROOT, RUN
from proworksim.software_context_builder_v230 import recover_observations, object_text, identity
from proworksim.storage import atomic_write, json_bytes, read_json


def evidence(folder):
    counts = Counter()
    for f in sorted((folder / "telemetry/worker").glob("*/manifest.json")):
        m = read_json(f)
        original, shown = [read_json(f.with_name(s + ".json")) for s in ("original", "shown")]
        if m["shown_wire"] != identity(shown) or m["original_wire"] != identity(original):
            raise ValueError("Wire identity mismatch")
        if len(original["messages"]) != len(shown["messages"]):
            raise ValueError("SDK positions changed")
        old, new = recover_observations(original), recover_observations(shown)
        counts["snapshots"] += len(old)
        counts["snapshots_recovered"] += sum(new.get(k) == v for k, v in old.items())
        for a, b in zip(original["messages"], shown["messages"]):
            text = a.get("content") or ""
            if a["role"] == "user" and text.startswith("Work observation: "):
                counts["evidence"] += 1
                counts["retained"] += b["content"] == text
            if a["role"] == "tool":
                ao = object_text(text) or {}
                bo = object_text(b.get("content")) or {}
                if ao.get("ok") is False:
                    counts["evidence"] += 1
                    counts["retained"] += bo == ao
                result = ao.get("result")
                if (
                    isinstance(result, dict)
                    and result.get("report_id")
                    and result.get("source_reference")
                ):
                    counts["evidence"] += 1
                    br = bo.get("result") or {}
                    counts["retained"] += all(
                        br.get(k) == result.get(k)
                        for k in (
                            "report_id",
                            "source_reference",
                            "body_sha256",
                            "passed",
                            "diagnostic_summary",
                        )
                    )
        counts["indexed_pages"] += len(m["tool_pages"])
        counts["message_refs"] += len(m["message_refs"])
    return counts


def report():
    a = read_json(RUN / "authority.json")
    rows = []
    with sqlite3.connect("file:" + a["ledger"] + "?mode=ro", uri=True) as db:
        for state in read_json(DESIGN)["states"]:
            for arm in ("T0", "T1"):
                slot = "v231:" + state["case"] + ":" + arm
                folder = RUN / state["case"] / arm
                rc = folder / "result.json"
                result = read_json(rc) if rc.exists() else {}
                row = {
                    "case": state["case"],
                    "arm": arm,
                    "status": result.get("status", "no_result"),
                    "error": result.get("error"),
                    "logical_tokens": result.get("logical_tokens"),
                    "remaining_at_start": state["remaining_per_branch"],
                    "code": None,
                    "delivery": None,
                }
                if "finished" in result:
                    row["wall_seconds"] = result["finished"] - result["started"]
                totals = Counter()
                for rid, status, amount, raw in db.execute(
                    "select id,status,cost,body from requests where slot=?", (slot,)
                ):
                    totals[status] += 1
                    if status != "settled":
                        continue

                    data = json.loads(raw)
                    totals.update(
                        {
                            k: data[k]
                            for k in [
                                "input_tokens",
                                "output_tokens",
                                "cache_hit_tokens",
                                "cache_miss_tokens",
                                "total_tokens",
                            ]
                        }
                    )
                    totals["nanoyuan"] += amount
                row["physical"] = dict(totals)
                if result.get("status") == "closed":
                    row["usage_reconciled"] = (
                        row["logical_tokens"]
                        == totals["total_tokens"]
                        + state["shared_prefix_usage"]
                        + state["shared_controller_usage"]
                    )
                    row["trace_complete"] = (
                        not result.get("observer_errors")
                        and not (folder / "telemetry/events.incomplete.json").exists()
                    )
                    row["evidence"] = dict(evidence(folder))
                    native = folder / "runtime/experience.jsonl"
                    counts = Counter()
                    with native.open() as f:
                        for line in f:

                            event = json.loads(line)
                            if event["kind"] == "tool_call":
                                tool = event["payload"]
                                response = tool["response"]
                                counts["world_actions"] += 1
                                counts["public_test_actions"] += tool["action"] in (
                                    "run_tests",
                                    "run_patch_review_tests",
                                )
                                counts["reread_actions"] += tool["action"] == "read_test_result"
                                if not response["ok"]:
                                    counts["rejections"] += 1
                                    code = (
                                        (response.get("error") or {}).get("rejection") or {}
                                    ).get("code", "")
                                    counts["graph_rejections"] += code.startswith("graph_")
                    row["tool_receipts"] = dict(counts)
                for kind in ("code", "delivery"):
                    score = folder.with_name(arm + "-" + kind) / "receipt.json"
                    if score.exists():
                        grade = read_json(score)
                        row[kind], row[kind + "_status"] = grade.get("resolved"), grade["status"]
                rows.append(row)
    return {
        "planned_pairs": 3,
        "rows": rows,
        "historical_shared_cost_excluded_from_incremental_spend": True,
        "incremental_nanoyuan": sum(row["physical"].get("nanoyuan", 0) for row in rows),
        "completed_pairs": sum(
            all(
                type(row["code"]) is bool and type(row["delivery"]) is bool
                for row in rows[i : i + 2]
            )
            for i in range(0, 6, 2)
        ),
    }


if __name__ == "__main__":
    dest = ROOT / "artifacts/software-benchmark-v231/paired-r1/results.json"
    atomic_write(dest, json_bytes(report()))
