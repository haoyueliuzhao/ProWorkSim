"""Prospective two-condition experiment with a separate blind diagnostic stratum."""

import argparse
import fcntl
import json
import random
from pathlib import Path
import sys
from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_obligation_boundary_v239_2 import PLAN, ROOT, RUN, freeze, previous
from proworksim import software_obligation_boundary_v239_2 as policy
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.storage import read_json

first = previous.first


def wire(row):
    return previous.prior.old.wire(row) if row["arm"] == "P0" else policy.request(row)


def design():
    sources = read_json(previous.PLAN / "panel.json") + read_json(PLAN / "additional-states.json")
    labels = read_json(previous.PLAN / "agreed-reference.json") + read_json(
        PLAN / "agreed-reference.json"
    )
    assert {r["id"] for r in labels} == {r["id"] for r in sources if r["id"] != "gap"}
    random.Random(2392).shuffle(sources)
    rows = []
    for i, s in enumerate(sources):
        arms = ["P0", "P1"] if i % 2 == 0 else ["P1", "P0"]
        for rep, seq in ((1, arms), (2, arms[::-1])):
            for arm in seq:
                rows.append(
                    {
                        **s,
                        "id": s["id"] + "_" + arm + "_" + str(rep),
                        "site": s["id"],
                        "arm": arm,
                        "repeat": rep,
                    }
                )
    schedule = [r["id"] + "-structured" for r in rows]
    paths = [
        Path(__file__),
        Path(policy.__file__),
        Path(policy.base.__file__),
        Path(previous.__file__),
        Path(first.__file__),
        Path(previous.prior.old.__file__),
        previous.PLAN / "panel.json",
        previous.PLAN / "agreed-reference.json",
        *(
            PLAN / x
            for x in (
                "additional-states.json",
                "ref-one.json",
                "ref-two.json",
                "agreed-reference.json",
                "natural-a5.json",
                "cpu-controls.json",
            )
        ),
    ]
    return rows, dict(
        labels=schedule,
        case="structure",
        arm_limit=first.LIMIT,
        account_cap_nanoyuan=first.prior.CAP,
        opening_balance=read_json(previous.PLAN / "results.json")["balance_nanoyuan"],
        worst_pair_nanoyuan=len(rows) * first.LIMIT * 8000,
        max_output_tokens=2048,
        files=[reference(p) for p in paths],
        model="deepseek-flash non-thinking temperature/top_p 1.0; identical bounds",
        design="Unmodified P0 v237.1 and revised receipt-grounded P1. Four serial calls per site, ABBA or BAAB. No resamples. 14 development sites (56), four separately reviewed additional historical sites (16), masked probe (4). Both conditions have independent new calls.",
        scoring="Retain previous strict set match and separate order/choice; unknowns or invalids zero. Secondary actor/package binding scored only for P1. Development gate unchanged: >=27/28 valid and patch-legal, >=24/28 obligations/order, both probe repeats valid without activation, <=1/4 stable sites requesting change. New sites are reported independently. Do not pool or substitute. Fixed-logic comparator reports the set of currently evidenced obligations and whether only one action is available.",
        followup="Retain ordered v240 roster and first P1 replicate. A2 lacks a same-boundary SDK restore. Do not substitute an earlier prefix. If admitted, assess paired resource authority and budget separately; no C/N update.",
    )


def observe(row, body):
    if row["arm"] == "P0":
        return previous.observe(row, body)
    r = dict(valid=False, patch_legal=False)
    try:
        calls = body["choices"][0]["message"].get("tool_calls") or []
        if len(calls) == 1:
            raw = json.loads(calls[0]["function"]["arguments"])
            if isinstance(raw, dict):
                opt = str(raw.get("route", "")).partition("|")[0]
                r["requested_change"] = opt in policy.options(row) and opt != "K"
        d = policy.parse(row, body)
        compiled = policy.compile_decision(row, d)
        graph = policy.base.apply_patch(row, compiled["patch"])
        r.update(patch_legal=True, option=compiled["option"])
        binding = policy.dispatch(row, compiled, graph)
        tasks = policy.snapshot(row)
        r.update(
            valid=True,
            choice=compiled["disposition"],
            effective=compiled["disposition"],
            labels=sorted({tasks[k]["action"] for k in d["current_obligations"]}),
            first_action=binding["action"],
            binding=binding,
            plan=compiled["execution"],
            operations=compiled["patch"]["operations"],
        )
    except (ValueError, KeyError, TypeError, ValidationError, AttributeError) as e:
        r["error"] = str(e).splitlines()[0][:300]
    return r


def metrics(group, arm):
    keys = ["valid", "patch_legal", "obligation_ok", "order_ok", "choice_ok"]
    if arm == "P1":
        keys.append("binding_ok")
    return dict(n=len(group), **{k: sum(bool(r.get(k)) for r in group) for k in keys})


