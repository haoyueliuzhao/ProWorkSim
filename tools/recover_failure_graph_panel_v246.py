"""Resume the two v246.1 slots interrupted by provider billing, keeping the failed attempts."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_failure_graph_panel_v246 as batch
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import read_json

NS = "v246.2"
PLAN = batch.ROOT / "artifacts/software-benchmark-v246/balance-recovery-r1"
RUN = batch.ROOT / "runs/software-benchmark-v246/balance-recovery-r1"
AUTH = RUN / "authority.json"
CAP = 400_000_000_000


def prepare():
    prior = read_json(batch.PLAN / "protocol.json")
    for file in prior["files"]:
        batch.old.checked(file)
    queue = batch.PLAN / "recovery-queue.json"
    interrupted = read_json(queue)["tasks"]
    ids = [r["index"] for r in interrupted]
    roster = [
        r for r in read_json(batch.old.checked(prior["roster"]))["roster"] if r["index"] in ids
    ]
    assert ids == [18, 23] == [r["index"] for r in roster]
    bank = {r["index"]: r for r in read_json(batch.old.checked(prior["bank"]))["rows"]}
    freeze = batch.old.previous.freeze
    authority = read_json(batch.old.checked(prior["authority"]))
    freeze(
        AUTH,
        {
            **authority,
            "scope": "v246.2 balance recovery",
            "account_cap_CNY": 400,
            "stage_cap_CNY": 400,
            "cap_nanoyuan": CAP,
        },
    )
    freeze(PLAN / "roster.json", dict(roster=roster))
    freeze(
        PLAN / "protocol.json",
        dict(
            namespace=NS,
            queue=batch.old.reference(queue),
            bank=prior["bank"],
            roster=batch.old.reference(PLAN / "roster.json"),
            old_results=prior["old_results"],
            parent=batch.old.reference(batch.PLAN / "protocol.json"),
            cumulative_cap_nanoyuan=CAP,
            authority=batch.old.reference(AUTH),
            entry=batch.old.reference(Path(__file__)),
            design="Two original repository starts with the unchanged v246.1 policy and separate new slots. Index 18 is an independent recovery after two model responses; index 23 had zero prior model responses. Retain both original slots and their costs. No other repeats.",
        ),
    )
    marker = "amendment:v246.2:total400"
    with batch.previous.PairedLedger.load(AUTH).db() as db:
        amount = db.execute("select value from meta where key='cap'").fetchone()
        delta = db.execute("select value from meta where key=?", (marker,)).fetchone()
        if amount == (str(batch.CAP),) and delta is None:
            db.execute("update meta set value=? where key='cap'", (str(CAP),))
            db.execute("insert into meta values(?,?)", (marker, str(CAP - batch.CAP)))
        elif (amount, delta) != ((str(CAP),), (str(CAP - batch.CAP),)):
            raise ValueError("Unexpected cumulative budget")
    return roster, bank


scope = {
    **batch.scope,
    "RUN": RUN,
    "PLAN": PLAN,
    "NS": NS,
    "CAP": CAP,
    "AUTH": AUTH,
    "prepare": prepare,
}
scope["run_case"] = clone_function(batch.previous.run_case, scope)
run = clone_function(batch.previous.main, scope)
collect = clone_function(
    batch.collect, {**batch.collect.__globals__, "RUN": RUN, "PLAN": PLAN, "NS": NS, "AUTH": AUTH}
)
summarize = clone_function(
    batch.summarize, {**vars(batch), "RUN": RUN, "PLAN": PLAN, "collect": collect}
)

if __name__ == "__main__":
    run()
    summarize()
