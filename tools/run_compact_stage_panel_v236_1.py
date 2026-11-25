"""Prospective full-panel interface replication; do not modify historical decisions."""

import argparse
import fcntl
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_osa_stage_panel_v236 as first
from proworksim.software_stage_response_v236 import wire as original, validate, enum
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_context_builder_v230 import compact
from proworksim.storage import read_json

PLAN = first.ROOT / "artifacts/software-benchmark-v236-1/compact-decisions-r1"
RUN = first.ROOT / "runs/software-benchmark-v236-1/compact-decisions-r1"


def short_wire(row, arm):
    w = original(row, arm)
    p = w["tools"][0]["function"]["parameters"]
    props = p["properties"]
    del props["cost_and_check"], props["reason"]
    props["extra_coordination"] = enum(["none", "one_handoff", "multiple_handoffs"])
    props["verification"] = enum(
        [
            "public_test",
            "dependency_receipt",
            "conflict_retest",
            "independent_patch_review",
            "submission_receipt",
            "inspect_evidence",
        ]
    )
    p["required"] = list(props)
    w["messages"][0]["content"] += (
        " Return only the function call with these short fields. extra_coordination estimates added coordination over the current assignments; verification names the check for the proposed next step. Activation reserves are conservative capacity bounds. Existing workers still consume tokens under KEEP."
    )
    view = json.loads(w["messages"][1]["content"])
    for detail in view["options"].values():
        detail["additional_activation_reserve"] = detail.pop("activation_reserve")
    w["messages"][1]["content"] = compact(view)
    return w


def check(row, body):
    return validate(row, body, schema_builder=short_wire)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    panel = read_json(first.PLAN / "panel.json")
    base = read_json(first.PLAN / "protocol.json")
    initial = read_json(first.PLAN / "results.json")
    spec = {k: v for k, v in base.items() if k != "files"}
    spec.update(
        previous_balance=initial["balance_nanoyuan"],
        previous_results=reference(first.PLAN / "results.json"),
        files=[
            reference(q)
            for q in (
                first.PLAN / "panel.json",
                Path(__file__),
                Path(first.__file__),
                first.ROOT / "src/proworksim/software_stage_response_v236.py",
            )
        ],
        amendment="New attempts on all 12 matched states. Same labels, evidence, budgets, existing support, scoring and gate. Replace long cost explanations by cost and verification enums; explicitly distinguish the incremental activation reservation from worker spend. No replacement of first series.",
    )
    dest = PLAN / "protocol.json"
    if args.freeze:
        if dest.exists() and read_json(dest) != spec:
            raise ValueError("Frozen revision differs")
        first.save(dest, spec)
        return
    if read_json(dest) != spec:
        raise ValueError("Frozen revision differs")
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fn = first.execute
        first.prior.clone_function(
            fn, {**fn.__globals__, "wire": short_wire, "validate": check, "RUN": RUN, "PLAN": PLAN}
        )(panel, spec, namespace="v236.1", opening_balance=spec["previous_balance"])


if __name__ == "__main__":
    main()
