"""Matched prompt-only comparison with repeated free-choice states; use the amended ledger."""

import argparse
import fcntl
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_compact_stage_panel_v236_1 as previous
from run_osa_stage_panel_v236 import LIMIT, prior, save
from proworksim.software_context_panel_v231 import ROOT, PairedLedger
from proworksim.software_stage_response_v236 import options
from proworksim.software_intervention_prompt_v236_2 import INTERVENTION_PROMPT
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import read_json

PLAN = ROOT / "artifacts/software-benchmark-v236-2/intervention-prompt-r1"
RUN = ROOT / "runs/software-benchmark-v236-2/intervention-prompt-r1"
PANEL_PATH = previous.first.PLAN / "panel.json"
CAP = 230_000_000_000
OLD_CAP = 181_374_666_400
NAMESPACE = "v236.2"


def prompt_wire(row, arm):
    w = previous.short_wire(row, "staged")
    if arm == "staged":
        w["messages"][0]["content"] += INTERVENTION_PROMPT
    elif arm != "direct":
        raise ValueError("Unknown prompt arm")
    return w


def design():
    source = read_json(PANEL_PATH)
    panel, schedule = [], []
    rng = random.Random(2362)
    singles = ["direct"] * 4 + ["staged"] * 4
    rng.shuffle(singles)
    repeats = []
    for r in source:
        repeat = len(options(r)) > 1 and r["reference_type"] in ("A1", "A4", "STABLE")
        if repeat:
            repeats.append(r["id"])
        first = ["direct"] * 4 + ["staged"] * 4 if repeat else [singles.pop()]
        rng.shuffle(first)
        for n, arm in enumerate(first, 1):
            row = {**r, "id": f"{r['id']}r{n:02}", "source_state": r["id"]}
            panel.append(row)
            schedule.append(
                [row["id"] + "-" + a for a in (arm, "staged" if arm == "direct" else "direct")]
            )
    rng.shuffle(schedule)
    assert not singles and set(repeats) == {"s01", "s03", "s05", "s06"}
    for r in source:
        base = prompt_wire(r, "direct")
        change = prompt_wire(r, "staged")
        assert (
            change["messages"][0]["content"].removesuffix(INTERVENTION_PROMPT)
            == base["messages"][0]["content"]
        )
        assert base["messages"][1:] == change["messages"][1:] and base["tools"] == change["tools"]
    spec = dict(
        case="stage-panel",
        schedule=schedule,
        arm_limit=LIMIT,
        account_cap_nanoyuan=CAP,
        old_cap_nanoyuan=OLD_CAP,
        cap_interpretation="Cumulative CNY 230 on the existing account",
        worst_pair_nanoyuan=2 * len(schedule) * LIMIT * 8000,
        alias={"direct": "original staged compact", "staged": "same plus path comparison"},
        repeated_states=repeats,
        candidate_prompt=INTERVENTION_PROMPT,
        files=[
            reference(p)
            for p in (
                Path(__file__),
                PANEL_PATH,
                Path(previous.__file__),
                Path(previous.first.__file__),
                ROOT / "src/proworksim/software_stage_response_v236.py",
                ROOT / "src/proworksim/software_intervention_prompt_v236_2.py",
            )
        ],
        primary="Report original and revised unnecessary changes on s03,s05 (8 fresh calls per state per arm), paired directions, invalid and forced choices separately. Keep appropriate diagnosis changes on s01,s06 (8 each per arm).",
        promotion="Pilot support only if revised errors plus invalids on s03,s05 are strictly fewer than observed original changes, neither no-change state worsens, and appropriate changes on s01,s06 do not decrease overall or by state. Require no lower valid count or appropriate-next-action count on the equally weighted first run across all 12. Otherwise keep candidate experimental.",
        limitations="Development states previously exposed; no shared provider seed; repetition is within-state. No task execution, C/N fitting or outcome-based resampling.",
    )
    return panel, spec


