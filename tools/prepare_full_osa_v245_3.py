"""Select twelve distinct bank tasks whose last conclusive official code test failed."""

from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_full_osa_v245_3 import BANK, ROOT, PLAN, AUTH, read_json, reference, previous
import run_full_osa_v245_3 as runner


def main():
    bank = read_json(BANK)["rows"]
    known = {r["instance_id"] for r in bank}
    seen = defaultdict(list)
    patterns = (
        "*/*/scores/*/code*/receipt.json",
        "*/*/*-code/receipt.json",
        "*/*/code/receipt.json",
        "*/code/receipt.json",
        "*/*/*/code/receipt.json",
        "*/*/*/scores/*/code*/receipt.json",
    )
    for d in sorted((ROOT / "runs").glob("software-benchmark-v2*")):
        n = d.name.partition("-v")[2].split("-")[0]
        if not n.isdigit() or not 216 <= int(n) <= 245 or d.name == "software-benchmark-v245-3":
            continue
        for f in sorted(set(f for pat in patterns for f in d.glob(pat))):
            q = read_json(f)
            iid = q.get("instance_id")
            if (
                iid not in known
                or q.get("kind") != "code"
                or q.get("status") != "official_report"
                or not q.get("official_result")
            ):
                continue
            report = q["official_result"][1][iid]
            if (
                report.get("patch_successfully_applied") is not True
                or report.get("infra_failure")
                or type(q.get("resolved")) is not bool
                or report.get("resolved") != q["resolved"]
            ):
                continue
            failed = sum(
                len(report["tests_status"].get(k, {}).get("failure", []))
                for k in ("FAIL_TO_PASS", "PASS_TO_PASS")
            )
            if not q["resolved"] and not failed:
                continue
            seen[iid].append(
                dict(
                    finished=q["finished"], path=str(f), resolved=q["resolved"], failed_tests=failed
                )
            )
    groups = defaultdict(list)
    for r in sorted(bank, key=lambda t: t["index"]):
        iid = r["instance_id"]
        records = sorted(seen[iid], key=lambda t: (t["finished"], t["path"]))
        if not records or records[-1]["resolved"]:
            continue
        latest = records[-1]
        groups[r["repo"]].append(
            dict(
                instance=iid,
                index=r["index"],
                repo=r["repo"],
                base_commit=r["base_commit"],
                public_title=r["public_problem"].splitlines()[0],
                prior_failure=reference(Path(latest["path"])),
                failed_official_tests=latest["failed_tests"],
                known_passing_receipts=sum(x["resolved"] for x in records),
                known_failing_receipts=sum(not x["resolved"] for x in records),
            )
        )
    full = [
        groups[repo][i]
        for i in range(max(map(len, groups.values())))
        for repo in sorted(groups)
        if i < len(groups[repo])
    ]
    roster = full[:12]
    if len({r["instance"] for r in roster}) != 12:
        raise ValueError("Insufficient distinct official code failures")
    previous.freeze(
        PLAN / "roster.json",
        dict(
            roster=roster,
            eligible=len(full),
            bank_size=len(bank),
            patterns=list(patterns),
            rule="Among v217-supported tasks, last conclusive official final-code test in the listed v216–245 archives is unresolved and has a failing target/regression test. Round robin over repositories, then original index. Historical receipts never enter an API request.",
        ),
    )
    previous.freeze(
        PLAN / "protocol.json",
        dict(
            roster=reference(PLAN / "roster.json"),
            bank=reference(BANK),
            ledger=reference(AUTH),
            opening_available_nanoyuan=121564031680,
            files=[
                reference(p)
                for p in (
                    Path(__file__),
                    Path(runner.__file__),
                    Path(previous.fair.__file__),
                    ROOT / "tools/score_project_relations_v217_1.py",
                )
            ],
            design="Single arm, fresh official repository and SDK sessions. Two workers plus independent OSA, DeepSeek Flash non-thinking, T1, 5M full-task tokens. One policy call on live state at opportunity 12; if no valid bounded route, check again on later live actions. Terminal jobs close normally. No historical workspace/feedback, no KEEP run, no C/N update. Original cumulative cash ceiling 150 CNY.",
        ),
    )
    print([(r["index"], r["instance"]) for r in roster])


if __name__ == "__main__":
    main()
