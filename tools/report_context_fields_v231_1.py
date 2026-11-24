"""Post-run accounting, official endpoints and request-level retention for T2."""

import json
import sqlite3
from collections import Counter

from proworksim.software_benchmark_deepseek_contract_v105 import normalize_usage
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_context_builder_v230 import (
    compact,
    identity,
    object_text,
    recover_observations,
)
from proworksim.software_context_fields_v231_1 import PATCHED, transform
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import atomic_write, read_json, json_bytes, digest

RUN = ROOT / "runs/software-benchmark-v231-1/three-r1"
PLAN = ROOT / "artifacts/software-benchmark-v231-1/context-r1"


def token_ids(counter, wire):
    obj = counter.recipe.ChatCompletionRequest({**wire, "model": "DeepSeek-V4.1-Flash"}).convert(
        counter.recipe.ConversionOptions()
    )
    return counter.encoding.encode(obj.conversation)


def prefix(a, b):
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


def measurements(folder, meter, counter):
    # Use native request_id to join the member manifest, actual wire, response and settlement.
    slot = "v231:" + folder.parent.name + ":T2"
    settlements = {
        rid: (status, pid, tokens, cost)
        for rid, status, pid, tokens, cost in meter.execute(
            "select id,status,provider_id,tokens,cost from requests where slot=?", (slot,)
        )
    }
    field_bytes = Counter()
    previous = {}
    totals = Counter()
    paths = sorted((folder / "api").glob("*/request.json"), key=lambda p: read_json(p)["time"])
    for path in paths:
        physical = read_json(path)
        rid = physical["physical_id"]
        payload = physical["payload"]
        wire = payload["wire"]
        record = settlements.pop(rid)
        folder_id = identity([slot, payload["member_id"], payload["request_id"]])
        attempt = folder / "telemetry/worker" / folder_id
        if record[0] != "settled":
            totals[record[0]] += 1
            continue
        usage = read_json(path.with_name("usage.json"))
        if normalize_usage(read_json(path.with_name("response.json"))) != usage or record[1:] != (
            usage["provider_response_id"],
            usage["total_tokens"],
            usage["peak_cost_nanoyuan"],
        ):
            raise ValueError("Response and physical ledger differ")
        meta = read_json(attempt / "manifest.json")
        stage = read_json(attempt / "final-manifest.json")
        t1 = read_json(attempt / "shown.json")
        if (
            wire != read_json(attempt / "final.json")
            or identity(wire) != stage["physical_t2"]
            or identity(t1) != stage["intermediate_t1"]
            or stage["request_id"] != payload["request_id"]
        ):
            raise ValueError("Wire evidence mismatch")
        restored, _ = transform(wire, meta["actor"], restore=True)
        if identity(restored) != identity(t1):
            raise ValueError("Intermediate message or evidence lost")
        raw = read_json(attempt / "original.json")
        obs = recover_observations(restored)
        if recover_observations(raw) != obs:
            raise ValueError("Observation did not round-trip")
        totals["snapshots"] += len(obs)
        ids1 = token_ids(counter, t1)
        ids2 = token_ids(counter, wire)
        if physical["count"]["local_encoded_prompt_tokens"] != len(ids2):
            raise ValueError("Tokenizer drift")
        totals.update(
            requests=1,
            local_t1=len(ids1),
            local_t2=len(ids2),
            input=usage["input_tokens"],
            output=usage["output_tokens"],
            cache_hit=usage["cache_hit_tokens"],
            cache_miss=usage["cache_miss_tokens"],
            cost_nanoyuan=record[-1],
        )
        key = (meta["actor"], meta["role"])
        if key in previous:
            a, b = previous[key]
            totals.update(adjacent_pairs=1, t1_prefix=prefix(a, ids1), t2_prefix=prefix(b, ids2))
        previous[key] = ids1, ids2
        for i, msg in enumerate(wire["messages"]):
            v = object_text(msg.get("content")) or {}
            delta = v.get("observation_delta", {})
            if PATCHED not in delta:
                continue
            orig = object_text(t1["messages"][i]["content"])["observation_delta"]["changed"]
            for field in delta[PATCHED]:
                field_bytes[field] += len(compact(orig[field]).encode()) - len(
                    compact(delta["changed"][field]).encode()
                )
    if settlements:
        raise ValueError("Missing archived physical requests")
    return totals, field_bytes, action_counts(folder)


