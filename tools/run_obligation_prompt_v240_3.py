"""Matched live generations; vary only a suffix in the system message."""

import argparse
import fcntl
import json
from pathlib import Path
import random
import sys
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_three_graph_v240 as previous
from proworksim import software_obligation_prompt_v240_3 as candidate
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import read_json

ROOT = previous.ROOT
PLAN = ROOT / "artifacts/software-benchmark-v240-3/prompt-only-r1"
RUN = ROOT / "runs/software-benchmark-v240-3/prompt-only-r1"
EXTRA = previous.prior.PLAN
ARMS = ("BASE", "TEXT")
PROBES = {
    "y01": ("pkg_standalone_kbd/independent_review", "BLOCKED", "UNSATISFIED"),
    "y02": ("flush_wrapper/complete_package", "BLOCKED", "UNSATISFIED"),
    "y03": ("pkg_rst_header_rows/repair_target", "BLOCKED", "UNSATISFIED"),
    "y04": ("neither_mask/dependency/one_mask/EXECUTE_UPSTREAM_WORK", "CONDITIONAL", "UNKNOWN"),
}


def wire(row):
    fn = candidate.request if row["arm"] == "TEXT" else previous.policy.request
    return json.loads(json.dumps(fn(row), allow_nan=False))


def references():
    refs = read_json(previous.PLAN / "references.json")
    for ref in read_json(EXTRA / "agreed-reference.json"):
        k, ready, completion = PROBES[ref["id"]]
        refs[ref["id"]] = {
            **ref,
            "probe_id": k,
            "readiness": ready,
            "completion": completion,
            "consensus_due": sorted(set.intersection(*(set(s) for s in ref["obligations"]))),
        }
    return refs


def design():
    refs = references()
    states = previous.sources() + read_json(EXTRA / "states.json")
    random.Random(2403).shuffle(states)
    rows = []
    for i, s in enumerate(states):
        row = {**s, "probe_id": refs[s["id"]]["probe_id"]}
        order = ARMS if i % 2 == 0 else ARMS[::-1]
        before = wire({**row, "arm": "BASE"})
        after = wire({**row, "arm": "TEXT"})
        assert (
            after["messages"][0]["content"] == before["messages"][0]["content"] + candidate.ADDITION
        )
        after["messages"][0]["content"] = before["messages"][0]["content"]
        assert before == after and row["probe_id"] in previous.policy.build(s)[1]
        for rep, seq in ((1, order), (2, order[::-1])):
            for arm in seq:
                rows.append(
                    {
                        **row,
                        "site": s["id"],
                        "arm": arm,
                        "repeat": rep,
                        "id": f"{s['id']}_{arm}_{rep}",
                    }
                )
    prev = read_json(previous.PLAN / "results.json")
    paths = [
        Path(__file__),
        Path(candidate.__file__),
        Path(previous.__file__),
        Path(previous.policy.__file__),
        Path(previous.first.__file__),
        previous.PLAN / "references.json",
        previous.MAIN / "panel.json",
        previous.EXTRA / "additional-states.json",
        EXTRA / "states.json",
        EXTRA / "agreed-reference.json",
    ]
    return rows, dict(
        case="structure",
        labels=[r["id"] + "-structured" for r in rows],
        arm_limit=previous.first.LIMIT,
        account_cap_nanoyuan=previous.first.prior.CAP,
        opening_balance=prev["balance_nanoyuan"] - prev["held_nanoyuan"],
        worst_pair_nanoyuan=len(rows) * previous.first.LIMIT * 8000,
        files=[reference(p) for p in paths],
        addition=candidate.ADDITION,
        scope="Prompt-only decision test. Real calls to identical DeepSeek Flash non-thinking model and unchanged v240 graph, schema, compiler and dispatch. No post hoc projection in either arm. No Worker calls. Each state uses two independent calls per arm, reversed order on second repeat. No resampling.",
        scoring="Primary raw exact obligations against frozen acceptable sets on 15 main states; report final exact, over-inclusion (predicted set not a subset of any accepted set), consensus retention, readiness, first action, legality, cache and cost. Four previously reviewed challenge states unseen in v240 analyzed separately; one evidence probe excluded. Prefer revision for engineering use only if raw exact improves on main, required-item retention does not fall, and both probes avoid activation. Report original pilot thresholds separately. Descriptive site-matched contrasts; repetitions are not independent tasks.",
    )


