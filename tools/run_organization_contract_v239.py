"""Balanced paired decision experiment with two independent generations per condition."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
from pathlib import Path
import random
import sys

from jsonschema import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_organization_contract_v239 import PLAN, RUN, ROOT, prior, frozen
from proworksim import software_organization_contract_v239 as contract
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_structured_activation import executable_decision
from proworksim.storage import read_json

first = prior.first
STEP = {
    "investigate_failure": "diagnose_failure",
    "finish_upstream": "release_upstream",
    "adopt_upstream": "adopt_upstream",
    "resolve_merge": "resolve_conflict",
    "retest_integrated_tree": "verify_integrated_version",
    "complete_package": "complete_package",
    "review_current_version": "independent_review",
    "continue_current_work": "continue_progress",
    "inspect_evidence": "gather_evidence",
    "report_blocker": "gather_evidence",
    "fix_and_submit": "fix_tree",
}


class BalancedPool(ThreadPoolExecutor):
    def map(self, fn, labels):
        groups = {}
        for label in labels:
            groups.setdefault(label.split("_")[0], []).append(label)

        def run_group(group):
            for label in group:
                fn(label)

        return super().map(run_group, groups.values())


def wire(row):
    return prior.old.wire(row) if row["arm"] == "P0" else contract.request(row)


def design():
    states = read_json(PLAN / "panel.json")
    refs = read_json(PLAN / "agreed-reference.json")
    assert {r["id"] for r in refs} == {r["id"] for r in states if r["id"] != "gap"}
    order = list(states)
    random.Random(2391).shuffle(order)
    rows = []
    for i, r in enumerate(order):
        arms = ["P0", "P1"] if i % 2 == 0 else ["P1", "P0"]
        for rep, sequence in [(1, arms), (2, arms[::-1])]:
            for arm in sequence:
                rows.append(
                    {
                        **r,
                        "id": f"{r['id']}_{arm}_{rep}",
                        "site": r["id"],
                        "arm": arm,
                        "repeat": rep,
                    }
                )
    labels = [r["id"] + "-structured" for r in rows]
    paths = [
        PLAN / n
        for n in (
            "panel.json",
            "review-packet.json",
            "ref-one.json",
            "ref-two.json",
            "agreed-reference.json",
            "cpu-replay.json",
        )
    ]
    paths.extend(
        [Path(contract.__file__), Path(__file__), Path(prior.old.__file__), Path(first.__file__)]
    )
    return rows, dict(
        case="structure",
        labels=labels,
        files=[reference(p) for p in paths],
        account_cap_nanoyuan=first.prior.CAP,
        opening_balance=read_json(prior.PLAN / "results.json")["available_after_settled_nanoyuan"],
        arm_limit=first.LIMIT,
        worst_pair_nanoyuan=len(labels) * first.LIMIT * 8000,
        per_request_output=2048,
        unit_max_nanoyuan_per_token=8000,
        design="14 real states out of 16 planned. Two natural A5 cases pending. Separate masked evidence probe. P0 unchanged v237.1, P1 one OSA plus deterministic compiler. Counterbalanced within state, 4 concurrent states, no retries. 56 main calls + 4 probe calls; same input/output bound and model settings, no external benchmark scoring.",
        scoring="Per 28 main calls/arm, unknown/invalid score zero. Legal output = accepted complete contract. Correct obligations = exact match to one acceptable set, separately correct action = first action type in accepted list. For P1 also report exact actor/package/action. Legitimate graph patch = parsed, native-equivalent and authorized; P0 complete contract validated. Report change-only denominator and correct organization choice separately. P0 first step fix_and_submit maps to fix_tree unless ready with a fixed tree. Unknowns not resampled.",
        gate="P1 legal >=95%, exact obligations >=85%, first action >=85%, legal patch >=95%; neither missing-evidence repeat activates CHANGE, at most one of the four stable states ever requests CHANGE (including malformed proposals with a readable choice). Two repeats per state are dependent. Natural A5 absent from denominators; a pass admits a limited pilot, not an A5 claim.",
        v240="Roster fixed before calls: q07 and q03 repeated failure, q14 blocked dependency, q11 verification. One same-prefix KEEP/OSA pair per case, first planned P1 decision only. No replacement or outcome selection. Missing restorable A2 checkpoint and incomplete block funding must be recorded. Same original team envelope, T1, tools and scoring. No C/N update.",
    )


def observe(row, body):
    result = {"valid": False, "patch_legal": False}
    try:
        calls = body["choices"][0]["message"].get("tool_calls") or []
        if len(calls) == 1:
            import json

            raw = json.loads(calls[0]["function"]["arguments"])
            if isinstance(raw, dict):
                choice = (
                    raw.get("choice")
                    if row["arm"] == "P1"
                    else (raw.get("decision") or {}).get("result")
                )
                result["requested_change"] = (
                    choice in [k for k in contract.options(row) if k != "K"]
                    if row["arm"] == "P1"
                    else choice == "CHANGE"
                )
        if row["arm"] == "P0":
            d, t = prior.old.validate(row, body)
            observed, t2, hold = executable_decision(row, d, t)
            step = STEP[d["decision"]["next_step"]]
            if d["decision"]["next_step"] == "fix_and_submit" and any(
                e.get("ready") and e.get("fixed") for e in row["evidence"].values()
            ):
                step = "submit"
            result.update(
                valid=True,
                patch_legal=True,
                choice=t["disposition"],
                effective=t2["disposition"],
                labels=d["work"]["obligations"],
                first_action=step,
                option=t["option"],
                hold=hold,
            )
        else:
            d = contract.parse(row, body)
            k = d["choice"]
            patch = contract.make_patch(row, "K" if k == "WAIT" else k)
            graph = contract.apply_patch(row, patch)
            result.update(patch_legal=True, option=patch["option"], operations=patch["operations"])
            compiled = contract.compile_decision(row, d)
            binding = contract.dispatch(row, compiled, graph, d["immediate"])
            result.update(
                valid=True,
                choice=compiled["disposition"],
                effective=compiled["disposition"],
                labels=sorted({contract.state(row)[v]["action"] for v in d["current_obligations"]}),
                first_action=binding["action"],
                binding=binding,
                plan=compiled["execution"],
            )
    except (KeyError, TypeError, ValueError, ValidationError, AttributeError) as e:
        result["error"] = str(e).splitlines()[0][:300]
    return result


def reconcile(rows, spec, meter, *, namespace):
    refs = {x["id"]: x for x in read_json(PLAN / "agreed-reference.json")}
    records = []
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
            rid, _, tok, cost, provider = charges[0]
            f = RUN / label / "api" / rid.rsplit(":", 1)[-1]
            body, usage = read_json(f / "response.json"), read_json(f / "usage.json")
            if (
                read_json(f / "request.json")["payload"]["wire"] != wire(row)
                or body["id"] != provider
                or tok != usage["total_tokens"]
                or cost != usage["peak_cost_nanoyuan"]
            ):
                raise ValueError("Receipt/ledger mismatch")
            r.update(
                status="settled",
                input=usage["input_tokens"],
                output=usage["output_tokens"],
                cost_nanoyuan=cost,
                response=reference(f / "response.json"),
                **observe(row, body),
            )
            ref = refs.get(r["id"])
            if ref and r.get("valid"):
                r.update(
                    obligation_ok=any(set(r["labels"]) == set(s) for s in ref["obligations"]),
                    order_ok=r["first_action"] in ref["actions"],
                    choice_ok=r["choice"] in ref["choices"],
                )
                if r["arm"] == "P1":
                    r["binding_ok"] = r["binding"] in ref["action_bindings"]
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
    summary = {}
    for arm in ("P0", "P1"):
        main = [r for r in records if r["arm"] == arm and r["id"] != "gap"]
        summary[arm] = {}
        for category in ("ALL", "A1", "A2", "A3", "A4", "STABLE"):
            group = [r for r in main if category == "ALL" or r["category"] == category]
            summary[arm][category] = dict(
                n=len(group),
                **{
                    k: sum(bool(x.get(k)) for x in group)
                    for k in (
                        "valid",
                        "patch_legal",
                        "obligation_ok",
                        "order_ok",
                        "choice_ok",
                        *(["binding_ok"] if arm == "P1" else []),
                    )
                },
            )
    main = summary["P1"]["ALL"]
    probe = [r for r in records if r["id"] == "gap" and r["arm"] == "P1"]
    stable = {
        r["id"]
        for r in records
        if r["arm"] == "P1" and r["category"] == "STABLE" and r.get("requested_change")
    }
    gate = (
        all(r["status"] == "settled" for r in records)
        and main["valid"] >= 27
        and main["patch_legal"] >= 27
        and min(main["obligation_ok"], main["order_ok"]) >= 24
        and all(r.get("valid") and r["effective"] != "CHANGE" for r in probe)
        and len(stable) <= 1
    )
    first.save(
        PLAN / "results.json",
        dict(
            records=records,
            summary=summary,
            worker_gate=gate,
            stable_changed=sorted(stable),
            pending_A5=2,
            settled=sum(r["status"] == "settled" for r in records),
            total_cost_nanoyuan=sum(r.get("cost_nanoyuan", 0) for r in records),
            balance_nanoyuan=meter.cap - paid,
            held_nanoyuan=held,
            worker_pairs=0,
            cn_updates=0,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    a = p.parse_args()
    rows, spec = design()
    if a.freeze:
        frozen("protocol.json", spec)
    else:
        if read_json(PLAN / "protocol.json") != spec:
            raise ValueError("Frozen protocol differs")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fn = first.run
            prior.old.clone_function(
                fn,
                {
                    **fn.__globals__,
                    "RUN": RUN,
                    "ThreadPoolExecutor": BalancedPool,
                    "wire": wire,
                    "reconcile": reconcile,
                },
            )(rows, spec, namespace="v239.1")
