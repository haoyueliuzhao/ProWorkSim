"""Independent prompt-format follow-up to the completed v240.3 wording experiment."""

import argparse
import fcntl
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_obligation_prompt_v240_3 as trial
import summarize_obligation_prompt_v240_3 as diagnostics
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import read_json

PLAN = trial.ROOT / "artifacts/software-benchmark-v240-3/submission-r2"
RUN = trial.ROOT / "runs/software-benchmark-v240-3/submission-r2"
DELIVERY = " Submit the arguments through exactly one activate_organization tool call. A JSON object written in the assistant message does not execute the plan."
CLONE = trial.previous.prior.prior.previous.prior.old.clone_function


def wire(row):
    w = trial.wire({**row, "arm": "TEXT"})
    if row["arm"] == "TEXT":
        original = trial.wire({**row, "arm": "BASE"})["messages"][0]["content"]
        start = original.removesuffix(" Return exactly one activate_organization call.")
        if start == original:
            raise ValueError("Missing original terminal instruction")
        w["messages"][0]["content"] = start + trial.candidate.ADDITION + DELIVERY
    return w


def design():
    rows, _ = trial.design()
    groups = {}
    for row in rows:
        groups.setdefault(row["site"], {})[row["arm"], row["repeat"]] = row
    sites = sorted(groups)
    random.Random(24032).shuffle(sites)
    rows = []
    for i, site in enumerate(sites):
        order = trial.ARMS if i % 2 == 0 else trial.ARMS[::-1]
        for rep, seq in ((1, order), (2, order[::-1])):
            for arm in seq:
                rows.append(groups[site][arm, rep])
        left, right = (wire({**rows[-1], "arm": a}) for a in trial.ARMS)
        assert left["messages"][0]["content"] != right["messages"][0]["content"]
        del left["messages"][0]["content"], right["messages"][0]["content"]
        assert left == right
    previous = read_json(trial.PLAN / "results.json")
    _, original = trial.design()
    spec = {
        **original,
        "labels": [r["id"] + "-structured" for r in rows],
        "opening_balance": previous["balance_nanoyuan"] - previous["held_nanoyuan"],
        "files": [
            *original["files"],
            reference(Path(__file__)),
            reference(trial.PLAN / "results.json"),
        ],
        "scope": "New, independently charged A/B experiment. BASE=first trial's appended guidance. TEXT=same decision guidance followed by a final explicit tool-submission requirement in place of the original tool-call sentence. No decoder, schema or compiler change. Same cohort and limits. All calls repeated independently, no resampling.",
        "scoring": "Predeclare paired arm comparison: test whether BASE->TEXT improves main valid response count while preserving or improving raw exact and consensus retention. Report challenge separately, keep original pilot gates and all denominators. Descriptive results only; no full Worker runs.",
        "terminal_instruction": DELIVERY,
    }
    return rows, spec


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    a = p.parse_args()
    rows, spec = design()
    dest = PLAN / "protocol.json"
    if a.freeze:
        if dest.exists() and read_json(dest) != spec:
            raise ValueError("Frozen protocol differs")
        trial.previous.first.save(dest, spec)
    else:
        if read_json(dest) != spec:
            raise ValueError("Frozen protocol differs")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rec = CLONE(
                trial.reconcile,
                {**trial.reconcile.__globals__, "RUN": RUN, "PLAN": PLAN, "wire": wire},
            )
            fn = trial.previous.first.run
            CLONE(
                fn,
                {
                    **fn.__globals__,
                    "RUN": RUN,
                    "ThreadPoolExecutor": trial.previous.prior.prior.previous.BalancedPool,
                    "wire": wire,
                    "reconcile": rec,
                },
            )(rows, spec, namespace="v240.3-submission")
        CLONE(diagnostics.main, {**diagnostics.main.__globals__, "PLAN": PLAN})()
