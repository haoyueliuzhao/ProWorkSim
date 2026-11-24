"""Three T2 continuations with the frozen v231 checkpoints, schedules and official scorers."""

import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
import fcntl
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_context_pair_v231 as previous
from run_context_panel_v231 import stored_run, score
from proworksim.software_context_panel_v231 import (
    ROOT,
    DESIGN,
    PairedLedger,
    panel_row,
    RUN as PRIOR,
)
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_field_execution_v231_1 import FieldExecution
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import atomic_write, json_bytes, read_json

RUN = ROOT / "runs/software-benchmark-v231-1/three-r1"
PLAN = ROOT / "artifacts/software-benchmark-v231-1/context-r1"


def save(path, value):
    atomic_write(path, json_bytes(value))


def reserve(meter, state):
    slot = "v231:" + state["case"] + ":T2"
    limit = state["remaining_per_branch"]
    with meter.db() as db:
        if db.execute("select value from meta where key='cap'").fetchone() != (str(meter.cap),):
            raise ValueError("Wrong source account")
        old = db.execute(
            "select block_id,token_limit from block_slots where slot=?", (slot,)
        ).fetchone()
        if old:
            if old != ("v231.1:three-r1", limit):
                raise ValueError("Different existing hold")
            return True
        spent = db.execute(
            "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
        ).fetchone()[0]
        holds = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        pending = db.execute(
            "select coalesce(sum(token_limit),0) from block_slots where status='pending'"
        ).fetchone()[0]
        if spent + holds + (pending + limit) * 8000 > meter.cap:
            return False
        db.execute(
            "insert into block_slots values(?,?,?,'pending')", (slot, "v231.1:three-r1", limit)
        )
    return True


def run():
    study = read_json(PLAN / "protocol.json")
    if not study["offline_passed"] or len(study["states"]) != 3:
        raise ValueError("Offline gate or panel missing")
    for f in study["sources"]:
        checked(f)
    auth = read_json(PRIOR / "authority.json")
    if auth["cap_nanoyuan"] != 144374666400:
        raise ValueError("Mismatch with approved unchanged cap")
    authority = RUN / "authority.json"
    if not authority.exists():
        save(
            authority,
            {
                **auth,
                "scope": "v231.1 three T2 continuations on same v229 account",
                "available_on_approval_nanoyuan": 50582217120,
            },
        )
    meter = PairedLedger.load(authority)
    waiting = [2, 1, 0]
    active = {}
    grading = []
    outcomes = {}
    with ThreadPoolExecutor(2) as workers, ThreadPoolExecutor(2) as scorers:
        while waiting or active:
            for i in waiting.copy():
                if len(active) >= 2:
                    break
                state = study["states"][i]
                if not reserve(meter, state):
                    continue
                dest = RUN / state["case"] / "T2"
                dest.parent.mkdir(exist_ok=True)
                job = workers.submit(
                    stored_run, Path(__file__).name, ["--index", i], dest, "result.json"
                )
                active[job] = (i, dest)
                waiting.remove(i)
            if not active:
                for i in waiting:
                    outcomes[study["states"][i]["case"]] = {"status": "not_cash_admitted"}
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for job in done:
                i, dest = active.pop(job)
                try:
                    result = job.result()
                    outcomes[study["states"][i]["case"]] = {
                        k: result.get(k) for k in ("status", "error", "termination")
                    }
                    if result["status"] == "closed":
                        grading.append(
                            scorers.submit(score, panel_row(study["states"][i]), dest, "T2")
                        )
                except Exception as exc:
                    outcomes[study["states"][i]["case"]] = {
                        "status": "technical_unknown",
                        "error": repr(exc),
                    }
            save(RUN / "progress.json", outcomes)
        for job in grading:
            job.result()
    save(RUN / "completed.json", {"branches": outcomes, "finished": time.time()})


def freeze():
    data = read_json(PLAN / "offline.json")
    if not data["passed"] or sum(v["stats"]["requests"] for v in data["cases"]) != 193:
        raise ValueError("Missing required full replay")
    previous_freeze = ROOT / "artifacts/software-benchmark-v231/paired-r1/freeze.json"
    for f in read_json(previous_freeze)["files"]:
        checked(f)
    files = [
        Path(__file__),
        ROOT / "src/proworksim/software_context_fields_v231_1.py",
        ROOT / "src/proworksim/software_field_execution_v231_1.py",
        ROOT / "tools/replay_context_fields_v231_1.py",
        PLAN / "offline.json",
        DESIGN,
        previous_freeze,
        ROOT / "artifacts/software-benchmark-v231/paired-r1/results.json",
    ]
    obj = {
        "offline_passed": True,
        "states": read_json(DESIGN)["states"],
        "sources": [reference(f) for f in files],
        "treatment": "Lossless edits to nine changing object fields after v231 T1 projection",
        "comparison": "Previously scored T1, same three checkpoints; one new T2 each",
        "account_cap_nanoyuan": 144374666400,
        "approval_balance_nanoyuan": 50582217120,
        "new_controller_calls": 0,
        "default_order": [2, 1, 0],
        "max_generation_lanes": 2,
        "max_scoring_lanes": 2,
    }
    path = PLAN / "protocol.json"
    if path.exists() and read_json(path) != obj:
        raise ValueError("Protocol already frozen")
    save(path, obj)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--index", type=int, choices=range(3))
    p.add_argument("--output", type=Path)
    p.add_argument("--freeze", action="store_true")
    a = p.parse_args()
    if a.freeze:
        freeze()
    elif a.index is not None:
        expected = RUN / read_json(DESIGN)["states"][a.index]["case"] / "T2"
        if a.output != expected:
            raise ValueError("Invalid physical identity")
        clone_function(
            previous.episode,
            {**previous.episode.__globals__, "RUN": RUN, "Execution": FieldExecution},
        )(a.index, "T2", expected, False)
    else:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run()
