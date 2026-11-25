"""Prospective paired decision calls on real historical states with a separate masked probe."""

import argparse
import fcntl
import json
import math
from pathlib import Path
import random
import sys
from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_three_graph_v240 import (
    PLAN,
    RUN,
    ROOT,
    MAIN,
    EXTRA,
    sources,
    prior,
    policy,
    freeze,
    read_json,
)
from proworksim.software_benchmark_candidates_v054 import reference

first = prior.first


def wire(row):
    return policy.baseline.request(row) if row["arm"] == "P0" else policy.request(row)


def design():
    sites = sources()
    ref = read_json(PLAN / "references.json")
    random.Random(2402).shuffle(sites)
    rows = []
    for i, s in enumerate(sites):
        order = ["P0", "P1"] if i % 2 == 0 else ["P1", "P0"]
        for rep, seq in ((1, order), (2, order[::-1])):
            for arm in seq:
                rows.append(
                    {
                        **s,
                        "site": s["id"],
                        "id": f"{s['id']}_{arm}_{rep}",
                        "arm": arm,
                        "repeat": rep,
                        "probe_id": ref[s["id"]]["probe_id"],
                    }
                )
    prev = read_json(prior.PLAN / "results.json")
    files = [
        Path(__file__),
        Path(policy.__file__),
        Path(policy.baseline.__file__),
        Path(first.__file__),
        ROOT / "tools/prepare_three_graph_v240.py",
        MAIN / "panel.json",
        EXTRA / "additional-states.json",
        EXTRA / "natural-a5.json",
        *(PLAN / p for p in ("references.json", "cpu-controls.json", "worker-preflight.json")),
    ]
    return rows, dict(
        labels=[r["id"] + "-structured" for r in rows],
        case="structure",
        arm_limit=first.LIMIT,
        account_cap_nanoyuan=first.prior.CAP,
        opening_balance=prev["balance_nanoyuan"] - prev["held_nanoyuan"],
        worst_pair_nanoyuan=len(rows) * first.LIMIT * 8000,
        files=[reference(p) for p in files],
        design="15 original real states (A1/2/3/4/stable =3/3/2/3/4), natural A5 vacant. P0 v239.3 unchanged, P1 three graphs. ABBA/BAAB, two independent calls per arm, 60 main and four masked probe calls. DeepSeek Flash nonthinking with identical 2048 output and 8192 request envelope. No resampling.",
        metrics="All 30 decisions per arm in denominator. Exact obligation sets preadjudicated; dependency first actions for missing references prospectively harmonized to CHECK or INSPECT. P1 readout of one frozen readiness/completion probe per state; P0 did not report these or anomaly type. Patch applicable if graph is legal, choice accepted by reviewers and patch operations tied to applicable obligations (also separate changed-only counts). Retention micro numerator: intersection of predicted labels and consensus due (intersection of all acceptable sets), denominator: all such obligatory items, includes invalid/unknown, excludes sites with no consensus labels. Report raw and compiled. Macro-average per state/task/repository separately.",
        gate="P1 final obligations >=26/30, first action >=27/30, readiness >=26/30, legal patches >=29/30 and no missing-evidence CHANGE (two valid probes). No positive credit for omission; exact-set primary. No C/N updates. If admitted, run first two preflight-eligible complete pairs in roster order using replicate one and archived checks, preserving five-million team budget including shared prefix and OSA call. Never force a CHANGE.",
        hold_unit_nanoyuan=8000,
        max_output=2048,
    )


def observe(row, body):
    model = policy.baseline if row["arm"] == "P0" else policy
    result = {"valid": False, "patch_legal": False}
    try:
        d = model.parse(row, body)
        c = model.compile_decision(row, d)
        g = policy.base.apply_patch(row, c["patch"])
        result.update(
            patch_legal=True, option=c["patch"]["option"], change=c["disposition"] == "CHANGE"
        )
        binding = model.dispatch(row, c, g)
        if row["arm"] == "P0":
            nodes = model.snapshot(row)
            raw = {nodes[k]["action"] for k in d["current_obligations"]}
            effective = {nodes[k]["action"] for k in c["obligations"]}
        else:
            _, nodes, _ = policy.build(row)
            raw = {nodes[k]["label"] for k in d["current_obligations"]}
            effective = {nodes[k]["label"] for k in c["effective"]}
            result.update(
                anomaly=d["anomaly"],
                completion=d["probe_completion"],
                readiness=d["probe_readiness"],
                specific_action=c["execution"].get("dependency_action"),
                patch_links=c["patch_links"],
                added=c["added"],
                subsequent=c["execution"]["subsequent"],
            )
        result.update(
            valid=True,
            choice=c["disposition"],
            raw=sorted(raw),
            effective=sorted(effective),
            binding=binding,
            basis=d["basis"],
        )
    except (ValueError, KeyError, TypeError, ValidationError) as e:
        result["error"] = str(e).splitlines()[0][:300]
    return result


