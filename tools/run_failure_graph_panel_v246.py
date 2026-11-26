"""Run only the seven unstarted retests under the incident-driven full-task policy."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_full_osa as policy
import run_osa_retest_v245_4 as previous
from report_osa_retest_v245_4 import comparison
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import read_json

old = previous.old
ROOT = old.ROOT
NS = "v246.1"
PLAN = ROOT / "artifacts/software-benchmark-v246/remaining-seven-r1"
RUN = ROOT / "runs/software-benchmark-v246/remaining-seven-r1"
AUTH = previous.AUTH
CAP = previous.CAP


def prepare():
    previous_results = previous.PLAN / "results.json"
    paused = read_json(previous_results)["paused_unstarted"]
    prior = read_json(previous.PLAN / "protocol.json")
    roster = [r for r in read_json(old.checked(prior["roster"]))["roster"] if r["index"] in paused]
    if [r["index"] for r in roster] != paused or len(set(paused)) != 7:
        raise ValueError("Paused roster does not match the seven previously unstarted tasks")
    bank = {r["index"]: r for r in read_json(old.checked(prior["bank"]))["rows"]}
    for case in roster:
        task = bank[case["index"]]
        assert (task["instance_id"], task["base_commit"]) == (case["instance"], case["base_commit"])
    with previous.PairedLedger.load(AUTH).db() as db:
        if db.execute("select value from meta where key='cap'").fetchone() != (str(CAP),):
            raise ValueError("Budget differs")
        for i in paused:
            if db.execute(
                "select 1 from block_slots where slot=?", (f"{previous.NS}:{i}:OSA",)
            ).fetchone():
                raise ValueError("Old slot already consumed")
    old.previous.freeze(PLAN / "roster.json", dict(roster=roster))
    old.previous.freeze(
        PLAN / "protocol.json",
        dict(
            namespace=NS,
            roster=old.reference(PLAN / "roster.json"),
            bank=prior["bank"],
            old_results=prior["old_results"],
            pause_source=old.reference(previous_results),
            cumulative_cap_nanoyuan=CAP,
            authority=old.reference(AUTH),
            new_cash=0,
            design="Same official repository bases, frozen order, fresh two-worker T1 episodes, DeepSeek Flash non-thinking, 5M team tokens including all OSA calls. Public failure-graph incidents may trigger multiple OSA decisions. Separate final-code and last legal delivery scores. Reference is v245.3 on the same seven tasks.",
            files=[
                old.reference(p)
                for p in (
                    Path(__file__),
                    Path(policy.__file__),
                    ROOT / "src/proworksim/software_failure_graph_v246.py",
                    ROOT / "src/proworksim/software_osa_prompt_v245_4.py",
                    Path(previous.__file__),
                    ROOT / "tools/score_project_relations_v217_1.py",
                )
            ],
        ),
    )
    return roster, bank


scope = {
    **vars(previous),
    "RUN": RUN,
    "PLAN": PLAN,
    "NS": NS,
    "AUTH": AUTH,
    "revised": policy,
    "prepare": prepare,
}
scope["run_case"] = clone_function(previous.run_case, scope)
run = clone_function(previous.main, scope)
collect = clone_function(
    comparison, {**comparison.__globals__, "RUN": RUN, "PLAN": PLAN, "NS": NS, "AUTH": AUTH}
)


def summarize():
    rows = collect()
    for row in rows:
        dest = RUN / str(row["index"]) / "OSA"
        decisions = []
        for f in sorted(dest.glob("osa-decisions/*/decision.json")):
            rec = read_json(f)
            inp = read_json(f.with_name("decision-input.json"))["row"]
            decisions.append(
                dict(
                    opportunity=rec["opportunity"],
                    trigger="incident" if "incident" in inp else "scheduled",
                    target=inp.get("incident", {}).get("target"),
                    changed=rec["active"]["changed"],
                    version=rec["active"]["version"],
                    option=rec["active"]["decision"]["option"],
                    validator=rec["info"]["validator"],
                    tokens=rec["info"]["osa_tokens"],
                )
            )
        row.update(decisions=decisions, changed=any(d["changed"] for d in decisions))
        if row["status"] == "closed":
            result = read_json(dest / "result.json")
            assert (
                len(decisions) == result["osa_calls"]
                and sum(d["tokens"] for d in decisions) == result["osa_tokens"]
            )
    old.save(
        PLAN / "results.json",
        dict(
            rows=rows,
            planned=len(rows),
            settled_tokens=sum(r["usage"]["paid"].get("tokens", 0) for r in rows),
            settled_nanoyuan=sum(r["usage"]["paid"].get("nanoyuan", 0) for r in rows),
        ),
    )


if __name__ == "__main__":
    run()
    summarize()
