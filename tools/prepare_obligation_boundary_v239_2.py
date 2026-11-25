"""Prospective diagnostic panel drawn from original receipts. Development and new states are separate."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_organization_contract_v239 as previous
from prepare_osa_states_v236 import build
from proworksim.software_anomaly_graph_v226 import AnomalyGraph
from proworksim.software_stage_response_v236 import options
from proworksim.storage import read_json

ROOT = previous.ROOT
PLAN = ROOT / "artifacts/software-benchmark-v239-2/obligation-boundary-r1"
RUN = ROOT / "runs/software-benchmark-v239-2/obligation-boundary-r1"


def freeze(name, value):
    p = PLAN / name
    if p.exists() and read_json(p) != value:
        raise ValueError(f"Unexpected change to frozen {name}")
    previous.first.save(p, value)


def main():
    original = read_json(previous.PLAN / "panel.json")
    seen = {r["instance"] for r in original}
    rows = [
        build("x01", "A4", "software-benchmark-v217/confirmation-resume-r1/task-13/KEEP", [1]),
        build("x02", "A4", "software-benchmark-v217/selection28-r1/task-20/KEEP", [1]),
    ]
    seen.update(x["instance"] for x in rows)
    missing = {"A1", "A2"}
    scanned = ready_count = 0
    hits = []
    for f in sorted((ROOT / "runs").glob("software-benchmark-v2*/**/boundary.json")):
        if any(
            s in str(f.relative_to(ROOT)).lower()
            for s in ("/sdk", "fixture", "rehearsal", "performance-benchmark")
        ):
            continue
        outcomes = read_json(f).get("outcomes", [])
        if not outcomes:
            continue
        scanned += 1
        graph = AnomalyGraph("member_001")
        case = f.parent
        result = case / "result.json"
        instance = read_json(result).get("instance_id") if result.is_file() else None
        last_fail = {}
        for n, o in enumerate(outcomes, 1):
            graph.observe(n, o)
            v = (o.get("response") or {}).get("result") or {}
            actor = o.get("worker_id")
            tool = (o.get("decision") or {}).get("action")
            if tool == "delivery_readiness" and actor == "member_001" and v.get("ready_to_submit"):
                ready_count += 1
            if any(
                z["anomaly_type"] == "A5" and z["status"] in ("OPEN", "ACTIVE")
                for z in graph.nodes.values()
            ):
                if not hits or hits[-1][0] != str(f.relative_to(ROOT)):
                    hits.append([str(f.relative_to(ROOT)), n])
            if (
                not missing
                or not instance
                or instance in seen
                or not (case / "runtime/experience.jsonl").exists()
            ):
                continue
            event = (
                v
                if tool == "work_readiness"
                else (((o.get("response") or {}).get("error") or {}).get("rejection") or {})
                .get("context", {})
                .get("readiness", {})
            )
            if (
                "A2" in missing
                and tool in ("begin_work", "work_readiness")
                and any(
                    x.get("kind") in ("upstream_not_current", "upstream_patch_not_adopted")
                    for x in event.get("gaps", [])
                )
            ):
                kind, seq = "A2", [n]
            elif (
                "A1" in missing
                and tool == "run_tests"
                and v.get("executed")
                and v.get("passed") is False
            ):
                version = v.get("source_reference")
                old = last_fail.get(actor)
                last_fail[actor] = (n, version)
                if not old or old[1] == version:
                    continue
                kind, seq = "A1", [old[0], n]
            else:
                continue
            try:
                r = build(
                    "x03" if kind == "A1" else "x04",
                    kind,
                    str(case.relative_to(ROOT / "runs")),
                    seq,
                )
            except (AssertionError, ValueError, KeyError, FileNotFoundError):
                continue
            if not r["targets"]:
                continue
            rows.append(r)
            seen.add(instance)
            missing.remove(kind)
    if missing:
        raise ValueError(missing)
    freeze(
        "natural-a5.json",
        dict(
            scope="recursive v2* archived boundary files with outcomes, excluding SDK/fixtures/rehearsal/performance-benchmark; original primary observer",
            branches=scanned,
            ready_receipts=ready_count,
            matches=hits,
        ),
    )
    freeze("additional-states.json", sorted(rows, key=lambda r: r["id"]))
    freeze(
        "review-packet.json",
        [
            {
                **{
                    k: r[k]
                    for k in (
                        "id",
                        "observer",
                        "graph",
                        "targets",
                        "evidence",
                        "work_status",
                        "available_tokens",
                    )
                },
                "legal_options": options(r),
            }
            for r in sorted(rows, key=lambda r: r["id"])
        ],
    )


if __name__ == "__main__":
    main()