def reconcile(rows, spec, meter, *, namespace):
    refs = read_json(PLAN / "references.json")
    records = []
    with meter.db() as db:
        for row in rows:
            sid = row["site"]
            ref = refs[sid]
            label = row["id"] + "-structured"
            r = dict(
                id=sid,
                arm=row["arm"],
                repeat=row["repeat"],
                category=row["reference_type"],
                task=row["instance"],
                repo=row["instance"].split("__")[0],
                status="unknown",
                due=len(ref["consensus_due"]),
            )
            records.append(r)
            charges = db.execute(
                "select id,status,tokens,cost,provider_id from requests where slot=?",
                (namespace + ":structure:" + label,),
            ).fetchall()
            if len(charges) != 1 or charges[0][1] != "settled":
                if (RUN / label / "error.json").exists():
                    r["transport"] = read_json(RUN / label / "error.json")
                continue
            rid, _, tokens, cost, provider = charges[0]
            f = RUN / label / "api" / rid.rsplit(":", 1)[-1]
            body = read_json(f / "response.json")
            u = read_json(f / "usage.json")
            if (
                wire(row) != read_json(f / "request.json")["payload"]["wire"]
                or body["id"] != provider
                or tokens != u["total_tokens"]
                or cost != u["peak_cost_nanoyuan"]
            ):
                raise ValueError("Receipt mismatch")
            r.update(
                status="settled",
                response=reference(f / "response.json"),
                input=u["input_tokens"],
                output=u["output_tokens"],
                cost_nanoyuan=cost,
                **observe(row, body),
            )
            if not r.get("valid"):
                continue
            for k in ("raw", "effective"):
                r[k + "_ok"] = any(set(r[k]) == set(a) for a in ref["obligations"])
                r[k + "_retained"] = len(set(r[k]) & set(ref["consensus_due"]))
            r.update(
                first_ok=r["binding"]["action"] in ref["actions"],
                choice_ok=r["choice"] in ref["choices"],
            )
            if row["arm"] == "P1":
                r.update(
                    readiness_ok=r["readiness"] == ref["readiness"],
                    completion_ok=r["completion"] == ref["completion"],
                    anomaly_ok=r["anomaly"] == ref["category"],
                )
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
    summary = {}
    macro = {}
    for arm in ("P0", "P1"):
        group = [r for r in records if r["id"] != "gap" and r["arm"] == arm]
        summary[arm] = {}
        fields = [
            "valid",
            "raw_ok",
            "effective_ok",
            "first_ok",
            "patch_legal",
            "choice_ok",
            "due",
            "raw_retained",
            "effective_retained",
            "change",
        ] + (["anomaly_ok", "readiness_ok", "completion_ok"] if arm == "P1" else [])
        for cat in ["ALL", "A1", "A2", "A3", "A4", "STABLE"]:
            selected = [r for r in group if cat == "ALL" or r["category"] == cat]
            summary[arm][cat] = dict(
                n=len(selected), **{k: sum(r.get(k, 0) for r in selected) for k in fields}
            )
        macro[arm] = {}
        for cluster in ("id", "task", "repo"):
            values = set(r[cluster] for r in group)
            result = {}
            for metric in ("effective_ok", "first_ok"):
                rates = []
                for value in values:
                    subset = [r for r in group if r[cluster] == value]
                    rates.append(sum(bool(r.get(metric)) for r in subset) / len(subset))
                result[metric] = sum(rates) / len(rates)
            macro[arm][cluster] = dict(n=len(values), **result)
    s = summary["P1"]["ALL"]
    probes = [r for r in records if r["id"] == "gap" and r["arm"] == "P1"]
    gate = (
        s["effective_ok"] >= 26
        and s["first_ok"] >= 27
        and s["readiness_ok"] >= 26
        and s["patch_legal"] >= 29
        and all(r.get("valid") and not r["change"] for r in probes)
    )
    first.save(
        PLAN / "results.json",
        dict(
            records=records,
            summary=summary,
            macro=macro,
            worker_gate=gate,
            settled=sum(r["status"] == "settled" for r in records),
            cost_nanoyuan=sum(r.get("cost_nanoyuan", 0) for r in records),
            balance_nanoyuan=meter.cap - paid,
            held_nanoyuan=held,
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
            raise ValueError("Frozen materials differ")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fn = first.run
            prior.prior.previous.prior.old.clone_function(
                fn,
                {
                    **fn.__globals__,
                    "RUN": RUN,
                    "ThreadPoolExecutor": prior.prior.previous.BalancedPool,
                    "wire": wire,
                    "reconcile": reconcile,
                },
            )(rows, spec, namespace="v240.2")
