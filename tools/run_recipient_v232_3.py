"""Single independent, funded Sphinx continuation to measure actual recipient exposure."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_handoff_v232_1 as prior
from run_context_panel_v231 import stored_run, score
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_receive_v232_3 import RecipientExecution
from proworksim.software_context_panel_v231 import ROOT, DESIGN, PairedLedger, panel_row
from proworksim.storage import atomic_write, read_json, json_bytes

PLAN = ROOT / "artifacts/software-benchmark-v232-3/recipient-r1"
RUN = ROOT / "runs/software-benchmark-v232-3/recipient-r1"
ARM = "RECEIVE"
CASE = prior.CASE
SLOT = "v232:" + CASE + ":" + ARM


def save(path, data):
    atomic_write(path, json_bytes(data))


class FixedRecipient(RecipientExecution):
    decide = clone_function(
        prior.FixedDiagnosis.decide,
        {**prior.FixedDiagnosis.decide.__globals__, "ARM": ARM, "PLAN": PLAN},
    )


def freeze():
    base = read_json(prior.PLAN / "protocol.json")
    results = read_json(prior.PLAN / "results.json")
    gate = read_json(PLAN / "sdk-control.json")
    if [
        (
            r["case"],
            r["repair_dispatches"],
            r["real_handoffs"],
            r["recipient_payloads_with_message"],
        )
        for r in gate
    ] != [("clean", 0, 1, 1), ("repair", 1, 1, 1), ("twice", 1, 0, 0)]:
        raise ValueError("Native handoff/recipient controls incomplete")
    data = {
        k: base[k]
        for k in (
            "case",
            "checkpoint",
            "prefix_tokens",
            "inherited_controller_tokens",
            "arm_limit",
            "worker_budget",
            "old_decision",
            "old_activation",
            "baseline",
            "account_cap_nanoyuan",
        )
    }
    data.update(
        arm=ARM,
        approved_available_nanoyuan=results["available_nanoyuan"],
        comparison=reference(prior.PLAN / "results.json"),
        new_paid_branches=1,
        new_controller_calls=0,
        main_endpoint="Conditional on a new formal handoff, match its event sequence and exact body hash within a subsequent physical worker request of the addressed member.",
        secondary="Record linked response/tool receipts after exposure, independently of evidence of adoption, and official code and legal delivery.",
        intervention="Keep r2 sender-correction protection. Earmark one additional 131072-token recipient opportunity inside the original worker allowance; give recipient priority immediately after world acceptance. Preserve native inbox and action choice.",
        recruitment="Single exposed Sphinx checkpoint, one attempt irrespective of whether a natural diagnosis handoff occurs. No resampling.",
        files=[
            reference(p)
            for p in [
                Path(__file__),
                ROOT / "tools/check_recipient_v232_3.py",
                ROOT / "src/proworksim/software_handoff_v232_2.py",
                ROOT / "src/proworksim/software_handoff_receive_v232_3.py",
                ROOT / "tools/run_handoff_v232_1.py",
                prior.PLAN / "protocol.json",
                prior.BASE_PROTOCOL,
                PLAN / "sdk-control.json",
            ]
        ],
    )
    dest = PLAN / "protocol.json"
    if dest.exists() and read_json(dest) != data:
        raise ValueError("Different registered protocol")
    save(dest, data)


def run():
    p = read_json(PLAN / "protocol.json")
    for f in [
        *p["files"],
        *read_json(prior.PLAN / "protocol.json")["files"],
        *read_json(prior.BASE_PROTOCOL)["sources"],
        p["old_activation"],
        p["old_decision"],
        p["comparison"],
    ]:
        checked(f)
    auth = read_json(prior.RUN / "authority.json")
    auth.update(
        scope="one v232.3 recipient exposure continuation, same account",
        available_on_approval_nanoyuan=p["approved_available_nanoyuan"],
    )
    if auth["cap_nanoyuan"] != p["account_cap_nanoyuan"]:
        raise ValueError("Cash cap changed")
    if not (RUN / "authority.json").exists():
        save(RUN / "authority.json", auth)
    ledger = PairedLedger.load(RUN / "authority.json")
    limit = p["arm_limit"]
    with ledger.db() as c:
        if c.execute("select value from meta where key='cap'").fetchone() != (str(ledger.cap),):
            raise ValueError("Account identity mismatch")
        hold = c.execute(
            "select block_id,token_limit from block_slots where slot=?", (SLOT,)
        ).fetchone()
        if hold and hold != ("v232.3:receive", limit):
            raise ValueError("Conflicting slot identity")
        if not hold:
            paid = c.execute(
                "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
            ).fetchone()[0]
            active = c.execute(
                "select coalesce(sum(hold),0) from slots where status!='closed'"
            ).fetchone()[0]
            pending = c.execute(
                "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
            ).fetchone()[0]
            if paid + active + pending + limit * 8000 > ledger.cap:
                raise ValueError("Insufficient balance")
            c.execute(
                "insert into block_slots values(?,?,?,'pending')", (SLOT, "v232.3:receive", limit)
            )
    dest = RUN / CASE / ARM
    dest.parent.mkdir(exist_ok=True)
    r = stored_run(Path(__file__).name, ["--episode"], dest, "result.json")
    if r["status"] == "closed":
        score(panel_row(read_json(DESIGN)["states"][1]), dest, ARM)
    save(RUN / "completed.json", {k: r.get(k) for k in ("status", "error", "termination")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--episode", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.episode:
        dest = RUN / CASE / ARM
        if args.output != dest:
            raise ValueError("Wrong continuation identity")
        clone_function(
            prior.original.episode,
            {
                **prior.original.episode.__globals__,
                "RUN": RUN,
                "OrganizationExecution": FixedRecipient,
            },
        )(1, ARM, dest, False)
    else:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            run()
