"""Inventory natural, actor-visible evidence at the actual saved boundary, without reading scores."""

from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proworksim.software_anomaly_graph_v226 import AnomalyGraph
from proworksim.software_context_panel_v231 import ROOT
from proworksim.storage import read_json, atomic_write, json_bytes

PLAN = ROOT / "artifacts/software-benchmark-v242/multitype-r1"
RUN = ROOT / "runs/software-benchmark-v242/multitype-r1"


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json_bytes(value))


def history(prefix):
    direct = prefix / "observations.json"
    if direct.exists():
        return read_json(direct)
    records = []
    with (prefix / "runtime/experience.jsonl").open("rb") as f:
        for line in f:
            if b'"kind":"tool_call"' not in line and b'"kind": "tool_call"' not in line:
                continue
            e = json.loads(line)
            if e["kind"] != "tool_call":
                continue
            d = e["payload"]
            ordid = d.get("opportunity_id", "").rsplit("-", 1)[-1]
            if not ordid.isdigit():
                continue
            records.append(
                dict(
                    ordinal=int(ordid),
                    outcome=dict(
                        worker_id=e["worker_id"],
                        decision={
                            k: d.get(k) for k in ("action", "arguments", "model_tool_call_id")
                        },
                        response=d["response"],
                    ),
                )
            )
    return records


def main():
    rows = []
    counts = Counter()
    for path in sorted((ROOT / "runs").glob("software-benchmark-v2*/**/checkpoint/manifest.json")):
        prefix = path.parent.parent
        if any(t in str(prefix).lower() for t in ("sdk-", "rehearsal", "fixture")):
            continue
        doc = prefix / "checkpoint/state.json"
        stat = prefix / "result.json"
        log = prefix / "runtime/experience.jsonl"
        if not all(p.exists() for p in (doc, stat, log)):
            continue
        ss = dict(read_json(doc)["__dict__"])
        rt = dict(ss["runtime"]["__dict__"])
        op = rt.get("opportunities")
        if not isinstance(op, int):
            continue
        inst = read_json(stat).get("instance_id")
        if not inst:
            continue
        m = read_json(path)
        ctrl = dict(ss["control_state"].get("__dict__", []))
        typed = dict(ctrl.get("node", {}).get("__dict__", []))
        obs = [o for o in history(prefix) if o["ordinal"] <= op]
        counts["inspected"] += 1
        views = []
        for worker in ("member_001", "member_002"):
            graph = AnomalyGraph(worker)
            for x in obs:
                graph.observe(x["ordinal"], x["outcome"])
            for n in graph.nodes.values():
                kind = n["anomaly_type"]
                if n["status"] not in ("OPEN", "ACTIVE") or kind not in (
                    "A1",
                    "A2",
                    "A3",
                    "A4",
                    "A5",
                ):
                    continue
                last = max(ref["opportunity"] for ref in n["evidence_refs"])
                # A detection at a different time is a lead, not a proved common start.
                views.append(
                    dict(
                        kind=kind,
                        observer=worker,
                        last=last,
                        exact=(
                            last == op
                            or (
                                typed.get("anomaly_id") == n["anomaly_id"]
                                and ctrl.get("ordinal") == op
                            )
                        ),
                        anomaly_id=n["anomaly_id"],
                        subject=n["subject"],
                        work=n["affected_work"],
                    )
                )
        rows.append(
            dict(
                source=str(prefix.relative_to(ROOT)),
                instance=inst,
                ordinal=op,
                checkpoint=m["identity"],
                prefix_tokens=m["prefix_tokens"],
                views=views,
            )
        )
    counts["exact"] = sum(any(v["exact"] for v in r["views"]) for r in rows)
    save(PLAN / "checkpoint-inventory.json", dict(counts=dict(counts), records=rows))


if __name__ == "__main__":
    main()
