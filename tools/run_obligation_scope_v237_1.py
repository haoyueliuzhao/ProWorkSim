"""Independent structured replication, separating immediate obligations from future checks."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_structured_decisions_v237 as first
from proworksim.software_structured_policy_v237 import (
    wire as original,
    validate as original_validate,
    OBLIGATIONS,
    arr,
)
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import read_json

PLAN = first.ROOT / "artifacts/software-benchmark-v237-1/obligation-scope-r1"
RUN = first.ROOT / "runs/software-benchmark-v237-1/obligation-scope-r1"


def wire(row):
    w = original(row)
    props = w["tools"][0]["function"]["parameters"]["properties"]
    work = props["work"]
    work["properties"]["obligations"]["description"] = (
        "Immediate unmet obligations evidenced NOW. Use the smallest sufficient set for this package, prior to the later actions listed separately."
    )
    work["properties"]["later_checks"] = arr(OBLIGATIONS)
    work["required"].append("later_checks")
    props["decision"]["properties"]["missing_evidence"]["description"] = (
        "Evidence needed to CHOOSE between paths now. For KEEP and CHANGE use none. Future evidence goes in reconsider_on, verification or later_checks."
    )
    w["messages"][0]["content"] += (
        " Separate the immediate gap from routine later steps. Cite both distinct test failures to diagnose repeated failure. If no supported incremental product exists, the alternative can explicitly have no useful product; do not invent one. If evidence is insufficient to choose a path, use ABSTAIN, request one specific observation, and set next_step to inspect_evidence."
    )
    return w


def validate(row, body):
    return original_validate(row, body, schema_builder=wire, distinguish_future=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    rows, _ = first.design()
    spec = read_json(first.PLAN / "protocol.json")
    spec["labels"] = [a for a in spec["labels"] if a.endswith("-structured")]
    spec.update(
        opening_balance=read_json(first.PLAN / "results.json")["balance_nanoyuan"],
        worst_pair_nanoyuan=len(spec["labels"]) * first.LIMIT * 8000,
        amendment="All structured states including evidence-gap control repeated prospectively with distinct identities. Same independent review, scoring and gate. Unchanged compact control reused only as historical reference. No substitution for first results.",
        files=[
            reference(x)
            for x in (
                Path(__file__),
                Path(first.__file__),
                first.ROOT / "src/proworksim/software_structured_policy_v237.py",
                first.PLAN / "panel.json",
                first.PLAN / "independent-review.json",
                first.PLAN / "results.json",
            )
        ],
    )
    dest = PLAN / "protocol.json"
    if args.freeze:
        if dest.exists() and read_json(dest) != spec:
            raise ValueError("Frozen design differs")
        first.save(dest, spec)
        first.save(
            PLAN / "independent-review.json", read_json(first.PLAN / "independent-review.json")
        )
        return
    if read_json(dest) != spec:
        raise ValueError("Frozen design differs")
    fn = first.reconcile
    reconcile = clone_function(
        fn, {**fn.__globals__, "wire": wire, "validate": validate, "PLAN": PLAN, "RUN": RUN}
    )
    fn = first.run
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        clone_function(fn, {**fn.__globals__, "wire": wire, "RUN": RUN, "reconcile": reconcile})(
            rows, spec, namespace="v237.1"
        )


if __name__ == "__main__":
    main()