def observe(row, body):
    # Both arms use the same unmodified v240 schema, compiler and dispatch.
    return previous.observe({**row, "arm": "P1"}, body)


def reconcile(rows, spec, meter, *, namespace):
    refs = references()
    records = []
    with meter.db() as db:
        for row in rows:
            sid = row["site"]
            ref = refs[sid]
            label = row["id"] + "-structured"
            r = dict(
                site=sid,
                arm=row["arm"],
                repeat=row["repeat"],
                group="probe" if sid == "gap" else "challenge" if sid in PROBES else "main",
                category=row["reference_type"],
                instance=row["instance"],
                due=len(ref["consensus_due"]),
                status="unknown",
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
            u = read_json(f / "usage.json")
            body = read_json(f / "response.json")
            if (
                wire(row) != read_json(f / "request.json")["payload"]["wire"]
                or provider != body["id"]
                or tokens != u["total_tokens"]
                or cost != u["peak_cost_nanoyuan"]
            ):
                raise ValueError("Provider accounting mismatch")
            r.update(
                status="settled",
                input=u["input_tokens"],
                output=u["output_tokens"],
                cache_hit=u["cache_hit_tokens"],
                cost_nanoyuan=cost,
                response=reference(f / "response.json"),
                **observe(row, body),
            )
            if not r.get("valid"):
                continue
            accepted = [set(s) for s in ref["obligations"]]
            for k in ("raw", "effective"):
                predicted = set(r[k])
                r[k + "_ok"] = predicted in accepted
                r[k + "_extra"] = not any(predicted <= s for s in accepted)
                r[k + "_retained"] = len(predicted & set(ref["consensus_due"]))
            r.update(
                first_ok=r["binding"]["action"] in ref["actions"],
                choice_ok=r["choice"] in ref["choices"],
                readiness_ok=r["readiness"] == ref["readiness"],
                completion_ok=r["completion"] == ref["completion"],
            )
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
    stats = {}
    paired = {}
    gates = {}
    for group in ("main", "challenge", "probe"):
        stats[group] = {}
        subset = [r for r in records if r["group"] == group]
        for arm in ARMS:
            items = [r for r in subset if r["arm"] == arm]
            stats[group][arm] = dict(
                n=len(items),
                **{
                    k: sum(r.get(k, 0) for r in items)
                    for k in (
                        "valid",
                        "raw_ok",
                        "effective_ok",
                        "raw_extra",
                        "effective_extra",
                        "raw_retained",
                        "effective_retained",
                        "due",
                        "first_ok",
                        "choice_ok",
                        "readiness_ok",
                        "completion_ok",
                        "patch_legal",
                        "change",
                        "input",
                        "output",
                        "cost_nanoyuan",
                    )
                },
            )
        counts = Counter()
        for sid in {r["site"] for r in subset}:
            delta = sum(
                bool(r.get("raw_ok")) * (1 if r["arm"] == "TEXT" else -1)
                for r in subset
                if r["site"] == sid
            )
            counts["improved" if delta > 0 else "worse" if delta < 0 else "tied"] += 1
        paired[group] = dict(counts)
    for arm in ARMS:
        m = stats["main"][arm]
        p = stats["probe"][arm]
        gates[arm] = (
            m["effective_ok"] >= 26
            and m["first_ok"] >= 27
            and m["readiness_ok"] >= 26
            and m["patch_legal"] >= 29
            and p["valid"] == 2
            and p["change"] == 0
        )
    previous.first.save(
        PLAN / "results.json",
        dict(
            records=records,
            summary=stats,
            paired_site_raw=paired,
            pilot_thresholds=gates,
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
    dest = PLAN / "protocol.json"
    if a.freeze:
        if dest.exists() and read_json(dest) != spec:
            raise ValueError("Frozen design differs")
        previous.first.save(dest, spec)
    else:
        if read_json(dest) != spec:
            raise ValueError("Frozen design differs")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fn = previous.first.run
            previous.prior.prior.previous.prior.old.clone_function(
                fn,
                {
                    **fn.__globals__,
                    "RUN": RUN,
                    "wire": wire,
                    "reconcile": reconcile,
                    "ThreadPoolExecutor": previous.prior.prior.previous.BalancedPool,
                },
            )(rows, spec, namespace="v240.3-prompt")
