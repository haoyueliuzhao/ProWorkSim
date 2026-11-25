"""Paired regression under the shared v245 contract, with a four-pair validity checkpoint."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fcntl
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_midtask_panel_v244 as prior
from proworksim import software_fair_delivery_v245 as fair
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_graph_budget_v229 import WindowLedger
from proworksim.software_benchmark_candidates_v054 import checked
from proworksim.storage import read_json

ROOT = prior.ROOT
PLAN = ROOT / "artifacts/software-benchmark-v245/fair-regression-r1"
RUN = ROOT / "runs/software-benchmark-v245/fair-regression-r1"
AUTH = RUN / "authority.json"
NS = "v245.1"
CAP = 150_000_000_000
ARMS = prior.ARMS
freeze = prior.ordinary.pairs.previous.freeze
save = prior.save
decision = clone_function(
    prior.decision, {**prior.decision.__globals__, "PLAN": PLAN, "Execution": fair.Execution}
)
generate = clone_function(
    prior.generate,
    {
        **prior.generate.__globals__,
        "decision": decision,
        "Execution": fair.Execution,
        "AUTH": AUTH,
        "NS": NS,
    },
)
run_pair = clone_function(
    prior.run_pair, {**prior.run_pair.__globals__, "RUN": RUN, "__file__": __file__}
)


# Use the same Worker restore, tools, scoring and OSA implementation in both arms.
decision = clone_function(
    prior.decision, {**prior.decision.__globals__, "Execution": fair.Execution, "PLAN": PLAN}
)
generate = clone_function(
    prior.generate,
    {
        **prior.generate.__globals__,
        "Execution": fair.Execution,
        "decision": decision,
        "NS": NS,
        "AUTH": AUTH,
    },
)
run_pair = clone_function(
    prior.run_pair, {**prior.run_pair.__globals__, "RUN": RUN, "__file__": __file__}
)


def review_wave(roster):
    from report_ordinary_successor_v243_2 import counts
    from contextlib import closing
    import sqlite3

    problems = []
    paid = 0
    with closing(sqlite3.connect((RUN / "ledger.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
        for case in roster:
            folder = RUN / str(case["index"])
            pair = read_json(folder / "completed.json")
            for arm in ARMS:
                dest = folder / arm
                row = pair[arm]
                if row["status"] != "closed" or any(
                    type(row.get("scores", {}).get(k, {}).get("resolved")) != bool
                    for k in ("code", "delivery")
                ):
                    problems.append([case["index"], arm, row])
                    continue
                end = read_json(dest / "result.json")
                d = read_json(dest / "decision.json")
                actual = counts(db, end["slot"])["paid"]
                paid += actual["nanoyuan"]
                if actual["tokens"] + case["prefix"] != end["logical_tokens"] + d["info"][
                    "osa_tokens"
                ] or end.get("cleanup_errors"):
                    problems.append([case["index"], arm, "accounting or cleanup"])
    return dict(
        cases=[c["instance"] for c in roster],
        paid_nanoyuan=paid,
        problems=problems,
        valid=not problems and paid <= CAP,
    )


def run_wave(roster, tasks):
    queue = [c for c in roster if not (RUN / str(c["index"]) / "completed.json").exists()]
    active = {}
    with ThreadPoolExecutor(2) as pool:
        while queue or active:
            while queue and len(active) < 2:
                case = queue[0]
                index = case["index"]
                prior.pre.check_images(
                    dict(roster=[dict(configuration=tasks[index]["configuration"])])
                )
                remaining = 5_000_000 - case["prefix"]
                try:
                    prior.pre.paired.reserve(
                        AUTH,
                        dict(
                            case=str(index),
                            account_cap_nanoyuan=CAP,
                            arm_limit=remaining,
                            worst_pair_nanoyuan=remaining * 16000,
                        ),
                        namespace=NS,
                        block=f"{NS}:{index}",
                    )
                except ValueError as exc:
                    if str(exc) != "Insufficient funds for this complete pair":
                        raise
                    if active:
                        break
                    save(RUN / "cash-boundary.json", dict(index=index, required=remaining * 16000))
                    return False
                queue.pop(0)
                active[pool.submit(run_pair, case, tasks[index])] = index
            if active:
                complete, _ = wait(active, return_when=FIRST_COMPLETED)
                for f in complete:
                    print(active.pop(f), f.result(), flush=True)
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    spec = read_json(PLAN / "protocol.json")
    for f in [spec["cpu"], spec["preflight"], *spec["files"]]:
        checked(f)
    roster = read_json(checked(spec["roster"]))["roster"]
    tasks = {
        r["index"]: r
        for r in read_json(
            ROOT / "artifacts/software-benchmark-v217/protocol-r1/candidate-tasks.json"
        )["rows"]
    }
    (RUN / "tmp").mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(RUN / "tmp")
    if args.output:
        dest = args.output.resolve()
        case = next(c for c in roster if dest.parent == RUN / str(c["index"]) and dest.name in ARMS)
        return generate(case, tasks[case["index"]], dest.name, dest)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        a = dict(
            scope="independent",
            ledger=str(RUN / "ledger.sqlite"),
            account_cap_CNY=150,
            stage_cap_CNY=150,
            cap_nanoyuan=CAP,
        )
        freeze(AUTH, a)
        if not Path(a["ledger"]).exists():
            WindowLedger.create_independent(a)
        for n in (4, 6):
            if not run_wave(roster[:n], tasks):
                break
            outcome = review_wave(roster[:n])
            save(PLAN / f"wave-{n}.json", outcome)
            if not outcome["valid"]:
                break


if __name__ == "__main__":
    main()
