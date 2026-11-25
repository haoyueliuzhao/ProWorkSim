"""Freeze and run one direct and one staged OSA decision per archived state."""

import argparse
import fcntl
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_osa_states_v236 import PLAN, save
import run_readiness_decisions_v235 as prior
from proworksim.software_stage_response_v236 import wire, options, validate, grade, RULES
from proworksim.software_context_panel_v231 import ROOT, PairedLedger
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_project_relations_v217 import identity
from proworksim.storage import read_json

RUN = ROOT / "runs/software-benchmark-v236/decision-differentiation-r1"
LIMIT = 6144


def freeze(panel):
    order = ["direct", "staged"] * 6
    random.Random(236).shuffle(order)
    assert (
        len(panel) == 12
        and len({(r["provenance"]["source"], tuple(r["provenance"]["ordinals"])) for r in panel})
        == 12
    )
    schedule = [
        [f"{r['id']}-{arm}" for arm in (first, "direct" if first == "staged" else "staged")]
        for first, r in zip(order, panel)
    ]
    return dict(
        case="stage-panel",
        schedule=schedule,
        arm_limit=LIMIT,
        worst_pair_nanoyuan=24 * LIMIT * 8000,
        account_cap_nanoyuan=read_json(prior.PLAN / "results.json")["cash_cap_nanoyuan"],
        files=[
            reference(PLAN / "panel.json"),
            reference(Path(__file__)),
            reference(ROOT / "src/proworksim/software_stage_response_v236.py"),
            reference(ROOT / "tools/prepare_osa_states_v236.py"),
        ],
        grading={k: list(v) for k, v in RULES.items()},
        no_change_review_ids=[r["id"] for r in panel if r["reference_type"] in ("STABLE", "A4")],
        gate="Primary staged arm: all 12 valid; >=10/12 correct evidence-supported types; >=9/12 phases; >=10/12 appropriate option and next step; <=1/5 unnecessary changes; at least one voluntary KEEP and one appropriate change. Before v237 require a real restorable, non-forced state of each A1-A4 for the first four pairs, and reservable cash. Forced choices cannot demonstrate policy discrimination or graph-change benefit.",
        design="Matched descriptive control, same isolated evidence-only controller inputs, schemas and feasible menus, only the staged instruction differs. One fresh nonthinking Flash call per condition/state, no retries of settled decisions, no worker execution or training.",
    )


