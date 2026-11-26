"""Join common-prefix, branch, replay and scoring receipts without pooling independent units."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_dynamic_panel_v248_2 as repair
import recover_dynamic_test_history_v248_3 as replay
import recover_dynamic_test_binding_v248_4 as canonical
import run_expansion_supplement_v248 as supplement
from report_ordinary_successor_v243_2 import counts
from proworksim.storage import read_json

first = repair.first


def paid(db, slot):
    return counts(db, slot)["paid"]


def details(root, index, arm):
    path = root / str(index) / arm
    close = read_json(path / "result.json")
    checks = []
    for f in sorted(path.glob("decisions/*/decision.json")):
        state = read_json(f.with_name("state.json"))
        r = read_json(f)
        p = f.with_name("proposal.json")
        q = read_json(p) if p.is_file() else {}
        checks.append(
            dict(
                opportunity=r["opportunity"],
                status=r["status"],
                tokens=r["tokens"],
                proposal=q.get("decision"),
                membership=q.get("membership_decision"),
                expected=q.get("expected_contribution"),
                first_action=q.get("execution_plan", {}).get("immediate_action"),
                offered_dimensions=sorted(
                    {
                        op["dimension"]
                        for c in state["candidates"].values()
                        for op in c["operations"]
                    }
                ),
                candidates=len(state["candidates"]),
                executed=r.get("completed", []),
                error=r.get("error"),
            )
        )
    outs = (
        read_json(path / "boundary.json").get("outcomes", [])
        if (path / "boundary.json").exists()
        else []
    )
    binding = read_json(path / "fork.json")
    after = binding["proof"]["checkpoint_identity"]
    actions = Counter()
    by_worker = Counter()
    hooks = []
    for j, o in enumerate(outs):
        d = o.get("decision") or {}
        resp = o.get("response") or {}
        res = resp.get("result") or {}
        if not resp.get("ok"):
            continue
        actions[d.get("action")] += 1
        by_worker[o["worker_id"]] += 1
        if d.get("action") in (
            "fix_patch",
            "handoff_patch",
            "integrate_patch",
            "complete_evidence",
            "adopt_evidence",
            "submit_integration",
            "org_review_patch",
            "send_message",
        ):
            args = d.get("arguments") or {}
            hooks.append(
                dict(
                    branch_step=j + 1,
                    worker=o["worker_id"],
                    tool=d["action"],
                    patch=res.get("patch_id", args.get("patch_id")),
                    recipient=args.get("to_member", args.get("recipient")),
                    message_kind=(args.get("body") or "").split(" ", 1)[0][:12]
                    if d["action"] == "send_message"
                    else None,
                )
            )
    scores = {}
    for k in ("code", "delivery"):
        receipt = path.parent / (arm + "-" + k) / "receipt.json"
        scores[k] = read_json(receipt).get("resolved") if receipt.is_file() else None
    usage_per_member = Counter()
    for f in path.glob("api/*/usage.json"):
        request = read_json(f.with_name("request.json"))["payload"]
        usage_per_member[request["member_id"]] += read_json(f)["total_tokens"]
    return dict(
        status=close["status"],
        incremental_member_tokens_this_deployment=dict(usage_per_member),
        checkpoint=after,
        initial_size=binding["initial_size"],
        final_members=close.get("final_members"),
        scores=scores,
        decision_count=len(checks),
        decisions=checks,
        worker_actions=dict(by_worker),
        accepted_actions=dict(actions),
        collaboration_receipts=hooks,
        logical_tokens=close.get("logical_tokens"),
        error=close.get("error"),
        replay=read_json(path / "replay.json") if (path / "replay.json").exists() else None,
    )


def report():
    spec = read_json(first.PLAN / "protocol.json")
    rows = []
    cohort = []
    with closing(
        sqlite3.connect(Path(read_json(first.AUTH)["ledger"]).as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("BEGIN")
        for case in [*spec["rows"], read_json(supplement.PLAN / "protocol.json")["case"]]:
            i = case["index"]
            commonroot = (
                first.RUN if (first.RUN / str(i) / "COMMON/result.json").is_file() else repair.RUN
            )
            if (supplement.RUN / str(i) / "COMMON/result.json").is_file():
                commonroot = supplement.RUN
            cp = commonroot / str(i) / "COMMON/result.json"
            if not cp.is_file():
                continue
            cr = read_json(cp)
            common_slot = cr["slot"]
            prefix = paid(db, common_slot)
            enrollment = dict(
                index=i,
                instance=case["instance"],
                initial=case["initial"],
                status=cr["status"],
                paid=prefix,
            )
            enrollment["recruitment_window"] = commonroot.name
            cohort.append(enrollment)
            if cr["status"] != "qualified":
                continue
            arms = {}
            for arm in first.ARMS:
                versions = [
                    (root, slot(i, arm))
                    for root, slot in (
                        (first.RUN, first.slot),
                        (repair.RUN, repair.resume_slot),
                        (replay.RUN, replay.slot),
                        (canonical.RUN, canonical.slot),
                        (supplement.RUN, supplement.slot),
                    )
                    if (root / str(i) / arm / "result.json").is_file()
                ]
                if not versions:
                    continue
                best = versions[-1][0]
                r = details(best, i, arm)
                expenses = Counter()
                for _, slot_id in versions:
                    expenses.update(paid(db, slot_id))
                r["physical_increment"] = dict(expenses)
                r["deployment"] = best.name
                if r["status"] == "closed":
                    assert (
                        r["logical_tokens"] == prefix["tokens"] + expenses["tokens"] <= first.LIMIT
                    )
                    assert (
                        r["checkpoint"]
                        == read_json(cp.parent / "checkpoint/manifest.json")["identity"]
                    )
                    if type(r["scores"]["delivery"]) == bool:
                        r["utility"] = (
                            float(r["scores"]["delivery"]) - 0.1 * r["logical_tokens"] / first.LIMIT
                        )
                arms[arm] = r
            rows.append(
                dict(instance=case["instance"], initial=case["initial"], prefix=prefix, arms=arms)
            )
        payments = db.execute(
            "select count(*),coalesce(sum(cost),0),coalesce(sum(tokens),0) from requests where slot glob 'v248.*' and status='settled'"
        ).fetchone()
        account = db.execute(
            "select coalesce(sum(cost),0) from requests where status='settled'"
        ).fetchone()[0]
    result = dict(
        cohort=cohort,
        blocks=rows,
        settled_calls=payments[0],
        cost_nanoyuan=payments[1],
        physical_tokens=payments[2],
        account_settled_nanoyuan=account,
    )
    first.save(repair.PLAN / "results.json", result)
    return result


if __name__ == "__main__":
    d = report()
    print(
        [
            (
                b["instance"],
                [(k, v["status"], v["scores"], v["logical_tokens"]) for k, v in b["arms"].items()],
            )
            for b in d["blocks"]
        ]
    )
