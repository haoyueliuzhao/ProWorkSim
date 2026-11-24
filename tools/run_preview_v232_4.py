"""One independent Sphinx continuation testing optional full-message readback."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_handoff_v232_1 as prior
from run_context_panel_v231 import stored_run, score
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_inbox_preview_v232_4 import PreviewExecution
from proworksim.software_context_panel_v231 import ROOT, DESIGN, PairedLedger, panel_row
from proworksim.storage import atomic_write, read_json, json_bytes

PLAN = ROOT / "artifacts/software-benchmark-v232-4/preview-r1"
RUN = ROOT / "runs/software-benchmark-v232-4/preview-r1"
ARM = "PREVIEW"
CASE = prior.CASE
SLOT = "v232:" + CASE + ":" + ARM


def save(path, data):
    atomic_write(path, json_bytes(data))


class FixedRecipient(PreviewExecution):
    decide = clone_function(
        prior.FixedDiagnosis.decide,
        {**prior.FixedDiagnosis.decide.__globals__, "ARM": ARM, "PLAN": PLAN},
    )


def freeze():
    base = read_json(prior.PLAN / "protocol.json")
    previous = ROOT / "artifacts/software-benchmark-v232-3/recipient-r1"
    results = read_json(previous / "results.json")
    gate = read_json(PLAN / "gate.json")
    if (
        len(gate["verified_full_lookup_on_prior_requests"]) != 2
        or gate["unchanged_other_requests"] != 11
    ):
        raise ValueError("Preview replay gate failed")
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
        comparison=reference(previous / "results.json"),
        new_paid_branches=1,
        new_controller_calls=0,
        main_endpoint="For an accepted truncated handoff, verify the recipient saw the length and locator, voluntarily requested the original event, received a same-body successful tool receipt, and subsequently received the entire text in a physical input.",
        secondary="Record linked response/tool receipts after exposure, independently of evidence of adoption, and official code and legal delivery.",
        intervention="Identical to v232.3 except a truncation count and optional native read_work_event arguments beside the latest addressed diagnosis preview. No automatic read, no extra turn and no mandatory adoption.",
        recruitment="Single exposed Sphinx checkpoint, one attempt irrespective of whether a natural diagnosis handoff occurs. No resampling.",
        files=[
            reference(p)
            for p in [
                Path(__file__),
                ROOT / "tools/check_inbox_preview_v232_4.py",
                ROOT / "src/proworksim/software_inbox_preview_v232_4.py",
                previous / "protocol.json",
                ROOT / "src/proworksim/software_handoff_v232_2.py",
                ROOT / "src/proworksim/software_handoff_receive_v232_3.py",
                ROOT / "tools/run_handoff_v232_1.py",
                prior.PLAN / "protocol.json",
                prior.BASE_PROTOCOL,
                PLAN / "gate.json",
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
        *read_json(ROOT / "artifacts/software-benchmark-v232-3/recipient-r1/protocol.json")[
            "files"
        ],
        p["old_activation"],
        p["old_decision"],
        p["comparison"],
    ]:
        checked(f)
    auth = read_json(prior.RUN / "authority.json")
    auth.update(
        scope="one v232.4 optional preview lookup continuation, same account",
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
        if hold and hold != ("v232.4:preview", limit):
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
                "insert into block_slots values(?,?,?,'pending')", (SLOT, "v232.4:preview", limit)
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
