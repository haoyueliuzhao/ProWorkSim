"""Close the ordinary task, its zero-charge replay attempt and the corrected continuation."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import json
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ordinary_successor_v243_2 as job
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import read_json


def counts(db, slot):
    paid = Counter()
    states = Counter()
    for status, tokens, cost, body in db.execute(
        "select status,tokens,cost,body from requests where slot=?", (slot,)
    ):
        states[status] += 1
        if status == "settled":
            u = json.loads(body)
            assert (
                tokens == u["input_tokens"] + u["output_tokens"] and cost == u["peak_cost_nanoyuan"]
            )
            paid.update(
                calls=1,
                input=u["input_tokens"],
                output=u["output_tokens"],
                tokens=tokens,
                nanoyuan=cost,
            )
    return dict(paid=dict(paid), states=dict(states))


def inspect_run(root, db):
    result = read_json(root / "ordinary/result.json")
    b = root / "ordinary/boundary.json"
    r = dict(
        status=result["status"],
        error=result.get("error"),
        slot=result["slot"],
        termination=result.get("termination"),
        logical=result.get("logical_tokens"),
        seconds=result["finished"] - result["started"],
        result=reference(root / "ordinary/result.json"),
        **counts(db, result["slot"]),
    )
    if b.exists():
        boundary = read_json(b)
        actors = Counter(o.get("worker_id") for o in boundary["outcomes"])
        r.update(
            actions_by_member=dict(actors),
            opportunities=len(boundary["outcomes"]),
            role_stops=boundary["role_stops"],
            boundary=reference(b),
        )
    if (root / "ordinary/verified-resume.json").exists():
        r["resume"] = read_json(root / "ordinary/verified-resume.json")
    test_gate = root / "ordinary/verified-test-recovery.json"
    if test_gate.exists():
        r["test_recovery"] = read_json(test_gate)
    cap = root / "ordinary/passive-captures/capture-index.json"
    if cap.exists():
        r["capture"] = read_json(cap)
    r["scores"] = {}
    for k in ("code", "delivery"):
        f = root / k / "receipt.json"
        if not f.exists():
            continue
        s = read_json(f)
        score = dict(status=s["status"], resolved=s["resolved"], source=reference(f))
        if s.get("official_result"):
            iid, report = s["official_result"]
            score["tests"] = {
                a: {b: len(c) for b, c in v.items()}
                for a, v in report[iid].get("tests_status", {}).items()
            }
        r["scores"][k] = score
    return r


def main():
    import docker

    cfg = read_json(job.PLAN / "protocol.json")
    auth = read_json(job.AUTH)
    stages = {
        "first": job.RUN,
        "replay_only": job.RUN / "recovery",
        "first_resume": job.RUN / "recovery-clock",
        "resumed": job.RUN / "recovery-rpc",
    }
    all_usage = Counter()
    roots = {}
    with closing(sqlite3.connect(Path(auth["ledger"]).as_uri() + "?mode=ro", uri=True)) as db:
        for name, root in stages.items():
            read_json(root / "completed.json")
            roots[name] = inspect_run(root, db)
            all_usage.update(roots[name]["paid"])
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        held += db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        live = db.execute(
            "select id,status from slots where status!='closed' and id like 'v243.2:%'"
        ).fetchall()
        pending = db.execute(
            "select slot from block_slots where status='pending' and slot like 'v243.2:%'"
        ).fetchall()
    if roots["resumed"]["status"] == "closed":
        assert (
            roots["resumed"]["test_recovery"]["executed"]
            and roots["resumed"]["test_recovery"]["historical_wires"] == 19
        )
        assert roots["resumed"]["logical"] == cfg["case"]["prefix"] + all_usage["tokens"]
    sock = read_json(checked(cfg["task"]["configuration"]))["scorer_request_base"]["docker_socket"]
    receipts = []
    with closing(
        docker.DockerClient(base_url="unix://" + str(Path(sock).resolve()), timeout=12)
    ) as client:
        for root in stages.values():
            for p in (
                root / "ordinary/actor/created.json",
                root / "code/created.json",
                root / "delivery/created.json",
            ):
                if not p.exists():
                    continue
                cid = read_json(p)["id"]
                assert re.fullmatch("[0-9a-f]{64}", cid)
                try:
                    client.containers.get(cid)
                    absent = False
                except docker.errors.NotFound:
                    absent = True
                receipts.append(dict(creation=reference(p), absent=absent))
    job.save(
        job.PLAN / "closeout.json",
        dict(
            stages=roots,
            total=dict(all_usage),
            cap=auth["cap_nanoyuan"],
            available=auth["cap_nanoyuan"] - paid - held,
            held=held,
            live=live,
            pending=pending,
            owned_containers=receipts,
            all_absent=all(v["absent"] for v in receipts),
            initial_score_adjudication=reference(job.PLAN / "first-score-adjudication.json"),
            queue_review=read_json(job.pairs.PLAN / "ordinary-intake.json"),
        ),
    )


if __name__ == "__main__":
    main()
