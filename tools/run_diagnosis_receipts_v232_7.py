"""One revised Sphinx branch; reuse the previous metered launcher and official scorer."""

import argparse
import fcntl
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_evidence_followup_v232_6 as prior
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import atomic_write, read_json, json_bytes

ROOT = prior.ROOT
CASE = prior.CASE
ARM = "SEARCHRECEIPT"
PLAN = ROOT / "artifacts/software-benchmark-v232-7/diagnosis-receipts-r1"
RUN = ROOT / "runs/software-benchmark-v232-7/diagnosis-receipts-r1"
CHANGES = [
    "software_graph_controller_v228",
    "software_graph_controller_v228_3",
    "software_organization_v232",
    "software_collaboration_v030",
    "software_handoff_evidence_v232_6",
    "software_handoff_disposition_v232_5",
    "software_handoff_v232_1",
]


def freeze():
    old = read_json(prior.PLAN / "protocol.json")
    gate = read_json(PLAN / "verification.json")
    if (
        gate["archived"]["new_guard"] != "accepted"
        or gate["sdk_search"]["accepted_messages"][-1][0] != "ADOPT"
        or gate["sdk_block"]["accepted_messages"][0][0] != "BLOCK"
    ):
        raise ValueError("Managed verification incomplete")
    changes = {ROOT / f"src/proworksim/{name}.py" for name in CHANGES} | {Path(prior.__file__)}
    files = {
        p: reference(p)
        for p in changes
        | {
            Path(__file__),
            PLAN / "verification.json",
            ROOT / "tools/check_diagnosis_receipts_v232_7.py",
        }
    }

    def collect(item):
        path = Path(item["path"])
        if path in changes:
            return
        checked(item)
        if path in files:
            return
        files[path] = item
        if path.name in ("protocol.json", "freeze.json"):
            data = read_json(path)
            for child in data.get("files", []) + data.get("sources", []):
                collect(child)

    collect(reference(prior.PLAN / "protocol.json"))
    receipt = read_json(prior.PLAN / "results.json")
    data = {
        k: old[k]
        for k in (
            "case",
            "checkpoint",
            "prefix_tokens",
            "inherited_controller_tokens",
            "arm_limit",
            "worker_budget",
            "account_cap_nanoyuan",
            "old_decision",
            "old_activation",
            "baseline",
        )
    }
    data.update(
        arm=ARM,
        comparison=reference(prior.PLAN / "results.json"),
        approved_available_nanoyuan=receipt["available_nanoyuan"],
        new_paid_branches=1,
        new_controller_calls=0,
        primary="Natural use of repository search by the diagnostician, its event ID on the model-facing response, and any accepted DIAG citing it. Independently record a BLOCK receipt and recipient capacity if triggered.",
        secondary="Official code and delivery, recipient disposition, actual tokens, cost and cleanup. A missing trigger is reported separately from rejection. No resampling.",
        files=[files[p] for p in sorted(files)],
    )
    dest = PLAN / "protocol.json"
    if dest.exists() and read_json(dest) != data:
        raise ValueError("Protocol already registered")
    atomic_write(dest, json_bytes(data))


def verify(protocol):
    for file in protocol["files"]:
        checked(file)


class FixedEvidence(prior.EvidenceFollowupExecution):
    decide = clone_function(
        prior.FixedEvidence.decide,
        {**prior.FixedEvidence.decide.__globals__, "PLAN": PLAN, "ARM": ARM},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--episode", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.episode:
        if args.output != RUN / CASE / ARM:
            raise ValueError("Wrong run identity")
        fn = prior.previous.prior.original.episode
        clone_function(fn, {**fn.__globals__, "RUN": RUN, "OrganizationExecution": FixedEvidence})(
            1, ARM, args.output, False
        )
    else:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fn = prior.launch
            clone_function(
                fn,
                {
                    **fn.__globals__,
                    "__file__": __file__,
                    "previous": prior,
                    "PLAN": PLAN,
                    "RUN": RUN,
                    "ARM": ARM,
                    "SLOT": f"v232:{CASE}:{ARM}",
                    "BLOCK": "v232.7:search-receipt",
                    "check_sources": verify,
                },
            )(scope="one v232.7 Sphinx search and blocker receipt verification")


if __name__ == "__main__":
    main()
