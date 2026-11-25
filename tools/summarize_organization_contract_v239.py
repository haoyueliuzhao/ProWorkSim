"""Count how much work the controller did, independently of the model, and export policy observations."""

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_organization_contract_v239 import PLAN, first, contract
from proworksim.storage import read_json


def main():
    result = read_json(PLAN / "results.json")
    panel = {r["id"]: r for r in read_json(PLAN / "panel.json")}
    ref = {r["id"]: r for r in read_json(PLAN / "agreed-reference.json")}
    raters = [
        {r["id"]: r for r in read_json(PLAN / name)} for name in ("ref-one.json", "ref-two.json")
    ]

    def canonical(field, v):
        if field == "obligations":
            return {tuple(sorted(x)) for x in v}
        return set(v)

    agreement = {
        field: sum(
            canonical(field, raters[0][i][field]) == canonical(field, raters[1][i][field])
            for i in ref
        )
        for field in ("obligations", "actions", "choices")
    }
    forced, covered = [], []
    for sid in ref:
        tasks = contract.state(panel[sid])
        choices = [k for k in tasks if contract.ready(tasks, k)]
        if len(choices) == 1:
            forced.append(sid)
        if any(tasks[k]["action"] in ref[sid]["actions"] for k in choices):
            covered.append(sid)
    policy = []
    for r in result["records"]:
        if r["arm"] != "P1" or not r.get("valid"):
            continue
        row = panel[r["id"]]
        # Package identity, roles, graph and team capacity are part of the policy context.
        # Only verified successor outcomes could supply utility; a decision does not supply one.
        policy.append(
            dict(
                state=r["id"],
                repeat=r["repeat"],
                context=dict(
                    graph=contract.identity(row["graph"]),
                    receipts=contract.identity(row["evidence"]),
                    obligations=contract.state(row),
                    budget=row["available_tokens"],
                ),
                candidates=[contract.make_patch(row, k) for k in contract.options(row)],
                disposition=r["choice"],
                selected_joint_patch=contract.make_patch(row, r["option"]),
                expected_additional_product=r["plan"]["product"],
                observed_successor_utility=None,
            )
        )
    first.save(
        PLAN / "policy-observations.json",
        {"eligible_for_parameter_update": False, "records": policy},
    )
    comparison = {}
    for arm in ("P0", "P1"):
        rows = [r for r in result["records"] if r["arm"] == arm and r["id"] != "gap"]
        sites = {s: [r for r in rows if r["id"] == s] for s in ref}
        comparison[arm] = dict(
            tokens=sum(r.get("input", 0) + r.get("output", 0) for r in rows),
            attempts=len(rows),
            both_obligation_correct=sum(
                all(r.get("obligation_ok") for r in v) for v in sites.values()
            ),
            both_order_correct=sum(all(r.get("order_ok") for r in v) for v in sites.values()),
            change_requests=sum(bool(r.get("requested_change")) for r in rows),
            compiled_changes=sum(r.get("choice") == "CHANGE" for r in rows),
            invalid_reasons=dict(
                Counter(r.get("error", "unknown") for r in rows if not r.get("valid"))
            ),
        )
    roster = []
    for sid in ["q07", "q03", "q14", "q11"]:
        row = panel[sid]
        roster.append(
            dict(
                site=sid,
                instance=row["instance"],
                remaining_team_tokens=row["available_tokens"],
                checkpoint=row["provenance"].get("checkpoint"),
                pair_reservation_yuan=2 * row["available_tokens"] * 8000 / 1e9,
            )
        )
    first.save(
        PLAN / "diagnostics.json",
        dict(
            reviewer_set_agreement=agreement,
            single_ready_action_sites=forced,
            acceptable_action_available=covered,
            arm_comparison=comparison,
            worker_roster=roster,
            four_pair_reservation_yuan=sum(x["pair_reservation_yuan"] for x in roster),
        ),
    )


if __name__ == "__main__":
    main()
