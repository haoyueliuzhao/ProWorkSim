"""Run the twelve fixed v245.3 tasks from fresh repositories with the revised OSA."""

from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import fcntl
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_full_osa_v245_3 as old
import run_full_osa_v245_4 as revised
from proworksim.software_context_panel_v231 import PairedLedger
from proworksim.storage import read_json

ROOT = old.ROOT
NS = "v245.4"
RUN = ROOT / "runs/software-benchmark-v245-4/full-osa12-r1"
PLAN = ROOT / "artifacts/software-benchmark-v245-4/full-osa12-r1"
AUTH = RUN / "authority.json"
CAP = 230_000_000_000
OLD_CAP = 150_000_000_000
reserve = old.clone_function(
    old.pre.paired.reserve, {**old.pre.paired.reserve.__globals__, "ARMS": ("OSA",)}
)


def prepare():
    original = read_json(old.PLAN / "protocol.json")
    roster = read_json(old.checked(original["roster"]))["roster"]
    bank = {r["index"]: r for r in read_json(old.checked(original["bank"]))["rows"]}
    assert len(roster) == len({r["instance"] for r in roster}) == 12
    for case in roster:
        task = bank[case["index"]]
        assert (task["instance_id"], task["base_commit"]) == (case["instance"], case["base_commit"])
    spec = dict(
        namespace=NS,
        roster=original["roster"],
        bank=original["bank"],
        design="Fresh full task, two workers plus OSA v245.4; DeepSeek Flash non-thinking, T1, one decision starting at opportunity 12, 5M shared tokens, official code and legal delivery endpoints.",
        old_results=old.reference(old.PLAN / "results.json"),
        cumulative_cap_nanoyuan=CAP,
        increase_nanoyuan=CAP - OLD_CAP,
        parallel=3,
        files=[
            old.reference(p)
            for p in (
                Path(__file__),
                Path(revised.__file__),
                ROOT / "src/proworksim/software_osa_prompt_v245_4.py",
                Path(old.__file__),
                ROOT / "tools/score_project_relations_v217_1.py",
            )
        ],
    )
    old.previous.freeze(PLAN / "protocol.json", spec)
    authority = read_json(old.checked(original["ledger"]))
    old.previous.freeze(
        AUTH,
        dict(
            **{
                **authority,
                "account_cap_CNY": 230,
                "stage_cap_CNY": 230,
                "cap_nanoyuan": CAP,
                "scope": "v245.4 reuse v245.1 account",
            }
        ),
    )
    marker = "amendment:v245.4:total230"
    with PairedLedger.load(AUTH).db() as db:
        amount = db.execute("select value from meta where key='cap'").fetchone()
        delta = db.execute("select value from meta where key=?", (marker,)).fetchone()
        if amount == (str(OLD_CAP),) and delta is None:
            db.execute("update meta set value=? where key='cap'", (str(CAP),))
            db.execute("insert into meta values(?,?)", (marker, str(CAP - OLD_CAP)))
        elif (amount, delta) != ((str(CAP),), (str(CAP - OLD_CAP),)):
            raise ValueError("Unexpected ledger or prior amendment")
    return roster, bank


def run_case(i):
    dest = RUN / str(i) / "OSA"
    dest.parent.mkdir(exist_ok=True)
    result = old.pre.isolated(
        Path(revised.__file__),
        ["--index", i, "--ledger", AUTH, "--namespace", NS],
        dest,
        "result.json",
    )
    scores = {}
    if result["status"] == "closed":
        for k in ("code", "delivery"):
            receipt = old.pre.isolated(
                ROOT / "tools/score_project_relations_v217_1.py",
                ["--index", i, "--kind", k, "--episode", dest],
                dest.parent / ("OSA-" + k),
                "receipt.json",
            )
            scores[k] = {key: receipt.get(key) for key in ("status", "resolved", "error")}
    old.save(
        dest.parent / "completed.json",
        dict(status=result["status"], error=result.get("error"), scores=scores),
    )


def main():
    (RUN / "tmp").mkdir(exist_ok=True, parents=True)
    os.environ["TMPDIR"] = str(RUN / "tmp")
    with (RUN / "coordinator.lock").open("a") as lock, ThreadPoolExecutor(3) as pool:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        roster, bank = prepare()
        todo = deque(
            r["index"] for r in roster if not (RUN / str(r["index"]) / "completed.json").exists()
        )
        active = {}
        while todo or active:
            while todo and len(active) < 3:
                i = todo[0]
                old.pre.check_images(dict(roster=[dict(configuration=bank[i]["configuration"])]))
                try:
                    reserve(
                        AUTH,
                        dict(
                            case=str(i),
                            account_cap_nanoyuan=CAP,
                            arm_limit=old.LIMIT,
                            worst_pair_nanoyuan=old.LIMIT * 8000,
                        ),
                        namespace=NS,
                        block=f"{NS}:{i}",
                    )
                except ValueError as exc:
                    if str(exc) != "Insufficient funds for this complete pair":
                        raise
                    if active:
                        break
                    old.save(
                        RUN / "cash-boundary.json", dict(remaining=list(todo), required_CNY=40)
                    )
                    return
                active[pool.submit(run_case, todo.popleft())] = i
            if active:
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                for future in done:
                    i = active.pop(future)
                    try:
                        future.result()
                    except Exception as exc:
                        old.save(
                            RUN / str(i) / "completed.json",
                            dict(status="technical_unknown", error=repr(exc), scores={}),
                        )
                    print(i, read_json(RUN / str(i) / "completed.json"), flush=True)


if __name__ == "__main__":
    main()
