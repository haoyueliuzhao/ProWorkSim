"""Compare the incumbent terminal-submission prompt with package-scoped commitment guidance."""

import argparse
import fcntl
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_obligation_prompt_submission_v240_3 as incumbent
from proworksim import software_commitment_prompt_v240_4 as revised
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import read_json

trial = incumbent.trial
PLAN = trial.ROOT / "artifacts/software-benchmark-v240-4/commitment-r1"
RUN = trial.ROOT / "runs/software-benchmark-v240-4/commitment-r1"
EXTRA = trial.previous.EXTRA
NEW_PROBES = {
    "x01": ("work_impl/complete_package", "BLOCKED", "UNSATISFIED"),
    "x02": ("core_kernS_fix/independent_review", "BLOCKED", "UNSATISFIED"),
    "x03": ("work_root/diagnose_failure", "READY", "UNSATISFIED"),
}


def references():
    refs = trial.references()
    for r in read_json(EXTRA / "agreed-reference.json"):
        if r["id"] not in NEW_PROBES:
            continue
        key, ready, completion = NEW_PROBES[r["id"]]
        refs[r["id"]] = {
            **r,
            "probe_id": key,
            "readiness": ready,
            "completion": completion,
            "consensus_due": sorted(set.intersection(*(set(s) for s in r["obligations"]))),
        }
    return refs


def wire(row):
    if row["arm"] == "BASE":
        return incumbent.wire({**row, "arm": "TEXT"})
    return json.loads(json.dumps(revised.request(row), allow_nan=False))


def design():
    base_rows, spec = incumbent.design()
    states = {r["site"]: {**r, "id": r["site"]} for r in base_rows}
    refs = references()
    for r in read_json(EXTRA / "additional-states.json"):
        if r["id"] in NEW_PROBES:
            states[r["id"]] = {**r, "probe_id": refs[r["id"]]["probe_id"]}
    sites = sorted(states)
    random.Random(2404).shuffle(sites)
    rows = []
    for i, sid in enumerate(sites):
        s = states[sid]
        order = trial.ARMS if i % 2 == 0 else trial.ARMS[::-1]
        for rep, seq in ((1, order), (2, order[::-1])):
            for arm in seq:
                rows.append(
                    {**s, "site": sid, "id": f"{sid}_{arm}_{rep}", "arm": arm, "repeat": rep}
                )
        a, b = (wire({**s, "arm": arm}) for arm in trial.ARMS)
        assert a["messages"][0].pop("content") != b["messages"][0].pop("content") and a == b
        assert s["probe_id"] in trial.previous.policy.build(s)[1]
    last = read_json(incumbent.PLAN / "results.json")
    spec.update(
        labels=[r["id"] + "-structured" for r in rows],
        opening_balance=last["balance_nanoyuan"] - last["held_nanoyuan"],
        worst_pair_nanoyuan=len(rows) * trial.previous.first.LIMIT * 8000,
        files=[
            *spec["files"],
            reference(Path(__file__)),
            reference(Path(revised.__file__)),
            reference(incumbent.PLAN / "results.json"),
            reference(EXTRA / "additional-states.json"),
            reference(EXTRA / "agreed-reference.json"),
        ],
        addition=revised.COMMITMENT_GUIDANCE,
        terminal_instruction=revised.SUBMISSION,
        scope="Prompt-only v240.4. BASE=v240.3 submission-r2 TEXT. TEXT=replace its field guidance, preserving the terminal tool instruction. Unchanged v240 compiler, no projection. 15 main + 4 prior challenge + 3 additional historical boundaries not used in v240.3 prompt comparisons + 1 masked control. Two fresh calls per site per arm, counterbalanced; no resampling or Worker runs.",
        scoring="Primary raw exact on main, secondary confirm over-inclusion and consensus retention. Adopt only if main raw exact improves, consensus raw retention does not fall, and both probes valid without change. Preserve original gate. Separate prior challenge and additional three; report targeted dependency raw and first-step paired counts, structural validity, state readout and cost. Development estimates only.",
    )
    return rows, spec


def summarize():
    result = read_json(PLAN / "results.json")
    sites = {
        "prior_challenge": set(trial.PROBES),
        "additional": set(NEW_PROBES),
        "dependency": {"q14", "x04", "y04"},
    }
    out = {}
    for name, ids in sites.items():
        out[name] = {}
        for arm in trial.ARMS:
            g = [r for r in result["records"] if r["site"] in ids and r["arm"] == arm]
            out[name][arm] = dict(
                n=len(g),
                **{
                    k: sum(r.get(k, 0) for r in g)
                    for k in (
                        "raw_ok",
                        "effective_ok",
                        "first_ok",
                        "readiness_ok",
                        "completion_ok",
                        "valid",
                        "raw_extra",
                        "raw_retained",
                        "due",
                    )
                },
            )
    trial.previous.first.save(PLAN / "subgroups.json", out)
    incumbent.CLONE(
        incumbent.diagnostics.main, {**incumbent.diagnostics.main.__globals__, "PLAN": PLAN}
    )()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    rows, spec = design()
    path = PLAN / "protocol.json"
    if args.freeze:
        if path.exists() and read_json(path) != spec:
            raise ValueError("Frozen materials differ")
        trial.previous.first.save(path, spec)
    else:
        if read_json(path) != spec:
            raise ValueError("Frozen materials differ")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rec = incumbent.CLONE(
                trial.reconcile,
                {
                    **trial.reconcile.__globals__,
                    "RUN": RUN,
                    "PLAN": PLAN,
                    "wire": wire,
                    "references": references,
                    "PROBES": {**trial.PROBES, **NEW_PROBES},
                },
            )
            fn = trial.previous.first.run
            incumbent.CLONE(
                fn,
                {
                    **fn.__globals__,
                    "RUN": RUN,
                    "wire": wire,
                    "reconcile": rec,
                    "ThreadPoolExecutor": trial.previous.prior.prior.previous.BalancedPool,
                },
            )(rows, spec, namespace="v240.4-commitments")
        summarize()
