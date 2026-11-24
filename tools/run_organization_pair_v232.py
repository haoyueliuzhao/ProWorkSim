"""Launch the approved first OSA pair, without drawing another case or updating C/N."""

import argparse
import fcntl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_context_panel_v231 import stored_run, score
from proworksim.software_context_panel_v231 import (
    ROOT,
    DESIGN,
    PairedLedger,
    panel_row,
    RUN as PREVIOUS,
)
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.storage import atomic_write, read_json, json_bytes

RUN = ROOT / "runs/software-benchmark-v232/first-pair-r1"
PLAN = ROOT / "artifacts/software-benchmark-v232/first-pair-r1"
ARMS = ("KEEP", "OSA")


def save(path, value):
    atomic_write(path, json_bytes(value))


def freeze():
    state = read_json(DESIGN)["states"][1]
    gate = read_json(PLAN / "engineering-gate.json")
    assert (
        gate["native_sdk"]["underfunded_activation_rejected"]
        and gate["native_sdk"]["provider_calls"] == 0
    )
    row = panel_row(state)
    src = ROOT / state["source_prefix"]
    files = [
        Path(__file__),
        ROOT / "tools/run_organization_episode_v232.py",
        ROOT / "tools/check_organization_v232.py",
        *(
            ROOT / "src/proworksim" / x
            for x in (
                "organization_harness.py",
                "software_context_v232.py",
                "software_organization_v232.py",
                "software_graph_execution_v230.py",
                "software_graph_controller_v228.py",
                "software_context_builder_v230.py",
            )
        ),
        PLAN / "engineering-gate.json",
        src / "observations.json",
        src / "checkpoint/manifest.json",
        DESIGN,
        ROOT / "tools" / row["scorer_script"],
        checked(row["configuration"]),
    ]
    result = {
        "case": state["case"],
        "checkpoint": state["checkpoint"],
        "prefix_tokens": state["shared_prefix_usage"],
        "arm_limit": 5_000_000 - state["shared_prefix_usage"],
        "roles": ["two managed workers", "isolated OSA in OSA arm only"],
        "arms": ARMS,
        "context": "checked T1",
        "anchor_every": 8,
        "primary_mechanism": [
            "owner opportunity",
            "real evidence work",
            "formal handoff",
            "postdecision anomaly resolution and recurrence",
        ],
        "secondary": [
            "official code",
            "legal delivery",
            "all physical input and output",
            "cache",
            "CNY",
            "worker opportunity costs",
        ],
        "invalid_proposal": "one paid OSA decision; rejected plan recorded, maintain graph",
        "keep_choice_valid": True,
        "settings": "DeepSeek Flash nonthinking, same two-worker harness, one continuation per arm",
        "CN_updates": 0,
        "cash_cap_nanoyuan": 144374666400,
        "prior_spend_nanoyuan": 103932272000,
        "approved_balance_nanoyuan": 40442394400,
        "sources": [reference(x) for x in files],
    }
    result["arms"] = list(ARMS)
    path = PLAN / "protocol.json"
    if path.exists() and read_json(path) != result:
        raise ValueError("Protocol already registered")
    save(path, result)


def launch():
    protocol = read_json(PLAN / "protocol.json")
    for r in protocol["sources"]:
        checked(r)
    auth = read_json(PREVIOUS / "authority.json")
    auth.update(
        scope="approved v232 Sphinx KEEP and OSA only",
        available_on_approval_nanoyuan=protocol["approved_balance_nanoyuan"],
    )
    if auth["cap_nanoyuan"] != protocol["cash_cap_nanoyuan"]:
        raise ValueError("Account changed")
    path = RUN / "authority.json"
    if not path.exists():
        save(path, auth)
    ledger = PairedLedger.load(path)
    case = protocol["case"]
    lim = protocol["arm_limit"]
    with ledger.db() as c:
        if c.execute("select value from meta where key='cap'").fetchone() != (str(ledger.cap),):
            raise ValueError("Account cap differs")
        keys = [("v232:" + case + ":" + arm, "v232:first-pair", lim) for arm in ARMS]
        existing = c.execute(
            "select slot,block_id,token_limit from block_slots where block_id='v232:first-pair' order by slot"
        ).fetchall()
        if existing and existing != keys:
            raise ValueError("Partial prior allocation")
        if not existing:
            paid = c.execute(
                "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
            ).fetchone()[0]
            active = c.execute(
                "select coalesce(sum(hold),0) from slots where status!='closed'"
            ).fetchone()[0]
            pending = c.execute(
                "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
            ).fetchone()[0]
            if paid + active + pending + 2 * lim * 8000 > ledger.cap:
                raise ValueError("Cannot fully reserve this pair")
            c.executemany("insert into block_slots values(?,?,?,'pending')", keys)
    dest = RUN / case
    dest.mkdir(exist_ok=True)
    records = {}
    row = panel_row(read_json(DESIGN)["states"][1])
    with ThreadPoolExecutor(2) as gen, ThreadPoolExecutor(2) as grader:
        jobs = {
            gen.submit(
                stored_run,
                "run_organization_episode_v232.py",
                ["--index", 1, "--arm", arm],
                dest / arm,
                "result.json",
            ): arm
            for arm in ARMS
        }
        scores = []
        for f in as_completed(jobs):
            arm = jobs[f]
            try:
                rc = f.result()
                records[arm] = {k: rc.get(k) for k in ("status", "error", "termination", "option")}
                if rc["status"] == "closed":
                    scores.append(grader.submit(score, row, dest / arm, arm))
            except Exception as exc:
                records[arm] = {"status": "technical_unknown", "error": repr(exc)}
            save(RUN / "progress.json", records)
        for f in scores:
            f.result()
    save(RUN / "completed.json", {"finished": time.time(), "branches": records})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            launch()