def reconcile(rows, spec, meter, *, namespace):
    records = []
    refs = {
        r["id"]: r for p in [previous.PLAN, PLAN] for r in read_json(p / "agreed-reference.json")
    }
    with meter.db() as db:
        for row in rows:
            label = row["id"] + "-structured"
            r = dict(
                id=row["site"],
                arm=row["arm"],
                repeat=row["repeat"],
                category=row["reference_type"],
                status="unknown",
            )
            records.append(r)
            charges = db.execute(
                "select id,status,tokens,cost,provider_id from requests where slot=?",
                (namespace + ":structure:" + label,),
            ).fetchall()
            if len(charges) != 1 or charges[0][1] != "settled":
                continue
            rid, _, tokens, cost, provider = charges[0]
            folder = RUN / label / "api" / rid.rsplit(":", 1)[-1]
            body = read_json(folder / "response.json")
            u = read_json(folder / "usage.json")
            if (
                wire(row) != read_json(folder / "request.json")["payload"]["wire"]
                or body["id"] != provider
                or tokens != u["total_tokens"]
                or cost != u["peak_cost_nanoyuan"]
            ):
                raise ValueError("Usage or request mismatch")
            r.update(
                status="settled",
                input=u["input_tokens"],
                output=u["output_tokens"],
                cost_nanoyuan=cost,
                response=reference(folder / "response.json"),
                **observe(row, body),
            )
            if r.get("valid") and r["id"] in refs:
                ref = refs[r["id"]]
                r.update(
                    obligation_ok=any(set(s) == set(r["labels"]) for s in ref["obligations"]),
                    order_ok=r["first_action"] in ref["actions"],
                    choice_ok=r["choice"] in ref["choices"],
                )
                if row["arm"] == "P1":
                    r["binding_ok"] = r["binding"] in ref["action_bindings"]
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
    summary = {}
    for stratum, prefix in [("development", "q"), ("new", "x")]:
        summary[stratum] = {}
        for arm in ("P0", "P1"):
            group = [r for r in records if r["id"].startswith(prefix) and r["arm"] == arm]
            summary[stratum][arm] = {
                "ALL": metrics(group, arm),
                **{
                    c: metrics([r for r in group if r["category"] == c], arm)
                    for c in sorted({r["category"] for r in group})
                },
            }
    new = summary["development"]["P1"]["ALL"]
    probe = [r for r in records if r["id"] == "gap" and r["arm"] == "P1"]
    stable = {
        r["id"]
        for r in records
        if r["arm"] == "P1" and r["category"] == "STABLE" and r.get("requested_change")
    }
    admitted = (
        all(r["status"] == "settled" for r in records)
        and min(new["valid"], new["patch_legal"]) >= 27
        and min(new["order_ok"], new["obligation_ok"]) >= 24
        and len(stable) <= 1
        and all(r.get("valid") and r["effective"] != "CHANGE" for r in probe)
    )
    mechanics = []
    for row in rows:
        if row["arm"] != "P1" or row["repeat"] != 1 or row["site"] not in refs:
            continue
        tasks = policy.snapshot(row)
        paths = policy.routes(row, tasks)
        inferred = sorted(
            {
                t["action"]
                for t in tasks.values()
                if t["source"] not in ("workflow_successor", "satisfied", "unobserved")
            }
        )
        mechanics.append(
            dict(
                id=row["site"],
                program_labels=inferred,
                program_match=any(
                    set(inferred) == set(s) for s in refs[row["site"]]["obligations"]
                ),
                distinct_immediate_actions=sorted({v["immediate"] for v in paths.values()}),
                distinct_routes=len(paths),
            )
        )
    first.save(
        PLAN / "results.json",
        dict(
            records=records,
            summary=summary,
            mechanics=mechanics,
            worker_gate=admitted,
            stable_changed=sorted(stable),
            pending_A5=2,
            settled=sum(r["status"] == "settled" for r in records),
            cost_nanoyuan=sum(r.get("cost_nanoyuan", 0) for r in records),
            balance_nanoyuan=meter.cap - paid,
            held_nanoyuan=held,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    a = p.parse_args()
    rows, spec = design()
    if a.freeze:
        freeze("protocol.json", spec)
    else:
        if read_json(PLAN / "protocol.json") != spec:
            raise ValueError("Changed frozen run")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fn = first.run
            previous.prior.old.clone_function(
                fn,
                {
                    **fn.__globals__,
                    "RUN": RUN,
                    "ThreadPoolExecutor": previous.BalancedPool,
                    "wire": wire,
                    "reconcile": reconcile,
                },
            )(rows, spec, namespace="v239.2")
