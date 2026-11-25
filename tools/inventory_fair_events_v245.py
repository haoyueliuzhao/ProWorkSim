"""Validate ordinary event-time captures for the prospective panel; never start a paid job."""

from contextlib import closing
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_fair_pairs_v245 import ROOT, freeze, save
from proworksim.software_fair_intake_v245 import BANK, QUOTAS, EXPOSED
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.storage import read_json

PLAN = ROOT / "artifacts/software-benchmark-v245/prospective-r1"


def verified(path, excluded):
    t = read_json(path)
    reg_file = checked(t["registration"])
    if reg_file.parent != BANK / "ordinary-registrations":
        raise ValueError("Unregistered parent")
    reg = read_json(reg_file)
    iid = reg["instance"]
    job = Path(reg["job_root"]).resolve()
    site_path = checked(t["capture"])
    src = site_path.parent
    if (
        iid in excluded
        or reg["source"] != "ordinary"
        or not job.is_relative_to(ROOT / "runs")
        or not src.is_relative_to(job)
    ):
        raise ValueError("Dependent source or unrelated work")
    s = read_json(site_path)
    proof = read_json(src / "checkpoint/manifest.json")
    kind = s["node"]["anomaly_type"]
    if (
        s["parent_condition"] != "ordinary"
        or s["scope"] != "event"
        or s["complementary_only"]
        or kind not in QUOTAS
        or not s["capacity"]["enough"]
        or s["checkpoint"] != proof["identity"]
        or s["menu"]["base_version"] != 0
        or proof["prefix_tokens"] != s["prefix_tokens"]
        or not (src / "checkpoint/state.json").is_file()
    ):
        raise ValueError("Wrong event, capacity or point")
    last = read_json(src / "observations.json")[-1]
    o = last["outcome"]
    if (
        last["ordinal"] != s["ordinal"]
        or o["worker_id"] != s["observer"]
        or o["decision"].get("model_tool_call_id") != t["model_call"]
        or o["response"].get("command_id") != t["command"]
    ):
        raise ValueError("Unmatched action")
    ledger = Path(reg["ledger"]).resolve()
    if not ledger.is_relative_to(ROOT / "runs"):
        raise ValueError("Independent job ledger missing")
    with closing(sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)) as db:
        for f in (job / "api").glob("*/response.json"):
            r = read_json(f)
            calls = r["choices"][0]["message"].get("tool_calls") or []
            if not any(x["id"] == t["model_call"] for x in calls):
                continue
            req = read_json(f.with_name("request.json"))["payload"]
            if (
                req["member_id"] == s["observer"]
                and db.execute(
                    "select 1 from requests where status='settled' and provider_id=? and slot=?",
                    (r["id"], req["team_slot_id"]),
                ).fetchone()
            ):
                return dict(
                    instance=iid,
                    kind=kind,
                    checkpoint=proof["identity"],
                    ordinal=s["ordinal"],
                    source=reference(path),
                )
    raise ValueError("No matching actual model receipt")


def main():
    freeze(
        PLAN / "protocol.json",
        dict(
            quotas=QUOTAS,
            prior_excluded=reference(EXPOSED),
            contract="v245 shared task-level delivery",
            enrollment="Independent, prospectively registered normal jobs only. One state per task; within each kind take in registration order, then action ordinal; no quota substitution. Recheck the saved world and whole-pair reservation before dispatch.",
            source=reference(ROOT / "src/proworksim/software_fair_intake_v245.py"),
            budget_authorized_yuan=0,
            team_size=2,
            cn_updates=0,
        ),
    )
    excluded = {r["instance"] for r in read_json(EXPOSED)["roster"]}
    errors = []
    rows = []
    selected = []
    for f in sorted((BANK / "inbox").glob("*.json")):
        try:
            rows.append(verified(f, excluded))
        except (OSError, ValueError, KeyError, sqlite3.Error) as err:
            errors.append(dict(entry=f.name, error=str(err)))

    # Input registration sequence is explicit in each ordinary job record, not inferred from task scores.
    def order(r):
        reg = read_json(checked(read_json(checked(r["source"]))["registration"]))
        return reg["registration_sequence"], r["ordinal"], r["checkpoint"]

    for r in sorted(rows, key=order):
        if (
            r["instance"] not in excluded
            and sum(x["kind"] == r["kind"] for x in selected) < QUOTAS[r["kind"]]
        ):
            selected.append(r)
            excluded.add(r["instance"])
    save(
        PLAN / "intake.json",
        dict(
            ordinary_registrations=len(list((BANK / "ordinary-registrations").glob("*.json"))),
            selected=selected,
            unknown=errors,
            per_type={k: sum(x["kind"] == k for x in selected) for k in QUOTAS},
            paid_pairs_started=0,
        ),
    )


if __name__ == "__main__":
    main()
