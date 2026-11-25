"""Prospective A/D comparison after v237.2: amend instructions at the point of use."""

import argparse
import fcntl
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_decision_clarity_v237_2 as trial
from prepare_decision_precision_v237_3 import PLAN, RUN, freeze
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import read_json

old, first = trial.old, trial.first


def wire(row):
    w = old.wire(row)
    if row["arm"] == "D":
        props = w["tools"][0]["function"]["parameters"]["properties"]
        props["work"]["properties"]["obligations"]["description"] += (
            " Include a second obligation only if it can start on the current artifact now. "
            "Put work that must wait for the first result in later_checks. If the latest receipt "
            "clears the only observed obstacle, continue_progress is sufficient."
        )
        props["keep"]["properties"]["blockers"]["description"] = (
            "Receipt IDs that show why current roles alone are blocked. If selecting CHANGE, "
            "cite at least one here. If no such obstacle is evidenced, reconsider the change."
        )
    return w


def design():
    old_rows, _ = first.design()
    fresh = read_json(PLAN / "additional-states.json")
    rows = [
        {**r, "id": r["id"] + arm, "sid": r["id"], "arm": arm}
        for r in [*old_rows, *fresh]
        for arm in ("A", "D")
    ]
    labels = [r["id"] + "-structured" for r in rows]
    random.Random(2373).shuffle(labels)
    paths = [
        Path(__file__),
        Path(trial.__file__),
        Path(old.__file__),
        Path(first.__file__),
        first.PLAN / "panel.json",
        first.PLAN / "independent-review.json",
        PLAN / "additional-states.json",
        PLAN / "independent-review.json",
    ]
    return rows, dict(
        case="structure",
        labels=labels,
        account_cap_nanoyuan=first.prior.CAP,
        arm_limit=first.LIMIT,
        worst_pair_nanoyuan=len(labels) * first.LIMIT * 8000,
        opening_balance=read_json(trial.PLAN / "results.json")["available_after_settled_nanoyuan"],
        files=[reference(p) for p in paths],
        conditions="A is unmodified v237.1. D adds only two field descriptions. Same schema, validator, system and data. No retries.",
        gate="To replace A for worker continuation, D must be valid on >=9/12, correct on >=8/12 old sites, request information on the separate gap probe, correctly name immediate obligations on >=3/4 fresh sites with strict improvement over paired A, and have no invalid or independently unacceptable fresh decision. Worker delivery is a distinct endpoint.",
    )


def reconcile(rows, spec, meter, *, namespace):
    refs = {
        r["id"]: r
        for path in (first.PLAN, PLAN)
        for r in read_json(path / "independent-review.json")["states"]
    }
    records = []
    with meter.db() as db:
        for row in rows:
            arm, sid = row["arm"], row["sid"]
            label = row["id"] + "-structured"
            slot = namespace + ":structure:" + label
            r = dict(state=sid, arm=arm, status="unknown")
            records.append(r)
            charges = db.execute(
                "select id,status,tokens,cost,provider_id from requests where slot=?", (slot,)
            ).fetchall()
            if len(charges) != 1 or charges[0][1] != "settled":
                continue
            rid, _, tokens, cost, provider = charges[0]
            folder = RUN / label / "api" / rid.rsplit(":", 1)[-1]
            response = read_json(folder / "response.json")
            usage = read_json(folder / "usage.json")
            if (
                read_json(folder / "request.json")["payload"]["wire"] != wire(row)
                or provider != response["id"]
                or tokens != usage["total_tokens"]
                or cost != usage["peak_cost_nanoyuan"]
            ):
                raise ValueError("Unreconciled request")
            r.update(
                input=usage["input_tokens"],
                output=usage["output_tokens"],
                cost_nanoyuan=cost,
                response=reference(folder / "response.json"),
            )
            try:
                d, g = old.validate(row, response)
                r.update(
                    status="valid",
                    decision=g["disposition"],
                    option=g["option"],
                    next_step=d["decision"]["next_step"],
                    obligations=d["work"]["obligations"],
                )
                if sid != "gap":
                    ref = refs[sid]
                    r.update(
                        correct=trial.obligations(row, d, ref, sid.startswith("s")),
                        acceptable=r["decision"]
                        in ref.get("acceptable_decisions", [ref["preferred"]]),
                    )
            except (TypeError, KeyError, ValueError) as e:
                r.update(status="invalid", error=str(e)[:300])
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
    stats = {}
    for arm in ("A", "D"):
        for prefix in ("s", "n"):
            group = [r for r in records if r["arm"] == arm and r["state"].startswith(prefix)]
            stats[arm + prefix] = dict(
                valid=sum(r["status"] == "valid" for r in group),
                correct=sum(bool(r.get("correct")) for r in group),
                acceptable=sum(bool(r.get("acceptable")) for r in group),
            )
    old_set, new_set = stats["Ds"], stats["Dn"]
    gap = next(r for r in records if r["arm"] == "D" and r["state"] == "gap")
    gate = (
        old_set["valid"] >= 9
        and old_set["correct"] >= 8
        and gap.get("decision") == "ABSTAIN"
        and new_set["correct"] >= 3
        and new_set["correct"] > stats["An"]["correct"]
        and new_set["acceptable"] == 4
    )
    first.save(
        PLAN / "results.json",
        dict(
            records=records,
            summary=stats,
            worker_gate=gate,
            settled=sum("cost_nanoyuan" in r for r in records),
            total_cost_nanoyuan=sum(r.get("cost_nanoyuan", 0) for r in records),
            available_after_settled_nanoyuan=meter.cap - paid,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    rows, spec = design()
    if args.freeze:
        freeze("protocol.json", spec)
    else:
        if read_json(PLAN / "protocol.json") != spec:
            raise ValueError("Protocol differs")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fn = first.run
            old.clone_function(
                fn, {**fn.__globals__, "RUN": RUN, "wire": wire, "reconcile": reconcile}
            )(rows, spec, namespace="v237.3")
