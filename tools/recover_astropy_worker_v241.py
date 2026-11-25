"""Read the v227 predecision observer from its same-boundary record for both pending arms."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_three_graph_worker_v241 as batch
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import read_json

OUT = batch.RUN / "observer-compat-r1"
REPAIR = batch.PLAN / "astropy-restore-revision.json"


def prepare(item, state):
    src = batch.ROOT / state["source_prefix"]
    row = batch.panel_row(state)
    graph = read_json(src / "graph.json")
    bank = read_json(src / "bank.json")
    panel = next(r for r in batch.sources() if r["id"] == item["id"])
    assert row["observer"] == graph["observer"] == panel["observer"]
    assert bank["ordinal"] == panel["provenance"]["ordinals"][-1]
    return dict(
        case=item["case"],
        checkpoint=state["checkpoint"],
        observer=row["observer"],
        ordinal=bank["ordinal"],
        anomaly_id=bank["node"]["anomaly_id"],
        source=reference(src / "graph.json"),
        bank=reference(src / "bank.json"),
        revision=reference(Path(__file__)),
        mode="Both original arms failed before admission. Supply only missing observation identity in the loader view; no checkpoint bytes or account IDs change.",
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", choices=batch.ARMS)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    spec = read_json(batch.PLAN / "protocol.json")
    for f in spec["files"]:
        checked(f)
    (item,) = [r for r in spec["roster"] if r["id"] == "q03"]
    state = read_json(batch.DESIGN)["states"][item["index"]]
    rev = prepare(item, state)
    if a.arm:
        if a.output != OUT / item["case"] / a.arm or read_json(REPAIR) != rev:
            raise ValueError("Unexpected recovery scope")

        class Bound(batch.Replay):
            pass

        Bound.binding = item
        module = batch.paired.episode_module
        original = module.resume

        def read_legacy(point):
            saved, proof = original.read(point)
            control = saved["control_state"]
            if (
                proof["identity"] != rev["checkpoint"]
                or control["node"]["anomaly_id"] != rev["anomaly_id"]
                or control["ordinal"] != rev["ordinal"]
            ):
                raise ValueError("Legacy checkpoint identity mismatch")
            if control.get("observer", rev["observer"]) != rev["observer"]:
                raise ValueError("Conflicting observer")
            return {**saved, "control_state": {**control, "observer": rev["observer"]}}, proof

        resume = SimpleNamespace(**{**vars(original), "read": read_legacy})
        fn = module.episode
        batch.paired.clone_function(
            fn,
            {**fn.__globals__, "RUN": batch.RUN, "OrganizationExecution": Bound, "resume": resume},
        )(
            item["index"],
            a.arm,
            a.output,
            False,
            slot_namespace=batch.NS,
            expected_case=item["case"],
        )
        return
    OUT.mkdir(exist_ok=True)
    with (OUT / "recovery.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (OUT / "completed.json").exists():
            return
        if REPAIR.exists() and read_json(REPAIR) != rev:
            raise ValueError("Recovery revision differs")
        batch.save(REPAIR, rev)
        meter = batch.PairedLedger.load(batch.RUN / "authority.json")
        with meter.db() as db:
            for arm in batch.ARMS:
                old = read_json(batch.RUN / item["case"] / arm / "result.json")
                slot = old["slot"]
                if (
                    old.get("error") != "'observer'"
                    or db.execute("select count(*) from requests where slot=?", (slot,)).fetchone()[
                        0
                    ]
                    or db.execute("select status from block_slots where slot=?", (slot,)).fetchone()
                    != ("pending",)
                ):
                    raise ValueError("Recovery expects untouched slots")
        folder = OUT / item["case"]
        folder.mkdir(exist_ok=True)
        import os

        os.environ["TMPDIR"] = str(batch.RUN / "tmp")

        def one(arm):
            d = folder / arm
            scores = {}
            res = batch.isolated(Path(__file__).resolve(), ["--arm", arm], d, "result.json")
            if res["status"] == "closed":
                for kind in ("code", "delivery"):
                    receipt = batch.isolated(
                        batch.ROOT / "tools" / item["score_script"],
                        ["--index", item["score_index"], "--kind", kind, "--episode", d],
                        folder / (arm + "-" + kind),
                        "receipt.json",
                    )
                    scores[kind] = {k: receipt.get(k) for k in ("status", "resolved", "error")}
            return {"status": res["status"], "error": res.get("error"), "scores": scores}

        with ThreadPoolExecutor(2) as pool:
            results = dict(zip(batch.ARMS, pool.map(one, batch.ARMS)))
        batch.save(OUT / "completed.json", results)


if __name__ == "__main__":
    main()
