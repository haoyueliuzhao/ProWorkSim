"""Three matched decision conditions, one paid call per state and condition."""

import argparse
import fcntl
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_obligation_scope_v237_1 as old
from prepare_decision_clarity_v237_2 import PLAN, RUN, freeze_file
from proworksim import software_decision_clarity_v237_2 as clarity
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import read_json

first = old.first
ARMS = ("A", "B", "C")


def wire(row):
    if row["condition"] == "A":
        return old.wire(row)
    return clarity.request(row, old.wire, bound=row["condition"] == "C")


def validate(row, body):
    if row["condition"] == "A":
        return old.validate(row, body)
    return clarity.evaluate(row, body, old.wire, old.validate, bound=row["condition"] == "C")


def obligations(row, proposal, review, extra):
    allowed = set()
    if extra:
        readiness = {
            "complete_current_code_or_evidence": "complete_package",
            "independent_current_review": "independent_review",
            "evidence_version_differs_from_final_tree_revalidate": "verify_integrated_version",
        }
        for ev in row["evidence"].values():
            for pkg in ev.get("packages", []):
                allowed.update(readiness[g] for g in pkg["missing"] if g in readiness)
            if ev.get("fixed") == []:
                allowed.add("fix_tree")
    predicted = set(proposal["work"]["obligations"])
    return any(
        set(s) <= predicted <= set(s) | allowed for s in review["obligation_label_sets"] if s
    )


def design():
    primary, _ = first.design()
    holdout = read_json(PLAN / "additional-states.json")
    rows = [
        {**r, "source_id": r["id"], "id": r["id"] + arm, "condition": arm}
        for r in [*primary, *holdout]
        for arm in ARMS
    ]
    labels = [r["id"] + "-structured" for r in rows]
    random.Random(2372).shuffle(labels)
    paths = [
        Path(__file__),
        Path(clarity.__file__),
        Path(old.__file__),
        Path(first.__file__),
        first.PLAN / "panel.json",
        first.PLAN / "independent-review.json",
        PLAN / "additional-states.json",
        PLAN / "independent-review.json",
    ]
    spec = dict(
        case="structure",
        labels=labels,
        account_cap_nanoyuan=first.prior.CAP,
        opening_balance=read_json(old.PLAN / "results.json")["balance_nanoyuan"],
        arm_limit=first.LIMIT,
        worst_pair_nanoyuan=len(labels) * first.LIMIT * 8000,
        files=[reference(p) for p in paths],
        conditions={
            "A": "unmodified v237.1",
            "B": "receipt-first wording; original response fields",
            "C": "same reasoning prompt as B; controller supplies five graph-derived fields",
        },
        design="One independent generation per arm per state. Twelve reused states including one synthetic, four additional historical checkpoints independently reviewed without answers, one separate masked gap probe. No retries.",
        gate="C only: old panel valid >=9 and immediate obligations >=8 (historical grading); fresh panel valid >=3, exact immediate obligations >=3, all valid fresh decisions independently acceptable, probe valid ABSTAIN. Eligible restorable state required for worker execution. Report arm A and B on identical states regardless.",
    )
    return rows, spec


def reconcile(rows, spec, meter, *, namespace):
    original = read_json(first.PLAN / "independent-review.json")["states"]
    fresh = read_json(PLAN / "independent-review.json")["states"]
    refs = {x["id"]: x for x in [*original, *fresh]}
    records = []
    with meter.db() as db:
        for row in rows:
            sid, arm = row["source_id"], row["condition"]
            label = row["id"] + "-structured"
            slot = namespace + ":structure:" + label
            charges = db.execute(
                "select id,status,tokens,cost,provider_id from requests where slot=?", (slot,)
            ).fetchall()
            r = dict(state=sid, condition=arm, status="unknown")
            records.append(r)
            if len(charges) != 1 or charges[0][1] != "settled":
                continue
            rid, _, tokens, cost, provider = charges[0]
            folder = RUN / label / "api" / rid.rsplit(":", 1)[-1]
            body, usage = (read_json(folder / name) for name in ("response.json", "usage.json"))
            if (
                read_json(folder / "request.json")["payload"]["wire"] != wire(row)
                or tokens != usage["total_tokens"]
                or cost != usage["peak_cost_nanoyuan"]
                or body["id"] != provider
            ):
                raise ValueError("Provider request or ledger mismatch")
            r.update(
                input=usage["input_tokens"],
                output=usage["output_tokens"],
                cost_nanoyuan=cost,
                response=reference(folder / "response.json"),
            )
            try:
                d, graph = validate(row, body)
                r.update(
                    status="valid",
                    decision=d["decision"]["result"],
                    obligations=d["work"]["obligations"],
                    package=d["work"]["package"],
                    option=graph["option"],
                )
                if sid != "gap":
                    ref = refs[sid]
                    r.update(
                        correct=obligations(row, d, ref, sid.startswith("s")),
                        exact=obligations(row, d, ref, False),
                        preferred=r["decision"] == ref["preferred"],
                        acceptable=r["decision"]
                        in ref.get("acceptable_decisions", [ref["preferred"]]),
                    )
            except (KeyError, TypeError, ValueError) as e:
                r.update(status="invalid", error=str(e)[:300])
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
    stats = {}
    for arm in ARMS:
        stats[arm] = {}
        for prefix in ("s", "h"):
            group = [r for r in records if r["condition"] == arm and r["state"].startswith(prefix)]
            stats[arm][prefix] = {
                k: sum(bool(r.get(k)) for r in group)
                for k in ("correct", "exact", "preferred", "acceptable")
            }
            stats[arm][prefix]["valid"] = sum(r["status"] == "valid" for r in group)
    c = stats["C"]
    probe = next(r for r in records if r["state"] == "gap" and r["condition"] == "C")
    restorable = any(
        r["status"] == "valid" and r["condition"] == "C" and r["state"] in ("s01", "s06", "s03")
        for r in records
    )
    gate = (
        c["s"]["valid"] >= 9
        and c["s"]["correct"] >= 8
        and c["h"]["valid"] >= 3
        and c["h"]["exact"] >= 3
        and c["h"]["acceptable"] == c["h"]["valid"]
        and probe.get("decision") == "ABSTAIN"
        and restorable
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
        freeze_file("protocol.json", spec)
    else:
        if read_json(PLAN / "protocol.json") != spec:
            raise ValueError("Protocol differs")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fn = first.run
            old.clone_function(
                fn, {**fn.__globals__, "RUN": RUN, "wire": wire, "reconcile": reconcile}
            )(rows, spec, namespace="v237.2")
