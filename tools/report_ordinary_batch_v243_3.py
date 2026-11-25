"""Reconcile native task scores, passive captures and ledger costs for the registered batch."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sqlite3

import docker

from run_ordinary_batch_v243_3 import PLAN, RUN, SPEC, ordinary, read_json, reference
from report_ordinary_successor_v243_2 import inspect_run
from proworksim.software_benchmark_candidates_v054 import checked


def main():
    spec = read_json(SPEC)
    completed = read_json(RUN / "completed.json")
    authority = read_json(ordinary.AUTH)
    totals = Counter()
    cases = {}
    resources = []
    with closing(sqlite3.connect(Path(authority["ledger"]).as_uri() + "?mode=ro", uri=True)) as db:
        for job in spec["jobs"]:
            name = job["name"]
            root = RUN / name
            if completed[name]["status"] == "deferred_cash":
                cases[name] = completed[name]
                continue
            case = inspect_run(root, db)
            result = read_json(root / "ordinary/result.json")
            case.update(
                termination=result.get("termination"),
                prefix=result.get("prefix_tokens"),
                logical=result.get("logical_tokens"),
            )
            if case["status"] == "closed":
                assert case["logical"] == job["case"]["prefix"] + case["paid"]["tokens"]
                assert set(case["scores"]) == {"code", "delivery"}
            boundary = root / "ordinary/boundary.json"
            if boundary.exists():
                outcomes = read_json(boundary)["outcomes"]
                case["actions_by_member"] = dict(Counter(o["worker_id"] for o in outcomes))
            repair = root / "ordinary/prefix-stop-repair.json"
            if repair.exists():
                case["repair"] = reference(repair)
            totals.update(case["paid"])
            cases[name] = case
            sock = read_json(checked(job["task"]["configuration"]))["scorer_request_base"][
                "docker_socket"
            ]
            with closing(
                docker.DockerClient(base_url="unix://" + str(Path(sock).resolve()), timeout=12)
            ) as client:
                for path in (
                    root / "ordinary/actor/created.json",
                    root / "code/created.json",
                    root / "delivery/created.json",
                ):
                    if not path.exists():
                        continue
                    cid = read_json(path)["id"]
                    assert re.fullmatch("[0-9a-f]{64}", cid)
                    try:
                        client.containers.get(cid)
                        absent = False
                    except docker.errors.NotFound:
                        absent = True
                    resources.append(dict(creation=reference(path), absent=absent))
        paid = db.execute(
            "select coalesce(sum(cost),0) from requests where status='settled'"
        ).fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        held += db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        pending = db.execute(
            "select count(*) from block_slots where status='pending' and slot like 'v243.3:%'"
        ).fetchone()[0]
    ordinary.save(
        PLAN / "closeout.json",
        dict(
            cases=cases,
            total=dict(totals),
            resources=resources,
            cap=authority["cap_nanoyuan"],
            held=held,
            available=authority["cap_nanoyuan"] - paid - held,
            pending_ordinary=pending,
            intake=read_json(ordinary.pairs.PLAN / "ordinary-intake.json"),
            protocol=reference(SPEC),
        ),
    )


if __name__ == "__main__":
    main()
