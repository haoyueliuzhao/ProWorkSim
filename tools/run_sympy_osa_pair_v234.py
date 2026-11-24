"""One matched A4 verification-obligation pair funded by a single 37 CNY amendment."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_repaired_osa_pair_v233 as prior
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_context_panel_v231 import ROOT, DESIGN, PairedLedger, panel_row
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_handoff_evidence_v232_6 import EvidenceFollowupExecution
from proworksim.storage import read_json

PLAN = ROOT / "artifacts/software-benchmark-v234/sympy-a4-r1"
RUN = ROOT / "runs/software-benchmark-v234/sympy-a4-r1"
CASE = "SymPy-19954"
BLOCK = "v234:sympy-a4-pair"
ADD = 37_000_000_000


def freeze():
    old = read_json(prior.PLAN / "protocol.json")
    previous = read_json(prior.PLAN / "results.json")
    state = read_json(DESIGN)["states"][2]
    if state["case"] != CASE:
        raise ValueError("Wrong source")
    (selected,) = [
        r for r in previous["independent_sites"] if r["checkpoint"] == state["checkpoint"]
    ]
    source = ROOT / state["source_prefix"]
    row = panel_row(state)
    cap = old["account_cap_nanoyuan"]
    files = {Path(r["path"]): r for r in old["files"]}
    for path in (
        Path(__file__),
        Path(prior.__file__),
        Path(prior.episode_module.__file__),
        source / "observations.json",
        source / "checkpoint/manifest.json",
        checked(row["configuration"]),
        ROOT / "tools" / row["scorer_script"],
        prior.PLAN / "protocol.json",
        prior.PLAN / "results.json",
    ):
        files[path] = reference(path)
    for ref in files.values():
        checked(ref)
    data = dict(
        case=CASE,
        checkpoint=state["checkpoint"],
        source_prefix=state["source_prefix"],
        prefix_tokens=state["shared_prefix_usage"],
        arm_limit=5_000_000 - state["shared_prefix_usage"],
        old_cap_nanoyuan=cap,
        amendment_nanoyuan=ADD,
        account_cap_nanoyuan=cap + ADD,
        previous_balance_nanoyuan=previous["balance_nanoyuan"],
        worst_pair_nanoyuan=selected["full_pair_reservation_nanoyuan"],
        arms=list(prior.ARMS),
        attempts=2,
        anomaly="A4",
        subject="independent_current_review",
        conditions=old["conditions"],
        harness=old["shared_harness"],
        primary="Observe whether the independent current-version review obligation closes, the review and any receipt-linked handoff. A fresh OSA KEEP is a valid outcome. Record non-observability and recurrence separately.",
        secondary=old["secondary"],
        analysis=old["analysis"],
        site_scope="First v233/234 A4 pair on this previously exposed task, distinct from the Sphinx A1. Do not treat historical decisions or scores as current choices. No parameter update or resampling.",
        files=list(files.values()),
    )
    if (
        data["worst_pair_nanoyuan"] != 2 * data["arm_limit"] * 8000
        or data["previous_balance_nanoyuan"] + ADD < data["worst_pair_nanoyuan"]
    ):
        raise ValueError("Pair not covered")
    PLAN.mkdir(parents=True, exist_ok=True)
    dest = PLAN / "protocol.json"
    if dest.exists() and read_json(dest) != data:
        raise ValueError("Protocol already registered")
    prior.save(dest, data)


def launch():
    p = read_json(PLAN / "protocol.json")
    for x in p["files"]:
        checked(x)
    a = read_json(prior.RUN / "authority.json")
    old = p["old_cap_nanoyuan"]
    if a["cap_nanoyuan"] != old:
        raise ValueError("Unexpected previous ledger")
    a.update(
        scope="one matched SymPy A4 KEEP and fresh OSA pair",
        cap_nanoyuan=old + ADD,
        available_on_approval_nanoyuan=p["previous_balance_nanoyuan"] + ADD,
    )
    auth = RUN / "authority.json"
    if auth.exists() and read_json(auth) != a:
        raise ValueError("Authority mismatch")
    prior.save(auth, a)
    ledger = PairedLedger.load(auth)
    amendment = "amendment:" + BLOCK
    with ledger.db() as db:
        current = int(db.execute("select value from meta where key='cap'").fetchone()[0])
        receipt = db.execute("select value from meta where key=?", (amendment,)).fetchone()
        if receipt:
            if receipt != (str(ADD),) or current != old + ADD:
                raise ValueError("Amendment mismatch")
        else:
            if current != old:
                raise ValueError("Conflicting previous cap")
            db.execute("insert into meta values(?,?)", (amendment, str(ADD)))
            db.execute("update meta set value=? where key='cap'", (str(old + ADD),))
    prior.reserve(auth, p, namespace="v234", block=BLOCK)
    prior.run_pair(RUN, CASE, panel_row(read_json(DESIGN)["states"][2]), Path(__file__).name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--arm", choices=prior.ARMS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.arm:
        if args.output != RUN / CASE / args.arm:
            parser.error("Unexpected branch identity")
        fn = prior.episode_module.episode
        clone_function(
            fn, {**fn.__globals__, "RUN": RUN, "OrganizationExecution": EvidenceFollowupExecution}
        )(2, args.arm, args.output, False, slot_namespace="v234", expected_case=CASE)
    else:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            launch()
