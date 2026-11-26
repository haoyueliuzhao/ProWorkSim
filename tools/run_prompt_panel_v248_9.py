"""Prospective P2.2 OSA continuations from both qualified v248 first-stage checkpoints."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_dynamic_panel_v248_2 as repair
import run_expansion_supplement_v248 as extension
from proworksim import software_organization_intent_v248_8 as policy
from proworksim.storage import read_json

first = repair.first
ROOT = first.ROOT
RUN = ROOT / "runs/software-benchmark-v248/p22-online-r1"
PLAN = ROOT / "artifacts/software-benchmark-v248/p22-online-r1/protocol.json"
ARMS = ("O-FIXED", "O-DYNAMIC")
SOURCES = {1: first.RUN, 6: extension.RUN}


def slot(i, arm):
    return f"v248.9:{i}:{arm}"


def register():
    tasks = [
        read_json(first.PLAN / "protocol.json")["rows"][1],
        read_json(extension.PLAN / "protocol.json")["case"],
    ]
    rows = []
    for case in tasks:
        i = case["index"]
        source = SOURCES[i] / str(i) / "COMMON"
        manifest = read_json(source / "checkpoint/manifest.json")
        rows.append(
            dict(
                case=case,
                checkpoint=first.old.reference(source / "checkpoint/manifest.json"),
                eligibility=first.old.reference(source / "eligibility.json"),
                identity=manifest["identity"],
                prefix=manifest["prefix_tokens"],
            )
        )
    first.freeze(
        PLAN,
        dict(
            rows=rows,
            arms=ARMS,
            cap_yuan=400,
            team_limit=first.LIMIT,
            method="New P2.2 independent continuations on the two previously qualified v248 checkpoint blocks; four new trajectories. Historical K and P1 are references, no before/after inference specific to P2.1. No outcome-dependent selection, repeats or candidature changes. Identical v245 scoring rules, initial workers, partial usage and test counts.",
            metrics=[
                "official code and delivery",
                "logical team tokens including prefix",
                "physical API cost",
                "accepted and rejected proposals",
                "D0 changes",
                "assessment versus cited receipts",
                "observed worker product/verification/adoption",
            ],
            files=[
                first.old.reference(f)
                for f in (
                    Path(__file__),
                    Path(policy.__file__),
                    Path(policy.p2.__file__),
                    Path(first.__file__),
                    Path(repair.__file__),
                    first.AUTH,
                )
            ],
        ),
    )


def reserve(rows):
    meter = first.PairedLedger.load(first.AUTH)
    with meter.db() as db:
        if db.execute("select value from meta where key='cap'").fetchone() != (str(meter.cap),):
            raise ValueError("Ledger cap mismatch")
        expected = [
            (slot(row["case"]["index"], arm), "v248.9:panel", first.LIMIT - row["prefix"])
            for row in rows
            for arm in ARMS
        ]
        exists = db.execute(
            "select slot,block_id,token_limit from block_slots where block_id='v248.9:panel'"
        ).fetchall()
        if exists:
            if sorted(exists) != sorted(expected):
                raise ValueError("Reservations do not match panel")
            return
        paid = db.execute(
            "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
        ).fetchone()[0]
        active = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
        pending = db.execute(
            "select coalesce(sum(token_limit),0) from block_slots where status='pending'"
        ).fetchone()[0]
        if paid + active + (pending + sum(x[2] for x in expected)) * 8000 > meter.cap:
            raise ValueError("Full block exceeds available balance")
        db.executemany("insert into block_slots values(?,?,?,'pending')", expected)


def generate(row, arm, out):
    module = SimpleNamespace(
        **{
            **vars(first.M),
            "Actor": repair.Actor,
            "substrate": SimpleNamespace(
                **{**vars(first.M.substrate), "prepare_case": repair.prepare_case}
            ),
        }
    )
    fn = repair.clone_function(
        first.generate,
        {
            **vars(first),
            "M": module,
            "patch": policy,
            "RUN": SOURCES[row["case"]["index"]],
            "slot": slot,
        },
    )
    fn(row["case"], arm, out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--index", type=int, choices=SOURCES)
    p.add_argument("--arm", choices=ARMS)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.freeze:
        register()
        return
    spec = read_json(PLAN)
    for f in spec["files"]:
        first.old.checked(f)
    for row in spec["rows"]:
        first.old.checked(row["checkpoint"])
        first.old.checked(row["eligibility"])
    if args.output:
        row = next(r for r in spec["rows"] if r["case"]["index"] == args.index)
        if args.output.resolve() != RUN / str(args.index) / args.arm:
            raise ValueError("Foreign destination")
        generate(row, args.arm, args.output)
        return
    (RUN / "tmp").mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(RUN / "tmp")
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reserve(spec["rows"])
        branch = repair.clone_function(
            repair.branch, {**vars(repair), "RUN": RUN, "__file__": __file__}
        )
        with ThreadPoolExecutor(4) as pool:
            futures = [
                (row["case"]["index"], arm, pool.submit(branch, row["case"], arm))
                for row in spec["rows"]
                for arm in ARMS
            ]
            for i, arm, future in futures:
                try:
                    result = future.result()
                except Exception as exc:
                    result = dict(status="technical_unknown", error=repr(exc))
                first.save(RUN / str(i) / (arm + "-summary.json"), result)


if __name__ == "__main__":
    main()