def execute(panel, spec, *, namespace="v236", opening_balance=None):
    lookup = {r["id"]: r for r in panel}
    labels = sorted(x for pair in spec["schedule"] for x in pair)
    authority = read_json(prior.RUN / "authority.json")
    authority.update(
        scope=f"{namespace} twelve matched decision states only",
        available_on_approval_nanoyuan=read_json(prior.PLAN / "results.json")[
            "balance_after_settlement_nanoyuan"
        ]
        if opening_balance is None
        else opening_balance,
    )
    auth = RUN / "authority.json"
    save(auth, authority)
    meter = PairedLedger.load(auth)
    prior.clone_function(prior.reserve, {**prior.reserve.__globals__, "ARMS": labels})(
        auth, spec, namespace=namespace, block=f"{namespace}:decision-panel"
    )
    counter = prior.OfficialDeepSeekCounter(
        prior.TOKENIZER, manifest_sha256=reference(prior.TOKENIZER)["sha256"]
    )
    key = prior.load_api_key(ROOT / ".env")

    def pair(names):
        for name in names:
            sid, arm = name.split("-")
            slot = namespace + ":stage-panel:" + name
            folder = RUN / name
            folder.mkdir(exist_ok=True)
            with meter.db() as db:
                state = db.execute("select status from slots where id=?", (slot,)).fetchone()
                attempted = db.execute(
                    "select count(*) from requests where slot=?", (slot,)
                ).fetchone()[0]
            if state and (state != ("active",) or attempted):
                if state == ("active",):
                    meter.close(slot)
                continue
            if not state:
                meter.admit(slot, LIMIT)
            try:
                w = wire(lookup[sid], arm)
                if counter.measure(w)["prompt_tokens"] + w["max_tokens"] > LIMIT:
                    raise ValueError("Outside admitted call")
                backend = prior.Backend(
                    folder / "api",
                    meter,
                    slot,
                    counter,
                    prior.DirectHTTPS(key, timeout_seconds=120),
                    {"activate_organization"},
                )
                backend.post(
                    "/chat/completions",
                    dict(
                        team_slot_id=slot,
                        request_id=slot,
                        member_id=lookup[sid]["observer"],
                        usage_id="agent",
                        wire=w,
                    ),
                )
            except Exception as e:
                save(folder / "error.json", {"error": str(e)[:300]})
            finally:
                meter.close(slot)

    with ThreadPoolExecutor(3) as pool:
        list(pool.map(pair, spec["schedule"]))
    rows = []
    with meter.db() as db:
        for name in labels:
            sid, arm = name.split("-")
            r = lookup[sid]
            folder = RUN / name
            req = db.execute(
                "select id,tokens,cost,provider_id from requests where slot=? and status='settled'",
                (namespace + ":stage-panel:" + name,),
            ).fetchall()
            entry = dict(
                id=sid,
                arm=arm,
                type=r["reference_type"],
                options=list(options(r)),
                status="technical_unknown",
                input=0,
                output=0,
                cost_nanoyuan=0,
            )
            if len(req) == 1:
                pid, tokens, cost, provider = req[0]
                archive = folder / "api" / pid.rsplit(":", 1)[1]
                body = read_json(archive / "response.json")
                usage = read_json(archive / "usage.json")
                if (
                    body["id"] != provider
                    or tokens != usage["total_tokens"]
                    or cost != usage["peak_cost_nanoyuan"]
                    or read_json(archive / "request.json")["payload"]["wire"] != wire(r, arm)
                ):
                    raise ValueError("Wrong physical response")
                entry.update(
                    input=usage["input_tokens"],
                    output=usage["output_tokens"],
                    cost_nanoyuan=cost,
                    provider=provider,
                    fingerprint=body.get("system_fingerprint"),
                )
                try:
                    answer, graph = validate(r, body)
                    entry.update(
                        status="valid",
                        decision=answer,
                        graph_after=graph,
                        graph_changed=identity(graph) != identity(r["graph"]),
                        **grade(r, answer),
                    )
                except (ValueError, KeyError, TypeError) as e:
                    entry.update(status="invalid", error=str(e))
            rows.append(entry)
        paid = db.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = db.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
    stats = {}
    for arm in ("direct", "staged"):
        a = [x for x in rows if x["arm"] == arm]
        stats[arm] = {
            k: sum(bool(x.get(k)) for x in a)
            for k in (
                "correct_situation",
                "supported_identification",
                "correct_phase",
                "appropriate_action",
                "unnecessary_change",
                "graph_changed",
            )
        }
        stats[arm].update(
            valid=sum(x["status"] == "valid" for x in a),
            voluntary_keep=sum(
                len(x["options"]) > 1 and x.get("decision", {}).get("option") == "K" for x in a
            ),
            appropriate_changes=sum(
                x.get("graph_changed", False) and x.get("appropriate_action", False) for x in a
            ),
        )
    a = stats["staged"]
    passed = (
        a["valid"] == 12
        and min(a["supported_identification"], a["appropriate_action"]) >= 10
        and a["correct_phase"] >= 9
        and a["unnecessary_change"] <= 1
        and a["voluntary_keep"] > 0
        and a["appropriate_changes"] > 0
    )
    save(
        PLAN / "results.json",
        dict(
            rows=rows,
            metrics=stats,
            decision_gate=passed,
            balance_nanoyuan=meter.cap - paid,
            held_nanoyuan=held,
            actual_worker_calls=0,
            CN_updates=0,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    panel = read_json(PLAN / "panel.json")
    spec = freeze(panel)
    dest = PLAN / "protocol.json"
    if args.freeze:
        if dest.exists() and read_json(dest) != spec:
            raise ValueError("Already registered")
        save(dest, spec)
    else:
        if read_json(dest) != spec:
            raise ValueError("Frozen protocol differs")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            execute(panel, spec)
