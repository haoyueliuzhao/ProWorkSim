"""One natural NEED follow-up continuation with the frozen v232.5 organization."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_disposition_v232_5 as previous
from run_context_panel_v231 import stored_run, score
from proworksim.software_context_panel_v231 import PairedLedger, ROOT, DESIGN, panel_row
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_evidence_v232_6 import EvidenceFollowupExecution
from proworksim.storage import read_json, json_bytes, atomic_write

PLAN = ROOT / "artifacts/software-benchmark-v232-6/need-followup-r1"
RUN = ROOT / "runs/software-benchmark-v232-6/need-followup-r1"
ARM = "NEEDCHECK"
CASE = previous.CASE
SLOT = f"v232:{CASE}:{ARM}"
BLOCK = "v232.6:independent-check"


class FixedEvidence(EvidenceFollowupExecution):
    decide = clone_function(
        previous.prior.FixedDiagnosis.decide,
        {**previous.prior.FixedDiagnosis.decide.__globals__, "ARM": ARM, "PLAN": PLAN},
    )


def check_sources(protocol):
    for item in protocol["files"]:
        path = checked(item)
        if path.name in ("protocol.json", "freeze.json"):
            child = read_json(path)
            if "files" in child:
                check_sources(child)
            for src in child.get("sources", []):
                checked(src)


def freeze():
    old = read_json(previous.PLAN / "protocol.json")
    result = read_json(previous.PLAN / "results.json")
    gate = read_json(PLAN / "sdk-control.json")
    if (
        gate["provider_calls"]
        or gate["accepted_sender_sequence"][-4:] != ["NEED", "read_work_event", "read_file", "DIAG"]
        or gate["recipient"]["choice"] != "ADOPT"
    ):
        raise ValueError("Native SDK control incomplete")
    data = {
        k: old[k]
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
        approved_available_nanoyuan=result["available_nanoyuan"],
        comparison=reference(previous.PLAN / "results.json"),
        new_paid_branches=1,
        new_controller_calls=0,
        intervention="v232.5 except one successful read of an addressed, same-task reply after NEED preserves one independent verification opportunity. Existing permissions, graph, budget, evidence ownership and recipient disposition unchanged.",
        primary="If a real NEED and addressed reply read occur: verify a successful independent source/search/test action after the read, then check whether its own event was cited in an accepted DIAG.",
        secondary="Report accepted handoff, physical recipient exposure or supported same-version skip, recorded recipient disposition, code and delivery. Preserve non-triggered paths as untested for the conditional endpoint.",
        recruitment="One independent Sphinx continuation from the registered predecision state. No forced NEED, answer, or re-sampling.",
        files=[
            reference(f)
            for f in (
                Path(__file__),
                previous.PLAN / "protocol.json",
                ROOT / "tools/check_evidence_followup_v232_6.py",
                ROOT / "src/proworksim/software_handoff_evidence_v232_6.py",
                PLAN / "sdk-control.json",
            )
        ],
    )
    path = PLAN / "protocol.json"
    if path.exists() and read_json(path) != data:
        raise ValueError("Protocol already registered")
    atomic_write(path, json_bytes(data))


def launch():
    p = read_json(PLAN / "protocol.json")
    check_sources(p)
    for k in ("comparison", "old_decision", "old_activation", "baseline"):
        checked(p[k])
    auth = read_json(previous.RUN / "authority.json")
    if auth["cap_nanoyuan"] != p["account_cap_nanoyuan"]:
        raise ValueError("Different cash cap")
    auth.update(
        scope="one v232.6 NEED follow-up continuation",
        available_on_approval_nanoyuan=p["approved_available_nanoyuan"],
    )
    auth_file = RUN / "authority.json"
    if not auth_file.exists():
        atomic_write(auth_file, json_bytes(auth))
    if read_json(auth_file) != auth:
        raise ValueError("Account identity differs")
    meter = PairedLedger.load(auth_file)
    limit = p["arm_limit"]
    with meter.db() as db:
        if db.execute("select value from meta where key='cap'").fetchone() != (str(meter.cap),):
            raise ValueError("Account changed")
        hold = db.execute(
            "select block_id,token_limit from block_slots where slot=?", (SLOT,)
        ).fetchone()
        if hold and hold != (BLOCK, limit):
            raise ValueError("Slot collision")
        if not hold:
            paid = db.execute(
                "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
            ).fetchone()[0]
            active = db.execute(
                "select coalesce(sum(hold),0) from slots where status!='closed'"
            ).fetchone()[0]
            pending = db.execute(
                "select coalesce(sum(token_limit),0) from block_slots where status='pending'"
            ).fetchone()[0]
            if paid + active + (pending + limit) * 8000 > meter.cap:
                raise ValueError("Unfunded continuation")
            db.execute("insert into block_slots values(?,?,?,'pending')", (SLOT, BLOCK, limit))
    dest = RUN / CASE / ARM
    dest.parent.mkdir(exist_ok=True)
    result = stored_run(Path(__file__).name, ["--episode"], dest, "result.json")
    if result["status"] == "closed":
        score(panel_row(read_json(DESIGN)["states"][1]), dest, ARM)
    atomic_write(
        RUN / "completed.json",
        json_bytes({k: result.get(k) for k in ("status", "error", "termination")}),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--episode", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.freeze:
        freeze()
    elif args.episode:
        dest = RUN / CASE / ARM
        if args.output != dest:
            raise ValueError("Wrong episode identity")
        fn = previous.prior.original.episode
        clone_function(fn, {**fn.__globals__, "RUN": RUN, "OrganizationExecution": FixedEvidence})(
            1, ARM, dest, False
        )
    else:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            launch()
