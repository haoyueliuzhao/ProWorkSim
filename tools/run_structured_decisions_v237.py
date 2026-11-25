"""Prospective structured OSA trials, matched compact controls, and an evidence-gap probe."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import fcntl
import random
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_intervention_prompt_v236_2 as prior
from prepare_structured_panel_v237 import PLAN, save
from proworksim.software_structured_policy_v237 import wire, validate, options
from proworksim.software_stage_response_v236 import grade
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_context_panel_v231 import ROOT, PairedLedger
from proworksim.storage import read_json

RUN = ROOT / "runs/software-benchmark-v237/structured-decisions-r1"
LIMIT = 8192


def design():
    rows = read_json(PLAN / "panel.json")
    review = read_json(PLAN / "independent-review.json")
    assert len(rows) == 12 and {x["id"] for x in rows} == {x["id"] for x in review["states"]}
    probe = deepcopy(rows[0])
    probe.update(
        id="gap",
        reference_type="UNKNOWN",
        evidence={
            "E1": {
                "operation": "run_tests",
                "accepted": True,
                "executed": False,
                "passed": None,
                "counts": None,
                "source_reference": None,
            }
        },
        work_status={k: {"completed": None, "authors": []} for k in probe["targets"]},
    )
    rows.append(probe)
    labels = [
        r["id"] + "-" + a
        for r in rows
        for a in (["structured"] if r["id"] in ("s13", "gap") else ["baseline", "structured"])
    ]
    random.Random(237).shuffle(labels)
    files = [
        reference(p)
        for p in (
            Path(__file__),
            PLAN / "panel.json",
            PLAN / "independent-review.json",
            PLAN / "a5-inventory.json",
            ROOT / "src/proworksim/software_structured_policy_v237.py",
            Path(prior.__file__),
        )
    ]
    spec = dict(
        case="structure",
        labels=labels,
        account_cap_nanoyuan=prior.CAP,
        arm_limit=LIMIT,
        worst_pair_nanoyuan=len(labels) * LIMIT * 8000,
        files=files,
        primary="Twelve states (one separately identified synthetic A5); one structured decision per state. Eleven matched native v236.2 baseline decisions; it has no A5 or ABSTAIN in its schema. Extra masked CPU-derived evidence-gap probe separate.",
        obligation_rule="All labels in at least one independently accepted nonempty set and no unrelated labels (extra obligations allowed only when present in the state's public readiness gaps); stable may report continue_progress.",
        gate="Before spending on worker pairs require at least 9/12 validator-legal, 8/12 obligation-correct, and at least one eligible restorable accepted plan. ABSTAIN is a distinct evidence request, not a positive CHANGE. No resampling. Holistic policy utility and additional-product realization require actual worker runs.",
        followup="Use up to four distinct restorable states with executable alternatives from the panel, irrespective of OSA selection. Prioritize existing Sphinx, Astropy and SymPy source checkpoints. A fourth without a matching checkpoint remains an unfilled slot. No new budget or C/N update.",
    )
    return rows, spec


def reconcile(rows, spec, meter):
    lookup = {r["id"]: r for r in rows}
    reviews = {v["id"]: v for v in read_json(PLAN / "independent-review.json")["states"]}
    records = []
    with meter.db() as c:
        for label in sorted(spec["labels"]):
            sid, arm = label.split("-")
            row = lookup[sid]
            slot = "v237:structure:" + label
            charges = c.execute(
                "select id,status,tokens,cost,provider_id from requests where slot=?", (slot,)
            ).fetchall()
            record = dict(
                state=sid,
                arm=arm,
                forced=len(options(row)) == 1,
                source_kind="synthetic" if sid in ("s13", "gap") else "historical",
                status="unknown",
            )
            records.append(record)
            settled = [v for v in charges if v[1] == "settled"]
            if len(settled) != 1:
                continue
            rid, _, tokens, cost, provider = settled[0]
            f = RUN / label / "api" / rid.rsplit(":", 1)[-1]
            body = read_json(f / "response.json")
            u = read_json(f / "usage.json")
            w = read_json(f / "request.json")["payload"]["wire"]
            if (
                w != (wire(row) if arm == "structured" else prior.prompt_wire(row, "staged"))
                or provider != body["id"]
                or tokens != u["total_tokens"]
                or cost != u["peak_cost_nanoyuan"]
            ):
                raise ValueError("Physical ledger mismatch")
            record.update(
                input=u["input_tokens"],
                output=u["output_tokens"],
                cost_nanoyuan=cost,
                provider=provider,
            )
            try:
                if arm == "structured":
                    d, target = validate(row, body)
                    choice = d["decision"]["result"]
                    kind = d["assessment"]["situation"]
                    obl = set(d["work"]["obligations"])
                    record.update(
                        proposal=d,
                        target=target,
                        option=target["option"],
                        decision=choice,
                        classification_correct=kind == row["reference_type"],
                    )
                else:
                    d, g = prior.previous.check(row, body)
                    choice = "KEEP" if d["option"] == "K" else "CHANGE"
                    record.update(
                        proposal=d,
                        decision=choice,
                        option=d["option"],
                        classification_correct=d["situation"] == row["reference_type"],
                        baseline_grade=grade(row, d),
                    )
                record["status"] = "valid"
                if sid == "gap":
                    record["probe_abstained"] = choice == "ABSTAIN"
                    continue
                ref = reviews[sid]
                record["review_choice_match"] = choice == ref["preferred"]
                if arm == "structured":
                    extras = {
                        k
                        for ev in row["evidence"].values()
                        for p in ev.get("packages", [])
                        for q in p["missing"]
                        if (
                            k := {
                                "complete_current_code_or_evidence": "complete_package",
                                "independent_current_review": "independent_review",
                                "evidence_version_differs_from_final_tree_revalidate": "verify_integrated_version",
                            }.get(q)
                        )
                    }
                    if any(ev.get("fixed") == [] for ev in row["evidence"].values()):
                        extras.add("fix_tree")
                    record["obligations_correct"] = any(
                        set(s) <= obl <= set(s) | extras for s in ref["obligation_label_sets"] if s
                    )
                    record["dimensions_if_changed"] = target["dimensions"]
            except (KeyError, ValueError, TypeError) as e:
                record.update(status="invalid", error=str(e)[:300])
        paid = c.execute("select sum(cost) from requests where status='settled'").fetchone()[0]
        held = c.execute(
            "select coalesce(sum(hold),0) from slots where status!='closed'"
        ).fetchone()[0]
    main = [r for r in records if r["arm"] == "structured" and r["state"] != "gap"]
    valid = [r for r in main if r["status"] == "valid"]
    correct = sum(r.get("obligations_correct", False) for r in main)
    gate = (
        len(valid) >= 9
        and correct >= 8
        and any(
            lookup[r["state"]]["provenance"].get("checkpoint") and not r["forced"] for r in valid
        )
    )
    save(
        PLAN / "results.json",
        dict(
            records=records,
            valid=len(valid),
            obligations_correct=correct,
            gate=gate,
            opening_cap_nanoyuan=meter.cap,
            balance_nanoyuan=meter.cap - paid,
            held_nanoyuan=held,
            worker_calls=0,
            CN_updates=0,
        ),
    )


def run(rows, spec):
    lookup = {r["id"]: r for r in rows}
    auth = RUN / "authority.json"
    a = read_json(prior.RUN / "authority.json")
    a.update(
        scope="v237 structured decision panel only",
        available_on_approval_nanoyuan=read_json(prior.PLAN / "results.json")["balance_nanoyuan"],
    )
    save(auth, a)
    engine = prior.prior
    meter = PairedLedger.load(auth)
    labels = sorted(spec["labels"])
    engine.clone_function(engine.reserve, {**engine.reserve.__globals__, "ARMS": labels})(
        auth, spec, namespace="v237", block="v237:structure"
    )
    counter = engine.OfficialDeepSeekCounter(
        engine.TOKENIZER, manifest_sha256=reference(engine.TOKENIZER)["sha256"]
    )
    key = engine.load_api_key(ROOT / ".env")

    def call(label):
        sid, arm = label.split("-")
        row = lookup[sid]
        slot = "v237:structure:" + label
        folder = RUN / label
        folder.mkdir(exist_ok=True)
        with meter.db() as db:
            existing = db.execute("select status from slots where id=?", (slot,)).fetchone()
            seen = db.execute("select count(*) from requests where slot=?", (slot,)).fetchone()[0]
        if existing and (seen or existing != ("active",)):
            if existing == ("active",):
                meter.close(slot)
            return
        if not existing:
            meter.admit(slot, LIMIT)
        try:
            backend = engine.Backend(
                folder / "api",
                meter,
                slot,
                counter,
                engine.DirectHTTPS(key, timeout_seconds=150),
                {"activate_organization"},
            )
            backend.post(
                "/chat/completions",
                dict(
                    team_slot_id=slot,
                    request_id=slot,
                    member_id=row["observer"],
                    usage_id="agent",
                    wire=wire(row) if arm == "structured" else prior.prompt_wire(row, "staged"),
                ),
            )
        except Exception as exc:
            save(folder / "error.json", {"error": str(exc)[:400]})
        finally:
            meter.close(slot)

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(call, spec["labels"]))
    reconcile(rows, spec, meter)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    rows, spec = design()
    dest = PLAN / "protocol.json"
    if args.freeze:
        if dest.exists() and read_json(dest) != spec:
            raise ValueError("Protocol changed")
        save(dest, spec)
    else:
        if read_json(dest) != spec:
            raise ValueError("Frozen design differs")
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run(rows, spec)
