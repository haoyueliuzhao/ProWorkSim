"""Repeat the policy comparison once on the repaired, identical two-worker harness."""

import argparse
import fcntl
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_organization_episode_v232 as episode_module
import run_diagnosis_receipts_v232_7 as repaired
from run_context_panel_v231 import score, stored_run
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_context_panel_v231 import DESIGN, ROOT, PairedLedger, panel_row
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_evidence_v232_6 import EvidenceFollowupExecution
from proworksim.storage import atomic_write, json_bytes, read_json

RUN = ROOT / "runs/software-benchmark-v233/repaired-osa-pair-r1"
PLAN = ROOT / "artifacts/software-benchmark-v233/repaired-osa-pair-r1"
CASE = repaired.CASE
ARMS = ("KEEP", "OSA")
BLOCK = "v233:paired-sphinx"


def save(path, data):
    atomic_write(path, json_bytes(data))


def freeze():
    base = read_json(repaired.PLAN / "protocol.json")
    data = {
        k: base[k]
        for k in ("case", "checkpoint", "prefix_tokens", "account_cap_nanoyuan", "arm_limit")
    }
    files = {Path(x["path"]): x for x in base["files"]}
    for p in [
        Path(episode_module.__file__),
        Path(__file__),
        repaired.PLAN / "results.json",
        repaired.PLAN / "protocol.json",
    ]:
        files[p] = reference(p)
    for x in files.values():
        checked(x)
    assert data["arm_limit"] + data["prefix_tokens"] == 5_000_000
    data.update(
        arms=list(ARMS),
        attempts=2,
        source_contract="Prior exposed A1 checkpoint; no access to any later trials, diagnoses or grades from this state in either member or OSA input.",
        conditions={
            "KEEP": "fixed organization",
            "OSA": "one fresh paid decision; maintain or change according to the supplied predecision evidence",
        },
        shared_harness="v232.7 evidence and blocker receipts; checked T1, DeepSeek Flash nonthinking, same two workers, same tools and official scorer",
        primary=[
            "decision accepted and graph activated",
            "assigned worker action and evidence",
            "accepted handoff and actual recipient disposition",
            "anomaly resolution and recurrence when observable",
        ],
        secondary=["official code", "legal delivery", "all physical input/output and cost"],
        analysis="One exposed state. If strategies differ, report paired realized utility contrast (legal resolved delivery minus 0.1 * logical tokens / 5M); retain KEEP choices and unknowns. No parameter or novelty update from this pair.",
        files=list(files.values()),
        worst_pair_nanoyuan=2 * data["arm_limit"] * 8000,
    )
    dest = PLAN / "protocol.json"
    if dest.exists() and read_json(dest) != data:
        raise ValueError("Registered design differs")
    PLAN.mkdir(parents=True, exist_ok=True)
    save(dest, data)


def reserve(auth, p, *, namespace="v233", block=BLOCK):
    ledger = PairedLedger.load(auth)
    expected = [(f"{namespace}:{p['case']}:{a}", p["arm_limit"]) for a in ARMS]
    with ledger.db() as db:
        if db.execute("select value from meta where key='cap'").fetchone() != (
            str(p["account_cap_nanoyuan"]),
        ):
            raise ValueError("Ledger cap changed")
        existing = db.execute(
            "select slot,token_limit from block_slots where block_id=? order by slot", (block,)
        ).fetchall()
        if existing:
            if existing != expected:
                raise ValueError("Conflicting block")
            return
        used = db.execute(
            "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
        ).fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        pending = db.execute(
            "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
        ).fetchone()[0]
        if used + held + pending + p["worst_pair_nanoyuan"] > ledger.cap:
            raise ValueError("Insufficient funds for this complete pair")
        db.executemany(
            "insert into block_slots values(?,?,?,'pending')",
            [(slot, block, lim) for slot, lim in expected],
        )


def launch():
    p = read_json(PLAN / "protocol.json")
    for ref in p["files"]:
        checked(ref)
    previous = read_json(repaired.RUN / "authority.json")
    previous.update(
        scope="one v233 same-harness Sphinx KEEP and fresh OSA pair",
        available_on_approval_nanoyuan=read_json(repaired.PLAN / "results.json")[
            "available_nanoyuan"
        ],
    )
    auth = RUN / "authority.json"
    if not auth.exists():
        save(auth, previous)
    if read_json(auth) != previous:
        raise ValueError("Ledger identity differs")
    reserve(auth, p)
    run_pair(RUN, CASE, panel_row(read_json(DESIGN)["states"][1]), Path(__file__).name)


def run_pair(run, case, row, script):
    folder = run / case
    folder.mkdir(exist_ok=True)

    def branch(arm):
        dest = folder / arm
        result = stored_run(script, ["--arm", arm], dest, "result.json")
        if result["status"] == "closed":
            score(row, dest, arm)
        return {k: result.get(k) for k in ("status", "termination", "option", "error")}

    records = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(branch, arm): arm for arm in ARMS}
        for future in as_completed(jobs):
            arm = jobs[future]
            try:
                records[arm] = future.result()
            except Exception as exc:
                records[arm] = {"status": "technical_unknown", "error": repr(exc)}
            save(run / "progress.json", records)
    save(run / "completed.json", records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--arm", choices=ARMS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.arm:
        if args.output != RUN / CASE / args.arm:
            parser.error("Unexpected branch path")
        fn = episode_module.episode
        clone_function(
            fn, {**fn.__globals__, "RUN": RUN, "OrganizationExecution": EvidenceFollowupExecution}
        )(1, args.arm, args.output, False, slot_namespace="v233")
    else:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            launch()
