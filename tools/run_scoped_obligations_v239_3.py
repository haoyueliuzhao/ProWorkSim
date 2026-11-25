"""Paired repair validation, retaining the original model answer and compiled obligation set."""

import argparse
import fcntl
import json
from pathlib import Path
import random
import sys
from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_scoped_obligations_v239_3 import PLAN, RUN, prior, freeze
from proworksim import software_scoped_obligations_v239_3 as repaired
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import read_json

first = prior.first
old = repaired.old
GROUPS = [
    ("original", prior.previous.PLAN, "panel.json"),
    ("previous_challenge", prior.PLAN, "additional-states.json"),
    ("fresh", PLAN, "states.json"),
]


def wire(row):
    return (old if row["arm"] == "BASE" else repaired).request(row)


def design():
    rows = []
    sources = [{**r, "group": g} for g, p, f in GROUPS for r in read_json(p / f)]
    random.Random(2393).shuffle(sources)
    for i, s in enumerate(sources):
        order = ["BASE", "FIX"] if i % 2 == 0 else ["FIX", "BASE"]
        for rep, seq in [(1, order), (2, order[::-1])]:
            for arm in seq:
                rows.append(
                    {
                        **s,
                        "site": s["id"],
                        "id": f"{s['id']}_{arm}_{rep}",
                        "arm": arm,
                        "repeat": rep,
                    }
                )
    labels = [r["id"] + "-structured" for r in rows]
    paths = [
        Path(__file__),
        Path(old.__file__),
        Path(repaired.__file__),
        Path(first.__file__),
        PLAN / "cpu.json",
        PLAN / "ref-a.json",
        PLAN / "ref-b.json",
    ]
    for _, p, f in GROUPS:
        paths.extend([p / f, p / "agreed-reference.json"])
    prev = read_json(prior.PLAN / "results.json")
    return rows, dict(
        case="structure",
        labels=labels,
        arm_limit=first.LIMIT,
        account_cap_nanoyuan=first.prior.CAP,
        opening_balance=prev["balance_nanoyuan"] - prev["held_nanoyuan"],
        worst_pair_nanoyuan=len(labels) * first.LIMIT * 8000,
        design="BASE actual v239.2, FIX scoped requirements and scheduling. Per state two independent calls per arm, ABBA/BAAB, four concurrent sites. 14 development + 4 prior challenge + 4 new decision boundaries plus separate gap probe. No model resampling. Same Flash non-thinking, limits, sampling and provider.",
        endpoints="Report per stratum exact raw and effective obligation matches, valid, patch legal, action, binding, decision, number of requirements added and out-of-scope labels. All planned responses in denominators. Preserve original >=27/28 legal/patch, >=24/28 obligations/order, valid probes without change, <=1/4 stable changes. Show model-only and compiled gates separately. Fresh panel diagnostic only. No code delivery inferred from a decision.",
        files=[reference(f) for f in paths],
    )


def controls():
    states = [r for _, p, f in GROUPS for r in read_json(p / f)]
    dispatched = 0
    for r in states:
        tasks = repaired.snapshot(r)
        for path, route in old.routes(r, tasks).items():
            d = dict(
                route=path,
                current_obligations=[route["immediate"]],
                basis=[next(iter(r["evidence"]))],
                reason="CPU",
                reconsider_after="receipt",
            )
            c = repaired.compile_decision(r, d)
            g = old.base.apply_patch(r, c["patch"])
            assert repaired.dispatch(r, c, g)["actor"] == route["actor"]
            assert set(c["obligations"]).issuperset(
                repaired.required(r, tasks, route["immediate"].partition("/")[0])
            )
            dispatched += 1
    table = {r["id"]: r for r in states}
    r = table["q03"]
    tasks = repaired.snapshot(r)
    p = r["targets"][0]
    assert p + "/repair_target" in repaired.required(r, tasks, p)
    r = table["x03"]
    tasks = repaired.snapshot(r)
    p = r["targets"][0]
    assert p + "/repair_target" not in repaired.required(r, tasks, p)
    r = table["x01"]
    tasks = repaired.snapshot(r)
    assert not any(v["action"] == "complete_package" for v in old.routes(r, tasks).values())
    from copy import deepcopy

    passed = deepcopy(r)
    last = list(passed["evidence"].values())[-1]
    last["public_test"]["passed"] = True
    assert any(
        v["action"] == "complete_package"
        for v in old.routes(passed, repaired.snapshot(passed)).values()
    )
    r = table["x04"]
    assert {"release_upstream", "gather_evidence"} <= {
        v["action"] for v in old.routes(r, repaired.snapshot(r)).values()
    }
    freeze(
        "cpu.json",
        dict(
            route_round_trips=dispatched,
            checks=[
                "scoped receipt floor",
                "unnamed failure has no compulsory target repair",
                "unsubstantiated completion deferred for failed shared version",
                "passing shared version restores independent package action",
                "upstream lookup and release offered separately",
            ],
            model_calls=0,
        ),
    )


