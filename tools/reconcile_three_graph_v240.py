"""Canonical runner for the frozen v240.2 protocol; default to offline reconciliation."""

import argparse
import fcntl
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_three_graph_v240 as original
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim.software_benchmark_candidates_v054 import checked


def json_wire(row):
    return json.loads(json.dumps(original.wire(row), allow_nan=False))


def main(run_pending=False):
    rows, spec = original.design()
    if original.read_json(original.PLAN / "protocol.json") != spec:
        raise ValueError("Design drifted")
    for source in spec["files"]:
        checked(source)
    f = original.reconcile
    clone = original.prior.prior.previous.prior.old.clone_function
    reconcile = clone(f, {**f.__globals__, "wire": json_wire})
    if run_pending:
        original.RUN.mkdir(parents=True, exist_ok=True)
        engine = original.first.run
        with (original.RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            clone(
                engine,
                {
                    **engine.__globals__,
                    "RUN": original.RUN,
                    "ThreadPoolExecutor": original.prior.prior.previous.BalancedPool,
                    "wire": json_wire,
                    "reconcile": reconcile,
                },
            )(rows, spec, namespace="v240.2")
    else:
        reconcile(
            rows, spec, PairedLedger.load(original.RUN / "authority.json"), namespace="v240.2"
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--run-pending",
        action="store_true",
        help="Submit only unconsumed frozen identities; otherwise replay offline.",
    )
    main(p.parse_args().run_pending)
