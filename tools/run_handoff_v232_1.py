"""One registered diagnosis replay, with a legal example and a conditional correction grant."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_organization_episode_v232 as original
from run_context_panel_v231 import stored_run, score
from proworksim.software_context_panel_v231 import ROOT, DESIGN, PairedLedger, panel_row
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_v232_1 import HandoffExecution
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.storage import read_json, json_bytes, atomic_write

PLAN = ROOT / "artifacts/software-benchmark-v232-1/handoff-r1"
RUN = ROOT / "runs/software-benchmark-v232-1/handoff-r1"
PRIOR = ROOT / "runs/software-benchmark-v232/first-pair-r1"
BASE_PROTOCOL = ROOT / "artifacts/software-benchmark-v232/first-pair-r1/protocol.json"
CASE = "Sphinx-9591"
ARM = "HANDOFF"
SLOT = f"v232:{CASE}:{ARM}"


def save(path, value):
    atomic_write(path, json_bytes(value))


class FixedDiagnosis(HandoffExecution):
    def decide(self, node, observer, frozen, arm):
        if arm != ARM:
            raise ValueError("Unexpected trial arm")
        p = read_json(PLAN / "protocol.json")
        historical = read_json(checked(p["old_decision"]))
        if (
            frozen != historical["menu"]
            or node != historical["anomaly"]
            or historical["proposal"]["option"] != "D1"
        ):
            raise ValueError("Different decision boundary")
        debit = historical["osa_tokens"]
        self.native_limit -= debit
        self.runtime.team_budget.native_allocation = self.native_limit
        if self.runtime.team_budget.snapshot()["available_tokens"] != p["worker_budget"]:
            raise ValueError("Different worker budget")
        active = self.activate(node, observer, frozen, historical["proposal"])
        if active.get("after") != read_json(checked(p["old_activation"]))["after"]:
            raise ValueError("Different effective organization")
        return active, {
            "source": "frozen_original_osa_decision",
            "arm": arm,
            "validator": "accepted",
            "proposal": historical["proposal"],
            "osa_tokens": debit,
            "new_osa_tokens": 0,
            "inherited_osa_tokens": debit,
        }


def freeze():
    old = read_json(BASE_PROTOCOL)
    for f in old["sources"]:
        checked(f)
    case = PRIOR / CASE / "OSA"
    gate = read_json(PLAN / "sdk-control.json")
    if [(r["case"], r["repair_dispatches"], r["real_handoffs"]) for r in gate] != [
        ("clean", 0, 1),
        ("repair", 1, 1),
        ("twice", 1, 0),
    ]:
        raise ValueError("SDK gate failed")
    decision = read_json(case / "decision.json")
    data = {
        "case": CASE,
        "arm": ARM,
        "checkpoint": old["checkpoint"],
        "prefix_tokens": old["prefix_tokens"],
        "inherited_controller_tokens": decision["osa_tokens"],
        "arm_limit": old["arm_limit"],
        "worker_budget": old["arm_limit"] - decision["osa_tokens"],
        "old_decision": reference(case / "decision.json"),
        "old_activation": reference(case / "assigned-graph.json"),
        "baseline": reference(
            ROOT / "artifacts/software-benchmark-v232/first-pair-r1/results.json"
        ),
        "condition": "D1 fixed, same checked-T1 and team budget; one example after own eligible evidence and one same-worker correction after a native public-schema rejection of a diagnosis send.",
        "primary_endpoint": "new valid handoff in world; secondary: recipient exposure, resolution, official code/delivery, physical usage and CNY",
        "correction_window": "From activation to accepted handoff, or until prior ordinary grants are exhausted and less than two complete calls remain or no ordinary member is runnable.",
        "account_cap_nanoyuan": 144374666400,
        "approved_available_nanoyuan": 37160001680,
        "new_model_branches": 1,
        "new_controller_requests": 0,
        "files": [
            reference(f)
            for f in [
                Path(__file__),
                ROOT / "tools/check_handoff_v232_1.py",
                ROOT / "src/proworksim/software_handoff_v232_1.py",
                PLAN / "sdk-control.json",
                BASE_PROTOCOL,
            ]
        ],
    }
    f = PLAN / "protocol.json"
    if f.exists() and read_json(f) != data:
        raise ValueError("Changed registered intervention")
    save(f, data)


def launch():
    p = read_json(PLAN / "protocol.json")
    for r in [
        *p["files"],
        *read_json(BASE_PROTOCOL)["sources"],
        p["old_decision"],
        p["old_activation"],
        p["baseline"],
    ]:
        checked(r)
    a = read_json(PRIOR / "authority.json")
    if a["cap_nanoyuan"] != p["account_cap_nanoyuan"]:
        raise ValueError("Unapproved cash cap")
    a.update(
        scope="single v232.1 HANDOFF branch",
        available_on_approval_nanoyuan=p["approved_available_nanoyuan"],
    )
    if not (RUN / "authority.json").exists():
        save(RUN / "authority.json", a)
    meter = PairedLedger.load(RUN / "authority.json")
    limit = p["arm_limit"]
    with meter.db() as db:
        if db.execute("select value from meta where key='cap'").fetchone() != (str(meter.cap),):
            raise ValueError("Cash account changed")
        row = db.execute(
            "select block_id,token_limit from block_slots where slot=?", (SLOT,)
        ).fetchone()
        if row and row != ("v232.1:handoff", limit):
            raise ValueError("Slot collision")
        if not row:
            closed = db.execute(
                "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
            ).fetchone()[0]
            active = db.execute(
                "select coalesce(sum(hold),0) from slots where status!='closed'"
            ).fetchone()[0]
            pending = db.execute(
                "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
            ).fetchone()[0]
            if closed + active + pending + limit * 8000 > meter.cap:
                raise ValueError("Cash cannot protect this branch")
            db.execute(
                "insert into block_slots values(?,?,?,'pending')", (SLOT, "v232.1:handoff", limit)
            )
    dest = RUN / CASE / ARM
    dest.parent.mkdir(exist_ok=True)
    result = stored_run(Path(__file__).name, ["--episode"], dest, "result.json")
    if result["status"] == "closed":
        score(panel_row(read_json(DESIGN)["states"][1]), dest, ARM)
    save(RUN / "completed.json", {k: result.get(k) for k in ("status", "error", "termination")})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--episode", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.freeze:
        freeze()
    elif args.episode:
        if args.output != RUN / CASE / ARM:
            raise ValueError("Different branch identity")
        clone_function(
            original.episode,
            {**original.episode.__globals__, "RUN": RUN, "OrganizationExecution": FixedDiagnosis},
        )(1, ARM, args.output, False)
    else:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            launch()