def amend(auth_file):
    ledger = PairedLedger.load(auth_file)
    marker = "amendment:v236.2:total230"
    with ledger.db() as db:
        old = db.execute("select value from meta where key='cap'").fetchone()
        rec = db.execute("select value from meta where key=?", (marker,)).fetchone()
        if rec:
            if old != (str(CAP),) or rec != (str(CAP - OLD_CAP),):
                raise ValueError("Conflicting budget amendment")
        else:
            if old != (str(OLD_CAP),):
                raise ValueError("Unexpected prior budget")
            db.execute("update meta set value=? where key='cap'", (str(CAP),))
            db.execute("insert into meta values(?,?)", (marker, str(CAP - OLD_CAP)))
        return (
            CAP
            - db.execute(
                "select coalesce(sum(cost),0) from requests where status='settled'"
            ).fetchone()[0]
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    panel, spec = design()
    path = PLAN / "protocol.json"
    if args.freeze:
        if path.exists() and read_json(path) != spec:
            raise ValueError("Existing protocol differs")
        save(path, spec)
        return
    if read_json(path) != spec:
        raise ValueError("Frozen protocol differs")
    RUN.mkdir(parents=True, exist_ok=True)
    with (RUN / "coordinator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = read_json(previous.RUN / "authority.json")
        balance = amend(previous.RUN / "authority.json")
        auth = RUN / "authority.json"
        if auth.exists():
            balance = read_json(auth)["available_on_approval_nanoyuan"]
        save(
            auth,
            {
                **old,
                "scope": "v236.2 matched prompt comparison",
                "cap_nanoyuan": CAP,
                "available_on_approval_nanoyuan": balance,
            },
        )
        fn = previous.first.execute
        # Reuse the physical-request runner with this run's amended cash authority.
        from types import SimpleNamespace

        bindings = SimpleNamespace(**{**vars(prior), "RUN": RUN})
        prior.clone_function(
            fn,
            {
                **fn.__globals__,
                "RUN": RUN,
                "PLAN": PLAN,
                "wire": prompt_wire,
                "validate": previous.check,
                "prior": bindings,
            },
        )(panel, spec, namespace=NAMESPACE, opening_balance=balance)
        summarize(panel, spec)


def summarize(panel, spec):
    data = read_json(PLAN / "results.json")
    records = {(r["id"], r["arm"]): r for r in data["rows"]}
    states = {}
    for row in panel:
        state = row["source_state"]
        stats = states.setdefault(state, {})
        for arm in ("direct", "staged"):
            r = records[row["id"], arm]
            a = stats.setdefault(
                arm,
                dict(
                    n=0,
                    valid=0,
                    changed=0,
                    appropriate_changes=0,
                    appropriate=0,
                    first_valid=None,
                    first_appropriate=None,
                    input=0,
                    output=0,
                    cost_nanoyuan=0,
                ),
            )
            a["n"] += 1
            a["valid"] += r["status"] == "valid"
            a["changed"] += bool(r.get("graph_changed"))
            a["appropriate_changes"] += bool(r.get("graph_changed") and r.get("appropriate_action"))
            a["appropriate"] += bool(r.get("appropriate_action"))
            for k in ("input", "output", "cost_nanoyuan"):
                a[k] += r[k]
            if row["id"].endswith("r01"):
                a.update(
                    first_valid=r["status"] == "valid",
                    first_appropriate=bool(r.get("appropriate_action")),
                )
        pair = [
            records[row["id"], a].get("decision", {}).get("option", "invalid")
            for a in ("direct", "staged")
        ]
        changes = stats.setdefault("paired", {})
        key = " -> ".join(pair)
        changes[key] = changes.get(key, 0) + 1
    negatives = [states[k] for k in ("s03", "s05")]
    old = [x["direct"]["changed"] for x in negatives]
    new = [x["staged"]["changed"] + x["staged"]["n"] - x["staged"]["valid"] for x in negatives]
    promotion = (
        sum(new) < sum(old)
        and all(b <= a for a, b in zip(old, new))
        and all(
            states[k]["staged"]["appropriate_changes"] >= states[k]["direct"]["appropriate_changes"]
            for k in ("s01", "s06")
        )
        and all(
            sum(x["staged"][key] for x in states.values())
            >= sum(x["direct"][key] for x in states.values())
            for key in ("first_valid", "first_appropriate")
        )
    )
    data.pop("decision_gate", None)  # v236's 12-state gate does not apply to 40 repeated decisions.
    data.update(state_statistics=states, prompt_pilot_supported=promotion, cap_nanoyuan=CAP)
    save(PLAN / "results.json", data)


if __name__ == "__main__":
    main()