def observe(row, body):
    policy = old if row["arm"] == "BASE" else repaired
    r = dict(valid=False, patch_legal=False)
    try:
        calls = body["choices"][0]["message"].get("tool_calls") or []
        if len(calls) == 1:
            raw = json.loads(calls[0]["function"]["arguments"])
            if isinstance(raw, dict):
                k = str(raw.get("route", "")).partition("|")[0]
                r["requested_change"] = k in old.options(row) and k != "K"
        d = policy.parse(row, body)
        c = policy.compile_decision(row, d)
        g = old.base.apply_patch(row, c["patch"])
        r.update(patch_legal=True, option=c["option"])
        binding = policy.dispatch(row, c, g)
        tasks = policy.snapshot(row)

        def tags(keys):
            return sorted({tasks[k]["action"] for k in keys})

        r.update(
            valid=True,
            choice=c["disposition"],
            binding=binding,
            raw=tags(d["current_obligations"]),
            effective=tags(c.get("obligations", d["current_obligations"])),
            added=c.get("required_added", []),
            outside=c.get("outside_focus", []),
            operations=c["patch"]["operations"],
            basis=d["basis"],
        )
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError) as e:
        r["error"] = str(e).splitlines()[0][:300]
    return r


def reconcile(rows, spec, meter, *, namespace):
    refs = {r["id"]: r for _, p, _ in GROUPS for r in read_json(p / "agreed-reference.json")}
    records = []
    with meter.db() as db:
        for row in rows:
            label = row["id"] + "-structured"
            r = dict(
                id=row["site"],
                arm=row["arm"],
                repeat=row["repeat"],
                group="probe" if row["site"] == "gap" else row["group"],
                category=row["reference_type"],
                status="unknown",
            )
            records.append(r)
            charges = db.execute(
                "select id,status,tokens,cost,provider_id from requests where slot=?",
                (namespace + ":structure:" + label,),
            ).fetchall()
            if len(charges) != 1 or charges[0][1] != "settled":
                error = RUN / label / "error.json"
                if error.exists():
                    r["error_detail"] = read_json(error)
                continue
            rid, _, tokens, cost, prov = charges[0]
            f = RUN / label / "api" / rid.rsplit(":", 1)[-1]
            body = read_json(f / "response.json")
            u = read_json(f / "usage.json")
            if (
                wire(row) != read_json(f / "request.json")["payload"]["wire"]
                or body["id"] != prov
                or tokens != u["total_tokens"]
                or cost != u["peak_cost_nanoyuan"]
            ):
                raise ValueError("Physical ledger mismatch")
            r.update(
                status="settled",
                response=reference(f / "response.json"),
                input=u["input_tokens"],
                output=u["output_tokens"],
                cost_nanoyuan=cost,
                **observe(row, body),
            )
            if r.get("valid") and r["id"] in refs:
                ref = refs[r["id"]]
                for k in ("raw", "effective"):
                    r[k + "_ok"] = any(set(r[k]) == set(s) for s in ref["obligations"])
                r.update(
                    order_ok=r["binding"]["action"] in ref["actions"],
                    binding_ok=r["binding"] in ref["action_bindings"],
                    choice_ok=r["choice"] in ref["choices"],
                )
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
    summary = {}
    for grp, _, _ in GROUPS:
        summary[grp] = {}
        for arm in ("BASE", "FIX"):
            group = [r for r in records if r["arm"] == arm and r["group"] == grp]
            summary[grp][arm] = dict(
                n=len(group),
                **{
                    f: sum(bool(r.get(f)) for r in group)
                    for f in (
                        "valid",
                        "patch_legal",
                        "order_ok",
                        "binding_ok",
                        "choice_ok",
                        "raw_ok",
                        "effective_ok",
                        "added",
                        "outside",
                    )
                },
            )
    m = summary["original"]["FIX"]
    hold = [r for r in records if r["arm"] == "FIX" and r["group"] == "probe"]
    stable = {
        r["id"]
        for r in records
        if r["arm"] == "FIX" and r["category"] == "STABLE" and r.get("requested_change")
    }
    base_gate = (
        min(m["valid"], m["patch_legal"]) >= 27
        and m["order_ok"] >= 24
        and len(stable) <= 1
        and all(r.get("valid") and r["choice"] != "CHANGE" for r in hold)
    )
    first.save(
        PLAN / "results.json",
        dict(
            records=records,
            summary=summary,
            consistent_complete_measurement=all(r["status"] == "settled" for r in records),
            stable_changed=sorted(stable),
            model_only_gate=base_gate and m["raw_ok"] >= 24,
            compiled_gate=base_gate and m["effective_ok"] >= 24,
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
    if a.freeze:
        controls()
    rows, spec = design()
    if a.freeze:
        freeze("protocol.json", spec)
    else:
        if read_json(PLAN / "protocol.json") != spec:
            raise ValueError("Frozen materials differ")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fn = first.run
            prior.previous.prior.old.clone_function(
                fn,
                {
                    **fn.__globals__,
                    "RUN": RUN,
                    "ThreadPoolExecutor": prior.previous.BalancedPool,
                    "wire": wire,
                    "reconcile": reconcile,
                },
            )(rows, spec, namespace="v239.3")