def action_counts(folder):
    actions = Counter()
    tests_seen = set()
    events = folder / "runtime/experience.jsonl"
    if events.exists():
        with events.open() as source:
            for line in source:
                e = json.loads(line)
                if e["kind"] != "tool_call":
                    continue
                d = e["payload"]
                tool = d["action"]
                actions["all"] += 1
                if tool in ("run_tests", "run_patch_review_tests"):
                    actions["tests"] += 1
                    result = d["response"].get("result") or {}
                    if (
                        d["response"]["ok"]
                        and result.get("executed")
                        and result.get("source_reference")
                    ):
                        actions["executed_tests_with_version"] += 1
                        key = identity(
                            [
                                e.get("worker_id"),
                                tool,
                                result["source_reference"],
                                d["arguments"].get("patch_id"),
                                json.dumps(d["arguments"].get("selection"), sort_keys=True),
                            ]
                        )
                        actions["repeat_same_actor_version_selection"] += key in tests_seen
                        tests_seen.add(key)
                if tool == "read_file":
                    actions["file_reads"] += 1
                if tool == "reopen_work":
                    actions["work_reopen_requests"] += 1
                if tool == "read_test_result":
                    actions["rereads"] += 1
                if not d["response"]["ok"]:
                    actions["rejected"] += 1
                if tool == "send_message" and d["response"]["ok"]:
                    actions["accepted_messages"] += 1
                    if (d["arguments"].get("body") or "").startswith("DIAG "):
                        actions["diagnosis_handoffs"] += 1
    return actions


def main():
    protocol = read_json(PLAN / "protocol.json")
    old = read_json(ROOT / "artifacts/software-benchmark-v231/paired-r1/results.json")["rows"]
    token_path = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    counter = OfficialDeepSeekCounter(token_path, manifest_sha256=digest(token_path.read_bytes()))
    auth = read_json(RUN / "authority.json")
    rows = []
    with sqlite3.connect("file:" + auth["ledger"] + "?mode=ro", uri=True) as db:
        for state in protocol["states"]:
            case = state["case"]
            folder = RUN / case / "T2"
            rc = folder / "result.json"
            if not rc.exists():
                rows.append({"case": case, "status": "missing_result"})
                continue
            result = read_json(rc)
            totals, savings, actions = measurements(folder, db, counter)
            row = {
                "case": case,
                "status": result["status"],
                "error": result.get("error"),
                "physical": totals,
                "field_bytes_saved_before_index": savings,
                "actions": actions,
                "termination": result.get("termination"),
            }
            if result["status"] == "closed":
                if (
                    state["checkpoint"] != result["checkpoint"]
                    or state["both_arms_option"] != result["option"]
                    or result["logical_tokens"]
                    != state["shared_prefix_usage"]
                    + state["shared_controller_usage"]
                    + totals["input"]
                    + totals["output"]
                ):
                    raise ValueError("Task identity or usage mismatch")
                baseline = next(r for r in old if r["case"] == case and r["arm"] == "T1")
                prior = (
                    ROOT / "runs/software-benchmark-v231/paired-r1" / case / "T1" / "result.json"
                )
                if read_json(prior)["graph_sha256"] != result["graph_sha256"]:
                    raise ValueError("Organization differs between runs")
                row.update(
                    previous_T1=baseline,
                    previous_T1_actions=action_counts(prior.parent),
                    wall_seconds=result["finished"] - result["started"],
                    observer_errors=result.get("observer_errors"),
                    actor_cleanup=read_json(folder / "actor/cleanup.json"),
                )
            for kind in ("code", "delivery"):
                f = folder.with_name("T2-" + kind) / "receipt.json"
                receipt = read_json(f) if f.exists() else {}
                row[kind] = {
                    "status": receipt.get("status", "unknown"),
                    "resolved": receipt.get("resolved"),
                    "cleanup_errors": receipt.get("cleanup_errors"),
                    "receipt": str(f.relative_to(ROOT)),
                }
            rows.append(row)
        prior_spend = db.execute(
            "select coalesce(sum(cost),0) from requests where status='settled' and slot not glob 'v231:*:T2'"
        ).fetchone()[0]
        current = db.execute(
            "select coalesce(sum(cost),0) from requests where status='settled' and slot glob 'v231:*:T2'"
        ).fetchone()[0]
        if current != sum(r.get("physical", {}).get("cost_nanoyuan", 0) for r in rows):
            raise ValueError("Incomplete panel ledger")
        reserved = db.execute(
            "select count(*) from requests where slot glob 'v231:*:T2' and status='reserved'"
        ).fetchone()[0]
    atomic_write(
        PLAN / "results.json",
        json_bytes(
            {
                "states": rows,
                "historical_T1_not_recharged": True,
                "reserved_requests": reserved,
                "prior_nanoyuan": prior_spend,
                "new_nanoyuan": current,
                "cap_nanoyuan": auth["cap_nanoyuan"],
                "balance_nanoyuan": auth["cap_nanoyuan"] - prior_spend - current,
            }
        ),
    )


if __name__ == "__main__":
    main()
